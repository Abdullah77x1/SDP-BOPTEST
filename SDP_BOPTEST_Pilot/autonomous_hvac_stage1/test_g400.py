"""Focused G400 verification using native records and fabricated software fixtures."""

import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from energy_savings_g174_v1.policy import DURATION, ON, RECOVERY, TARGET
from hvac_control_expansion_b2f_v1.tests import offline_guard
from hvac_control_expansion_v1.registry import Registry
from stage4e_d0.plan import COOL, FLAG, SET, STEP, native_command
from stage4e_d2i_1.common import ROOT, digest, read

from . import g218, g400
from .controller import DAY
from .guard400 import MORNING_END, MORNING_START, GuardedController, mean_cooling_w, morning_times
from .test_g218 import ModelFixture
from .tests import Fixture


class MixedDemandFixture(ModelFixture):
    def observation(self, time, command=None):
        observation = super().observation(time, command)
        day = (time - self.run["start"]) // DAY
        observation[COOL] = (400.0 if day <= 0 else 300.0) - (100.0 if command and command[FLAG] else 0.0)
        return observation


class Guard400Tests(unittest.TestCase):
    def morning(self, power, *, drop=None, receipt=2, day_offset=0, temperature=None):
        case = Fixture(**({"temperature": temperature} if temperature is not None else {}))
        case.rule = GuardedController(case.rule.next_origin, case.rule.end)
        for origin in range(MORNING_START - STEP, MORNING_END, STEP):
            times = [t + day_offset for t in range(origin, origin + STEP + 1, 30) if t != drop]
            case.rule.accept_verified_history(origin + day_offset, {"time": times, COOL: [power] * len(times)}, receipt)
        case.prime(**({"temperature": temperature} if temperature is not None else {}))
        return case

    def test_inclusive_cutoff_and_original_safety(self):
        at_cutoff = self.morning(400)
        blocked = at_cutoff.decide()
        self.assertEqual(blocked.command, native_command())
        self.assertEqual(blocked.reason, "g400_high_morning_demand")
        self.assertTrue(at_cutoff.rule.morning_guard_evidence["stage1_would_start"])
        self.assertEqual(at_cutoff.rule.morning_guard_evidence["mean_cooling_w"], 400.0)
        at_cutoff.confirm(blocked)
        self.assertFalse(at_cutoff.decide().warmer)  # A veto applies for the whole eligible window.

        permitted = self.morning(399.9)
        self.assertEqual(permitted.decide().command[SET], TARGET)
        overheated = self.morning(399.9, temperature=298.65)
        self.assertEqual(overheated.decide().reason, "hot_margin_or_rising_trend")
        self.assertTrue(overheated.rule.morning_guard_evidence["screen_permits"])
        self.assertFalse(overheated.rule.morning_guard_evidence["risk_veto"])

    def test_missing_stale_invalid_or_late_history_fails_closed(self):
        inputs = [
            (300, {"drop": MORNING_END - 30}, "g400_missing_or_stale_morning_history"),
            (300, {"day_offset": -DAY}, "g400_missing_or_stale_morning_history"),
            (300, {"receipt": 7}, "g400_unverified_morning_receipt"),
            (float("nan"), {}, "g400_invalid_morning_power"),
            (-50, {}, "g400_invalid_morning_power"),
        ]
        for power, kwargs, reason in inputs:
            with self.subTest(reason=reason, kwargs=kwargs):
                case = self.morning(power, **kwargs)
                self.assertEqual(case.decide().reason, reason)
                self.assertIsNone(case.rule.morning_guard_evidence["mean_cooling_w"])

    def test_mean_uses_trapezoids_and_excludes_a_later_chunk(self):
        times = morning_times(0)
        values = dict.fromkeys(times, 300)
        values[times[0]] = 900
        self.assertEqual(mean_cooling_w(times, values), 305)
        case = self.morning(300)
        later = list(range(MORNING_END, ON + 1, 30))
        case.rule.accept_verified_history(MORNING_END, {"time": later, COOL: [1500] * len(later)}, 4)
        self.assertTrue(case.decide().warmer)
        self.assertEqual(case.rule.morning_guard_evidence["mean_cooling_w"], 300)

    def test_real_transport_requires_fresh_exact_authorization(self):
        with offline_guard():
            with self.assertRaisesRegex(ValueError, "does not bind"):
                g400.execute(ROOT / "g218_execution_authorization.json")
        self.assertEqual(g400.definition()["criteria"], g218.definition()["criteria"])
        audit = g400.scenario_audit()
        self.assertEqual(audit["nearest_gap_s"], DAY)
        self.assertEqual(audit["footprint_s"], [25228800, 26092800])

    def test_complete_pair_records_veto_delivery_release_and_recovery(self):
        manifest = g400.definition()
        with tempfile.TemporaryDirectory() as tmp, offline_guard():
            slots = [dict(run_id=r["run_id"], group_id=r["group_id"], partition=r["partition"], category="development",
                          status="UNUSED_NOT_AUTHORIZED", run_sha256=digest(r)) for r in manifest["runs"]]
            registry = Registry.create(Path(tmp) / "ledger", dict(campaign=g400.CAMPAIGN, slots=slots))
            batch = registry.new_batch(g400.CAMPAIGN, manifest["runs"], {"fabricated": True})
            result = g400._run_pair(manifest, registry, batch, MixedDemandFixture, fabricated=True)
            self.assertEqual(result["technical_validation"], "PASS", result)
            self.assertTrue(result["fabricated"])
            self.assertTrue(result["passed_proposed_criteria"], result["criteria"])
            self.assertTrue(result["criteria"]["high_demand_veto_and_delivered_hold"])
            self.assertEqual([d["screen"]["mean_cooling_w"] for d in result["guarded_days"]], [400.0, 300.0, 300.0])
            veto, first, _ = result["guarded_days"]
            self.assertTrue(veto["stage1_would_start"])
            self.assertTrue(veto["high_demand_veto"])
            self.assertIsNone(veto["delivered_hold"])
            self.assertEqual(veto["safety_vetoes"], [])
            self.assertEqual(first["delivered_hold"]["released_to_native"], first["day_start_s"] + ON + DURATION)
            self.assertIsNotNone(first["delivered_hold"]["rejoined_after_minutes"])
            directory = batch / manifest["runs"][1]["run_id"]
            with (directory / "steps.jsonl").open(encoding="utf-8") as stream:
                steps = {r["start"]: r for r in map(json.loads, stream)}
            release = first["delivered_hold"]["released_to_native"]
            self.assertEqual(steps[release]["actual_cooling_k"], 297.15)
            self.assertTrue(all(not steps[t]["cooling_override_active"] for t in range(release, release + RECOVERY, STEP)))
            self.assertEqual(read(batch / "NATIVE_QUALIFICATION.json")["qualified"], True)

            # Exercise the same orchestration gate with the verified arm artifacts.
            with patch.object(g400, "qualify_native", return_value={"qualified": False, "days": []}), \
                    patch.object(g218, "collect_policy_arm", return_value=read(directory / "RUN_COMPLETED.json")), \
                    patch.object(registry, "reserve", return_value=directory) as reserve, \
                    patch.object(registry, "finish"), patch.object(registry, "verify_evidence"):
                gated = Path(tmp) / "nonqualifying"
                gated.mkdir()
                stopped = g400._run_pair(manifest, registry, gated, MixedDemandFixture, fabricated=True)
                self.assertEqual(stopped["technical_validation"], "NONQUALIFYING SCENARIO")
                reserve.assert_called_once()

    def test_actual_guarded_start_rejects_bad_readback(self):
        class Fault(MixedDemandFixture):
            fault = "wrong_active"

        manifest = g400.definition()
        with tempfile.TemporaryDirectory() as tmp, offline_guard():
            status = g218.collect_policy_arm(manifest, manifest["runs"][1], Path(tmp) / "B", Fault,
                                            GuardedController, fabricated=True)
        self.assertEqual(status["classification"], "FAILED")
        self.assertIn("setpoint_readback", status["error"])
        self.assertEqual(status["advance_attempts"], (DAY + ON) // STEP + 1)
        self.assertEqual(status["cleanup"], "STOP_ACK_AND_REMOVAL_VERIFIED")
