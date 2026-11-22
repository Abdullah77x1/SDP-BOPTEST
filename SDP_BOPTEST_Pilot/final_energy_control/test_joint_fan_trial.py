"""Offline checks for the joint campaign with a fabricated actuator transport."""

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import Mock, patch

from hvac_control_expansion_b2f_v1.tests import offline_guard

from . import fan_trial as fan, joint_fan_trial as joint
from .test_fan_trial import FanFixture


class JointFixture(FanFixture):
    def observation(self, stamp, command=None):
        obs = super().observation(stamp, command)
        active = bool(command and command.get(fan.SUPPLY_FLAG))
        native_supply = 289.3 if stamp <= joint.WINDOW.hold_start else 288.7
        obs.update({fan.SUPPLY_FLAG: int(active), fan.SUPPLY: command[fan.SUPPLY] if active else native_supply})
        return obs


class JointFanTrialTests(unittest.TestCase):
    def setUp(self):
        self.spec = joint.definition()

    def pair(self, root, factory=JointFixture, treatment_factory=None, candidate=joint.supply_candidate):
        native, treatment = root / "native", root / "joint"
        first = fan.collect(self.spec, self.spec["runs"][0], native, factory, fabricated=True, joint_candidate=candidate)
        self.assertEqual(first["classification"], "PASS_VALID_RAW", first)
        fan.check_new_native_reference(native, self.spec["runs"][1], joint.WINDOW)
        outcome = fan.collect(self.spec, self.spec["runs"][1], treatment, treatment_factory or factory, native,
                              fabricated=True, joint_candidate=candidate)
        return native, treatment, outcome

    def test_sealed_1400_inputs_and_frozen_budget(self):
        screen = joint.screen_archive()
        self.assertEqual(screen["measured_at_sim"], 258 * fan.DAY + 14 * 3600)
        self.assertAlmostEqual(screen["example"]["supply_command_c"], 15.1975126759)
        self.assertEqual(self.spec["budgets"], dict(instances=2, concurrent_instances=1, initializations=2,
                         advances_per_arm=36, total_advances=72, maximum_fan_advances=6, maximum_joint_advances=6,
                         retries=0, replacements=0))
        self.assertFalse(self.spec["automatic_retries"] or self.spec["qualified_for_optimizer"])

    def test_matched_pair_calculates_once_then_releases_both_controls(self):
        candidate = Mock(wraps=joint.supply_candidate)
        with TemporaryDirectory() as temp, offline_guard():
            a, b, outcome = self.pair(Path(temp), candidate=candidate)
            self.assertEqual(outcome["classification"], "PASS_VALID_RAW", outcome)
            self.assertEqual(outcome["verified_advances"], 36)
            self.assertEqual(outcome["realized_fan_advances"], 6)
            candidate.assert_called_once()
            self.assertEqual(candidate.call_args.args[0]["time"], joint.WINDOW.hold_start)
            steps = fan.rows(b / "steps.jsonl")
            target = 297.15 - (0.55 * .65 / .330) * (297.15 - 289.3)
            command = {**fan.native_command(), fan.FAN_FLAG: 1, fan.FAN_SET: .60, fan.SUPPLY_FLAG: 1, fan.SUPPLY: target}
            self.assertEqual([s["command"] for s in steps], [fan.native_command()]*6 + [command]*6 + [fan.native_command()]*24)
            self.assertEqual(fan.read(b / "endpoints.json")[13][fan.SUPPLY], 288.7)
            report = joint.score_pair(a, b, fabricated=True)
            self.assertTrue(all(report["criteria"].values()), report["criteria"])
            self.assertIsNone(report["exploratory_joint_result"])
            self.assertFalse(report["optimizer_enabled"])

    def test_transport_rejects_recalculation_or_an_inexact_command(self):
        transport = fan.FanTrialTransport(Mock(), self.spec["runs"][1], joint.WINDOW, joint=True)
        transport.initialized = transport.step_confirmed = True
        with self.assertRaisesRegex(ValueError, "Invalid or late"):
            transport.freeze_supply(288.4)
        transport.advance_attempts = 6
        transport.freeze_supply(288.4)
        command = transport.treatment_command()
        for payload in ({**command, fan.SUPPLY: 288.5}, {**command, fan.SUPPLY_FLAG: 0}, {**command, fan.SET: 297.15}):
            with self.assertRaisesRegex(ValueError, "exact authorized shape"):
                transport.request("POST", "advance", payload)
        transport.request("POST", "advance", command)
        with self.assertRaisesRegex(ValueError, "Invalid or late"):
            transport.freeze_supply(288.5)
        transport.advance_attempts = 12
        with self.assertRaisesRegex(ValueError, "exact authorized shape"):
            transport.request("POST", "advance", command)
        self.assertEqual(transport.inner.request.call_count, 1)

    def test_out_of_range_calculation_vetoes_and_keeps_both_controls_native(self):
        class LowNativeSupply(JointFixture):
            def observation(self, stamp, command=None):
                return {**super().observation(stamp, command), fan.SUPPLY: 285.7}

        with TemporaryDirectory() as temp, offline_guard():
            a, b, outcome = self.pair(Path(temp), LowNativeSupply)
            self.assertEqual(outcome["classification"], "PASS_VALID_RAW", outcome)
            self.assertEqual(outcome["vetoes"], [dict(origin=joint.WINDOW.hold_start, reason="joint_supply_entry_veto")])
            self.assertEqual(outcome["realized_fan_advances"], 0)
            self.assertTrue(all(r["command"] == fan.native_command() for r in fan.rows(b / "steps.jsonl")))
            self.assertFalse(joint.score_pair(a, b, fabricated=True)["criteria"]["valid_joint_delivery"])

    def test_supply_history_mismatch_stops_and_cleans_up(self):
        class IncorrectSupply(JointFixture):
            def observation(self, stamp, command=None):
                obs = super().observation(stamp, command)
                if obs[fan.SUPPLY_FLAG] and stamp == joint.WINDOW.hold_start + 30:
                    obs[fan.SUPPLY] += .1
                return obs

        with TemporaryDirectory() as temp, offline_guard():
            _, _, outcome = self.pair(Path(temp), treatment_factory=IncorrectSupply)
            self.assertIn("joint supply temperature readback mismatch", outcome["error"])
            self.assertEqual(outcome["advance_attempts"], 7)
            self.assertEqual(outcome["cleanup"], "STOP_ACK_AND_REMOVAL_VERIFIED")

    def test_lower_guard_releases_both_and_an_official_increase_fails_acceptance(self):
        class LowRoom(JointFixture):
            def observation(self, stamp, command=None):
                obs = super().observation(stamp, command)
                if obs[fan.SUPPLY_FLAG] and stamp == joint.WINDOW.hold_start + 30:
                    obs[fan.TEMP] = fan.MINIMUM_ENTRY_K - .01
                return obs

        class WarmerRoom(JointFixture):
            def observation(self, stamp, command=None):
                obs = super().observation(stamp, command)
                if obs[fan.SUPPLY_FLAG]:
                    obs[fan.TEMP] += .01
                return obs

        with TemporaryDirectory() as temp, offline_guard():
            root = Path(temp)
            (root / "low").mkdir()
            (root / "warm").mkdir()
            _, b, low = self.pair(root / "low", treatment_factory=LowRoom)
            self.assertEqual(low["vetoes"][0]["reason"], "joint_history_low_temperature_guard")
            self.assertEqual(low["realized_fan_advances"], 1)
            self.assertTrue(all(r["command"] == fan.native_command() for r in fan.rows(b / "steps.jsonl")[7:]))
            a, b, warm = self.pair(root / "warm", treatment_factory=WarmerRoom)
            self.assertEqual(warm["classification"], "PASS_VALID_RAW", warm)
            criteria = joint.score_pair(a, b, fabricated=True)["criteria"]
            self.assertTrue(criteria["positive_full_net_savings"] and criteria["no_added_project_discomfort"])
            self.assertFalse(criteria["no_added_official_discomfort"])

    def test_fan_only_authorization_rejected_before_ledger_creation(self):
        with TemporaryDirectory() as temp, offline_guard():
            state = Path(temp) / "unused"
            with patch.object(joint, "STATE", state), self.assertRaisesRegex(ValueError, "exact two-arm fan trial"):
                joint.execute(fan.ROOT.parent / "g258_fan_trial_authorization.json")
            self.assertFalse(state.exists())
