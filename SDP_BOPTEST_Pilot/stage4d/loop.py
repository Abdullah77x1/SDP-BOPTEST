"""One-worker dashboard extension; the original baseline/intervention controllers are reused."""
from dataclasses import asdict
import json
import math
import threading
import time
from pathlib import Path
from client import utc
from core import CORE, COOL_U, COOL_A, FLAGS, TEMP, COOL, FAN, validate, observed_features
from dashboard import Controller
from experiment import write_json
from stage4d.rule import Context, ComfortRule, current_boundary, validate_command


class AutonomousController(Controller):
    def __init__(self, base, directory, client_factory, protocol):
        self.protocol = protocol
        self.rule = ComfortRule(protocol["rule"])
        self.advance_attempts = 0
        super().__init__(base, directory, client_factory)
        self.update(decision=None, current_boundary=None, maximum_steps=protocol["maximum_advances"],
                    advance_attempts=0, controller_label="Transparent rule; no optimizer or ML")

    def append(self, filename, record):
        with (self.directory/filename).open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(record, allow_nan=False)+"\n")

    def process(self, job):
        action = job["action"]
        if action == "connect":
            if self.connections or (self.directory/"INSTANCE_STARTED.json").exists():
                raise ValueError("The one-instance Stage 4D demonstration budget is consumed")
            with (self.directory/"INSTANCE_STARTED.json").open("x", encoding="utf-8") as stream:
                json.dump({"utc": utc(), "maximum_instances": 1,
                           "maximum_advances": self.protocol["maximum_advances"]}, stream)
            super().process(job)
            for point in ("LowerSetp[1]", "UpperSetp[1]", "Occupancy[1]"):
                if point not in self.metadata["forecast_points"]:
                    raise ValueError("Missing required current boundary point: "+point)
            for point in ("LowerSetp[1]", "UpperSetp[1]"):
                if self.metadata["forecast_points"][point].get("Unit") != "K":
                    raise ValueError("Comfort boundaries must use kelvin")
            if self.snapshot()["history"][0]["time"] != self.protocol["scenario_start"]:
                raise ValueError("Stage 4D start differs from preregistered window")
            self.update(controller_mode=job.get("mode", "autonomous"))
            observation, inputs, boundary, _ = self.refresh_current()
            self.update(effective_inputs=inputs, current_boundary=boundary)
        elif action == "start":
            state = self.snapshot()
            if not state["connected"]:
                raise ValueError("Connect first")
            if self.advance_attempts >= self.protocol["maximum_advances"]:
                raise ValueError("Stage 4D advance budget exhausted")
            mode = job.get("mode")
            if mode not in ("baseline", "intervention", "autonomous"):
                raise ValueError("Unknown controller mode")
            if state["steps"] and state["controller_mode"] != mode:
                raise ValueError("Mode is frozen after first advance")
            if mode == "autonomous":
                self.scheduler.start(time.monotonic(), job.get("pace", "accelerated"))
                self.update(running=True, controller_mode=mode, pace=self.scheduler.mode)
            else:
                super().process(job)
        else:
            super().process(job)

    def refresh_current(self):
        expected = self.snapshot()["history"][-1]["time"]
        points = list(dict.fromkeys([*CORE, *self.metadata["inputs"]]))
        raw = self.client.request("PUT", "results", {
            "point_names": points, "start_time": expected, "final_time": expected})
        times = raw.get("time", [])
        if not times or abs(times[-1]-expected) > 1e-6:
            raise ValueError("Stale or missing current observation timestamp")
        observation = {"time": times[-1], **{p: raw[p][-1] for p in CORE}}
        validate(observation)
        received_monotonic = time.monotonic()
        inputs = {p: raw[p][-1] for p in self.metadata["inputs"]}
        payload = self.client.request("PUT", "forecast", {
            "point_names": ["LowerSetp[1]", "UpperSetp[1]", "Occupancy[1]"],
            "horizon": 0, "interval": 300})
        boundary = current_boundary(payload, expected)
        boundary["time"] = expected
        return observation, inputs, boundary, received_monotonic

    def tick(self):
        began = time.monotonic()
        if not self.scheduler.ready(began):
            return
        if threading.get_ident() != self.thread.ident:
            raise RuntimeError("Only the dashboard worker may advance the simulator")
        if self.advance_attempts >= self.protocol["maximum_advances"]:
            self.scheduler.pause()
            self.update(running=False)
            return
        state = self.snapshot()
        if state["controller_mode"] != "autonomous":
            # Existing native/manual command logic remains untouched; the demonstration cap still applies.
            self.advance_attempts += 1
            self.update(advance_attempts=self.advance_attempts)
            super().tick()
            if self.advance_attempts >= self.protocol["maximum_advances"]:
                self.scheduler.pause()
                self.update(running=False)
            return
        self.update(busy=True)
        try:
            observation, inputs, boundary, received_mono = self.refresh_current()
            before = state["history"][-1]["time"]
            bounds = self.metadata["inputs"][COOL_U]
            context = Context(before, observation["time"], boundary["time"], received_mono,
                time.monotonic(), observation[TEMP], boundary["LowerSetp[1]"], boundary["UpperSetp[1]"],
                boundary["Occupancy[1]"], inputs["con_oveTSetHea_u"], bounds.get("Minimum"), bounds.get("Maximum"))
            decision = self.rule.decide(context,
                final_release=self.advance_attempts == self.protocol["maximum_advances"]-1)
            command = validate_command(decision, context, self.protocol["rule"])
            decision_record = {**decision.to_dict(), "decision_utc": utc(), "context": asdict(context),
                               "current_boundary": boundary, "command": command}
            self.append("decisions.jsonl", decision_record)
            if decision.fatal:
                self.update(decision=decision_record, current_boundary=boundary,
                            error="Safety stop: "+decision.reason)
                self.append("safety_events.jsonl", {"utc": utc(), "decision": decision_record,
                    "action": "Stop instance without advancing; proposed release is not claimed applied"})
                self.disconnect()
                self.update(busy=False)
                return
        except Exception as exc:
            self.append("safety_events.jsonl", {"utc": utc(), "error": str(exc),
                "action": "Stop instance without another advance; no substitute observations"})
            raise
        sent = utc()
        self.advance_attempts += 1
        self.update(advance_attempts=self.advance_attempts)
        new = self.client.request("POST", "advance", command)
        validate(new, before, 300)
        received = utc()
        step = {"start": before, "end": new["time"], "sent_utc": sent, "received_utc": received,
                "decision": decision_record, "command": command, "observation": new,
                "worker_thread_id": threading.get_ident(), "mode": "autonomous", "pace": self.scheduler.mode}
        self.append("accepted_advances.jsonl", step)
        readback = self.client.request("PUT", "results", {"point_names": list(self.metadata["inputs"]),
            "start_time": before, "final_time": new["time"]})
        if not readback.get("time") or abs(readback["time"][-1]-new["time"]) > 1e-6:
            raise ValueError("Missing/stale actual command readback")
        actual = {p: readback[p][-1] for p in self.metadata["inputs"]}
        if not all(v is not None and math.isfinite(float(v)) for v in actual.values()):
            raise ValueError("Invalid effective input readback")
        accepted = (float(actual[COOL_A]) == command[COOL_A]
                    and all(float(actual[k]) == 0 for k in FLAGS if k != COOL_A)
                    and (not decision.active or abs(actual[COOL_U]-decision.requested_k) <= 1e-5))
        step.update(effective_inputs=actual, command_applied=accepted,
                    response={"temperature_change_k": new[TEMP]-observation[TEMP],
                              "hvac_electric_w": new[COOL]+new[FAN]},
                    advance_wall_seconds=time.monotonic()-began)
        self.append("autonomous_steps.jsonl", step)
        if not accepted:
            raise ValueError("BOPTEST effective inputs do not match the command")
        post_payload = self.client.request("PUT", "forecast", {
            "point_names": ["LowerSetp[1]", "UpperSetp[1]", "Occupancy[1]"],
            "horizon": 0, "interval": 300})
        post_boundary = current_boundary(post_payload, new["time"])
        post_boundary["time"] = new["time"]
        kpis = self.client.request("GET", "kpi")
        with self.lock:
            self.state["history"].append({"time": new["time"], **observed_features(new, self.metadata)})
            self.state["actions"].append(step)
            self.state.update(steps=state["steps"]+1, kpis=kpis, effective_inputs=actual,
                decision=decision_record, current_boundary=post_boundary, latest_response=step["response"],
                last_wall_received_utc=received, busy=False)
        self.scheduler.complete(time.monotonic(), began)
        if self.advance_attempts >= self.protocol["maximum_advances"]:
            self.scheduler.pause()
            self.update(running=False, budget_complete=True)
            write_json(self.directory/"FINAL_NATIVE_RELEASE.json", {
                "time": new["time"], "command": command, "effective_inputs": actual,
                "verified": command[COOL_A] == 0 and float(actual[COOL_A]) == 0})
