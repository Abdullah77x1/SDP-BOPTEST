"""Checks for independent G258 scope and reuse of the unchanged fan limits."""

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from hvac_control_expansion_b2f_v1.tests import offline_guard
from stage4e_d2i_1.common import ROOT, read

from . import fan_replication as replication, fan_trial as fan
from .test_fan_trial import FanFixture


class FanReplicationTests(unittest.TestCase):
    def test_frozen_scope_uses_the_original_control_and_scoring_limits(self):
        original = fan.definition()
        recorded = fan.STATE / "batches" / fan.CAMPAIGN / "FAN_CONFIGURATION.json"
        self.assertEqual(original, read(recorded))
        new = replication.definition()
        for field in ("model", "policy", "limits", "budgets", "candidate_fraction", "qualified_for_optimizer"):
            self.assertEqual(new[field], original[field], field)
        self.assertEqual(new["budgets"]["total_advances"], 72)
        self.assertEqual(fan.declared_window(new), replication.WINDOW)
        self.assertEqual(new["candidate_fraction"], .60)

    def test_native_screen_chooses_independent_development_at_same_clock(self):
        result = replication.screen_archive()
        self.assertEqual(result["benchmark_day"], 258)
        self.assertEqual(result["start"] % fan.DAY, 14*3600)
        self.assertEqual(len(result["eligible_same_clock_windows"]), 3)
        self.assertAlmostEqual(result["fan_mean_w"], 50.8891901)
        self.assertAlmostEqual(result["cooling_mean_w"], 985.8508633)
        self.assertGreater(result["footprint"]["gap_from_original_screening_s"], 30*fan.DAY)

    def test_protected_overlap_refused(self):
        source = replication.source_run()
        plan = read(replication.PLAN)
        plan["expanded"].append(dict(group_id="TEST_PROTECTED", partition="protected_final_test",
                                     warmup_start_s=replication.WINDOW.start, scored_end_s=replication.WINDOW.end))
        with self.assertRaisesRegex(ValueError, "TEST_PROTECTED"):
            replication.footprint_audit(source, plan)

    def test_shared_collector_and_scorer_run_at_g258_times(self):
        with TemporaryDirectory() as temp, offline_guard():
            root, spec = Path(temp), replication.definition()
            a, b = root / "native", root / "fan"
            window = replication.WINDOW
            baseline = fan.collect(spec, spec["runs"][0], a, FanFixture, fabricated=True)
            self.assertEqual(baseline["classification"], "PASS_VALID_RAW", baseline)
            fan.check_new_native_reference(a, spec["runs"][1], window)
            treatment = fan.collect(spec, spec["runs"][1], b, FanFixture, a, fabricated=True)
            self.assertEqual(treatment["classification"], "PASS_VALID_RAW", treatment)
            self.assertEqual(treatment["realized_fan_advances"], 6)
            self.assertEqual(treatment["verified_advances"], 36)
            actions = [s["start"] for s in fan.rows(b / "steps.jsonl") if s["fan_active"]]
            self.assertEqual(actions, list(range(window.hold_start, window.hold_end, fan.STEP)))
            result = fan.score_pair(a, b, fabricated=True, window=window)
            self.assertTrue(result["verified_native_release"] and all(result["criteria"].values()), result)
            self.assertAlmostEqual(result["windows"]["full"]["fan"]["mean_indoor_c"], 24)
            self.assertIsNone(result["provisional_fan_result"])
            self.assertFalse(result["optimizer_enabled"])
            with self.assertRaisesRegex(ValueError, "native prefix"):
                fan.score_pair(a, b, fabricated=True)

    def test_consumed_g218_authorization_rejected_before_g258_reservation(self):
        with TemporaryDirectory() as temp, offline_guard():
            state = Path(temp) / "unused"
            with patch.object(replication, "STATE", state), self.assertRaisesRegex(ValueError, "exact two-arm fan trial"):
                replication.execute(ROOT.parent / "g218_fan_trial_authorization.json")
            self.assertFalse(state.exists())
