"""Model, causal features, search and actuation checks without a simulator."""

from pathlib import Path
import tempfile
import unittest

import numpy as np

from autonomous_hvac_stage1.test_g218 import ModelFixture
from hvac_control_expansion_b2f_v1.tests import offline_guard
from stage4e_d0.plan import COOL, FAN, FLAG, OCC, SET, STEP
from stage4e_d2i_1.common import ROOT, read

from . import optimizer_campaign as campaign
from .live_dashboard import DashboardState
from .optimizer import ACTIONS, rank
from .optimizer_model import STEPS, make_inputs, qualification


class CandidateModel:
    def __init__(self, *, peak=24.5, warmer_kw=.38):
        self.peak = peak
        self.warmer_kw = warmer_kw

    def predict(self, inputs):
        return np.tile([24.01, .4, .03], (STEPS, 1)), np.tile([self.peak, self.warmer_kw, .02], (STEPS, 1))


VALID = dict(qualified=True, metrics={"max_net_savings_error_kwh": .008}, observed_peak_limit_c=24.57)


class OptimizerTests(unittest.TestCase):
    def test_complete_grid_ranks_net_kwh_and_rejects_unsupported_actions(self):
        result = rank(CandidateModel(), VALID, object())
        self.assertEqual(len(ACTIONS), 13)
        self.assertEqual(result["selected"], "A3")
        actions = {r["id"]: r for r in result["candidates"]}
        self.assertAlmostEqual(actions["A3"]["predicted"]["total_kwh"], 1.1)
        self.assertAlmostEqual(actions["A3"]["predicted"]["recovery_penalty_kwh"], -.06)
        self.assertEqual({r["id"] for r in actions.values() if r["predicted"] is not None}, {"A0", "A3"})
        self.assertFalse(actions["A2"]["feasible"])
        self.assertFalse(actions["A6-45"]["feasible"])

    def test_native_for_weak_gain_heat_and_unqualified_model(self):
        cases = ((CandidateModel(warmer_kw=.408), VALID, True), (CandidateModel(peak=25.6), VALID, True),
                 (CandidateModel(), dict(VALID, qualified=False), True), (CandidateModel(), VALID, False))
        for model, validation, allowed in cases:
            with self.subTest(model=model, validation=validation, allowed=allowed):
                self.assertEqual(rank(model, validation, object(), allowed=allowed)["selected"], "A0")
        self.assertEqual(rank(CandidateModel(), VALID, None)["selected"], "A0")

    def test_held_out_fit_and_dashboard_evidence_boundaries(self):
        result = qualification()
        self.assertEqual({r["group"] for r in result["episodes"]}, {"G174", "G218"})
        self.assertEqual(len(result["horizons"]), STEPS)
        self.assertEqual(result["metrics"]["correct_rankings"], 6)
        dashboard = DashboardState("optimizer")
        snap = dashboard.snapshot()
        self.assertTrue(snap["ready"], snap)
        self.assertTrue(snap["optimization"]["shadow"])
        self.assertIsNone(snap["saved_kwh"])
        self.assertFalse(snap["override"])
        for lead in (5, 30, 165):
            self.assertIn(lead, result["horizons"])
        origin = snap["optimization"]["origin"]
        endpoint = dashboard.run.endpoints[origin]
        forecast = dashboard.run.forecast(132)
        native = dashboard.run.native
        i = native["time"].index(origin)
        leaked = {k: native[k][i - 10:i + 2] for k in ("time", COOL, FAN)}
        with self.assertRaisesRegex(ValueError, "future sample"):
            make_inputs(origin, endpoint, forecast, leaked, dashboard.schedule)
        with self.assertRaisesRegex(ValueError, "vintage mismatch"):
            make_inputs(origin, endpoint, dict(forecast, issued_at_sim=origin + STEP), leaked, dashboard.schedule)

    def test_three_arm_binding_rejects_old_authorization_before_runtime(self):
        self.assertEqual([r["strategy"] for r in campaign.definition()["runs"]], ["native", "fixed", "predictive"])
        self.assertEqual(campaign.definition()["budgets"]["total_advances"], 2592)
        self.assertGreaterEqual(campaign.scenario_audit()["nearest_gap_s"], 86400)
        with offline_guard(), self.assertRaisesRegex(ValueError, "does not bind"):
            campaign.execute(ROOT / "g218_execution_authorization.json")

    def test_collector_delivers_selects_feedback_releases_and_recovers(self):
        manifest = campaign.definition()
        run = manifest["runs"][2]
        with tempfile.TemporaryDirectory() as tmp, offline_guard():
            path = Path(tmp) / "C"
            status = campaign.collect(manifest, run, path, ModelFixture, CandidateModel(), VALID, fabricated=True)
            self.assertEqual(status["classification"], "PASS_VALID_RAW", status)
            import json

            with (path / "steps.jsonl").open(encoding="utf-8") as stream:
                rows = list(map(json.loads, stream))
            with (path / "optimizer_decisions.jsonl").open(encoding="utf-8") as stream:
                decisions = list(map(json.loads, stream))
            warm = [r for r in rows if r["cooling_override_active"]]
            self.assertEqual(len(warm), 9)
            self.assertEqual(warm[0]["actual_cooling_k"], 297.65)
            self.assertEqual(rows[141]["actual_cooling_k"], 297.15)
            self.assertEqual(rows[142]["decision"]["reason"], "native_recovery_lockout")
            self.assertEqual(decisions[0]["selected"], "A3")
            self.assertIn("feedback_adjusted_remaining_peak_c", decisions[1])
            self.assertTrue(read(path / "RUN_COMPLETED.json")["fabricated"])
