"""Offline checks for the final policy choices and dashboard evidence wiring."""

import base64
import json
from pathlib import Path
import tempfile
import threading
import unittest
from urllib.request import Request, urlopen

from autonomous_hvac_stage1.tests import END, START, Fixture
from dashboard import make_server
from energy_savings_g174_v1.policy import ON, TARGET
from stage4e_d0.plan import FLAG, SET, STEP, TEMP
from stage4e_d1r.proposed_validation import HEAT

from .live_dashboard import DashboardState, EvidenceRun, G218_TRACE, HERE
from .policies import make_controller


class PolicyTests(unittest.TestCase):
    def test_fixed_and_autonomous_have_distinct_demand_rules(self):
        for strategy, warmer in (("native", False), ("fixed", True), ("autonomous", False)):
            with self.subTest(strategy=strategy):
                case = Fixture(cooling=0)
                case.rule = make_controller(strategy, START, END)
                case.prime(cooling=0)
                choice = case.decide()
                self.assertEqual(choice.warmer, warmer)
                if warmer:
                    verified = case.confirm(choice)
                    self.assertEqual(verified.actual_cooling_k, TARGET)
                    self.assertEqual(case.current[HEAT], 294.15)

    def test_fixed_retains_stage_one_safety_and_release(self):
        case = Fixture(cooling=0)
        case.rule = make_controller("fixed", START, END)
        case.prime(cooling=0)
        case.confirm(case.decide(), temperature=298.65)
        fallback = case.decide()
        self.assertTrue(fallback.fallback)
        self.assertFalse(fallback.command[FLAG])
        case.confirm(fallback)
        self.assertEqual(case.decide().reason, "native_recovery_lockout")
        self.assertEqual(case.current[SET], 297.15)

    def test_higher_candidates_fail_closed(self):
        for candidate in (25, 25.5, 26):
            with self.subTest(candidate=candidate):
                case = Fixture()
                case.rule = make_controller("fixed", START, END, fixed_c=candidate)
                case.prime()
                decision = case.decide()
                self.assertFalse(decision.warmer)
                self.assertEqual(decision.reason, "candidate_requires_separate_qualification")


class DashboardTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.warm = DashboardState("warm")
        cls.shadow = DashboardState("shadow")

    def test_verified_archived_forecast_and_warm_interval(self):
        first = ON // STEP
        self.warm.submit(dict(action="seek", cursor=first))
        before = self.warm.snapshot()
        self.assertEqual(before["forecast"]["source"], "O25 Random Forest")
        self.assertEqual([r["horizon_min"] for r in before["forecast"]["values"]], [5, 10, 15, 30])
        self.warm.submit(dict(action="seek", cursor=first + 1))
        during = self.warm.snapshot()
        self.assertEqual(during["now"] - before["now"], STEP)
        self.assertEqual(during["effective_c"], 24.5)
        self.assertEqual(during["forecast"]["source"], "Persistence")
        self.assertIn("outside observed domain", during["forecast"]["reason"])
        self.assertLess(during["forecast"]["origin"], during["now"])
        self.assertTrue(during["status"].startswith("ARCHIVED REPLAY"))
        self.warm.submit(dict(action="seek", cursor=864))
        complete = self.warm.snapshot()
        self.assertAlmostEqual(complete["saved_kwh"], .078468, places=6)
        self.assertAlmostEqual(complete["official_kpi"], 2.537502, places=6)

    def test_shadow_displays_unapplied_choice(self):
        self.shadow.submit(dict(action="seek", cursor=ON // STEP + 1))
        view = self.shadow.snapshot()
        self.assertTrue(view["shadow"]["warmer"])
        self.assertEqual(view["effective_c"], 24.0)
        self.assertFalse(view["override"])
        self.assertIsNone(view["saved_kwh"])

    def test_rolling_archive_replays_verified_decisions_without_live_controls(self):
        replay = DashboardState("rolling")
        with self.assertRaisesRegex(ValueError, "Only replay"):
            replay.submit(dict(action="start"))
        for cursor, action, cooling in ((9, "start", 24.5), (10, "continue", 24.5), (18, "release", 24.0)):
            with self.subTest(cursor=cursor):
                replay.submit(dict(action="seek", cursor=cursor))
                view = replay.snapshot()
                self.assertTrue(view["ready"], view)
                self.assertEqual(view["rolling"]["action"], action)
                self.assertEqual(view["effective_c"], cooling)
                self.assertIsNone(view["saved_kwh"])
                self.assertIsNone(view["official_kpi"])
        replay.submit(dict(action="seek", cursor=41))
        end = replay.snapshot()
        self.assertAlmostEqual(end["energy"]["electricity_kwh"], 2.716347, places=6)
        self.assertIsNotNone(end["official_kpi"])

    def test_forecast_ignores_realized_future_temperature(self):
        index = ON // STEP - 1
        evidence = self.warm.run
        issued = evidence.forecast(index)
        forecast = self.warm.forecaster
        expected = forecast.for_step(evidence, index, issued)
        endpoint = evidence.endpoints[evidence.steps[index]["end"]]
        observed = endpoint[TEMP]
        forecast.cache.clear()
        try:
            endpoint[TEMP] = 320.0
            self.assertEqual(forecast.for_step(evidence, index, issued), expected)
        finally:
            endpoint[TEMP] = observed
            forecast.cache.clear()

    def test_read_only_follower_waits_for_the_verified_advance(self):
        source = EvidenceRun(G218_TRACE, archived=True)
        start = source.steps[0]["start"]
        end = start + STEP

        def row(method, endpoint, sequence, obs):
            data = base64.b64encode(json.dumps({"payload": obs}).encode()).decode()
            return dict(method=method, url=f"http://FABRICATED/{endpoint}/test", sequence=sequence,
                        http_status=200, raw_body_base64=data)

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)
            evidence = EvidenceRun(path)
            raw = [row("PUT", "initialize", 1, source.endpoints[start]),
                   row("POST", "advance", 2, source.endpoints[end])]
            (path / "raw_api.jsonl").write_text("".join(json.dumps(r) + "\n" for r in raw), encoding="utf-8")
            (path / "receipt_order.jsonl").write_text(
                json.dumps(dict(kind="api_received", endpoint="advance", order=7, raw_sequence=2)) + "\n",
                encoding="utf-8")
            evidence.refresh()
            self.assertEqual(list(evidence.endpoints), [start])
            self.assertFalse(evidence.steps)
            step = dict(start=start, end=end, response_receipt=7,
                        actual_cooling_k=source.endpoints[end][SET], cooling_override_active=False)
            (path / "steps.jsonl").write_text(json.dumps(step), encoding="utf-8")  # Incomplete append.
            evidence.refresh()
            self.assertFalse(evidence.steps)
            with (path / "steps.jsonl").open("a", encoding="utf-8") as stream:
                stream.write("\n")
            (path / "native_chunk_0000.json").write_text(
                json.dumps({k: values[:11] for k, values in source.native.items()}), encoding="utf-8")
            evidence.refresh()
            self.assertEqual(evidence.steps, [step])
            self.assertEqual(evidence.endpoints[end], source.endpoints[end])
            evidence.refresh()
            self.assertEqual(len(evidence.native["time"]), 11)

    def test_existing_server_polls_and_seeks(self):
        self.warm.submit(dict(action="seek", cursor=130))
        with make_server(self.warm, 0, html_path=HERE / "dashboard.html") as server:
            worker = threading.Thread(target=server.serve_forever, daemon=True)
            worker.start()
            base = f"http://127.0.0.1:{server.server_port}"
            try:
                with urlopen(base + "/", timeout=10) as response:
                    self.assertIn(b"Decision and verified feedback", response.read())
                request = Request(base + "/command", data=json.dumps(dict(action="seek", cursor=133)).encode(),
                                  headers={"Content-Type": "application/json"})
                with urlopen(request, timeout=10) as response:
                    self.assertEqual(response.status, 202)
                with urlopen(base + "/state", timeout=10) as response:
                    view = json.load(response)
                self.assertEqual(view["cursor"], 133)
                self.assertEqual(view["requested_c"], 24.5)
            finally:
                server.shutdown()
                worker.join(timeout=5)

