"""Native-only scenario selection and one-shot fan-control replication on G258."""

import argparse
import json
from pathlib import Path

from autonomous_hvac_stage1 import g218
from stage4e_d2i_1.common import ROOT, read, require, sha

from . import fan_trial as fan
from .optimizer_campaign import definition as optimizer_definition
from .optimizer_model import OUTDOOR, SOLAR, _checks

CAMPAIGN = "G258_FAN060_1400_01"
STATUS = "EXPLICITLY_AUTHORIZED_G258_FAN060_1400_01"
STATE = fan.STATE.parent / CAMPAIGN
ARCHIVE = ROOT / "stage4e_d2_prep02/runtime_state/batches/PUBLIC_D2_D2_G258_20261115_01/D2_G258_N"
ARCHIVE_SHA = "eae2b6954f9bbd3962d92582f86e1781eb98f6bf5756cb7974ee91962f795e1b"
PLAN = ROOT / "stage4e_d2p/COLLECTION_AND_PARTITION_PLAN.json"
SOURCE_GROUP = "D2_G258"
WINDOW = fan.TrialWindow(22339800, 22341600, 22343400, 22350600)


def source_run():
    require(sha(ARCHIVE / "ARTIFACT_MANIFEST.json") == ARCHIVE_SHA, "G258 native archive identity differs")
    _checks(ARCHIVE, ("ATTEMPT_STARTED.json", "DEPLOYED_FMU_IDENTITY.json", "RUN_COMPLETED.json"))
    source = read(ARCHIVE / "ATTEMPT_STARTED.json")["run"]
    require(source["run_id"] == "D2_G258_N" and source["group_id"] == SOURCE_GROUP and source["mode"] == "native"
            and source["partition"] == source["dataset_partition"] == "development"
            and source["start"] <= WINDOW.start < WINDOW.end <= source["end"]
            and read(ARCHIVE / "DEPLOYED_FMU_IDENTITY.json")["sha256"] == g218.FMU_SHA,
            "G258 source is outside the verified native development archive")
    return source


def definition():
    return fan.trial_definition(CAMPAIGN, source_run(), WINDOW, g218.definition())


def binding():
    scope = fan.trial_binding(definition(), ARCHIVE, ("fan_replication.py", "test_fan_replication.py", "optimizer_campaign.py"))
    return dict(scope, partition_plan_sha256=sha(PLAN))


def footprint_audit(source, plan):
    start, end = WINDOW.start - 7*fan.DAY, WINDOW.end
    groups = {r["group_id"]: r for r in plan["recommended"]}
    declared = groups[SOURCE_GROUP]
    require(declared["partition"] == "development" and declared["warmup_start_s"] == source["warmup_start"]
            and declared["scored_end_s"] == source["end"] and declared["warmup_start_s"] <= start
            and end <= declared["scored_end_s"], "G258 trial falls outside its declared development footprint")
    embargo = plan["cross_group_embargo_s"]
    reserved = [r for r in (*plan["recommended"], *plan["expanded"]) if r.get("partition") == "protected_final_test"]
    for entry in [*reserved, *plan["existing_exposed_footprints"]]:
        require(max(start - entry["scored_end_s"], entry["warmup_start_s"] - end) >= embargo,
                f"G258 is too close to {entry['group_id']}")
    # Use only the native screening footprints from the original fan study.
    g218_run = g218.definition()["runs"][0]
    g163 = optimizer_definition()["runs"][0]
    development = [(g163["warmup_start"], g163["end"]), (groups["D2_G174"]["warmup_start_s"], groups["D2_G174"]["scored_end_s"]),
                   (g218_run["warmup_start"], g218_run["end"])]
    gap = min(max(start - hi, lo - end) for lo, hi in development)
    require(gap >= embargo, "G258 overlaps a fan-study development footprint")
    return dict(warmup_start_s=start, end_s=end, gap_from_original_screening_s=gap, required_embargo_s=embargo)


def screen_archive():
    source = source_run()
    footprint = footprint_audit(source, read(PLAN))
    original = fan.screen_archive()
    candidates = []
    for day in range(source["start"], source["end"], fan.DAY):
        t = day + 14*3600
        window = fan.TrialWindow(t-1800, t, t+1800, t+1800+fan.RECOVERY)
        if window.start < source["start"] or window.end > source["end"]:
            continue
        try:
            screened = fan.screen_archive(ARCHIVE, window)
            fan.check_new_native_reference(ARCHIVE, {"arm": "B"}, window)
        except ValueError as error:
            if not str(error).startswith(("Archived window lost its eligibility", "Fresh native reference did not qualify")):
                raise
            continue
        distance = sum(abs(screened[k] / original[k] - 1) for k in ("fan_mean_w", "cooling_mean_w"))
        candidates.append((distance, screened))
    require(candidates, "No eligible G258 native window at the frozen time of day")
    distance, selected = min(candidates, key=lambda item: (item[0], item[1]["start"]))
    require(selected["start"] == WINDOW.hold_start, "Native-only selection differs from the frozen G258 window")
    obs = [r for r in read(ARCHIVE / "endpoints.json") if WINDOW.hold_start <= r["time"] <= WINDOW.hold_end]
    return dict(**selected, outdoor_c=[min(r[OUTDOOR] for r in obs)-273.15, max(r[OUTDOOR] for r in obs)-273.15],
                solar_w_m2=[min(r[SOLAR] for r in obs), max(r[SOLAR] for r in obs)],
                relative_native_load_distance=distance, eligible_same_clock_windows=[v for _, v in candidates],
                footprint=footprint)


def execute(authorization):
    return fan.execute_campaign(authorization, definition, binding, STATUS, STATE, screen_archive)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument("--describe", action="store_true")
    modes.add_argument("--execute", type=Path, metavar="EXACT_AUTHORIZATION")
    args = parser.parse_args()
    try:
        result = (dict(definition=definition(), binding=binding(), authorization_status=STATUS,
                       ledger_exists=STATE.exists(), native_selection=screen_archive()) if args.describe else execute(args.execute))
    except (OSError, KeyError, ValueError) as error:
        parser.error(str(error))
    print(json.dumps(result, indent=2, allow_nan=False))
    if result.get("technical_validation") == "FAIL":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
