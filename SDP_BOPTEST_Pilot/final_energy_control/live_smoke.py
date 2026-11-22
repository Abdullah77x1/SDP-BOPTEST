"""One authorized native-only live dashboard smoke session on the pinned stack."""

import argparse
from dataclasses import asdict
import json
from pathlib import Path
import time

from autonomous_hvac_stage1 import g218
from autonomous_hvac_stage1.controller import DAY, EnergyController
from core import integrate
from hvac_control_expansion_b2f_v1.packaging import inventory
from hvac_control_expansion_v1.registry import Registry
from stage4e_d0.plan import COOL, FAN, HEAT, LOW, OCC, POINTS, STEP, TEMP, UP, append_native, native_command
from stage4e_d2i_1.common import ROOT, digest, read, require, save_new, sha
from stage4e_d2i_1_v1_0_1.collector import _collect

from .live_dashboard import HERE, SMOKE_ROOT, SMOKE_STALE_SECONDS, ObservationalForecast, smoke_run

DEFAULT_SESSION = "LIVE_DASHBOARD_SMOKE_01"
STATUS = "EXPLICITLY_AUTHORIZED_LIVE_DASHBOARD_SMOKE"
ADVANCES = 13  # 35 min verified history, then 30 min of ground truth for the first valid origin.
START = 146 * DAY + 7 * 3600 + 35 * 60
PACE_SECONDS = 1.2
HORIZONS = (5, 10, 15, 30)


def definition(session):
    smoke_run(session)
    original = g218.definition()
    run = dict(original["runs"][0], run_id=session, group_id="LIVE_DASHBOARD_SMOKE", start=START,
               end=START + ADVANCES * STEP, warmup_start=START - 7 * DAY, maximum_advances=ADVANCES,
               initialization=dict(method="custom", start_time=START, warmup_period=7 * DAY, scenario_key=None))
    return dict(purpose="production", policy=original["policy"], runs=[run], session=session,
                controller="Stage 1 with native-only smoke constraint", training_release=False,
                automatic_retries=False, pace_seconds=PACE_SECONDS, stale_check_after_advances=4,
                stale_check_pause_seconds=SMOKE_STALE_SECONDS + 1.5,
                budgets=dict(instances=1, initializations=1, advances=ADVANCES, external_overrides=0))


def binding(session):
    spec = definition(session)
    ml = ROOT.parent / "ml_research_v1_0_0"
    files = [HERE / name for name in ("live_smoke.py", "live_dashboard.py", "dashboard.html", "test_live_smoke.py")]
    files += [ml / name for name in ("inference.py", "dataset.py", "MODEL_PROVENANCE.json")]
    files.append(ROOT.parent / "experiments/five_model_hvac16_v1_0_0/config.py")
    files.append(ROOT / "stage4e_d2i_1_v1_0_1/collector.py")
    return dict(session=session, config_sha256=digest(spec), budgets=spec["budgets"],
                implementation_sha256=digest(dict(stage1=g218.approval_binding()["implementation_sha256"],
                                                  sources={p.name: sha(p) for p in files})),
                automatic_retries=False)


class SmokeTransport:
    """Observe the qualified collector and require agreement with live Stage 1 before advance."""

    def __init__(self, inner, path, journal, run, definition, predictor, *, pace):
        self.inner, self.path, self.journal = inner, path, journal
        self.policy = EnergyController(run["start"], run["end"])
        self.start = run["start"]
        self.definition = definition
        self.predictor = predictor
        self.pace = pace
        self.native, self.endpoints = {}, {}
        self.pending = None
        self.forecast = None

    def __getattr__(self, name):
        return getattr(self.inner, name)

    def request(self, method, key, body=None):
        if (method, key) == ("POST", "advance"):
            return self._advance(body)
        if (method, key) == ("PUT", "forecast") and self.pace:
            index = (self.current["time"] - self.start) // STEP
            if index:
                time.sleep(self.definition["stale_check_pause_seconds"] if index == self.definition["stale_check_after_advances"]
                           else self.definition["pace_seconds"])
        result = self.inner.request(method, key, body)
        if (method, key) == ("PUT", "initialize"):
            self._observe(result)
            self.endpoints[result["time"]] = result
        elif (method, key) == ("PUT", "forecast"):
            self.forecast = dict(issued_at_sim=self.current["time"], received_order=self.inner.last_receipt_order, data=result)
        elif (method, key) == ("PUT", "results") and self.pending is not None:
            self._results(body, result)
        return result

    def _observe(self, result):
        self.current = result
        self.received = self.inner.last_receipt_order
        self.observed_at = time.monotonic()

    def _record_forecast(self, index, origin, command, cutoff):
        return record_o25(self.path, self.journal, index, origin, command, cutoff, self.start,
                          self.native, self.endpoints, self.forecast, self.predictor,
                          event="smoke_o25_before_advance")

    def _advance(self, command):
        require(self.pending is None and self.forecast is not None, "Missing prior Stage 1 feedback or forecast")
        origin = self.current["time"]
        data = self.forecast["data"]
        boundary = dict(time=origin, **{k: data[k][0] for k in POINTS})
        cutoff = self.journal.emit("smoke_stage1_cutoff", origin=origin, observation_receipt=self.received,
                                   forecast_receipt=self.forecast["received_order"])
        decision = self.policy.decide(origin, self.current, boundary, age_s=time.monotonic() - self.observed_at,
                                      receipts=(self.received, self.forecast["received_order"], cutoff))
        self.journal.emit("smoke_stage1_decision", decision=asdict(decision), command=decision.command, cutoff=cutoff)
        require(decision.advance, decision.reason)
        require(command == decision.command == native_command(), "Smoke authorization permits native commands only")
        index = (origin - self.start) // STEP
        forecast_receipt = self._record_forecast(index, origin, command, cutoff)
        result = self.inner.request("POST", "advance", command)
        self._observe(result)
        self.pending = dict(decision=decision, cutoff=cutoff, forecast_receipt=forecast_receipt, index=index)
        return result

    def _results(self, query, result):
        event = self.policy.pending_event_time
        pending = self.pending
        decision = pending["decision"]
        window = (query["start_time"], query["final_time"])
        origin = decision.origin
        if window == (origin, origin + STEP):
            pending["chunk"] = result
            if event is not None:
                return
            extra = {}
        else:
            require(event is not None and window == (event - STEP, event + STEP) and "chunk" in pending,
                    "Unexpected history request during Stage 1 feedback")
            extra = dict(event_history=result, history_receipt=self.inner.last_receipt_order)
        f = self.forecast["data"]
        checked = self.policy.confirm(decision, self.current,
                                      dict(time=origin + STEP, issued_at=origin, lower_k=f[LOW][1],
                                           upper_k=f[UP][1], occupancy=f[OCC][1]),
                                      response_receipt=self.received, native_history=pending["chunk"], **extra)
        append_native(self.native, pending["chunk"], origin, origin + STEP)
        self.endpoints[self.current["time"]] = self.current
        save_new(self.path / f"stage1_{pending['index']:04d}.json",
                 dict(asdict(checked), response_receipt=self.received, origin_cutoff_order=pending["cutoff"],
                      rf_before_advance_receipt=pending["forecast_receipt"]))
        self.pending = None


def record_o25(path, journal, index, origin, command, cutoff, start, native, endpoints, forecast, predictor, *, event):
    """Record the observational model output after commitment and before POST advance."""
    record = dict(source="unavailable", origin=origin, values=[], units={}, decision_cutoff=cutoff)
    if predictor.model is None:
        record["reason"] = predictor.load_error or "O25 model unavailable"
    elif origin - start < 2100:
        record["reason"] = f"Need 2100 seconds of verified native history; have {origin - start} seconds"
    else:
        support = {k: v[-71:] for k, v in native.items()}
        known = {t: endpoints[t] for t in (origin - 1800, origin - STEP, origin)}
        prediction = predictor.model.forecast_observations(origin, known, support, forecast, committed=command)
        record.update(reason=prediction["reason"], units=prediction["units"],
                      outside_development_fields=prediction.get("outside_development_fields", []))
        if record["outside_development_fields"]:
            record["reason"] += ": " + ", ".join(record["outside_development_fields"])
        if prediction["valid"]:
            require(tuple(p["horizon_min"] for p in prediction["predictions"]) == HORIZONS,
                    "O25 horizon order differs from the frozen contract")
            record.update(source="O25 Random Forest", values=prediction["predictions"])
    path = path / f"rf_{index:04d}.json"
    save_new(path, record)
    return journal.emit(event, origin=origin, source=record["source"], file=path.name,
                        artifact_sha256=sha(path), cutoff=cutoff)


def forecast_actual(endpoints, native, target):
    actual = {name: factor * integrate(native["time"], native[key], target - STEP, target) / (STEP * 1000)
              for name, key, factor in (("cooling", COOL, 1), ("fan", FAN, 1), ("heating", HEAT, .9))}
    actual.update(indoor_temperature=endpoints[target][TEMP] - 273.15, combined=actual["cooling"] + actual["fan"])
    return actual


def compare_forecasts(path):
    """Compare saved pre-advance O25 output against later verified native samples."""
    endpoints = {v["time"]: v for v in read(path / "endpoints.json")}
    native = read(path / "whole_native_results.json")
    with (path / "steps.jsonl").open(encoding="utf-8") as stream:
        steps = list(map(json.loads, stream))
    require([r["end"] for r in steps] == list(range(START + STEP, START + (ADVANCES + 1) * STEP, STEP))
            and list(endpoints) == list(range(START, START + (ADVANCES + 1) * STEP, STEP)),
            "Duplicate, missing or out-of-order smoke observations")
    comparisons, unavailable = [], []
    for i, row in enumerate(steps):
        proof = read(path / f"stage1_{i:04d}.json")
        forecast = read(path / f"rf_{i:04d}.json")
        require(forecast["origin"] == row["start"] and proof["response_receipt"] == row["endpoint_received_order"]
                and proof["origin_cutoff_order"] < proof["rf_before_advance_receipt"] < proof["response_receipt"],
                "Forecast and observed response receipts out of order")
        if forecast["source"] != "O25 Random Forest":
            unavailable.append(dict(origin=row["start"], reason=forecast["reason"],
                                    fields=forecast.get("outside_development_fields", [])))
        for prediction in forecast["values"]:
            target = row["start"] + prediction["horizon_min"] * 60
            if target not in endpoints:
                continue
            actual = forecast_actual(endpoints, native, target)
            comparisons.append(dict(origin=row["start"], target_s=target, prediction=prediction, actual=actual,
                                    units=forecast["units"]))
    return dict(verified_steps=len(steps), valid_origins=len(steps) - len(unavailable), unavailable=unavailable,
                target_comparisons=comparisons)


def execute(session, authorization):
    scope = binding(session)
    authorization_sha = g218._approval(authorization, dict(scope, status=STATUS))
    path = smoke_run(session)
    state = SMOKE_ROOT / session
    require(not state.exists(), "Existing smoke session: no resume or retry")
    require(sha(g218.FMU) == g218.FMU_SHA, "Local FMU source drift")
    from hvac_control_expansion_b2g_v1.launcher import real_factory
    from stage4e_d1_v2.runtime import verify_runtime

    runtime = verify_runtime()
    require(runtime["classification"] == "PASS" and binding(session) == scope, "Runtime or binding changed")
    manifest = definition(session)
    run, = manifest["runs"]
    predictor = ObservationalForecast()
    SMOKE_ROOT.mkdir(exist_ok=True)
    registry = Registry.create(state, dict(campaign=session, slots=[dict(
        run_id=session, group_id=run["group_id"], partition="development", category="development",
        status="UNUSED_NOT_AUTHORIZED", run_sha256=digest(run))]))
    batch = registry.new_batch(session, [run], dict(scope, runtime=runtime, authorization_sha256=authorization_sha))
    require(path == registry.reserve(session, run), "Unexpected smoke evidence path")
    save_new(batch / "SMOKE_CONFIGURATION.json", manifest)

    def factory(base, directory, journal, run, manifest):
        return SmokeTransport(real_factory(base, directory, journal, run, manifest), directory, journal, run,
                              manifest, predictor, pace=True)

    result = _collect(manifest, run, path, factory, "LIVE_DASHBOARD_SMOKE_ONLY")
    passed = result["classification"] == "PASS_VALID_RAW" and result["cleanup"] == "STOP_ACK_AND_REMOVAL_VERIFIED"
    seal = batch / f"{session}_SEALED_MANIFEST.json"
    save_new(seal, dict(run_id=session, files=inventory(path), training_release=False))
    registry.finish(session, "CONSUMED_COMPLETED" if passed else "CONSUMED_FAILED",
                    dict(seal_sha256=sha(seal), raw_result=result))
    if passed:
        save_new(batch / "FORECAST_VALIDATION.json", compare_forecasts(path))
    save_new(batch / "BATCH_ARTIFACT_MANIFEST.json", dict(files=inventory(batch)))
    registry.verify_evidence()
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--session", default=DEFAULT_SESSION)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--describe", action="store_true")
    mode.add_argument("--execute", type=Path, metavar="EXPLICIT_AUTHORIZATION")
    args = parser.parse_args()
    result = (dict(definition=definition(args.session), binding=binding(args.session)) if args.describe
              else execute(args.session, args.execute))
    print(json.dumps(result, indent=2, allow_nan=False))
    if result.get("classification") == "FAILED":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
