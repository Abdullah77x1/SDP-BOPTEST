"""Focused offline checks for the bounded Stage 1 and O25 smoke wiring."""

import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest

from autonomous_hvac_stage1.test_g218 import ModelFixture
from hvac_control_expansion_b2f_v1.packaging import chain
from hvac_control_expansion_b2f_v1.tests import offline_guard
from stage4e_d0.plan import native_command
from stage4e_d2i_1.common import ROOT, read

from . import live_smoke


class LiveSmokeTests(unittest.TestCase):
    def test_existing_campaign_authorization_is_rejected(self):
        with offline_guard():
            with self.assertRaisesRegex(ValueError, "does not bind"):
                live_smoke.execute(live_smoke.DEFAULT_SESSION, ROOT / "g218_execution_authorization.json")

    def test_qualified_collector_commits_native_and_saves_forecasts_before_feedback(self):
        checked = []

        def forecast(origin, endpoints, native, issued, *, committed):
            self.assertEqual(set(endpoints), {origin - 1800, origin - 300, origin})
            self.assertEqual((native["time"][0], native["time"][-1]), (origin - 2100, origin))
            self.assertEqual(issued["issued_at_sim"], origin)
            self.assertEqual(committed, native_command())
            checked.append(origin)
            return dict(valid=True, reason="", units={"indoor_temperature": "degC"},
                        predictions=[{"horizon_min": h} for h in live_smoke.HORIZONS])

        predictor = SimpleNamespace(model=SimpleNamespace(forecast_observations=forecast))
        manifest = live_smoke.definition(live_smoke.DEFAULT_SESSION)
        run, = manifest["runs"]

        def factory(base, directory, journal, run, manifest):
            return live_smoke.SmokeTransport(ModelFixture(base, directory, journal, run, manifest), directory,
                                             journal, run, manifest, predictor, pace=False)

        with TemporaryDirectory() as tmp, offline_guard():
            path = Path(tmp) / "FABRICATED_SMOKE"
            result = live_smoke._collect(manifest, run, path, factory, "FABRICATED_OFFLINE_TEST_ONLY")
            self.assertEqual(result["classification"], "PASS_VALID_RAW", result)
            self.assertEqual(result["advance_requests_attempted"], live_smoke.ADVANCES)
            self.assertEqual(result["cleanup"], "STOP_ACK_AND_REMOVAL_VERIFIED")
            self.assertGreater(chain(path / "receipt_order.jsonl")["events"], live_smoke.ADVANCES)
            self.assertEqual(checked[0], live_smoke.START + 2100)
            self.assertEqual(len(checked), 6)
            self.assertEqual(read(path / "rf_0006.json")["source"], "unavailable")
            self.assertEqual(read(path / "stage1_0007.json")["decision"]["reason"],
                             "outside_qualified_window_or_recovery_budget")
            with (path / "steps.jsonl").open(encoding="utf-8") as stream:
                self.assertTrue(all(r["applied_command"] == native_command() for r in map(json.loads, stream)))
            report = live_smoke.compare_forecasts(path)
            self.assertEqual(report["valid_origins"], 6)
            first = report["target_comparisons"][:4]
            self.assertEqual([r["prediction"]["horizon_min"] for r in first], [5, 10, 15, 30])
            self.assertTrue(all(r["origin"] == checked[0] and "heating" in r["actual"] for r in first))
