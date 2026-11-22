"""Offline fan trial checks with explicitly fabricated power and flow."""

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from core import integrate
from hvac_control_expansion_b2f_v1.tests import offline_guard
from stage4e_d0.plan import COOL, FAN, FLAGS, HEAT, SET, STEP, TEMP, native_command
from stage4e_d2i_1.common import ROOT, read

from . import fan_trial as trial
from .test_release_branch import BranchFixture


class FanFixture(BranchFixture):
    """Artificial fan-cube signal. It does not establish simulator savings."""

    def observation(self, stamp, command=None):
        obs = super().observation(stamp, command)
        active = bool(command and command.get(trial.FAN_FLAG))
        fraction = trial.CAP if active else .65
        obs.update({trial.FAN_FLAG: int(active), trial.FAN_SET: fraction, trial.FLOW: .55 * fraction,
                    trial.SUPPLY: 289.3, HEAT: 0., COOL: 950., FAN: 173. * fraction**3,
                    TEMP: 297.15})
        return obs

    def request(self, method, endpoint, payload=None):
        result = super().request(method, endpoint, payload)
        if endpoint == "kpi":
            times = list(self.samples)
            excess = [max(0., self.samples[t][TEMP] - 297.15, 294.15 - self.samples[t][TEMP]) for t in times]
            result["tdis_tot"] = integrate(times, excess, times[0], times[-1]) / 3600
        return result


class FanTrialTests(unittest.TestCase):
    def test_source_window_and_one_candidate(self):
        data = trial.screen_archive()
        self.assertEqual(data["benchmark_day"], 218)
        self.assertGreater(data["fan_mean_w"], 48)
        self.assertGreater(min(data["native_fan_fraction"]), trial.CAP)
        self.assertEqual(trial.definition()["budgets"]["total_advances"], 72)

    def test_real_transport_boundary_rejects_nonnative_commands_outside_the_fan_scope(self):
        spec = trial.definition()
        run = spec["runs"][1]
        budget = trial.FanTrialTransport(None, run)
        budget.initialized = budget.step_confirmed = True
        command = {**native_command(), trial.FAN_FLAG: 1, trial.FAN_SET: trial.CAP}
        with self.assertRaisesRegex(ValueError, "outside|exceeds"):
            budget.request("POST", "advance", command)
        budget.advance_attempts = (trial.HOLD_START-trial.START)//STEP
        for invalid in ({**command, trial.FAN_SET: .55}, {**command, SET: 297.15}, {**command, FLAGS[3]: 1}):
            with self.assertRaisesRegex(ValueError, "exact authorized"):
                budget.request("POST", "advance", invalid)

    def native_arm(self, root, spec):
        path = root / "native"
        outcome = trial.collect(spec, spec["runs"][0], path, FanFixture, fabricated=True)
        self.assertEqual(outcome["classification"], "PASS_VALID_RAW", outcome)
        trial.check_new_native_reference(path, spec["runs"][1])
        return path

    def test_matched_pair_measures_flow_electricity_recovery_and_comfort(self):
        with TemporaryDirectory() as tmp, offline_guard():
            root, spec = Path(tmp), trial.definition()
            native = self.native_arm(root, spec)
            fan = root / "fan"
            outcome = trial.collect(spec, spec["runs"][1], fan, FanFixture, native, fabricated=True)
            self.assertEqual(outcome["classification"], "PASS_VALID_RAW", outcome)
            self.assertEqual(outcome["realized_fan_advances"], 6, outcome)
            self.assertEqual(outcome["advance_attempts"], 36)
            proof = read(fan / "MATCH_BEFORE_FAN_COMMAND.json")
            self.assertEqual(proof["prefix_advances"], 6)
            steps = trial.rows(fan / "steps.jsonl")
            self.assertEqual([r["fan_active"] for r in steps], [False]*6+[True]*6+[False]*24)
            self.assertEqual(steps[12]["command"], native_command())
            report = trial.score_pair(native, fan, fabricated=True)
            self.assertGreater(report["windows"]["full"]["net_savings_kwh"], 0)
            self.assertTrue(all(report["criteria"].values()), report["criteria"])
            self.assertIsNone(report["provisional_fan_result"])
            self.assertFalse(report["optimizer_enabled"])

    def test_wrong_airflow_stops_with_verified_cleanup(self):
        class WrongAirflow(FanFixture):
            def observation(self, stamp, command=None):
                obs = super().observation(stamp, command)
                if obs[trial.FAN_FLAG]:
                    obs[trial.FLOW] += .03
                return obs

        with TemporaryDirectory() as tmp, offline_guard():
            root, spec = Path(tmp), trial.definition()
            native = self.native_arm(root, spec)
            failed = trial.collect(spec, spec["runs"][1], root / "fan", WrongAirflow, native, fabricated=True)
            self.assertEqual(failed["advance_attempts"], 7)
            self.assertEqual(failed["realized_fan_advances"], 0)
            self.assertIn("measured airflow", failed["error"])
            self.assertEqual(failed["cleanup"], "STOP_ACK_AND_REMOVAL_VERIFIED")

    def test_hot_history_releases_and_latches_native(self):
        class HotStep(FanFixture):
            def observation(self, stamp, command=None):
                obs = super().observation(stamp, command)
                if obs[trial.FAN_FLAG] and stamp == trial.HOLD_START+30:
                    obs[TEMP] = trial.TRIAL_HOT_K+.01
                return obs
        with TemporaryDirectory() as tmp, offline_guard():
            root, spec = Path(tmp), trial.definition()
            native = self.native_arm(root, spec)
            path = root / "fan"
            outcome = trial.collect(spec, spec["runs"][1], path, HotStep, native, fabricated=True)
            self.assertEqual(outcome["classification"], "PASS_VALID_RAW", outcome)
            self.assertEqual(outcome["realized_fan_advances"], 1)
            self.assertEqual(len(outcome["vetoes"]), 1)
            self.assertTrue(all(r["command"] == native_command() for r in trial.rows(path / "steps.jsonl")[7:]))
            self.assertFalse(trial.score_pair(native, path, fabricated=True)["criteria"]["full_verified_dose"])

    def test_native_prefix_mismatch_cannot_send_a_fan_command(self):
        class DifferentState(FanFixture):
            def observation(self, stamp, command=None):
                obs = super().observation(stamp, command)
                if stamp == trial.HOLD_START:
                    obs[TEMP] += .02
                return obs

        with TemporaryDirectory() as tmp, offline_guard():
            root, spec = Path(tmp), trial.definition()
            native = self.native_arm(root, spec)
            path = root / "fan"
            outcome = trial.collect(spec, spec["runs"][1], path, DifferentState, native, fabricated=True)
            self.assertEqual(outcome["advance_attempts"], 6)
            self.assertIn("Matched native-prefix endpoint", outcome["error"])
            self.assertFalse((path / "MATCH_BEFORE_FAN_COMMAND.json").exists())

    def test_prior_authorization_rejected_before_ledger(self):
        with TemporaryDirectory() as tmp, offline_guard():
            state = Path(tmp) / "unopened"
            with patch.object(trial, "STATE", state), self.assertRaisesRegex(ValueError, "exact two-arm fan trial"):
                trial.execute(ROOT.parent / "live_rolling_twin_authorization.json")
            self.assertFalse(state.exists())
