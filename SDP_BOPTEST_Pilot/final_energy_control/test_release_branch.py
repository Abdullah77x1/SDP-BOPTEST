"""Branch orchestration tests. The fixture is deliberately not a building model."""

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from hvac_control_expansion_b2f_v1.tests import offline_guard
from stage4e_d0.plan import FLAG, TEMP
from stage4e_d2i_1.common import ROOT, read

from . import digital_twin as twin
from . import release_branch as branch
from .test_digital_twin import WireFixture, collect as collect_reference


class BranchFixture(WireFixture):
    def request(self, method, endpoint, payload=None):
        if endpoint == "advance":
            self.journal.emit("api_request", method=method, endpoint=endpoint, request=payload, fabricated=True)
        return super().request(method, endpoint, payload)


class ReleaseBranchTests(unittest.TestCase):
    def test_archives_have_only_scheduled_releases_and_no_clone(self):
        spec = branch.definition()
        audit = branch.archive_audit()
        self.assertEqual(audit["release_times_of_day_s"], [42300])
        self.assertEqual(audit["matched_1115_release_pairs"], 0)
        self.assertFalse(audit["fmu_state_get_set"] or audit["fmu_state_serialization"])
        ref = branch.sealed_reference(spec)
        self.assertEqual(ref.path.name, branch.ROLLING_ID)
        self.assertEqual(ref.endpoints[11]["time"], spec["fork"])
        self.assertTrue(ref.endpoints[11][FLAG])
        self.assertEqual(spec["budgets"]["total_advances"], 82)

    def make_reference(self, directory, spec):
        controller = twin.SessionControl(lambda c: collect_reference(directory, c, BranchFixture), pace=0)
        controller.submit({"action": "start"})
        controller.thread.join(25)
        self.assertEqual(controller.phase, "stopped", controller.result)
        return branch.Reference.load(directory, spec, fabricated=True)

    def test_two_arms_differ_in_one_command_and_score_to_common_end(self):
        with TemporaryDirectory() as temp, offline_guard():
            root, spec = Path(temp), branch.definition()
            ref = self.make_reference(root / "reference", spec)
            paths = []
            for run in spec["runs"]:
                path = root / run["run_id"]
                result = branch.collect(spec, run, path, BranchFixture, ref, fabricated=True)
                self.assertEqual(result["classification"], "PASS_VALID_RAW", result)
                self.assertTrue(result["branch_verified"])
                self.assertEqual(result["advance_attempts"], 41)
                self.assertEqual(result["cleanup"], "STOP_ACK_AND_REMOVAL_VERIFIED")
                ref = branch.Reference.load(path, spec, fabricated=True)
                paths.append(path)
            measured = branch.score_pair(spec, paths, fabricated=True)
            self.assertTrue(measured["fabricated"])
            self.assertFalse(measured["economic_release_qualified"])
            a, b = (branch.Reference.load(p, spec, fabricated=True) for p in paths)
            self.assertEqual([i for i, (x, y) in enumerate(zip(a.commands, b.commands, strict=True)) if x != y], [11])
            self.assertEqual([len(arm["targets"]) for arm in measured["arms"].values()], [30, 30])
            self.assertEqual([arm["native_minutes"] for arm in measured["arms"].values()], [145, 150])
            self.assertTrue(measured["arms"]["A"]["decision_inputs"]["state"]["warmer"])
            self.assertEqual(measured["arms"]["A"]["decision_inputs"], measured["arms"]["B"]["decision_inputs"])
            self.assertLess(measured["release_advantage_kwh"]["total"], 0)

    def test_state_mismatch_aborts_before_branch_under_original_guard(self):
        class DifferentTemperature(BranchFixture):
            def observation(self, stamp, command=None):
                result = super().observation(stamp, command)
                if stamp == self.manifest["fork"]:
                    result[TEMP] += .01
                return result

        with TemporaryDirectory() as temp, offline_guard():
            root, spec = Path(temp), branch.definition()
            ref = self.make_reference(root / "reference", spec)
            path = root / "drift"
            result = branch.collect(spec, spec["runs"][0], path, DifferentTemperature, ref, fabricated=True)
            self.assertIn("Shared endpoint", result["error"])
            self.assertEqual(result["advance_attempts"], 11)
            self.assertFalse(result["branch_verified"])
            self.assertFalse((path / "PRE_BRANCH_EQUIVALENCE.json").exists())
            self.assertEqual(read(path / "RUN_COMPLETED.json")["cleanup"], "STOP_ACK_AND_REMOVAL_VERIFIED")

    def test_old_authorization_rejected_before_runtime_or_reservation(self):
        with TemporaryDirectory() as temp, offline_guard():
            state = Path(temp) / "unused"
            with patch.object(branch, "STATE", state), self.assertRaisesRegex(ValueError, "exact G218 branch pair"):
                branch.execute(ROOT.parent / "live_rolling_twin_authorization.json")
            self.assertFalse(state.exists())
