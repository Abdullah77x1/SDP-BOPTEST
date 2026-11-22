"""End-to-end G218 checks using only the existing fabricated collector transport."""

import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from hvac_control_expansion_b2f_v1.tests import offline_guard
from stage4e_d0.plan import COOL, FAN, FLAG, FLAGS, HEAT, LOW, OCC, SET, STEP, UP
from stage4e_d1r.proposed_validation import HEAT as HSET
from stage4e_d2i_1.common import read, save_new
from stage4e_d2i_1_v1_0_1.fixtures import FakeTransport

from . import g218
from .controller import DAY, EnergyController
from energy_savings_g174_v1.policy import DURATION, ON, RECOVERY, TARGET


class ModelFixture(FakeTransport):
    """Constant temperature and simple scripted power; no physical simulation."""

    def observation(self, time, command=None):
        observation = super().observation(time, command)
        if time >= self.run["start"] + DAY:
            observation[COOL] = 0.0  # The second and third days should remain native.
        if command and command[FLAG]:
            observation[COOL] -= 100.0
        return observation

    def request(self, method, key, data=None):
        if key != "kpi":
            return super().request(method, key, data)
        # Independent total-carrier fixture reconciliation, including gas.
        samples = [sum(row[k] for k in (COOL, FAN, HEAT)) for row in self.samples.values()]
        joules = (sum(samples) - (samples[0] + samples[-1]) / 2) * 30
        policy = self.manifest["policy"]
        self.receipt("response", method=method, endpoint=key)
        return {"ener_tot": joules * policy["official_kwh_per_j"] / policy["area_m2"], "tdis_tot": 0.0}


class WrongReadback(ModelFixture):
    fault = "wrong_active"


class G218IntegrationTests(unittest.TestCase):
    def test_full_pair_uses_only_current_inputs_and_verifies_release(self):
        manifest = g218.definition()
        native, autonomous = manifest["runs"]
        observed = []
        decide = EnergyController.decide

        def inspect(controller, origin, current, boundary, *, age_s, receipts):
            self.assertEqual(current["time"], origin)
            self.assertEqual(boundary["time"], origin)
            self.assertTrue(all(isinstance(value, (int, float)) for value in boundary.values()))
            self.assertLess(receipts[0], receipts[1])
            self.assertLess(receipts[1], receipts[2])
            outcome = decide(controller, origin, current, boundary, age_s=age_s, receipts=receipts)
            if current[HSET] == 294.15 and not current[FLAG]:
                self.assertEqual(current[SET], 297.15)
            if outcome.warmer:
                self.assertEqual(current[HSET], 294.15)
                self.assertTrue(all(outcome.command[flag] == 0 for flag in FLAGS if flag != FLAG))
                observed.append(origin)
            return outcome

        with tempfile.TemporaryDirectory() as tmp, offline_guard(), patch.object(EnergyController, "decide", inspect):
            paths = Path(tmp) / "A", Path(tmp) / "B"
            for run, path in zip(manifest["runs"], paths, strict=True):
                status = g218.collect_arm(manifest, run, path, ModelFixture, fabricated=True)
                self.assertEqual(status["classification"], "PASS_VALID_RAW", status)
                self.assertEqual(status["advance_attempts"], 864)
                self.assertEqual(status["cleanup"], "STOP_ACK_AND_REMOVAL_VERIFIED")
            paired = g218.score_pair(*paths, fabricated=True)
            self.assertTrue(paired["fabricated"])
            self.assertEqual(paired["technical_validation"], "PASS")
            behavior = paired["behavior"]
            self.assertEqual((behavior["warm_starts_selected"], behavior["warmer_intervals"],
                              behavior["native_intervals"], behavior["fallback_count"]), (1, 9, 855, 0))
            start = autonomous["start"] + ON
            self.assertEqual(observed, list(range(start, start + DURATION, STEP)))
            window, = paired["windows"]
            self.assertEqual((window["released_to_native"], window["recovery_minutes_scored"]),
                             (start + DURATION, RECOVERY // 60))
            self.assertAlmostEqual(paired["full"]["saved_kwh"], 0.075)
            self.assertEqual(paired["full"]["controller"]["official_reported_kh"], 0.0)
            self.assertEqual(paired["full"]["controller"]["project_replayed_kh"], 0.0)
            with (paths[1] / "steps.jsonl").open(encoding="utf-8") as stream:
                steps = {row["start"]: row for row in map(json.loads, stream)}
            self.assertEqual(steps[start]["actual_cooling_k"], TARGET)
            self.assertEqual(steps[start + DURATION]["actual_cooling_k"], 297.15)
            self.assertTrue(all(not steps[t]["cooling_override_active"]
                                for t in range(start + DURATION, start + DURATION + RECOVERY, STEP)))
            with (paths[1] / "receipt_order.jsonl").open(encoding="utf-8") as stream:
                events = {event["order"]: event for event in map(json.loads, stream)}
            row = steps[start]
            self.assertEqual(events[row["origin_cutoff_order"]]["kind"], "origin_cutoff")
            self.assertEqual(events[row["response_receipt"]]["endpoint"], "advance")

    def test_unverifiable_warm_command_stops_without_another_advance(self):
        manifest = g218.definition()
        with tempfile.TemporaryDirectory() as tmp, offline_guard():
            path = Path(tmp) / "B"
            status = g218.collect_arm(manifest, manifest["runs"][1], path, WrongReadback, fabricated=True)
            self.assertEqual(status["classification"], "FAILED")
            self.assertIn("setpoint_readback", status["error"])
            self.assertEqual(status["verified_advances"], ON // STEP)
            self.assertEqual(status["advance_attempts"], ON // STEP + 1)
            self.assertEqual(status["cleanup"], "STOP_ACK_AND_REMOVAL_VERIFIED")
            self.assertFalse((path / "official_kpis.json").exists())

    def test_prior_authorization_or_altered_budget_stops_before_runtime(self):
        binding = g218.approval_binding()
        prior = g218.ROOT / "stage4e_d2_public/batch_authorizations/D2_G218/COLLECTOR_AUTHORIZATION.json"
        with tempfile.TemporaryDirectory() as tmp, offline_guard(), patch.object(g218, "STATE", Path(tmp) / "ledger"):
            with self.assertRaisesRegex(ValueError, "exact new G218"):
                g218.execute(prior)
            approval = Path(tmp) / "approval.json"
            save_new(approval, dict(binding, status="EXPLICITLY_AUTHORIZED_G218_PAIR",
                                    approval_text="Fabricated test only",
                                    budgets=dict(binding["budgets"], total_advances=1729)))
            with self.assertRaisesRegex(ValueError, "exact new G218"):
                g218.execute(approval)
            self.assertFalse(g218.STATE.exists())

    def test_explicit_authorization_needs_no_second_record_and_cannot_reuse_a_slot(self):
        with tempfile.TemporaryDirectory() as tmp, offline_guard(), patch.object(g218, "STATE", Path(tmp) / "ledger"):
            approval = Path(tmp) / "approval.json"
            save_new(approval, dict(g218.approval_binding(), status="EXPLICITLY_AUTHORIZED_G218_PAIR",
                                    approval_text="Fabricated test only"))
            g218.STATE.mkdir()
            with self.assertRaisesRegex(ValueError, "no resume or retry"):
                g218.execute(approval)
            self.assertEqual(list(g218.STATE.iterdir()), [])

