"""One-shot BESTEST Air experiment for the marginal value of one warmer advance."""

import argparse
from dataclasses import asdict, dataclass
from hashlib import sha256
import json
from pathlib import Path
import time
from zipfile import ZipFile
from xml.etree import ElementTree

from autonomous_hvac_stage1 import g218
from autonomous_hvac_stage1.controller import DAY, Decision, EnergyController
from autonomous_hvac_stage1.evaluation import ComfortSchedule, score_window
from energy_savings_g174_v1.policy import DURATION, ON, RECOVERY, TARGET
from hvac_control_expansion_b2f_v1.packaging import chain, inventory
from hvac_control_expansion_v1.registry import Registry
from stage4e_d0.plan import COOL, FAN, FLAG, FLAGS, HEAT, LOW, OCC, POINTS, SET, STEP, UP
from stage4e_d0.plan import append_native, energy_audit, native_command
from stage4e_d0.runner import Journal, utc
from stage4e_d1_v2.validation import HISTORY_POINTS, history, initial_native
from stage4e_d2i_1.common import ROOT, digest, read, require, save_new, sha
from stage4e_d2i_1.manifest import require_public_collection
from stage4e_d2i_1.schema import canonical_schema, catalog_gate, forecast_gate, observation_gate, validate_schema
from stage4e_d2i_1.transport import BudgetedTransport, initialize_run
from stage4e_d2i_1_v1_0_1.metadata import validate_metadata_receipt
from stage4e_runtime_preflight.preflight import warmup_gate

from .live_dashboard import HERE, LIVE_BATCH, WARM_TRACE
from .live_smoke import forecast_actual
from .optimizer_campaign import BATCH as G163, CAMPAIGN as G163_ID
from .optimizer_model import OUTDOOR, SOLAR
from .rolling_model import conditions, observed_state

CAMPAIGN = "G218_RELEASE_BRANCH_1115_01"
STATUS = "EXPLICITLY_AUTHORIZED_G218_RELEASE_BRANCH_1115_01"
STATE = HERE / "release_branch_evidence" / CAMPAIGN
ROLLING_ID = "LIVE_ROLLING_TWIN_01"
ROLLING_BATCH = HERE / "live_twin_evidence" / ROLLING_ID / "batches" / ROLLING_ID
ROLLING = ROLLING_BATCH / ROLLING_ID
ROLLING_BATCH_SHA = "ac7f37278af3cfeab4f0df799295bb205b0ca085c006dd63bdcc7670f78ce604"
ROLLING_RUN_SHA = "d79687e77c2eaed508100808b06e57d488f8958fccce1cadfefebd7b8bef7deb"
TOLERANCE = 1e-7


def rows(path):
    with path.open(encoding="utf-8") as source:
        return [json.loads(row) for row in source]


def definition():
    require(sha(ROLLING_BATCH / "BATCH_ARTIFACT_MANIFEST.json") == ROLLING_BATCH_SHA,
            "Archived rolling batch identity differs")
    archived = read(ROLLING_BATCH / "LIVE_CONFIGURATION.json")
    original = archived["run"]
    day_start = 218 * DAY
    fork = day_start + ON + 15 * 60
    require(original["start"] == day_start + 10 * 3600 + 20 * 60
            and original["end"] == day_start + ON + DURATION + RECOVERY
            and original["maximum_advances"] == 41 and original["initialization"]["warmup_period"] == 7 * DAY
            and original["partition"] == original["dataset_partition"] == "development"
            and archived["model"]["FMU_sha256"] == g218.FMU_SHA, "Unexpected qualified development scenario")
    runs = [dict(original, run_id=f"{CAMPAIGN}_{arm}", group_id=CAMPAIGN, arm=arm, release_at=release)
            for arm, release in (("A", fork + STEP), ("B", fork))]
    return dict(campaign=CAMPAIGN, source_run=ROLLING_ID, model=archived["model"], policy=archived["policy"],
                runs=runs, warm_start=day_start + ON, fork=fork, evaluation_end=original["end"],
                budgets=dict(instances=2, concurrent_instances=1, initializations=2, advances_per_arm=41,
                             total_advances=82, warmer_advances_per_arm=[4, 3]),
                automatic_retries=False, training_release=False, economic_switching_enabled=False)


def binding():
    spec = definition()
    sources = {name: sha(HERE / name) for name in ("release_branch.py", "test_release_branch.py", "live_smoke.py",
                                                   "rolling_model.py", "optimizer_model.py", "live_dashboard.py")}
    sources["stage4e_d2i_1/manifest.py"] = sha(ROOT / "stage4e_d2i_1/manifest.py")
    return dict(campaign=CAMPAIGN, campaign_sha256=digest(spec),
                implementation_sha256=digest(dict(stage1=g218.approval_binding()["implementation_sha256"], files=sources)),
                archived_batch_sha256=ROLLING_BATCH_SHA, archived_run_sha256=ROLLING_RUN_SHA,
                run_ids=[run["run_id"] for run in spec["runs"]], budgets=spec["budgets"], automatic_retries=False)


def archive_audit():
    paths = (("G174 fixed", WARM_TRACE), ("G218 autonomous", LIVE_BATCH / (g218.CAMPAIGN + "_B")),
             ("G163 fixed", G163 / (G163_ID + "_B")), ("G163 predictive", G163 / (G163_ID + "_C")),
             ("Live rolling", ROLLING))
    releases = {}
    for name, path in paths:
        trace = path / "whole_native_results.json"
        require(sha(trace) == read(path / "ARTIFACT_MANIFEST.json")["files"][trace.name], "Historical result changed")
        native = read(trace)
        commands = dict(zip(native["time"], native[FLAG], strict=True))
        releases[name] = [origin for origin in range(int(native["time"][0]), int(native["time"][-1]), STEP)
                          if commands[origin] and not commands[origin + 30]]
    with ZipFile(g218.FMU) as fmu:
        description = ElementTree.fromstring(fmu.read("modelDescription.xml"))
    capabilities = description.find("CoSimulation").attrib
    times_of_day = sorted({t % DAY for arm in releases.values() for t in arm})
    require(ON + 15 * 60 not in times_of_day, "Archive contains an 11:15 release; investigate pairing before collecting")
    return dict(release_timestamps_s=releases, release_times_of_day_s=times_of_day,
                matched_1115_release_pairs=0,
                fmu_state_get_set=capabilities.get("canGetAndSetFMUstate", "false") == "true",
                fmu_state_serialization=capabilities.get("canSerializeFMUstate", "false") == "true")


def compare(actual, expected, label):
    """Compare flat recorded responses using the existing pair tolerance for numerical signals."""
    require(actual.keys() == expected.keys(), f"{label}: signal schema differs")
    for field, reference in expected.items():
        values = actual[field]
        if isinstance(reference, list):
            require(isinstance(values, list) and len(values) == len(reference), f"{label}: {field} length differs")
            pairs = zip(values, reference, strict=True)
        else:
            pairs = ((values, reference),)
        for observed, target in pairs:
            same = (abs(observed - target) <= TOLERANCE
                    if field != "time" and field not in FLAGS and type(observed) in (int, float)
                    and type(target) in (int, float) else observed == target)
            require(same, f"{label}: {field} differs")


def command_at(spec, run, origin):
    command = native_command()
    if spec["warm_start"] <= origin < run["release_at"]:
        command.update({FLAG: 1, SET: TARGET})
    return command


@dataclass(frozen=True)
class Reference:
    path: Path
    commands: list
    endpoints: list

    @classmethod
    def load(cls, path, spec, *, fabricated=False):
        status = read(path / "RUN_COMPLETED.json")
        require(status["classification"] == "PASS_VALID_RAW" and status["fabricated"] is fabricated and
                status["cleanup"] == "STOP_ACK_AND_REMOVAL_VERIFIED"
                and status["advance_attempts"] == status["verified_advances"] == 41,
                "A complete verified reference is required")
        journal = path / "receipt_order.jsonl"
        chain(journal)
        commands = [r["request"] for r in rows(journal) if r["kind"] == "api_request" and r["endpoint"] == "advance"]
        endpoints = read(path / "endpoints.json")
        run = spec["runs"][0]
        require(len(commands) == 41 and [r["time"] for r in endpoints] == list(range(run["start"], run["end"] + STEP, STEP)),
                "Reference command or endpoint clock differs")
        for i, origin in enumerate(range(run["start"], spec["fork"], STEP)):
            require(commands[i] == command_at(spec, run, origin), "Archive does not reproduce the shared pre-branch command")
        return cls(path, commands, endpoints)


def sealed_reference(spec):
    seal = ROLLING_BATCH / f"{ROLLING_ID}_SEALED_MANIFEST.json"
    require(sha(seal) == ROLLING_RUN_SHA, "Original live run seal differs")
    require(inventory(ROLLING) == read(seal)["files"], "Archived live observations differ from the frozen seal")
    files = read(ROLLING_BATCH / "BATCH_ARTIFACT_MANIFEST.json")["files"]
    for name in ("LIVE_CONFIGURATION.json", "BATCH_STARTED.json"):
        require(sha(ROLLING_BATCH / name) == files[name], f"Archived {name} changed")
    return Reference.load(ROLLING, spec)


class BranchPolicy(EnergyController):
    def __init__(self, spec, run):
        super().__init__(run["start"], run["end"])
        self.spec, self.run = spec, run

    def _select(self, origin, context, boundary, age_s):
        safe = super()._select(origin, context, boundary, age_s)
        expected_warm = bool(command_at(self.spec, self.run, origin)[FLAG])
        if expected_warm:
            require(safe.warmer, f"Safety veto during the assigned warmer path: {safe.reason}")
            return Decision(origin, True, "branch_assigned_continue")
        if origin == self.run["release_at"]:
            require(self._hold_until is not None and context[FLAG] == 1, "Assigned release requires verified warmer control")
            return Decision(origin, False, "branch_assigned_release")
        return Decision(origin, False, safe.reason if not safe.warmer else "branch_native_schedule")


def collect(spec, run, path, factory, reference, *, fabricated):
    """Use the pinned transport and Stage 1 safeguards with a pre-divergence equivalence gate."""
    require(run in spec["runs"], "Run is outside the bound branch campaign")
    require_public_collection(run)
    path.mkdir()
    save_new(path / "ATTEMPT_STARTED.json", dict(run=run, campaign_sha256=digest(spec), utc=utc(), fabricated=fabricated))
    journal = Journal(path / "receipt_order.jsonl")
    controller = BranchPolicy(spec, run)
    status = dict(classification="FAILED", run_id=run["run_id"], cleanup="NOT_CONFIRMED", fabricated=fabricated)
    client = None
    committed, branch_verified = 0, False
    endpoints, combined = [], {}
    try:
        client = BudgetedTransport(factory(spec["policy"]["base"], path, journal, run, spec), run)
        client.deploy()
        metadata = client.discover()
        save_new(path / "METADATA_RECEIPT_VALIDATION.json", validate_metadata_receipt(path, metadata))
        schema = canonical_schema()
        validate_schema(schema)
        optional = schema["optional_collected_variables"]
        save_new(path / "CATALOG_AVAILABILITY.json", catalog_gate(metadata, schema, optional))
        identity = client.fmu_identity()
        require(identity["sha256"] == g218.FMU_SHA, "Deployed FMU identity differs")
        save_new(path / "DEPLOYED_FMU_IDENTITY.json", identity)
        current = initialize_run(client, run)
        observed_at, prior = time.monotonic(), client.last_receipt_order
        observation_gate(current, run["start"], metadata)
        initial_native(current)
        compare(current, reference.endpoints[0], "Initial endpoint")
        endpoints.append(current)
        client.request("PUT", "step", {"step": STEP})
        client.request("GET", "step")
        scenario = client.request("GET", "scenario")
        require(scenario == read(reference.path / "SCENARIO.json"), "Scenario forcing differs")
        save_new(path / "SCENARIO.json", scenario)
        warmup = client.request("PUT", "results", dict(point_names=[COOL, FAN, HEAT, *FLAGS],
                               start_time=run["warmup_start"], final_time=run["start"]))
        warmup_gate(warmup, run["start"])
        compare(warmup, read(reference.path / "NATIVE_WARMUP_HISTORY.json"), "Seven-day native warmup")
        save_new(path / "NATIVE_WARMUP_HISTORY.json", warmup)
        with (path / "steps.jsonl").open("x", encoding="utf-8") as steps:
            for index, origin in enumerate(range(run["start"], run["end"], STEP)):
                forecast = client.request("PUT", "forecast", dict(point_names=[*schema["core_forecasts"], *optional],
                                          horizon=1800, interval=STEP))
                issued = client.last_receipt_order
                forecast_gate(forecast, origin, schema, optional)
                reference_forecast = read(reference.path / f"forecast_{index:04d}.json")
                require(reference_forecast["issued_at_sim"] == origin, "Issued forcing clock differs")
                compare(forecast, reference_forecast["data"], f"Issued forcing at {origin}")
                save_new(path / f"forecast_{index:04d}.json", dict(issued_at_sim=origin, received_order=issued, data=forecast))
                boundary = dict(time=origin, **{key: forecast[key][0] for key in POINTS})
                age = time.monotonic() - observed_at
                cutoff = journal.emit("origin_cutoff", sim_time=origin, observation_receipt=prior,
                                      forecast_receipt=issued, observation_age_s=age)
                if origin == spec["fork"]:
                    require(committed == index and current[FLAG] == 1 and abs(current[SET] - TARGET) <= TOLERANCE,
                            "Missing verified shared warmed state")
                    proof = dict(origin=origin, reference=reference.path.name, matched_prefix_advances=committed,
                                 matching_endpoints=len(endpoints), warmup_samples=len(warmup["time"]),
                                 warm_prefix_samples=len(combined["time"]), tolerance=TOLERANCE,
                                 reference_state_sha256=digest(reference.endpoints[index]), state_sha256=digest(current),
                                 forecast_receipt=issued, observation_receipt=prior, cutoff=cutoff)
                    save_new(path / "PRE_BRANCH_EQUIVALENCE.json", proof)
                    journal.emit("pre_branch_equivalence_confirmed", **proof)
                    branch_verified = True
                choice = controller.decide(origin, current, boundary, age_s=age, receipts=(prior, issued, cutoff))
                require(choice.advance, choice.reason)
                require(choice.command == command_at(spec, run, origin), "Assigned branch command differs")
                if origin < spec["fork"]:
                    require(choice.command == reference.commands[index], "Pre-branch command differs")
                else:
                    require(branch_verified, "Branch equivalence gate has not passed")
                journal.emit("controller_decision", decision=asdict(choice), command=choice.command, cutoff=cutoff)
                require(time.monotonic() - observed_at <= 30, "Observation became stale before actuation")
                following = client.request("POST", "advance", choice.command)
                observed_at, response = time.monotonic(), client.last_receipt_order
                end = origin + STEP
                observation_gate(following, end, metadata)
                chunk = client.request("PUT", "results", dict(point_names=list(HISTORY_POINTS), start_time=origin, final_time=end))
                follow = {}
                event = controller.pending_event_time
                if event is not None:
                    event_history = client.request("PUT", "results", dict(point_names=list(HISTORY_POINTS),
                                                   start_time=event - STEP, final_time=event + STEP))
                    follow = dict(event_history=event_history, history_receipt=client.last_receipt_order)
                    save_new(path / f"pending_history_{event}.json", event_history)
                checked = controller.confirm(choice, following, dict(time=end, issued_at=origin, lower_k=forecast[LOW][1],
                                             upper_k=forecast[UP][1], occupancy=forecast[OCC][1]), response_receipt=response,
                                             native_history=chunk, **follow)
                if end <= spec["fork"]:
                    compare(following, reference.endpoints[index + 1], f"Shared endpoint at {end}")
                    compare(chunk, read(reference.path / f"native_chunk_{index:04d}.json"), f"Shared 30-second history at {end}")
                append_native(combined, chunk, origin, end)
                save_new(path / f"native_chunk_{index:04d}.json", chunk)
                steps.write(json.dumps(dict(asdict(checked), start=origin, end=end, response_receipt=response,
                                            origin_cutoff_order=cutoff), allow_nan=False) + "\n")
                steps.flush()
                committed += 1
                endpoints.append(following)
                current, prior = following, response
        require(branch_verified and committed == run["maximum_advances"] and controller.pending_event_time is None
                and not any(current[f] for f in FLAGS), "Unverified final native state or incomplete run")
        whole = client.request("PUT", "results", dict(point_names=list(HISTORY_POINTS), start_time=run["start"], final_time=run["end"]))
        history(whole, run["start"], run["end"])
        require(combined == {k: whole[k] for k in combined}, "Chunk history differs from the full trace")
        kpis = client.request("GET", "kpi")
        save_new(path / "energy_audit.json", energy_audit(whole, run["start"], run["end"], kpis, spec["policy"]))
        save_new(path / "official_kpis.json", kpis)
        save_new(path / "endpoints.json", endpoints)
        save_new(path / "whole_native_results.json", whole)
        status["classification"] = "PASS_VALID_RAW"
    except (Exception, KeyboardInterrupt) as error:
        controller.abort(error)
        status["error"] = f"{type(error).__name__}: {error}"
        journal.emit("run_failed", error=status["error"], automatic_retry=False)
    finally:
        if client and client.deploy_attempts:
            try:
                result = client.stop()
                require(result.get("acknowledgement") == "OK" and result.get("instance_removed") is True,
                        "Cleanup acknowledgment or removal is unconfirmed")
                status.update(cleanup="STOP_ACK_AND_REMOVAL_VERIFIED", cleanup_evidence=result)
            except Exception as error:
                status.update(classification="FAILED", cleanup="STOP_UNCONFIRMED", cleanup_error=str(error))
        status.update(verified_advances=committed, advance_attempts=client.advance_attempts if client else 0,
                      branch_verified=branch_verified)
        journal.emit("attempt_closed", classification=status["classification"], cleanup=status["cleanup"])
        save_new(path / "RUN_COMPLETED.json", status)
    return status


def score_pair(spec, paths, *, fabricated):
    """Score the exact one-step intervention and preserve measured targets for later fitting."""
    fork, finish = spec["fork"], spec["evaluation_end"]
    schedule = ComfortSchedule.from_fmu()
    traces = {}
    for run, path in zip(spec["runs"], paths, strict=True):
        reference = Reference.load(path, spec, fabricated=fabricated)
        proof = read(path / "PRE_BRANCH_EQUIVALENCE.json")
        start = run["start"]
        origins = range(start, finish, STEP)
        require(reference.commands == [command_at(spec, run, t) for t in origins], "Measured command path differs")
        require(proof["origin"] == fork and proof["matched_prefix_advances"] == (fork - start) // STEP,
                "Shared-state proof has the wrong fork or prefix length")
        journal = rows(path / "receipt_order.jsonl")
        events = [r for r in journal if r["kind"] == "pre_branch_equivalence_confirmed"]
        posts = [r for r in journal if r["kind"] == "api_request" and r["endpoint"] == "advance"]
        require(len(events) == 1 and proof["cutoff"] < events[0]["order"] < posts[proof["matched_prefix_advances"]]["order"],
                "Equivalence must have been recorded before the assigned branch command")
        endpoints = {obs["time"]: obs for obs in reference.endpoints}
        fork_index = (fork - start) // STEP
        preceding = read(path / f"native_chunk_{fork_index - 1:04d}.json")
        vintage = read(path / f"forecast_{fork_index:04d}.json")
        require(vintage["received_order"] == proof["forecast_receipt"] < proof["cutoff"],
                "Branch features must use the forecast available at the decision cutoff")
        decision_inputs = dict(state=asdict(observed_state(endpoints[fork], preceding)),
                               issued_weather=conditions(fork, endpoints[fork], vintage, schedule))
        native = read(path / "whole_native_results.json")
        windows = {name: score_window(native, schedule, a, b) for name, a, b in (
            ("first_step", fork, fork + STEP), ("common_native_after_first_step", fork + STEP, finish),
            ("total", fork, finish), ("after_own_release", run["release_at"], finish))}
        targets = []
        for t in range(fork + STEP, finish + 1, STEP):
            actual = forecast_actual(endpoints, native, t)
            comfort = score_window(native, schedule, t - STEP, t)
            targets.append(dict(end_s=t, indoor_temperature_c=actual["indoor_temperature"], cooling_kwh=actual["cooling"] * STEP / 3600,
                                fan_kwh=actual["fan"] * STEP / 3600, peak_indoor_c=comfort["maximum_indoor_c"],
                                official_discomfort_kh=comfort["official_replayed_kh"], project_discomfort_kh=comfort["project_replayed_kh"],
                                occupied_violation_minutes=comfort["occupied_project_violation_minutes"]))
        traces[run["arm"]] = dict(windows=windows, targets=targets, release_at=run["release_at"],
                                    native_minutes=(finish - run["release_at"]) // 60, branch_proof=proof,
                                    decision_inputs=decision_inputs,
                                    forcing=[{k: obs[k] for k in ("time", OUTDOOR, SOLAR)} for obs in reference.endpoints])
    a, b = traces["A"], traces["B"]
    require(b["branch_proof"]["reference"] == paths[0].name, "Release arm was not verified against the continue arm")
    for current, reference in zip(a.pop("forcing"), b.pop("forcing"), strict=True):
        compare(current, reference, "Measured weather across branches")
    different = {name: a["windows"][name]["electricity_kwh"] - b["windows"][name]["electricity_kwh"]
                 for name in ("first_step", "common_native_after_first_step", "total")}
    return dict(technical_validation="PASS", fabricated=fabricated, campaign=spec["campaign"], branch_origin_s=fork,
                evaluation_end_s=finish, arms=traces, release_advantage_kwh=different,
                release_minus_continue_next_temperature_c=b["targets"][0]["indoor_temperature_c"] - a["targets"][0]["indoor_temperature_c"],
                release_minus_continue_peak_temperature_c=b["windows"]["total"]["maximum_indoor_c"] - a["windows"]["total"]["maximum_indoor_c"],
                release_minus_continue_official_kh=b["windows"]["total"]["official_replayed_kh"] - a["windows"]["total"]["official_replayed_kh"],
                release_minus_continue_project_kh=b["windows"]["total"]["project_replayed_kh"] - a["windows"]["total"]["project_replayed_kh"],
                economic_release_qualified=False, qualification_limit="One branch state supplies fit targets, not independent validation")


def execute(authorization):
    scope = binding()
    expected = dict(scope, status=STATUS)
    # The gate precedes runtime checks, ledger reservation, or any BOPTEST calls.
    auth = Path(authorization).read_bytes()
    approval = json.loads(auth.decode("utf-8-sig"))
    require(approval.keys() == expected.keys() | {"approval_text"}
            and all(approval[k] == v for k, v in expected.items()), "Authorization must bind the exact G218 branch pair")
    require(isinstance(approval["approval_text"], str) and approval["approval_text"].strip()
            and approval["approval_text"].strip().casefold() not in {"pending", "draft", "no"}, "Affirmative authorization text is required")
    require(not STATE.exists(), "Existing branch ledger: no resume or retry")
    require(sha(g218.FMU) == g218.FMU_SHA, "Local pinned FMU differs")
    spec = definition()
    archived = sealed_reference(spec)
    audit = archive_audit()
    from hvac_control_expansion_b2g_v1.launcher import real_factory
    from stage4e_d1_v2.runtime import verify_runtime

    runtime = verify_runtime()
    pinned = read(ROLLING_BATCH / "BATCH_STARTED.json")["binding"]["runtime"]
    require(runtime["classification"] == "PASS" and all(runtime[k] == pinned[k] for k in ("container_image_ids", "worker_identity"))
            and binding() == scope, "Pinned runtime or bound implementation changed")
    STATE.parent.mkdir(exist_ok=True)
    slots = [dict(run_id=r["run_id"], group_id=r["group_id"], partition="development", category="development",
                  status="UNUSED_NOT_AUTHORIZED", run_sha256=digest(r)) for r in spec["runs"]]
    registry = Registry.create(STATE, dict(campaign=CAMPAIGN, slots=slots))
    batch = registry.new_batch(CAMPAIGN, spec["runs"], dict(scope, authorization_sha256=sha256(auth).hexdigest(),
                                                          runtime=runtime, archive_audit=audit))
    save_new(batch / "BRANCH_CONFIGURATION.json", spec)
    paths = []
    try:
        ref = archived
        for run in spec["runs"]:
            rid = run["run_id"]
            path = registry.reserve(CAMPAIGN, run)
            outcome = collect(spec, run, path, real_factory, ref, fabricated=False)
            seal = batch / f"{rid}_SEALED_MANIFEST.json"
            save_new(seal, dict(run_id=rid, files=inventory(path), training_release=False))
            passed = outcome["classification"] == "PASS_VALID_RAW"
            registry.finish(rid, "CONSUMED_COMPLETED" if passed else "CONSUMED_FAILED",
                            dict(seal_sha256=sha(seal), raw_result=outcome))
            registry.verify_evidence()
            require(passed, f"Arm {run['arm']} failed. {outcome.get('error', outcome['cleanup'])}")
            paths.append(path)
            if run["arm"] == "A":
                ref = Reference.load(path, spec)
        result = score_pair(spec, paths, fabricated=False)
    except (Exception, KeyboardInterrupt) as error:
        result = dict(technical_validation="FAIL", automatic_retries=False, error=str(error))
    save_new(batch / "BRANCH_COMPARISON.json", result)
    save_new(batch / "BATCH_ARTIFACT_MANIFEST.json", dict(files=inventory(batch)))
    registry.verify_evidence()
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--describe", action="store_true")
    action.add_argument("--execute", type=Path, metavar="EXACT_AUTHORIZATION")
    args = parser.parse_args()
    try:
        if args.describe:
            spec = definition()
            ref = sealed_reference(spec)
            index = (spec["fork"] - spec["runs"][0]["start"]) // STEP
            result = dict(definition=spec, binding=binding(), authorization_status=STATUS, ledger_exists=STATE.exists(),
                          archive_audit=archive_audit(), archived_state=ref.endpoints[index])
        else:
            result = execute(args.execute)
    except (OSError, ValueError, KeyError) as error:
        parser.error(str(error))
    print(json.dumps(result, indent=2, allow_nan=False))
    if result.get("technical_validation") == "FAIL":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
