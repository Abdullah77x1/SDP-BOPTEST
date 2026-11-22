"""Local dependency-free live dashboard. Exactly one worker owns emulator mutations."""
from __future__ import annotations
import argparse
import json
import queue
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from client import Client, utc
from core import COOL_U, Scheduler, commands, observed_features, require_metadata, validate
from experiment import ROOT, frozen_plan, initialize, prepare_forecast, write_json


class Controller:
    def __init__(self, base, directory, client_factory=Client):
        self.base, self.directory, self.factory = base, Path(directory), client_factory
        self.directory.mkdir(parents=True, exist_ok=True)
        self.plan, self.digest = frozen_plan(self.directory)
        self.lock, self.jobs = threading.Lock(), queue.Queue()
        self.scheduler = Scheduler()
        self.client = None
        self.connections = 0
        self.finished = False
        self.seen = set()
        self.state = {"connected": False, "running": False, "busy": False,
                      "controller_mode": "baseline", "pace": "accelerated", "history": [],
                      "actions": [], "kpis": {}, "error": None, "steps": 0,
                      "predictions": None, "forecast_label": "No ML/RC models loaded",
                      "plan_sha256": self.digest, "live_label": "Live simulated building; no physical sensors"}
        self.thread = threading.Thread(target=self.worker, daemon=True)
        self.thread.start()

    def submit(self, message):
        if not isinstance(message.get("request_id"), str) or not message["request_id"]:
            raise ValueError("request_id required for idempotence")
        if message.get("action") not in ("connect", "start", "pause", "disconnect"):
            raise ValueError("Unknown command")
        with self.lock:
            if message["request_id"] in self.seen:
                return {"queued": False, "duplicate": True}
            self.seen.add(message["request_id"])
            self.jobs.put(message)
        return {"queued": True}

    def snapshot(self):
        with self.lock:
            return json.loads(json.dumps(self.state, allow_nan=False))

    def update(self, **kwargs):
        with self.lock:
            self.state.update(kwargs)

    def disconnect(self):
        self.scheduler.pause()
        self.update(running=False)
        try:
            if self.client:
                self.client.stop()
        finally:
            self.client = None
            self.update(connected=False)

    def process(self, job):
        action = job["action"]
        if action == "disconnect":
            self.disconnect()
        elif action == "pause":
            self.scheduler.pause()
            self.update(running=False)
        elif action == "connect":
            if self.client:
                raise ValueError("Disconnect existing instance first")
            # No deployment until the verified-TLS read-only reachability check succeeds.
            self.connections += 1
            self.client = self.factory(self.base, self.directory/f"connection_{self.connections:04d}")
            self.client.request("GET", "testcases", instance=False)
            self.client.deploy()
            self.metadata = self.client.discover()
            require_metadata(self.metadata)
            initial = initialize(self.client, self.plan)
            forecast = prepare_forecast(self.client, self.metadata, self.plan)
            write_json(self.directory/f"connection_{self.connections:04d}"/"boundary_forecast_NOT_ML.json", forecast)
            self.update(connected=True, history=[initial], steps=0, actions=[], error=None,
                        metadata=self.metadata, effective_inputs={})
        elif action == "start":
            if not self.client or not self.snapshot()["connected"]:
                raise ValueError("Connect to the live emulator first")
            if job.get("mode") not in ("baseline", "intervention"):
                raise ValueError("Unknown controller mode")
            # Freeze mode for a session: never blend a new treatment into a native history.
            state = self.snapshot()
            if state["steps"] and state["controller_mode"] != job["mode"]:
                raise ValueError("Controller mode is frozen after first step; reconnect for a new demo")
            if state["steps"] >= 288:
                raise ValueError("24-hour live-demo limit reached")
            self.scheduler.start(time.monotonic(), job.get("pace", "accelerated"))
            self.update(running=True, controller_mode=job["mode"], pace=self.scheduler.mode)

    def tick(self):
        began = time.monotonic()
        if not self.scheduler.ready(began):
            return
        state = self.snapshot()
        before = state["history"][-1]["time"]
        command = commands(state["controller_mode"], before, self.plan)
        self.update(busy=True)
        sent = utc()
        observation = self.client.request("POST", "advance", command)
        validate(observation, before)
        received = utc()
        action = {"start": before, "end": observation["time"], "sent_utc": sent,
                  "received_utc": received, "command": command,
                  "advance_wall_seconds": time.monotonic() - began,
                  "pace": self.scheduler.mode, "mode": state["controller_mode"]}
        with (self.directory/"live_steps.jsonl").open("a", encoding="utf-8") as stream:
            stream.write(json.dumps({**action, "observation": observation}) + "\n")
        # Query actual effective inputs; command value is not presented as a measured setpoint.
        points = [p for p in (COOL_U, "con_oveTSetHea_u", "fcu_oveFan_u", "fcu_oveTSup_u")
                  if p in self.metadata["inputs"]]
        effective = self.client.request("PUT", "results", {
            "point_names": points, "start_time": before, "final_time": observation["time"]})
        inputs = {p: effective[p][-1] for p in points if effective.get(p)}
        kpis = self.client.request("GET", "kpi")
        with self.lock:
            self.state["history"].append({"time": observation["time"],
                **observed_features(observation, self.metadata)})
            self.state["actions"].append(action)
            self.state.update(steps=state["steps"]+1, kpis=kpis, effective_inputs=inputs,
                              last_wall_received_utc=received, busy=False)
        self.scheduler.complete(time.monotonic(), began)
        if self.snapshot()["steps"] >= 288:
            self.scheduler.pause()
            self.update(running=False)

    def worker(self):
        while not self.finished:
            try:
                try:
                    job = self.jobs.get(timeout=0.05)
                except queue.Empty:
                    job = None
                if job:
                    self.process(job)
                self.tick()
            except Exception as exc:
                self.scheduler.pause()
                self.update(error=f"{type(exc).__name__}: {exc}", running=False, busy=False)
                # Ambiguous advancement is never retried; stop and discard connection.
                try:
                    self.disconnect()
                except Exception as cleanup:
                    self.update(cleanup_error=str(cleanup))

    def close(self):
        self.finished = True
        self.thread.join(timeout=45)
        if self.thread.is_alive():
            raise RuntimeError("Worker still owns an in-flight request; cleanup requires service timeout")
        self.disconnect()


def make_server(controller, port=8765, html_path=None):
    class Handler(BaseHTTPRequestHandler):
        def reply(self, code, value, mime="application/json"):
            body = value.encode() if isinstance(value, str) else json.dumps(value).encode()
            self.send_response(code)
            self.send_header("Content-Type", mime + "; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            if self.path == "/":
                self.reply(200, Path(html_path or ROOT/"index.html").read_text(encoding="utf-8"), "text/html")
            elif self.path == "/state":
                self.reply(200, controller.snapshot())
            else:
                self.reply(404, {"error": "Not found"})

        def do_POST(self):
            if self.path != "/command":
                self.reply(404, {"error": "Not found"}); return
            # Browser commands must originate from this loopback app, not another site.
            origin = self.headers.get("Origin")
            if origin and origin != f"http://{self.headers.get('Host')}":
                self.reply(403, {"error": "Cross-origin command denied"}); return
            try:
                size = int(self.headers.get("Content-Length", 0))
                if not 0 < size <= 4096 or self.headers.get("Content-Type") != "application/json":
                    raise ValueError("Small JSON command required")
                self.reply(202, controller.submit(json.loads(self.rfile.read(size))))
            except Exception as exc:
                self.reply(400, {"error": str(exc)})

        def log_message(self, *_):
            pass

    return ThreadingHTTPServer(("127.0.0.1", port), Handler)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default="https://api.boptest.net")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    directory = ROOT/"evidence"/"live"/time.strftime("%Y%m%d_%H%M%S")
    controller = Controller(args.base, directory)
    server = make_server(controller, args.port)
    print(f"Dashboard: http://127.0.0.1:{server.server_port} — synthetic live emulator, not physical sensors", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        controller.close()


if __name__ == "__main__":
    main()
