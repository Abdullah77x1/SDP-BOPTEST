"""Measured archive qualification and explicitly fabricated rolling transport tests."""

from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest

import numpy as np

from hvac_control_expansion_b2f_v1.tests import offline_guard
from stage4e_d0.plan import FLAG
from stage4e_d2i_1.common import ROOT

from . import digital_twin as twin
from .rolling_model import STEP, STEPS, calibrated_rolling, observed_state
from .test_digital_twin import WireFixture, fabricated_predictor, rows


class FabricatedStepModel:
    entry_reference = SimpleNamespace(predict=lambda state: None)

    def __init__(self, *, hot_continue=False):
        self.hot_continue = hot_continue
        self.calls = []

    def rollout(self, state, weather, path, phase):
        self.calls.append((state.warmer, path, phase, tuple(weather)))
        values = np.tile([24.0, .7, .04], (STEPS - phase, 1))
        upper = min(9 - phase, len(values))
        if path and upper > 0:
            values[:upper] = [25.6 if self.hot_continue and phase else 24.5, .5, .03]
        return values


VALID = dict(qualified=True, observed_peak_c=24.57, uncertainty_kwh=.006)


def collect(path, control, model, factory=WireFixture, validation=VALID):
    return twin.collect_session(path, control, factory, model, validation, fabricated_predictor(),
                                fabricated=True, rolling=True)


class RollingTests(unittest.TestCase):
    def test_measured_scenario_separated_qualification(self):
        with offline_guard():
            _, validation = calibrated_rolling()
        independent = validation["folds"]["G163"]
        self.assertTrue(validation["qualified"], validation["gates"])
        self.assertEqual(independent["counts"], {"native": 99, "start": 3, "continue": 24, "release": 3, "recovery": 69})
        self.assertEqual(len(independent["ranking"]), 3)
        self.assertTrue(all(row["correct"] for row in independent["ranking"]))
        self.assertEqual(independent["actual_hot_intervals"], 0)

    def test_rejects_future_history(self):
        with self.assertRaisesRegex(ValueError, "completed causal"):
            observed_state({"time": 600}, {"time": [300, 600, 630]})

    def test_earlier_authorization_cannot_launch_rolling(self):
        with offline_guard(), self.assertRaisesRegex(ValueError, "does not bind"):
            twin.create_application(ROOT.parent / "live_optimizer_twin_authorization.json", rolling=True)

    def test_fresh_rollouts_reach_scheduled_release_and_dashboard(self):
        model = FabricatedStepModel()
        with TemporaryDirectory() as temp, offline_guard():
            path = Path(temp) / "fixture"
            owner = twin.SessionControl(lambda control: collect(path, control, model), pace=0)
            owner.submit({"action": "start"})
            owner.thread.join(25)
            self.assertEqual(owner.phase, "stopped", owner.result)
            self.assertEqual(owner.result["verified_advances"], 41)
            self.assertEqual(owner.result["release"], "verified")
            steps = rows(path / "steps.jsonl")
            rolling = rows(path / "optimizer_decisions.jsonl")
            self.assertEqual([s["start"] for s in steps], [d["origin"] for d in rolling])
            self.assertEqual([rolling[i]["action"] for i in (0, 8, 9, 17, 18)],
                             ["native", "start", "continue", "release", "native"])
            self.assertEqual([rolling[i]["rolling_candidates"][1]["prediction"]["horizon_min"] for i in (8, 9)], [165, 160])
            self.assertTrue(rolling[8]["rolling_candidates"][0]["valid"])
            self.assertFalse(rolling[9]["rolling_candidates"][0]["valid"])
            self.assertEqual(rolling[17]["rolling_candidates"][0]["transition"], "release")
            self.assertEqual([s["cooling_override_active"] for s in steps[8:18]], [True] * 9 + [False])
            self.assertEqual(steps[8]["actual_cooling_k"], 297.65)
            self.assertEqual(steps[17]["actual_cooling_k"], 297.15)
            self.assertIn((True, True, 1), [call[:3] for call in model.calls])
            self.assertTrue(all(d["cutoff"] < s["response_receipt"] for d, s in zip(rolling, steps, strict=True)))
            display = twin.LiveApplication(owner, path, fabricated=True, rolling=True).snapshot()
            self.assertTrue(display["rolling_mode"] and display["fabricated"])
            self.assertEqual(display["rolling"]["origin"], steps[-1]["start"])
            self.assertIsNotNone(display["rolling"]["errors"])
            self.assertIsNone(display["saved_kwh"])

    def test_feedback_hot_margin_releases_without_reentry(self):
        model = FabricatedStepModel(hot_continue=True)
        with TemporaryDirectory() as temp, offline_guard():
            path = Path(temp) / "fixture"
            owner = twin.SessionControl(lambda control: collect(path, control, model), pace=0)
            owner.submit({"action": "start"})
            owner.thread.join(25)
            self.assertEqual(owner.phase, "stopped", owner.result)
            steps = rows(path / "steps.jsonl")
            self.assertEqual(sum(step["cooling_override_active"] for step in steps), 1)
            self.assertTrue(steps[9]["decision"]["fallback"])
            self.assertEqual(steps[9]["decision"]["reason"], "rolling_safety_or_model_validity_release")
            audit = rows(path / "optimizer_decisions.jsonl")
            self.assertIn("after early release", audit[10]["rolling_candidates"][0]["reasons"][0])
            self.assertFalse(audit[10]["rolling_candidates"][1]["valid"])
            self.assertEqual(steps[10]["decision"]["reason"], "native_recovery_lockout")

    def test_unverified_command_stops_without_retry(self):
        class WrongReadback(WireFixture):
            fault = "wrong_active"

        with TemporaryDirectory() as temp, offline_guard():
            path = Path(temp) / "fixture"
            owner = twin.SessionControl(lambda control: collect(path, control, FabricatedStepModel(), WrongReadback), pace=0)
            owner.submit({"action": "start"})
            owner.thread.join(25)
            self.assertEqual(owner.phase, "failed", owner.result)
            self.assertEqual(owner.result["verified_advances"], 8)
            self.assertEqual(owner.result["advance_attempts"], 9)
            self.assertEqual(owner.result["release"], "unverified")
            self.assertEqual(owner.result["cleanup"], "STOP_ACK_AND_REMOVAL_VERIFIED")

    def test_failed_model_qualification_leaves_all_warmer_commands_disabled(self):
        with TemporaryDirectory() as temp, offline_guard():
            path = Path(temp) / "fixture"
            model = FabricatedStepModel()
            unqualified = dict(VALID, qualified=False)
            owner = twin.SessionControl(lambda control: collect(path, control, model, validation=unqualified), pace=0)
            owner.submit({"action": "start"})
            owner.thread.join(25)
            self.assertEqual(owner.phase, "stopped", owner.result)
            self.assertFalse(any(step["cooling_override_active"] for step in rows(path / "steps.jsonl")))
            self.assertFalse(any(call[1] for call in model.calls))
            start = rows(path / "optimizer_decisions.jsonl")[8]
            self.assertIn("Measured stepwise-model qualification failed", start["rolling_candidates"][1]["reasons"])
