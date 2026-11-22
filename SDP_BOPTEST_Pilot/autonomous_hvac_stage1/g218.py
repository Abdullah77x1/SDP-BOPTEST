"""G218-only adapter to the qualified ordered BOPTEST collector and ledger."""

import argparse
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import time

from energy_savings_g174_v1.campaign import FMU
from energy_savings_g174_v1.comparison import check_equivalence
from energy_savings_g174_v1.policy import (
    DURATION, MIN_SAVINGS_KWH, ON, PROJECT_HI, PROJECT_HOT_FALLBACK, PROJECT_LO, RECOVERY, TARGET,
)
from hvac_control_expansion_b2f_v1.packaging import inventory
from hvac_control_expansion_v1.registry import Registry
from stage4e_d0.plan import COOL, FAN, FLAGS, HEAT, LOW, OCC, POINTS, STEP, UP, append_native, energy_audit
from stage4e_d0.runner import Journal, files_manifest, utc
from stage4e_d1_v2.validation import HISTORY_POINTS, history, initial_native
from stage4e_d2i_1.common import FMU_SHA, ROOT, digest, read, require, save_new, sha
from stage4e_d2i_1.manifest import require_public_collection
from stage4e_d2i_1.schema import canonical_schema, catalog_gate, forecast_gate, observation_gate, validate_schema
from stage4e_d2i_1.transport import BudgetedTransport, initialize_run
from stage4e_d2i_1_v1_0_1.metadata import validate_metadata_receipt
from stage4e_runtime_preflight.preflight import warmup_gate

from .controller import (
    COOLING_DEMAND_W, MAX_ACTIONS, MAX_ADVANCES, MINIMUM_ENTRY_K, MINIMUM_HOLD_K, VERSION,
    Decision, EnergyController, VerifiedInterval,
)
from .evaluation import COMFORT_TOLERANCE, Trace, evaluate_matched

HOME = Path(__file__).resolve().parent
STATE = HOME / "g218_runtime_state"
CAMPAIGN = "G218_STAGE1_NATIVE_AUTONOMOUS"
ARCHIVED_CONFIG = ROOT / "stage4e_d2_public/PUBLIC_DEVELOPMENT_VALIDATION_v1_0_0/RUN_CONFIGURATION_MANIFEST.json"
WARM_CONFIG = ROOT / "energy_savings_g174_v1/CAMPAIGN.json"


def definition():
    archived = next(r for r in read(ARCHIVED_CONFIG)["runs"] if r["run_id"] == "D2_G218_N")
    require(
        (archived["start"], archived["end"], archived["warmup_start"], archived["step"],
         archived["native_step"], archived["maximum_advances"], archived["group_id"],
         archived["partition"], archived["dataset_partition"])
        == (18835200, 19094400, 18230400, 300, 30, 864, "D2_G218", "development", "development")
        and archived["initialization"] == dict(method="custom", start_time=18835200,
                                                warmup_period=604800, scenario_key=None)
        and all(archived[k] is None for k in ("seed", "solar_uncertainty", "temperature_uncertainty")),
        "G218 initialization, forcing, partition or time window differs from the qualified source",
    )
    warm = read(WARM_CONFIG)
    require(warm["model"] == {"name": "bestest_air", "version": "0.9.0", "FMU_sha256": FMU_SHA}
            and warm["policy"]["base"] == "http://127.0.0.1:80",
            "Expected the pinned BESTEST Air model and localhost transport")
    runs = [dict(archived, run_id=CAMPAIGN + "_" + label, mode=mode, arm=label)
            for label, mode in (("A", "native"), ("B", "autonomous"))]
    return {
        "campaign": CAMPAIGN, "controller_version": VERSION, "runs": runs,
        "model": warm["model"], "policy": warm["policy"], "automatic_retries": False,
        "budgets": {"instances": 2, "initializations": 2, "advances_per_arm": MAX_ADVANCES,
                    "total_advances": 2 * MAX_ADVANCES, "warm_starts": MAX_ACTIONS,
                    "warm_intervals": MAX_ACTIONS * DURATION // STEP},
        "criteria": {
            "official_occupied_band_k": [294.15, 297.15], "project_occupied_band_k": [PROJECT_LO, PROJECT_HI],
            "warm_target_k": TARGET, "warm_start_s_of_day": ON, "warm_window_s": DURATION,
            "warm_maximum_k": PROJECT_HOT_FALLBACK, "screen_one_step_rising_trend": True,
            "minimum_entry_k": MINIMUM_ENTRY_K, "minimum_hold_k": MINIMUM_HOLD_K,
            "minimum_cooling_demand_w": COOLING_DEMAND_W, "required_positive_fan_power": True,
            "minimum_net_saved_kwh_both_full_and_hold_recovery": MIN_SAVINGS_KWH,
            "hold_and_recovery_occupied_violations_allowed": 0, "allowed_extra_project_kh": 0,
            "allowed_extra_occupied_minutes": 0, "comfort_numeric_tolerance": COMFORT_TOLERANCE,
            "recovery_s": RECOVERY, "required_recovery_marker": True, "minimum_verified_warm_intervals": 1,
            "require_complete_verified_72h_pair": True,
        },
    }


class NativeController(EnergyController):
    """Use the same receipt/readback state machine while leaving all flags released."""

    def _select(self, origin, context, boundary, age_s):
        return Decision(origin, False, "native_baseline")


def collect_arm(manifest, run, directory, factory, *, fabricated):
    """Collect a run from the original frozen G218 definition."""
    require(manifest == definition() and run in manifest["runs"], "Unexpected G218 run or budget")
    controller_type = NativeController if run["mode"] == "native" else EnergyController
    return collect_policy_arm(manifest, run, directory, factory, controller_type, fabricated=fabricated)


def collect_policy_arm(manifest, run, directory, factory, controller_type, *, fabricated):
    """Collect one authorized policy arm through the existing ordered BOPTEST transport."""
    require(run in manifest["runs"], "Run is outside the campaign definition")
    require_public_collection(run)
    directory = Path(directory)
    directory.mkdir()
    save_new(directory / "ATTEMPT_STARTED.json",
             dict(run=run, campaign_sha256=digest(manifest), started_utc=utc(), fabricated=fabricated))
    save_new(directory / "QUARANTINE.json", dict(training_release=False, dataset_constructed=False, fabricated=fabricated))
    journal = Journal(directory / "receipt_order.jsonl")
    controller = controller_type(run["start"], run["end"])
    status = dict(classification="FAILED", run_id=run["run_id"], cleanup="NOT_CONFIRMED", fabricated=fabricated)
    client = None
    records, endpoints, combined = [], [], {}
    try:
        client = BudgetedTransport(factory(manifest["policy"]["base"], directory, journal, run, manifest), run)
        client.deploy()
        metadata = client.discover()
        save_new(directory / "METADATA_RECEIPT_VALIDATION.json", validate_metadata_receipt(directory, metadata))
        schema = canonical_schema()
        validate_schema(schema)
        optional = schema["optional_collected_variables"]
        save_new(directory / "CATALOG_AVAILABILITY.json", catalog_gate(metadata, schema, optional))
        identity = client.fmu_identity()
        require(identity["sha256"] == FMU_SHA, "Selected FMU identity mismatch")
        save_new(directory / "DEPLOYED_FMU_IDENTITY.json", identity)
        current = initialize_run(client, run)
        observed_at, prior = time.monotonic(), client.last_receipt_order
        observation_gate(current, run["start"], metadata)
        initial_native(current)
        endpoints.append(current)
        client.request("PUT", "step", {"step": STEP})
        client.request("GET", "step")
        scenario = client.request("GET", "scenario")
        require(scenario.get("time_period") is None and scenario.get("electricity_price") == "constant"
                and all(scenario.get(key) is None for key in ("seed", "solar_uncertainty", "temperature_uncertainty")),
                "Unapproved scenario settings")
        save_new(directory / "SCENARIO.json", scenario)
        warmup = client.request("PUT", "results", {"point_names": [COOL, FAN, HEAT, *FLAGS],
                                                    "start_time": run["warmup_start"], "final_time": run["start"]})
        warmup_gate(warmup, run["start"])
        require(set(range(run["warmup_start"], run["start"] + 1, 30)) <= set(warmup["time"]), "Incomplete warmup")
        save_new(directory / "NATIVE_WARMUP_HISTORY.json", warmup)
        points = [*schema["core_forecasts"], *optional]
        with (directory / "steps.jsonl").open("x", encoding="utf-8") as steps:
            for i, origin in enumerate(range(run["start"], run["end"], STEP)):
                forecast = client.request("PUT", "forecast", {"point_names": points, "horizon": 1800, "interval": STEP})
                issued = client.last_receipt_order
                forecast_gate(forecast, origin, schema, optional)
                save_new(directory / f"forecast_{i:04d}.json",
                         dict(issued_at_sim=origin, received_order=issued, data=forecast))
                boundary = dict(time=origin, **{name: forecast[name][0] for name in POINTS})
                age = time.monotonic() - observed_at
                cutoff = journal.emit("origin_cutoff", sim_time=origin, observation_receipt=prior,
                                      forecast_receipt=issued, observation_age_s=age)
                choice = controller.decide(origin, current, boundary, age_s=age, receipts=(prior, issued, cutoff))
                morning_guard = getattr(controller, "morning_guard_evidence", None)
                decision_evidence = {"morning_guard": morning_guard} if morning_guard is not None else {}
                journal.emit("controller_decision", decision=asdict(choice), command=choice.command, cutoff=cutoff,
                             **decision_evidence)
                require(choice.advance, choice.reason)
                following = client.request("POST", "advance", choice.command)
                observed_at, response = time.monotonic(), client.last_receipt_order
                end = origin + STEP
                observation_gate(following, end, metadata)
                chunk = client.request("PUT", "results", {"point_names": list(HISTORY_POINTS),
                                                           "start_time": origin, "final_time": end})
                chunk_receipt = client.last_receipt_order
                event = controller.pending_event_time
                followup = followup_receipt = None
                if event is not None:
                    followup = client.request("PUT", "results", {"point_names": list(HISTORY_POINTS),
                                                                  "start_time": event - STEP, "final_time": event + STEP})
                    followup_receipt = client.last_receipt_order
                    save_new(directory / f"pending_history_{event}.json", followup)
                # The decision receives only point 0. Point 1 from the same issued vintage
                # enters the existing endpoint validator only after the advance.
                next_boundary = dict(time=end, issued_at=origin, lower_k=forecast[LOW][1],
                                     upper_k=forecast[UP][1], occupancy=forecast[OCC][1])
                delivered = controller.confirm(choice, following, next_boundary, response_receipt=response,
                                               native_history=chunk, event_history=followup,
                                               history_receipt=followup_receipt)
                accept_history = getattr(controller, "accept_verified_history", None)
                if accept_history is not None:
                    accept_history(origin, chunk, chunk_receipt)
                append_native(combined, chunk, origin, end)
                save_new(directory / f"native_chunk_{i:04d}.json", chunk)
                steps.write(json.dumps(dict(asdict(delivered), current_boundary=boundary, start=origin, end=end,
                                            response_receipt=response, origin_cutoff_order=cutoff,
                                            event_followup_receipt=followup_receipt, **decision_evidence),
                                       allow_nan=False) + "\n")
                steps.flush()
                records.append(delivered)
                endpoints.append(following)
                current, prior = following, response

        require(len(records) == MAX_ADVANCES and controller.pending_event_time is None
                and not any(current[f] for f in FLAGS), "Unverified final native state or incomplete run")
        whole = client.request("PUT", "results", {"point_names": list(HISTORY_POINTS),
                                                   "start_time": run["start"], "final_time": run["end"]})
        history(whole, run["start"], run["end"])
        require(combined == {k: whole[k] for k in combined}, "Native chunks differ from full history")
        kpis = client.request("GET", "kpi")
        save_new(directory / "energy_audit.json", energy_audit(combined, run["start"], run["end"], kpis, manifest["policy"]))
        save_new(directory / "official_kpis.json", kpis)
        save_new(directory / "endpoints.json", endpoints)
        save_new(directory / "whole_native_results.json", whole)
        status["classification"] = "PASS_VALID_RAW"
    except (Exception, KeyboardInterrupt) as error:
        controller.abort(error)
        status["error"] = f"{type(error).__name__}: {error}"
        journal.emit("run_failed", error=status["error"], automatic_retry=False)
    finally:
        if client is not None and client.deploy_attempts:
            try:
                cleanup = client.stop()
                require(cleanup.get("acknowledgement") == "OK" and cleanup.get("instance_removed") is True,
                        "Instance removal or stop acknowledgment unconfirmed")
                status.update(cleanup="STOP_ACK_AND_REMOVAL_VERIFIED", cleanup_evidence=cleanup)
            except Exception as error:
                status.update(classification="FAILED", cleanup="STOP_UNCONFIRMED", cleanup_error=str(error))
        status.update(verified_advances=len(records), advance_attempts=client.advance_attempts if client else 0,
                      deployments=client.deploy_attempts if client else 0,
                      initializations=client.initialization_attempts if client else 0)
        journal.emit("attempt_closed", classification=status["classification"], cleanup=status["cleanup"])
        save_new(directory / "RUN_COMPLETED.json", status)
        save_new(directory / "ARTIFACT_MANIFEST.json", dict(files=files_manifest(directory)))
    return status


def score_pair(native, autonomous, *, fabricated):
    return score_policy_pair(definition(), native, autonomous, fabricated=fabricated)


def score_policy_pair(manifest, native, autonomous, *, fabricated):
    """Verify equivalence and apply the frozen Stage 1 acceptance arithmetic."""
    paths = (Path(native), Path(autonomous))
    for path, run in zip(paths, manifest["runs"], strict=True):
        status = read(path / "RUN_COMPLETED.json")
        require(status["fabricated"] is fabricated and status["run_id"] == run["run_id"]
                and status["classification"] == "PASS_VALID_RAW" and status["cleanup"] == "STOP_ACK_AND_REMOVAL_VERIFIED"
                and (status["deployments"], status["initializations"], status["advance_attempts"],
                     status["verified_advances"]) == (1, 1, MAX_ADVANCES, MAX_ADVANCES),
                "Complete, verified G218 arm required")
    with (paths[1] / "steps.jsonl").open(encoding="utf-8") as stream:
        records = [VerifiedInterval(Decision(**r["decision"]), r["actual_cooling_k"], r["cooling_override_active"])
                   for r in map(json.loads, stream)]
    first_action = next((r.decision.origin for r in records if r.cooling_override_active), manifest["runs"][1]["end"])
    run = manifest["runs"][1]
    require(read(paths[0] / "SCENARIO.json") == read(paths[1] / "SCENARIO.json"), "Scenario mismatch between arms")
    equivalence = check_equivalence(*paths, run, first_action)
    traces = [Trace(read(path / "whole_native_results.json"), read(path / "official_kpis.json")["tdis_tot"]) for path in paths]
    return dict(technical_validation="PASS", fabricated=fabricated, forcing_equivalence=equivalence,
                **evaluate_matched(*traces, records, run["start"], run["end"]))


def approval_binding():
    """Display hashes and limits for the explicit execution authorization."""
    sources = [HOME / name for name in ("g218.py", "controller.py", "evaluation.py", "tests.py", "test_g218.py")]
    sources += [ARCHIVED_CONFIG, WARM_CONFIG, *(ROOT / path for path in (
        "energy_savings_g174_v1/policy.py", "energy_savings_g174_v1/comparison.py", "core.py",
        "stage4e_d0/plan.py", "stage4e_d0/runner.py", "stage4e_d0/RUNTIME_REFERENCE_IDENTITIES.json",
        "stage4e_d1r/proposed_validation.py", "stage4e_d1_v2/validation.py", "stage4e_d1_v2/runtime.py",
        "stage4e_d2i_1/transport.py", "stage4e_d2i_1/schema.py", "stage4e_d2i_1_v1_0_1/metadata.py",
        "stage4e_runtime_preflight/preflight.py", "hvac_control_expansion_b2g_v1/launcher.py",
        "hvac_control_expansion_v1/registry.py", "hvac_control_expansion_b2f_v1/packaging.py",
    ))]
    manifest = definition()
    return dict(campaign=CAMPAIGN, campaign_sha256=digest(manifest),
                implementation_sha256=digest({p.relative_to(ROOT).as_posix(): sha(p) for p in sources}),
                run_ids=[r["run_id"] for r in manifest["runs"]], budgets=manifest["budgets"], automatic_retries=False)


def _approval(path, expected):
    content = Path(path).read_bytes()
    got = json.loads(content.decode("utf-8-sig"))
    require(set(got) == set(expected) | {"approval_text"}
            and all(got.get(key) == value for key, value in expected.items()),
            "Approval does not bind to this exact new G218 campaign")
    text = got["approval_text"]
    require(type(text) is str and text.strip() and text.strip().casefold() not in {"pending", "draft", "no"},
            "Explicit approval text is required")
    return hashlib.sha256(content).hexdigest()


def _verify_offline():
    import unittest
    from hvac_control_expansion_b2f_v1.tests import offline_guard

    suite = unittest.defaultTestLoader.loadTestsFromNames(
        ("autonomous_hvac_stage1.tests", "autonomous_hvac_stage1.test_g218"))
    with offline_guard():
        result = unittest.TextTestRunner().run(suite)
    require(result.wasSuccessful(), "Mandatory offline controller or collector checks failed")
    return result.testsRun


def execute(authorization):
    binding = approval_binding()
    authorization_sha = _approval(authorization, dict(binding, status="EXPLICITLY_AUTHORIZED_G218_PAIR"))
    require(not STATE.exists(), "Existing campaign directory: no resume or retry")
    require(sha(FMU) == FMU_SHA, "Local FMU source drift")
    from stage4e_d1_v2.runtime import verify_runtime
    from hvac_control_expansion_b2g_v1.launcher import real_factory
    runtime = verify_runtime()
    require(runtime["classification"] == "PASS", "Pinned runtime failed")
    offline_tests = _verify_offline()
    require(approval_binding() == binding, "Campaign or code changed after approval")
    manifest = definition()
    slots = [dict(run_id=r["run_id"], group_id=r["group_id"], partition=r["partition"], category="development",
                  status="UNUSED_NOT_AUTHORIZED", run_sha256=digest(r)) for r in manifest["runs"]]
    registry = Registry.create(STATE, dict(campaign=CAMPAIGN, slots=slots))
    batch = registry.new_batch(CAMPAIGN, manifest["runs"],
                               dict(binding, runtime=runtime, authorization_sha256=authorization_sha,
                                    offline_tests_passed=offline_tests))
    paths = []
    for run in manifest["runs"]:
        run_id = run["run_id"]
        path = registry.reserve(CAMPAIGN, run)
        result = collect_arm(manifest, run, path, real_factory, fabricated=False)
        seal = batch / f"{run_id}_SEALED_MANIFEST.json"
        save_new(seal, dict(run_id=run_id, files=inventory(path), training_release=False))
        passed = result["classification"] == "PASS_VALID_RAW" and result["cleanup"] == "STOP_ACK_AND_REMOVAL_VERIFIED"
        registry.finish(run_id, "CONSUMED_COMPLETED" if passed else "CONSUMED_FAILED",
                        dict(seal_sha256=sha(seal), raw_result=result))
        registry.verify_evidence()
        require(passed, "Arm failed; campaign stopped without retry")
        paths.append(path)
    try:
        scored = score_pair(*paths, fabricated=False)
    except (Exception, KeyboardInterrupt) as error:
        scored = dict(technical_validation="FAIL", fabricated=False,
                      error=f"{type(error).__name__}: {error}", automatic_retry=False)
    save_new(batch / "PAIRED_VALIDATION.json", scored)
    save_new(batch / "BATCH_ARTIFACT_MANIFEST.json", dict(files=inventory(batch)))
    registry.verify_evidence()
    return scored


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--describe", action="store_true", help="Read-only campaign and authorization binding")
    action.add_argument("--execute", type=Path, metavar="EXECUTION_AUTHORIZATION")
    args = parser.parse_args()
    output = dict(definition=definition(), binding=approval_binding()) if args.describe else execute(args.execute)
    print(json.dumps(output, indent=2, allow_nan=False))
    if output.get("technical_validation") == "FAIL":
        raise SystemExit(1)


if __name__ == "__main__":
    main()

