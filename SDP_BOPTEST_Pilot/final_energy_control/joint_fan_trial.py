"""Bounded G258 exploratory trial of airflow and fixed supply-temperature compensation."""

import argparse
import json
from pathlib import Path

from . import fan_replication as replication, fan_trial as fan

CAMPAIGN = "G258_JOINT060_1400_01"
STATUS = f"EXPLICITLY_AUTHORIZED_{CAMPAIGN}"
STATE = fan.STATE.parent / CAMPAIGN
WINDOW = replication.WINDOW
TARGET_FLOW = 0.330
NATIVE_ID = f"{replication.CAMPAIGN}_A"
NATIVE_BATCH = replication.STATE / "batches" / replication.CAMPAIGN
NATIVE_SEAL = NATIVE_BATCH / f"{NATIVE_ID}_SEALED_MANIFEST.json"
NATIVE_SEAL_SHA = "8262980cffe19e0a9e332d935c935ae9ed1f006b2c515ea8cfc8e70977c04a56"


def definition():
    spec = fan.trial_definition(CAMPAIGN, replication.source_run(), WINDOW, fan.g218.definition())
    spec["budgets"].update(maximum_joint_advances=6, retries=0, replacements=0)
    spec["joint_policy"] = dict(version="1.0.0", exploratory_development_reuse=True,
        decision_time=WINDOW.hold_start, temperature_inputs_k=[fan.TEMP, fan.SUPPLY], native_flow_input=fan.FLOW,
        target_flow_kg_s=TARGET_FLOW, supply_bounds_k=[fan.SUPPLY_MIN_K, fan.SUPPLY_MAX_K],
        formula="T_room - (m_native / 0.330) * (T_room - T_supply_native)", recompute_during_hold=False,
        require_positive_full_net_savings=True, maximum_added_official_kh=0.0,
        maximum_added_project_kh=0.0, maximum_added_project_violation_minutes=0.0)
    return spec


def binding():
    scope = fan.trial_binding(definition(), replication.ARCHIVE,
                              ("joint_fan_trial.py", "test_joint_fan_trial.py", "fan_replication.py", "optimizer_campaign.py"))
    return dict(scope, native_screen_seal_sha256=fan.sha(NATIVE_SEAL), partition_plan_sha256=fan.sha(replication.PLAN))


def supply_candidate(observation):
    """Compute once from the verified native 14:00 endpoint, using Kelvin throughout."""
    fan.require(observation["time"] == WINDOW.hold_start, "Joint candidate requires the exact 14:00 endpoint")
    fan.check_signals(observation, False)
    room, supply, flow = (fan.finite(observation[k]) for k in (fan.TEMP, fan.SUPPLY, fan.FLOW))
    fan.require(flow > TARGET_FLOW and supply < room and fan.finite(observation[fan.COOL]) >= fan.ENTRY_COOL_W
                and fan.finite(observation[fan.HEAT]) <= fan.COMFORT_TOLERANCE,
                "Joint candidate requires active cooling and a reduction from native airflow")
    command = room - (flow / TARGET_FLOW) * (room - supply)
    fan.require(fan.SUPPLY_MIN_K <= command < supply <= fan.SUPPLY_MAX_K,
                "Calculated joint supply temperature is outside the cooling/interface limits")
    return dict(room_k=room, native_supply_k=supply, native_flow_kg_s=flow, target_flow_kg_s=TARGET_FLOW,
                supply_command_k=command, supply_command_c=command - 273.15)


def screen_archive():
    fan.require(fan.sha(NATIVE_SEAL) == NATIVE_SEAL_SHA, "Sealed G258 native arm identity differs")
    source = NATIVE_BATCH / NATIVE_ID
    seal = fan.read(NATIVE_SEAL)
    for name in ("RUN_COMPLETED.json", "DEPLOYED_FMU_IDENTITY.json", "endpoints.json", "forecast_0006.json", "runtime_metadata.json"):
        fan.require(fan.sha(source / name) == seal["files"][name], f"Sealed G258 screening record changed: {name}")
    outcome = fan.read(source / "RUN_COMPLETED.json")
    fan.require(outcome["fabricated"] is False and outcome["classification"] == "PASS_VALID_RAW"
                and fan.read(source / "DEPLOYED_FMU_IDENTITY.json")["sha256"] == fan.g218.FMU_SHA,
                "Screening requires the completed pinned G258 native arm")
    metadata = fan.read(source / "runtime_metadata.json")
    supply = metadata["inputs"][fan.SUPPLY]
    fan.require((supply["Unit"], supply["Minimum"], supply["Maximum"]) == ("K", fan.SUPPLY_MIN_K, fan.SUPPLY_MAX_K)
                and metadata["measurements"][fan.FLOW]["Unit"] == "kg/s"
                and metadata["measurements"][fan.TEMP]["Unit"] == "K", "G258 catalog units or supply limits differ")
    fan.check_new_native_reference(source, {"arm": "B"}, WINDOW)
    endpoint = next(row for row in fan.read(source / "endpoints.json") if row["time"] == WINDOW.hold_start)
    return dict(archive=NATIVE_ID, measured_at_sim=WINDOW.hold_start, screening_only=True,
                example=supply_candidate(endpoint), footprint=replication.footprint_audit(replication.source_run(), fan.read(replication.PLAN)))


def score_pair(a, b, *, fabricated, window=WINDOW):
    report = fan.score_pair(a, b, fabricated=fabricated, window=window)
    delivered = report.pop("intervention_readbacks")
    report.pop("provisional_fan_result")
    actuator_valid = report["criteria"]["full_verified_dose"] and report["criteria"]["measured_airflow_reduced"]
    proof_path = b / "JOINT_SUPPLY_FREEZE.json"
    proof = fan.read(proof_path) if proof_path.exists() else None
    if proof is not None:
        steps = fan.rows(b / "steps.jsonl")
        entry = (window.hold_start - window.start) // fan.STEP
        endpoint = fan.read(b / "endpoints.json")[entry]
        expected = supply_candidate(endpoint)
        fan.require(proof == dict(expected, origin=window.hold_start, observation_receipt=steps[entry-1]["response_receipt"],
                                  cutoff=steps[entry]["cutoff"]), "Supply freeze differs from the actual entry observation")
        journal = fan.rows(b / "receipt_order.jsonl")
        freezes = [row for row in journal if row["kind"] == "joint_supply_freeze"]
        advances = [row for row in journal if row["kind"] == "api_request" and row["endpoint"] == "advance"]
        fan.require(len(freezes) == 1 and all(freezes[0][k] == v for k, v in proof.items())
                    and proof["observation_receipt"] < proof["cutoff"] < freezes[0]["order"] < advances[entry]["order"],
                    "Supply freeze was not recorded between observation and first treatment command")
    if delivered:
        fan.require(proof is not None, "Joint actuation lacks an entry freeze")
        command = {**fan.native_command(), fan.FAN_FLAG: 1, fan.FAN_SET: fan.CAP,
                   fan.SUPPLY_FLAG: 1, fan.SUPPLY: proof["supply_command_k"]}
        fan.require(all(row["command"] == command and window.hold_start <= row["start"] < window.hold_end for row in delivered),
                    "Delivered actuator command differed from the frozen pair")
    native, treatment = (fan.read(path / "whole_native_results.json") for path in (a, b))
    fan.require(not any(native[fan.SUPPLY_FLAG]), "Native comparison contains a supply override")
    for i, stamp in enumerate(treatment["time"]):
        active = any(row["start"] < stamp <= row["end"] for row in delivered)
        snapshot = {k: treatment[k][i] for k in (*fan.FLAGS, fan.FAN_SET, fan.FLOW, fan.SUPPLY, fan.SET, fan.HEAT_SET)}
        fan.check_signals(snapshot, active, proof["supply_command_k"] if active else None)
    full = report["windows"]["full"]
    added_official = full["fan"]["official_reported_kh"] - full["native"]["official_reported_kh"]
    criteria = dict(valid_joint_delivery=actuator_valid and report["verified_native_release"],
                    safety_guards_respected=report["criteria"]["guard_respected"] and not report["vetoes"],
                    positive_full_net_savings=full["net_savings_kwh"] > 0,
                    no_added_official_discomfort=added_official <= 0,
                    no_added_project_discomfort=full["added_project_kh"] <= 0,
                    no_added_project_violation_minutes=full["fan"]["occupied_project_violation_minutes"] <=
                                                        full["native"]["occupied_project_violation_minutes"])
    times = native["time"]
    differences = [y - x for x, y in zip(native[fan.TEMP], treatment[fan.TEMP], strict=True)]
    for phase in report["windows"].values():
        phase["joint"] = phase.pop("fan")
    report.update(criteria=criteria, exploratory_joint_result=all(criteria.values()) if not fabricated else None,
                  joint_supply_freeze=proof, joint_intervention_readbacks=delivered,
                  added_official_api_kh=added_official, recovery_penalty_kwh=-report["windows"]["recovery"]["net_savings_kwh"],
                  full_paired_indoor_difference_c=[min(differences), max(differences)],
                  full_heating_input_kwh={arm: fan.integrate(times, data[fan.HEAT], window.start, window.end) / 3600000
                                          for arm, data in (("native", native), ("joint", treatment))})
    return report


def execute(authorization):
    return fan.execute_campaign(authorization, definition, binding, STATUS, STATE, screen_archive,
                                joint_candidate=supply_candidate, pair_score=score_pair)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument("--describe", action="store_true")
    modes.add_argument("--execute", type=Path, metavar="EXACT_AUTHORIZATION")
    args = parser.parse_args()
    try:
        result = (dict(definition=definition(), binding=binding(), authorization_status=STATUS,
                       ledger_exists=STATE.exists(), native_screen=screen_archive()) if args.describe else execute(args.execute))
    except (OSError, KeyError, ValueError) as error:
        parser.error(str(error))
    print(json.dumps(result, indent=2, allow_nan=False))
    if result.get("technical_validation") == "FAIL":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
