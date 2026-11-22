"""Fabricated full-loop and operator-safety tests. No real BOPTEST requests."""

import base64
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Thread
import time
from types import SimpleNamespace
import unittest
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from autonomous_hvac_stage1.test_g218 import ModelFixture
from dashboard import make_server
from hvac_control_expansion_b2f_v1.packaging import chain
from hvac_control_expansion_b2f_v1.tests import offline_guard
from stage4e_d0.plan import FLAG
from stage4e_d2i_1.common import ROOT, read

from . import digital_twin as twin
from .live_dashboard import HERE
from .test_optimizer import CandidateModel, VALID


class WireFixture(ModelFixture):
    """Adds explicitly fabricated endpoint receipts for exercising the real dashboard reader."""

    def request(self, method, key, data=None):
        result = super().request(method, key, data)
        if (method, key) in {("PUT", "initialize"), ("POST", "advance")}:
            sequence = self.journal.order
            self.last_receipt_order = self.journal.emit("api_received", endpoint=key, raw_sequence=sequence, fabricated=True)
            raw = dict(sequence=sequence, method=method, url=f"http://FABRICATED/{key}/fixture", http_status=200,
                       raw_body_base64=base64.b64encode(json.dumps({"payload": result}).encode()).decode(), fabricated=True)
            with (self.directory / "raw_api.jsonl").open("a", encoding="utf-8") as stream:
                stream.write(json.dumps(raw) + "\n")
        return result


def fabricated_predictor():
    def forecast(origin, known, native, issued, *, committed):
        if set(known) != {origin - 1800, origin - 300, origin} or native["time"][-1] != origin or issued["issued_at_sim"] != origin:
            raise AssertionError("Forecast leaked unavailable measurements")
        units = dict(indoor_temperature="degC", cooling="kW electric", fan="kW electric", combined="kW electric")
        values = [dict(horizon_min=h, indoor_temperature=23.0, cooling=.4, fan=.10, combined=.50, heating=0.0)
                  for h in (5, 10, 15, 30)]
        return dict(valid=not committed[FLAG], reason="Warm action outside O25 domain" if committed[FLAG] else "",
                    units=units, predictions=values)
    return SimpleNamespace(model=SimpleNamespace(forecast_observations=forecast))


def collect(path, control, factory=WireFixture):
    return twin.collect_session(path, control, factory, CandidateModel(), VALID, fabricated_predictor(), fabricated=True)


def rows(path):
    return [json.loads(row) for row in path.read_text(encoding="utf-8").splitlines()]


class TwinTests(unittest.TestCase):
    def test_authorization_rejects_previous_smoke_before_runtime(self):
        with offline_guard(), self.assertRaisesRegex(ValueError, "does not bind"):
            twin.create_application(ROOT / "live_dashboard_smoke_authorization.json")

    def test_automatic_full_loop_and_readback(self):
        with TemporaryDirectory() as tmp, offline_guard():
            path = Path(tmp) / "fabricated"
            control = twin.SessionControl(lambda c: collect(path, c), pace=0)
            control.submit({"action": "start"})
            control.thread.join(25)
            self.assertEqual(control.phase, "stopped", control.result)
            self.assertEqual(control.result["verified_advances"], 41)
            self.assertEqual(control.result["cleanup"], "STOP_ACK_AND_REMOVAL_VERIFIED")
            steps = rows(path / "steps.jsonl")
            warmer = [s for s in steps if s["cooling_override_active"]]
            self.assertEqual(len(warmer), 9)
            self.assertEqual(warmer[0]["actual_cooling_k"], 297.65)
            self.assertEqual(steps[17]["actual_cooling_k"], 297.15)
            self.assertEqual(steps[18]["decision"]["reason"], "native_recovery_lockout")
            self.assertTrue(all(r["rf_before_advance_receipt"] < r["response_receipt"] for r in steps))
            self.assertGreater(chain(path / "receipt_order.jsonl")["events"], 41)
            display = twin.LiveApplication(control, path, fabricated=True).snapshot()
            self.assertEqual(display["cursor"], 41, display)
            self.assertEqual(len(display["forecast_feedback"]), 4)
            self.assertIsNone(display["saved_kwh"])
            self.assertTrue(display["fabricated"])

    def test_loopback_controls_pause_resume_and_verified_operator_release(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "fabricated"
            control = twin.SessionControl(lambda c: collect(path, c), pace=.15)
            app = twin.LiveApplication(control, path, fabricated=True)
            with make_server(app, 0, html_path=HERE / "dashboard.html") as server:
                thread = Thread(target=server.serve_forever, daemon=True)
                thread.start()
                address = f"http://127.0.0.1:{server.server_port}"

                def request(endpoint, action=None):
                    message = None if action is None else json.dumps({"action": action}).encode()
                    with urlopen(Request(address + endpoint, data=message, headers={"Content-Type": "application/json"}),
                                 timeout=5) as response:
                        return json.load(response)

                def wait(predicate):
                    for _ in range(400):
                        state = request("/state")
                        if predicate(state):
                            return state
                        if state["lifecycle"] == "failed":
                            self.fail(str(state))
                        time.sleep(.025)
                    self.fail(f"Timed out awaiting lifecycle: {state}")

                try:
                    self.assertEqual(request("/state")["lifecycle"], "ready")
                    request("/command", "start")
                    with self.assertRaises(HTTPError):
                        request("/command", "start")
                    wait(lambda s: s.get("cursor", 0) >= 2)
                    request("/command", "pause")
                    paused = wait(lambda s: s["lifecycle"] == "paused")
                    time.sleep(.25)
                    self.assertEqual(request("/state")["now"], paused["now"])
                    request("/command", "resume")
                    active = wait(lambda s: s.get("override"))
                    self.assertEqual(active["effective_c"], 24.5)
                    request("/command", "stop")
                    stop = wait(lambda s: s["lifecycle"] == "stopped")
                    self.assertEqual(stop["effective_c"], 24)
                    self.assertEqual(stop["session_result"]["release"], "verified")
                    self.assertEqual(stop["session_result"]["cleanup"], "STOP_ACK_AND_REMOVAL_VERIFIED")
                    self.assertLess(stop["cursor"], twin.ADVANCES)
                    self.assertTrue(any(r["kind"] == "paused_endpoint_reverified" for r in rows(path / "receipt_order.jsonl")))
                finally:
                    control.close()
                    server.shutdown()
                    thread.join(5)

    def test_unverified_delivery_stops_without_a_compensating_advance(self):
        class WrongReadback(WireFixture):
            fault = "wrong_active"

        with TemporaryDirectory() as tmp, offline_guard():
            path = Path(tmp) / "fabricated"
            control = twin.SessionControl(lambda c: collect(path, c, WrongReadback), pace=0)
            control.submit({"action": "start"})
            control.thread.join(25)
            self.assertEqual(control.phase, "failed", control.result)
            self.assertEqual(control.result["verified_advances"], 8)
            self.assertEqual(control.result["advance_attempts"], 9)
            self.assertEqual(control.result["release"], "unverified")
            self.assertEqual(control.result["cleanup"], "STOP_ACK_AND_REMOVAL_VERIFIED")
