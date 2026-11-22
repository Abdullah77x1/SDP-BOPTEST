"""One separately authorized native/fixed/predictive comparison on BESTEST Air."""

import argparse
from collections import Counter
import csv
from io import TextIOWrapper
import json
from pathlib import Path
from zipfile import ZipFile

from autonomous_hvac_stage1 import g218, g400
from autonomous_hvac_stage1.controller import DAY
from hvac_control_expansion_b2f_v1.packaging import inventory
from hvac_control_expansion_v1.registry import Registry
from stage4e_d0.plan import STEP
from stage4e_d2i_1.common import digest, read, require, save_new, sha

from .optimizer import VERSION, PredictiveController, calibrated_model
from .optimizer_model import MIN_GAIN_KWH, TEMP_RESERVE_C, qualification
from .policies import FixedWarmer

HERE = Path(__file__).resolve().parent
STATE = HERE / "optimizer_runtime_state"
CAMPAIGN = "OPTIMIZER_G163_NATIVE_FIXED_PREDICTIVE"
BATCH = STATE / "batches" / CAMPAIGN
STATUS = "EXPLICITLY_AUTHORIZED_OPTIMIZER_G163_TRIO"
DAY_OFFSET = 163


def definition():
    base = g218.definition()
    native, warmer = base["runs"]
    start = DAY_OFFSET * DAY
    arms = (("A", "native", native), ("B", "fixed", warmer), ("C", "predictive", warmer))
    runs = [dict(source, arm=arm, strategy=strategy, run_id=f"{CAMPAIGN}_{arm}", group_id="OPTIMIZER_G163",
                 start=start, end=start + 3 * DAY, warmup_start=start - 7 * DAY,
                 initialization=dict(method="custom", start_time=start, warmup_period=7 * DAY, scenario_key=None))
            for arm, strategy, source in arms]
    return dict(base, campaign=CAMPAIGN, controller_version=VERSION, runs=runs,
                optimizer=dict(start_local_sim_s=39600, action_ids=["A0", "A3"], use_400w=False,
                               conditional_temperature_reserve_c=TEMP_RESERVE_C, net_floor_kwh=MIN_GAIN_KWH),
                budgets=dict(base["budgets"], instances=3, initializations=3, total_advances=3 * 864))


def scenario_audit():
    run = definition()["runs"][0]
    lo, hi = run["warmup_start"], run["end"]
    plan = read(g400.PARTITION_PLAN)
    windows = [(row["warmup_start_s"], row["scored_end_s"]) for row in
               [*plan["recommended"], *plan["existing_exposed_footprints"],
                *(r for r in plan["expanded"] if r["partition"] == "protected_final_test")]]
    guard = g400.definition()["runs"][0]
    windows.append((guard["warmup_start"], guard["end"]))
    for path in g218.ROOT.rglob("ATTEMPT_STARTED.json"):
        if STATE in path.parents:
            continue
        row = read(path)
        row = row.get("run", row)
        start, end = row.get("warmup_start", row.get("start")), row.get("end")
        if type(start) in (int, float) and type(end) in (int, float):
            windows.append((start, end))
    gap = min(max(lo - end, start - hi) for start, end in windows)
    require(gap > plan["cross_group_embargo_s"], "Optimizer comparison overlaps a reserved or measured footprint")
    weather = {DAY_OFFSET + day: [-273.15, 0.0] for day in range(3)}
    with ZipFile(g218.FMU) as archive, archive.open("resources/weather.csv") as stream:
        for row in csv.DictReader(TextIOWrapper(stream, encoding="utf-8")):
            day, phase = divmod(float(row["time"]), DAY)
            if day in weather and 8 * 3600 <= phase <= 18 * 3600:
                weather[day][0] = max(weather[day][0], float(row["TDryBul"]) - 273.15)
                weather[day][1] = max(weather[day][1], float(row["HGloHor"]))
    require(sum(temp >= 24 and solar >= 850 for temp, solar in weather.values()) >= 2,
            "G163 failed the exogenous cooling plausibility check")
    return dict(footprint_s=[lo, hi], nearest_gap_s=gap, weather_day_peaks=list(weather.values()),
                expanded_unreserved_development_overlap="Planning-only D2_G160, no registered slot")


def binding():
    manifest = definition()
    return dict(campaign=CAMPAIGN, campaign_sha256=digest(manifest),
                implementation_sha256=digest(dict(shared=g218.approval_binding()["implementation_sha256"],
                    model_evaluation_sha256=digest(qualification()), partition_plan_sha256=sha(g400.PARTITION_PLAN),
                    sources={name: sha(HERE / name) for name in ("optimizer.py", "optimizer_model.py",
                             "optimizer_campaign.py", "policies.py", "test_optimizer.py")})),
                run_ids=[r["run_id"] for r in manifest["runs"]], budgets=manifest["budgets"], automatic_retries=False)


class IssuedWeatherTransport:
    def __init__(self, inner, issued):
        self.inner, self.issued = inner, issued

    def __getattr__(self, item):
        return getattr(self.inner, item)

    def request(self, method, endpoint, body=None):
        value = self.inner.request(method, endpoint, body)
        if (method, endpoint) == ("PUT", "forecast"):
            self.issued.update(issued_at_sim=value["time"][0], received_order=self.inner.last_receipt_order, data=value)
        return value


def collect(manifest, run, path, factory, model, tests, *, fabricated):
    if run["strategy"] == "native":
        policy = g218.NativeController
    elif run["strategy"] == "fixed":
        policy = FixedWarmer
    else:
        issued = {}
        transport = factory

        def factory(base, directory, journal, run, campaign):
            return IssuedWeatherTransport(transport(base, directory, journal, run, campaign), issued)

        def record(row):
            with (path / "optimizer_decisions.jsonl").open("a", encoding="utf-8") as stream:
                stream.write(json.dumps(row, allow_nan=False) + "\n")

        def policy(start, end):
            return PredictiveController(start, end, model=model, validation=tests, issued=lambda: issued,
                                        record=record, use_400w=manifest["optimizer"]["use_400w"])
    return g218.collect_policy_arm(manifest, run, path, factory, policy, fabricated=fabricated)


def score(manifest, paths, *, fabricated):
    runs = manifest["runs"]
    fixed, optimized = [g218.score_policy_pair(dict(manifest, runs=[runs[0], r]), paths[0], p, fabricated=fabricated)
                        for r, p in zip(runs[1:], paths[1:], strict=True)]
    fixed_kwh = fixed["full"]["controller"]["electricity_kwh"]
    optimization_kwh = optimized["full"]["controller"]["electricity_kwh"]
    fixed_discomfort = fixed["full"]["controller"]["project_replayed_kh"]
    optimized_discomfort = optimized["full"]["controller"]["project_replayed_kh"]
    with (paths[2] / "optimizer_decisions.jsonl").open(encoding="utf-8") as stream:
        ranked = [row for row in map(json.loads, stream) if "candidates" in row]
    require(len(ranked) == 3, "Missing optimizer decision-time rankings")
    return dict(technical_validation="PASS", fabricated=fabricated,
                fixed_vs_native=fixed, optimizer_vs_native=optimized,
                optimizer_saved_vs_fixed_kwh=fixed_kwh - optimization_kwh,
                optimizer_added_project_vs_fixed_kh=optimized_discomfort - fixed_discomfort,
                optimizer_start_choices=dict(Counter(r["selected"] for r in ranked)),
                optimizer_candidate_rejections=dict(Counter(reason for row in ranked for candidate in row["candidates"]
                                                            for reason in candidate["reasons"])),
                optimizer_passed=optimized["passed_proposed_criteria"],
                optimizer_positive_energy_vs_fixed=fixed_kwh > optimization_kwh)


def execute(authorization):
    scope = binding()
    seal = g218._approval(authorization, dict(scope, status=STATUS))
    require(not STATE.exists(), "Existing optimizer ledger: no resume or retry")
    require(sha(g218.FMU) == g218.FMU_SHA, "Local FMU source drift")
    audit = scenario_audit()
    model, tests = calibrated_model()
    require(tests["qualified"], "No warmer action-response model passed offline qualification")
    from hvac_control_expansion_b2g_v1.launcher import real_factory
    from stage4e_d1_v2.runtime import verify_runtime
    from hvac_control_expansion_b2f_v1.tests import offline_guard
    import unittest

    runtime = verify_runtime()
    with offline_guard():
        suite = unittest.defaultTestLoader.loadTestsFromName("final_energy_control.test_optimizer")
        result = unittest.TextTestRunner().run(suite)
    require(runtime["classification"] == "PASS" and result.wasSuccessful() and binding() == scope,
            "Runtime or offline verification did not pass")
    manifest = definition()
    slots = [dict(run_id=r["run_id"], group_id=r["group_id"], partition=r["partition"], category="development",
                  status="UNUSED_NOT_AUTHORIZED", run_sha256=digest(r)) for r in manifest["runs"]]
    registry = Registry.create(STATE, dict(campaign=CAMPAIGN, slots=slots))
    batch = registry.new_batch(CAMPAIGN, manifest["runs"], dict(scope, runtime=runtime, scenario_audit=audit,
                                                              authorization_sha256=seal))
    paths = []
    try:
        for run in manifest["runs"]:
            run_id = run["run_id"]
            path = registry.reserve(CAMPAIGN, run)
            outcome = collect(manifest, run, path, real_factory, model, tests, fabricated=False)
            attempt_seal = batch / f"{run_id}_SEALED_MANIFEST.json"
            save_new(attempt_seal, dict(run_id=run_id, files=inventory(path), training_release=False))
            ok = outcome["classification"] == "PASS_VALID_RAW" and outcome["cleanup"] == "STOP_ACK_AND_REMOVAL_VERIFIED"
            registry.finish(run_id, "CONSUMED_COMPLETED" if ok else "CONSUMED_FAILED",
                            dict(seal_sha256=sha(attempt_seal), raw_result=outcome))
            registry.verify_evidence()
            require(ok, f"Arm {run['arm']} failed: {outcome.get('error', outcome['cleanup'])}")
            paths.append(path)
        result = score(manifest, paths, fabricated=False)
    except (Exception, KeyboardInterrupt) as error:
        result = dict(technical_validation="FAIL", fabricated=False, error=str(error), automatic_retry=False)
    save_new(batch / "OPTIMIZER_COMPARISON.json", result)
    save_new(batch / "BATCH_ARTIFACT_MANIFEST.json", dict(files=inventory(batch)))
    registry.verify_evidence()
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--describe", action="store_true")
    mode.add_argument("--validate", action="store_true")
    mode.add_argument("--execute", type=Path, metavar="EXPLICIT_AUTHORIZATION")
    args = parser.parse_args()
    result = (qualification() if args.validate else
              dict(definition=definition(), binding=binding(), scenario_audit=scenario_audit()) if args.describe
              else execute(args.execute))
    print(json.dumps(result, indent=2, allow_nan=False))
    if result.get("technical_validation") == "FAIL":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
