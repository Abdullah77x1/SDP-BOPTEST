"""Single authorized native/400 W comparison in a new BESTEST Air window."""

import argparse
import csv
from io import TextIOWrapper
import json
from pathlib import Path
from zipfile import ZipFile

from hvac_control_expansion_b2f_v1.packaging import inventory
from hvac_control_expansion_v1.registry import Registry
from stage4e_d0.plan import COOL, FAN, OCC, STEP
from stage4e_d2i_1.common import ROOT, digest, read, require, save_new, sha

from . import g218
from .controller import COOLING_DEMAND_W, DAY
from .evaluation import ComfortSchedule, score_window
from .guard400 import CUTOFF_W, MORNING_END, MORNING_START, VERSION, GuardedController, mean_cooling_w, morning_times

HOME = Path(__file__).resolve().parent
STATE = HOME / "g400_runtime_state"
CAMPAIGN = "G400_G299_NATIVE_GUARDED"
STATUS = "EXPLICITLY_AUTHORIZED_G400_G299_PAIR"
DAY_OFFSET = 299
PARTITION_PLAN = ROOT / "stage4e_d2p/COLLECTION_AND_PARTITION_PLAN.json"


def definition():
    manifest = g218.definition()
    start = DAY_OFFSET * DAY
    manifest.update(campaign=CAMPAIGN, controller_version=VERSION)
    manifest["runs"] = [dict(r, run_id=f"{CAMPAIGN}_{r['arm']}", group_id="G400_G299",
                             start=start, end=start + 3 * DAY, warmup_start=start - 7 * DAY,
                             initialization=dict(method="custom", start_time=start, warmup_period=7 * DAY,
                                                 scenario_key=None)) for r in manifest["runs"]]
    manifest["morning_screen"] = dict(window_start_s=MORNING_START, window_end_s=MORNING_END,
                                      sample_s=30, cutoff_w=CUTOFF_W, missing_policy="skip_for_day",
                                      qualification="native cooling active at 10:50 and 10:55 with one morning per side",
                                      require_high_demand_veto_and_delivered_hold=True)
    return manifest


def scenario_audit():
    """Read timing metadata and public weather only. Scored results are outside selection."""
    plan = read(PARTITION_PLAN)
    embargo = plan["cross_group_embargo_s"]
    windows = {(row["group_id"], row["warmup_start_s"], row["scored_end_s"])
               for name in ("minimum", "recommended", "expanded", "existing_exposed_footprints")
               for row in plan[name]}
    for path in ROOT.rglob("ATTEMPT_STARTED.json"):
        if STATE in path.parents:
            continue
        row = read(path)
        row = row.get("run", row)
        start = row.get("warmup_start", row.get("warmup_start_s", row.get("start")))
        end = row.get("end", row.get("scored_end_s"))
        if type(start) in (int, float) and type(end) in (int, float):
            windows.add((path.parent.name, start, end))
    run = definition()["runs"][0]
    left, right = run["warmup_start"], run["end"]
    gap = min(max(left - end, start - right) for _, start, end in windows)
    require(gap > embargo, "G299 overlaps an existing or reserved footprint or its embargo")

    peaks = {day: [-273.15, 0.0] for day in range(DAY_OFFSET, DAY_OFFSET + 3)}
    with ZipFile(g218.FMU) as fmu, fmu.open("resources/weather.csv") as data:
        for row in csv.DictReader(TextIOWrapper(data, encoding="utf-8")):
            day, phase = divmod(float(row["time"]), DAY)
            if day in peaks and 8 * 3600 <= phase <= 18 * 3600:
                peaks[day][0] = max(peaks[day][0], float(row["TDryBul"]) - 273.15)
                peaks[day][1] = max(peaks[day][1], float(row["HGloHor"]))
    require(sum(temperature >= 14 and solar >= 600 for temperature, solar in peaks.values()) >= 2,
            "G299 fails the archived weather-only plausibility check")
    return dict(day_offset=DAY_OFFSET, footprint_s=[left, right], nearest_gap_s=gap, embargo_s=embargo,
                daytime_weather_peaks=[dict(outdoor_c=temp, solar_w_m2=solar) for temp, solar in peaks.values()])


def authorization_binding():
    manifest = definition()
    return dict(campaign=CAMPAIGN, campaign_sha256=digest(manifest),
                implementation_sha256=digest(dict(
                    shared=g218.approval_binding()["implementation_sha256"],
                    files={name: sha(HOME / name) for name in ("g400.py", "guard400.py", "test_g400.py")},
                    partition_plan_sha256=sha(PARTITION_PLAN))),
                run_ids=[r["run_id"] for r in manifest["runs"]], budgets=manifest["budgets"], automatic_retries=False)


def qualify_native(path, start):
    """Read only the native morning samples and the as-issued occupied state."""
    days = []
    for day_start in range(start, start + 3 * DAY, DAY):
        times = morning_times(day_start)
        cool, fan = {}, {}
        for i in range((times[0] - start) // STEP - 1, (times[-1] - start) // STEP):
            data = read(path / f"native_chunk_{i:04d}.json")
            for t, c, f in zip(data["time"], data[COOL], data[FAN], strict=True):
                if t in times:
                    cool.setdefault(t, c)
                    fan.setdefault(t, f)
        mean = mean_cooling_w(times, cool)
        activity_times = (times[-1] - STEP, times[-1])
        forecast = read(path / f"forecast_{(times[-1] - start) // STEP:04d}.json")
        require(forecast["issued_at_sim"] == times[-1], "Invalid native qualification forecast clock")
        active = forecast["data"][OCC][0] > 0 and all(
            cool[t] >= COOLING_DEMAND_W and fan[t] > 0 for t in activity_times)
        days.append(dict(day_start_s=day_start, mean_cooling_w=mean, cooling_active=active,
                         above_or_at_cutoff=mean >= CUTOFF_W))
    qualified = {d["above_or_at_cutoff"] for d in days if d["cooling_active"]} == {False, True}
    return dict(qualified=qualified, days=days)


def score_pair(manifest, native, guarded, *, fabricated):
    result = g218.score_policy_pair(manifest, native, guarded, fabricated=fabricated)
    with (guarded / "steps.jsonl").open(encoding="utf-8") as stream:
        steps = list(map(json.loads, stream))
    traces = [read(path / "whole_native_results.json") for path in (native, guarded)]
    schedule = ComfortSchedule.from_fmu()
    start = manifest["runs"][0]["start"]
    behavior = result["behavior"]
    days = []
    for day_start in range(start, start + 3 * DAY, DAY):
        end = day_start + DAY
        choices = [r["morning_guard"] for r in steps if day_start <= r["start"] < end and "morning_guard" in r]
        require(bool(choices), "Missing guarded morning decision evidence")
        windows = [w for w in result["windows"] if day_start <= w["activation"] < end]
        require(len(windows) <= 1, "More than one delivered hold in a day")
        days.append(dict(day_start_s=day_start, screen=choices[0],
                         stage1_would_start=any(d["stage1_would_start"] for d in choices),
                         high_demand_veto=any(d["risk_veto"] and d["screen_reason"] == "g400_high_morning_demand"
                                              for d in choices),
                         delivered_hold=windows[0] if windows else None,
                         maximum_indoor_c=[score_window(n, schedule, day_start, end)["maximum_indoor_c"] for n in traces],
                         safety_vetoes=[v for v in behavior["safety_vetoes"] if day_start <= v["time"] < end],
                         fallback_origins=[t for t in behavior["fallback_origins"] if day_start <= t < end]))
    result["guarded_days"] = days
    result["criteria"]["high_demand_veto_and_delivered_hold"] = (
        any(day["high_demand_veto"] for day in days) and bool(result["windows"]))
    result["passed_proposed_criteria"] = all(result["criteria"].values())
    return result


def _verify_offline():
    import unittest
    from hvac_control_expansion_b2f_v1.tests import offline_guard

    with offline_guard():
        tests = unittest.defaultTestLoader.loadTestsFromNames(
            ("autonomous_hvac_stage1.tests", "autonomous_hvac_stage1.test_g218", "autonomous_hvac_stage1.test_g400"))
        result = unittest.TextTestRunner().run(tests)
    require(result.wasSuccessful(), "Mandatory offline qualification failed")
    return result.testsRun


def _run_pair(manifest, registry, batch, factory, *, fabricated):
    paths = []
    for run, policy in zip(manifest["runs"], (g218.NativeController, GuardedController), strict=True):
        run_id = run["run_id"]
        path = registry.reserve(CAMPAIGN, run)
        outcome = g218.collect_policy_arm(manifest, run, path, factory, policy, fabricated=fabricated)
        seal = batch / f"{run_id}_SEALED_MANIFEST.json"
        save_new(seal, dict(run_id=run_id, files=inventory(path), training_release=False))
        passed = outcome["classification"] == "PASS_VALID_RAW" and outcome["cleanup"] == "STOP_ACK_AND_REMOVAL_VERIFIED"
        registry.finish(run_id, "CONSUMED_COMPLETED" if passed else "CONSUMED_FAILED",
                        dict(seal_sha256=sha(seal), raw_result=outcome))
        registry.verify_evidence()
        if not passed:
            return dict(technical_validation="FAIL", error=outcome.get("error", "Unconfirmed cleanup"),
                        failed_arm=run["arm"], fabricated=fabricated, automatic_retry=False)
        paths.append(path)
        if run["arm"] == "A":
            qualification = qualify_native(path, run["start"])
            save_new(batch / "NATIVE_QUALIFICATION.json", qualification)
            if not qualification["qualified"]:
                return dict(technical_validation="NONQUALIFYING SCENARIO", fabricated=fabricated,
                            native_qualification=qualification, automatic_retry=False)
    return score_pair(manifest, *paths, fabricated=fabricated)


def execute(authorization):
    binding = authorization_binding()
    record_sha = g218._approval(authorization, dict(binding, status=STATUS))
    require(not STATE.exists(), "Existing campaign directory: no resume or retry")
    require(sha(g218.FMU) == g218.FMU_SHA, "Local FMU source drift")
    audit = scenario_audit()
    from hvac_control_expansion_b2g_v1.launcher import real_factory
    from stage4e_d1_v2.runtime import verify_runtime

    runtime = verify_runtime()
    require(runtime["classification"] == "PASS", "Pinned runtime failed")
    test_count = _verify_offline()
    require(authorization_binding() == binding and scenario_audit() == audit, "Campaign or evidence changed after approval")
    manifest = definition()
    slots = [dict(run_id=r["run_id"], group_id=r["group_id"], partition=r["partition"], category="development",
                  status="UNUSED_NOT_AUTHORIZED", run_sha256=digest(r)) for r in manifest["runs"]]
    registry = Registry.create(STATE, dict(campaign=CAMPAIGN, slots=slots))
    batch = registry.new_batch(CAMPAIGN, manifest["runs"], dict(binding, runtime=runtime, scenario_audit=audit,
                               authorization_sha256=record_sha, offline_tests_passed=test_count))
    try:
        result = _run_pair(manifest, registry, batch, real_factory, fabricated=False)
    except (Exception, KeyboardInterrupt) as error:
        result = dict(technical_validation="FAIL", fabricated=False, error=f"{type(error).__name__}: {error}",
                      automatic_retry=False)
    save_new(batch / "PAIRED_VALIDATION.json", result)
    save_new(batch / "BATCH_ARTIFACT_MANIFEST.json", dict(files=inventory(batch)))
    registry.verify_evidence()
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--describe", action="store_true")
    action.add_argument("--execute", type=Path, metavar="EXECUTION_AUTHORIZATION")
    args = parser.parse_args()
    output = (dict(definition=definition(), binding=authorization_binding(), scenario_audit=scenario_audit())
              if args.describe else execute(args.execute))
    print(json.dumps(output, indent=2, allow_nan=False))
    if output.get("technical_validation") == "FAIL":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
