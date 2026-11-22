"""One bounded native-versus-airflow comparison on pinned BESTEST Air."""

import argparse
from dataclasses import dataclass
from hashlib import sha256
import json
from pathlib import Path
import time

from autonomous_hvac_stage1 import g218
from autonomous_hvac_stage1.controller import DAY, MINIMUM_ENTRY_K
from autonomous_hvac_stage1.evaluation import COMFORT_TOLERANCE, ComfortSchedule, _recovery_mark, score_window
from core import integrate
from energy_savings_g174_v1.policy import PROJECT_HOT_FALLBACK, RECOVERY
from hvac_control_expansion_b2f_v1.packaging import chain, inventory
from hvac_control_expansion_v1.registry import Registry
from stage4e_d0.plan import COOL, FAN, FLAGS, HEAT, LOW, OCC, POINTS, SET, STEP, TEMP, UP
from stage4e_d0.plan import append_native, energy_audit, native_command, validate_readback
from stage4e_d0.runner import Journal, utc
from stage4e_d1r.proposed_validation import HEAT as HEAT_SET, finite, near
from stage4e_d1_v2.validation import HISTORY_POINTS, command_guard, endpoint, history, initial_native
from stage4e_d2i_1.common import ROOT, ContractError, digest, read, require, save_new, sha
from stage4e_d2i_1.manifest import require_public_collection
from stage4e_d2i_1.schema import canonical_schema, catalog_gate, forecast_gate, observation_gate, validate_schema
from stage4e_d2i_1.transport import BudgetedTransport, initialize_run
from stage4e_d2i_1_v1_0_1.metadata import validate_metadata_receipt
from stage4e_runtime_preflight.preflight import warmup_gate

from .live_dashboard import HERE, LIVE_BATCH
from .optimizer_model import OUTDOOR, SOLAR, _checks
from .release_branch import compare, rows

CAMPAIGN = "G218_FAN060_1400_01"
STATUS = "EXPLICITLY_AUTHORIZED_G218_FAN060_1400_01"
STATE = HERE / "fan_trial_evidence" / CAMPAIGN
MODELICA = ROOT / "deployment/official_v0.9.0/project1-boptest-0.9.0/testcases/bestest_air/models"
ARCHIVE = LIVE_BATCH / f"{g218.CAMPAIGN}_A"
FAN_FLAG = "fcu_oveFan_activate"
FAN_SET = "fcu_oveFan_u"
FLOW = "fcu_reaFloSup_y"
SUPPLY = "fcu_oveTSup_u"
SUPPLY_FLAG = "fcu_oveTSup_activate"
SUPPLY_MIN_K, SUPPLY_MAX_K = 285.15, 313.15
POINTS_30S = HISTORY_POINTS + (FAN_SET, FLOW, SUPPLY, OUTDOOR, SOLAR)
CAP = .60
NOMINAL_KG_S = .55
FLOW_TOLERANCE = .002
ENTRY_FRACTION = .63
ENTRY_FAN_W = 35.0
ENTRY_COOL_W = 100.0
ENTRY_INDOOR_K = 297.30  # 24.15°C, selected from native recordings.
TRIAL_HOT_K = 297.65     # Conservative 24.5°C stop for this unqualified input.
DAY_OFFSET = 218
HOLD_START = DAY_OFFSET * DAY + 14 * 3600
HOLD_END = HOLD_START + 1800
END = HOLD_END + RECOVERY
START = HOLD_START - 1800
ADVANCES = (END - START) // STEP


@dataclass(frozen=True)
class TrialWindow:
    start: int
    hold_start: int
    hold_end: int
    end: int

    def __post_init__(self):
        require(all(t >= 0 and t % STEP == 0 for t in (self.start, self.hold_start, self.hold_end, self.end))
                and self.hold_start - self.start == self.hold_end - self.hold_start == 1800
                and self.end - self.hold_end == RECOVERY, "Fan trial must keep the original timing and recovery")

    @property
    def advances(self):
        return (self.end - self.start) // STEP


ORIGINAL_WINDOW = TrialWindow(START, HOLD_START, HOLD_END, END)


def declared_window(spec):
    window = TrialWindow(spec["runs"][0]["start"], spec["hold_start"], spec["hold_end"], spec["recovery_end"])
    require(spec["candidate_fraction"] == CAP and all(
        (run["start"], run["end"], run["maximum_advances"]) == (window.start, window.end, window.advances)
        for run in spec["runs"]), "Fan trial timing, cap, or advance limit differs between arms")
    return window


def definition():
    original = g218.definition()
    base = original["runs"][0]
    require(base["start"] // DAY == DAY_OFFSET and base["partition"] == "development", "Unexpected source scenario")
    return trial_definition(CAMPAIGN, base, ORIGINAL_WINDOW, original)


def trial_definition(campaign, base, window, original):
    runs = [dict(base, run_id=f"{campaign}_{arm}", group_id=campaign, arm=arm, mode=mode,
                 start=window.start, end=window.end, warmup_start=window.start - 7 * DAY, maximum_advances=window.advances,
                 initialization=dict(method="custom", start_time=window.start, warmup_period=7 * DAY, scenario_key=None))
            for arm, mode in (("A", "native"), ("B", "autonomous"))]
    return dict(campaign=campaign, model=original["model"], policy=original["policy"], runs=runs,
                hold_start=window.hold_start, hold_end=window.hold_end, recovery_end=window.end, candidate_fraction=CAP,
                qualified_for_optimizer=False, training_release=False, automatic_retries=False,
                limits=dict(entry_fraction=ENTRY_FRACTION, entry_fan_w=ENTRY_FAN_W, entry_cooling_w=ENTRY_COOL_W,
                            entry_indoor_k=ENTRY_INDOOR_K, intervention_hot_k=TRIAL_HOT_K,
                            original_hot_guard_k=PROJECT_HOT_FALLBACK, minimum_indoor_k=MINIMUM_ENTRY_K,
                            measured_flow_tolerance_kg_s=FLOW_TOLERANCE, comfort_tolerance=COMFORT_TOLERANCE),
                budgets=dict(instances=2, concurrent_instances=1, initializations=2, advances_per_arm=window.advances,
                             total_advances=2 * window.advances, maximum_fan_advances=6))


def binding():
    return trial_binding(definition(), ARCHIVE)


def trial_binding(spec, archive, additional_files=()):
    modelica = ("wrapped.mo", "BESTESTAir/package.mo", "BESTESTAir/TestCases/TestCase_Ideal.mo",
                "BESTESTAir/BaseClasses/FanCoilUnit_T.mo", "BESTESTAir/BaseClasses/Thermostat_T.mo",
                "BESTESTAir/BaseClasses/ControlToTemperature.mo")
    sources = ("fan_trial.py", "test_fan_trial.py", "release_branch.py", "optimizer_model.py", *additional_files)
    return dict(campaign=spec["campaign"], campaign_sha256=digest(spec), budgets=spec["budgets"],
                implementation_sha256=digest(dict(shared=g218.approval_binding()["implementation_sha256"],
                    files={p: sha(HERE / p) for p in sources},
                    partition_gate=sha(ROOT / "stage4e_d2i_1/manifest.py"),
                    modelica={p: sha(MODELICA / p) for p in modelica})),
                archive_manifest_sha256=sha(archive / "ARTIFACT_MANIFEST.json"),
                run_ids=[r["run_id"] for r in spec["runs"]], automatic_retries=False)


def screen_archive(archive=ARCHIVE, window=ORIGINAL_WINDOW):
    _checks(archive, ("endpoints.json", "whole_native_results.json", "RUN_COMPLETED.json"))
    data = read(archive / "whole_native_results.json")
    endpoints = {r["time"]: r for r in read(archive / "endpoints.json")}
    schedule = ComfortSchedule.from_fmu()
    metrics = score_window(data, schedule, window.hold_start, window.hold_end)
    hold = [endpoints[t] for t in range(window.hold_start, window.hold_end + STEP, STEP)]
    require(all(all(row[f] == 0 for f in FLAGS) and near(row[SET], 297.15) and near(row[HEAT_SET], 294.15)
                and row[FAN_SET] >= ENTRY_FRACTION and row[HEAT] <= COMFORT_TOLERANCE
                and row[TEMP] <= ENTRY_INDOOR_K for row in hold)
            and 2 * metrics["fan_kwh"] * 1000 >= ENTRY_FAN_W
            and all(schedule.at(t)[2] for t in range(window.start, window.end + STEP, STEP)), "Archived window lost its eligibility")
    return dict(benchmark_day=window.hold_start // DAY, start=window.hold_start, end=window.hold_end,
                fan_mean_w=metrics["fan_kwh"] * 2000, cooling_mean_w=metrics["cooling_kwh"] * 2000,
                native_fan_fraction=[min(s[FAN_SET] for s in hold), max(s[FAN_SET] for s in hold)],
                observed_mass_flow_kg_s=[min(s[FLOW] for s in hold), max(s[FLOW] for s in hold)],
                supply_setpoint_c=[min(s[SUPPLY] for s in hold) - 273.15, max(s[SUPPLY] for s in hold) - 273.15],
                peak_indoor_c=metrics["occupied_max_c"])


class FanTrialTransport(BudgetedTransport):
    """Retain the native budget guard and allow exactly one versioned fan command."""

    def __init__(self, inner, run, window=ORIGINAL_WINDOW, *, joint=False):
        super().__init__(inner, run)
        self.window = window
        self.joint = joint
        self.supply_k = None

    def freeze_supply(self, supply_k):
        origin = self.run["start"] + self.advance_attempts * STEP
        require(self.joint and self.supply_k is None and self.run["arm"] == "B" and origin == self.window.hold_start
                and SUPPLY_MIN_K <= finite(supply_k) <= SUPPLY_MAX_K, "Invalid or late joint supply freeze")
        self.supply_k = supply_k

    def treatment_command(self):
        command = {**native_command(), FAN_FLAG: 1, FAN_SET: CAP}
        if self.joint:
            require(self.supply_k is not None, "Joint supply command was not frozen at entry")
            command.update({SUPPLY_FLAG: 1, SUPPLY: self.supply_k})
        return command

    def request(self, method, key, data=None):
        if key != "advance" or data == native_command():
            return super().request(method, key, data)
        origin = self.run["start"] + self.advance_attempts * STEP
        expected = self.treatment_command()
        require(method == "POST" and self.initialized and self.step_confirmed and self.run["arm"] == "B"
                and self.advance_attempts < self.run["maximum_advances"] and self.window.hold_start <= origin < self.window.hold_end
                and data == expected, "Fan command exceeds the exact authorized shape, arm, or window")
        self.advance_attempts += 1
        return self.inner.request(method, key, data)


def check_signals(observation, expected_active, supply_k=None):
    expected_joint = expected_active and supply_k is not None
    expected_flags = {**native_command(), FAN_FLAG: int(expected_active), SUPPLY_FLAG: int(expected_joint)}
    require(all(finite(observation[flag]) == expected_flags[flag] for flag in FLAGS),
            "Wrong fan flag or an unexpected simultaneous override")
    fan_set, airflow, supply = (finite(observation[key]) for key in (FAN_SET, FLOW, SUPPLY))
    require(0 <= fan_set <= 1 and airflow >= 0 and SUPPLY_MIN_K <= supply <= SUPPLY_MAX_K,
            "Fan setpoint, measured airflow, or effective supply temperature is invalid")
    require(near(observation[SET], 297.15) and near(observation[HEAT_SET], 294.15),
            "The original occupied 24°C cooling and 21°C heating setpoints must remain native")
    if expected_active:
        require(near(fan_set, CAP), "Fan command readback mismatch")
    if expected_joint:
        require(near(supply, supply_k), "Effective joint supply temperature readback mismatch")


def verified_history(chunk, origin, end, commanded, previously_active, supply_k=None):
    # Verify the raw actuator latches before projecting the separately verified flags out of the thermostat check.
    for i, stamp in enumerate(chunk["time"]):
        snapshot = {key: chunk[key][i] for key in (*FLAGS, FAN_SET, FLOW, SUPPLY, SET, HEAT_SET)}
        check_signals(snapshot, previously_active if stamp == origin else commanded, supply_k)
    zeros = [0] * len(chunk["time"])
    history({**chunk, FAN_FLAG: zeros, SUPPLY_FLAG: zeros}, origin, end)
    require(all(len(chunk[p]) == len(chunk["time"]) and all(finite(value) == value for value in chunk[p])
                for p in (OUTDOOR, SOLAR)), "Measured weather history missing")


def choose_fan(run, origin, observation, previous, boundary, next_occupied, latched_out, *, window=ORIGINAL_WINDOW):
    if run["arm"] != "B" or not window.hold_start <= origin < window.hold_end or latched_out:
        return False, "native_schedule"
    temp = observation[TEMP]
    rise = max(0.0, temp - previous[TEMP])
    if (boundary[OCC] <= 0 or next_occupied <= 0 or not near(boundary[UP], 297.15) or not near(boundary[LOW], 294.15)
            or temp < MINIMUM_ENTRY_K or temp + rise >= min(TRIAL_HOT_K, PROJECT_HOT_FALLBACK)
            or observation[HEAT] > COMFORT_TOLERANCE or observation[COOL] < ENTRY_COOL_W):
        return False, "fan_thermal_or_occupancy_veto"
    if origin == window.hold_start and (temp > ENTRY_INDOOR_K or min(observation[FAN_SET], previous[FAN_SET]) < ENTRY_FRACTION
                                or min(observation[FAN], previous[FAN]) < ENTRY_FAN_W or observation[SUPPLY] <= 285.65):
        return False, "fan_start_outside_recorded_operating_point"
    return True, "fan_candidate"


def collect(spec, run, path, factory, reference=None, *, fabricated=False, joint_candidate=None):
    """Collect with the existing ordered transport, pinned readback gates and native scorer."""
    require(run in spec["runs"] and (reference is None) == (run["arm"] == "A"), "Unexpected fan trial arm")
    require((joint_candidate is not None) == ("joint_policy" in spec), "Campaign and joint policy must be bound together")
    require_public_collection(run)
    window = declared_window(spec)
    path.mkdir()
    journal = Journal(path / "receipt_order.jsonl")
    save_new(path / "ATTEMPT_STARTED.json", dict(run=run, campaign_sha256=digest(spec), utc=utc(), fabricated=fabricated))
    status = dict(classification="FAILED", cleanup="NOT_CONFIRMED", fabricated=fabricated, run_id=run["run_id"])
    client, committed, active, latched_out = None, 0, False, False
    combined, endpoints, fan_intervals, vetoes = {}, [], 0, []
    try:
        client = FanTrialTransport(factory(spec["policy"]["base"], path, journal, run, spec), run, window,
                                   joint=joint_candidate is not None)
        client.deploy()
        catalog = client.discover()
        save_new(path / "METADATA_RECEIPT_VALIDATION.json", validate_metadata_receipt(path, catalog))
        schema = canonical_schema()
        validate_schema(schema)
        optional = schema["optional_collected_variables"]
        save_new(path / "CATALOG_AVAILABILITY.json", catalog_gate(catalog, schema, optional))
        identity = client.fmu_identity()
        require(identity["sha256"] == g218.FMU_SHA, "Deployed pinned FMU differs")
        save_new(path / "DEPLOYED_FMU_IDENTITY.json", identity)
        current = initialize_run(client, run)
        observed_at, prior = time.monotonic(), client.last_receipt_order
        observation_gate(current, window.start, catalog)
        initial_native(current)
        check_signals(current, False)
        endpoints.append(current)
        client.request("PUT", "step", {"step": STEP})
        client.request("GET", "step")
        scenario = client.request("GET", "scenario")
        require(scenario.get("electricity_price") == "constant" and all(scenario.get(k) is None for k in
                ("time_period", "seed", "solar_uncertainty", "temperature_uncertainty")), "Unexpected scenario forcing")
        save_new(path / "SCENARIO.json", scenario)
        warmup = client.request("PUT", "results", dict(point_names=[COOL, FAN, HEAT, *FLAGS],
                                start_time=run["warmup_start"], final_time=window.start))
        warmup_gate(warmup, window.start)
        require(set(range(run["warmup_start"], window.start+1, 30)) <= set(warmup["time"]), "Incomplete warmup")
        save_new(path / "NATIVE_WARMUP_HISTORY.json", warmup)
        if reference is not None:
            require(scenario == read(reference / "SCENARIO.json"), "Matched scenario forcing differs")
            compare(warmup, read(reference / "NATIVE_WARMUP_HISTORY.json"), "Matched native warmup")
            expected_endpoints = read(reference / "endpoints.json")
            compare(current, expected_endpoints[0], "Matched initialized endpoint")
        previous = current
        with (path / "steps.jsonl").open("x", encoding="utf-8") as steps:
            for i, origin in enumerate(range(window.start, window.end, STEP)):
                forecast = client.request("PUT", "forecast", dict(point_names=[*schema["core_forecasts"], *optional],
                                          horizon=1800, interval=STEP))
                issued = client.last_receipt_order
                forecast_gate(forecast, origin, schema, optional)
                if reference is not None:
                    same_issued = read(reference / f"forecast_{i:04d}.json")
                    require(same_issued["issued_at_sim"] == origin, "Matched forecast clock differs")
                    compare(forecast, same_issued["data"], "Matched as-issued forcing")
                save_new(path / f"forecast_{i:04d}.json", dict(issued_at_sim=origin, received_order=issued, data=forecast))
                boundary = dict(time=origin, **{k: forecast[k][0] for k in POINTS})
                check_signals(current, active, client.supply_k)
                age = time.monotonic() - observed_at
                command_guard(native_command(), {**current, FAN_FLAG: 0, SUPPLY_FLAG: 0}, boundary, origin, age)
                require(0 < prior < issued, "Stale or out-of-order receipt")
                cutoff = journal.emit("origin_cutoff", sim_time=origin, observation_receipt=prior, forecast_receipt=issued)
                if reference is not None and origin == window.hold_start:
                    require(committed == 6, "The shared native prefix did not complete")
                    proof = dict(origin=origin, prefix_advances=committed, initial_and_prefix_endpoints=len(endpoints),
                                 warmup_samples=len(warmup["time"]), source=reference.name, cutoff=cutoff)
                    save_new(path / "MATCH_BEFORE_FAN_COMMAND.json", proof)
                    journal.emit("match_before_fan_command", **proof)
                selected, reason = choose_fan(run, origin, current, previous, boundary, forecast[OCC][1], latched_out, window=window)
                if selected and joint_candidate is not None and origin == window.hold_start:
                    try:
                        candidate = joint_candidate(current)
                    except ContractError as error:
                        selected, reason = False, "joint_supply_entry_veto"
                        journal.emit("joint_supply_veto", origin=origin, cutoff=cutoff, reason=str(error))
                    else:
                        client.freeze_supply(candidate["supply_command_k"])
                        proof = dict(candidate, origin=origin, observation_receipt=prior, cutoff=cutoff)
                        save_new(path / "JOINT_SUPPLY_FREEZE.json", proof)
                        journal.emit("joint_supply_freeze", **proof)
                if reason.endswith("veto") or reason == "fan_start_outside_recorded_operating_point":
                    latched_out = True
                    vetoes.append(dict(origin=origin, reason=reason))
                command = client.treatment_command() if selected else native_command()
                journal.emit("controller_decision", origin=origin, command=command, reason=reason, cutoff=cutoff)
                require(time.monotonic() - observed_at <= 30, "Observation became stale before fan actuation")
                following = client.request("POST", "advance", command)
                observed_at, response = time.monotonic(), client.last_receipt_order
                end = origin + STEP
                observation_gate(following, end, catalog)
                validate_readback(command, following, native_upper=297.15)
                check_signals(following, selected, client.supply_k)
                next_boundary = dict(time=end, issued_at=origin, lower_k=forecast[LOW][1], upper_k=forecast[UP][1], occupancy=forecast[OCC][1])
                verified = endpoint(origin, native_command(), {**following, FAN_FLAG: 0, SUPPLY_FLAG: 0}, next_boundary,
                                    dict(observation=prior, forecast=issued, cutoff=cutoff, response=response), age)
                require(verified.status == "VERIFIED_REFERENCE", "Campaign unexpectedly entered a thermostat event")
                if selected:
                    require(abs(following[FLOW] - NOMINAL_KG_S * CAP) <= FLOW_TOLERANCE, "Fan command did not deliver the measured airflow")
                chunk = client.request("PUT", "results", dict(point_names=list(POINTS_30S), start_time=origin, final_time=end))
                verified_history(chunk, origin, end, selected, active, client.supply_k)
                if joint_candidate is not None and selected and min(chunk[TEMP]) < MINIMUM_ENTRY_K:
                    latched_out = True
                    vetoes.append(dict(origin=end, reason="joint_history_low_temperature_guard"))
                if selected and (max(chunk[TEMP]) >= TRIAL_HOT_K or max(chunk[HEAT]) > COMFORT_TOLERANCE):
                    latched_out = True
                    vetoes.append(dict(origin=end, reason="fan_history_temperature_or_heating_guard"))
                if reference is not None and end <= window.hold_start:
                    compare(following, expected_endpoints[i+1], "Matched native-prefix endpoint")
                    compare(chunk, read(reference / f"native_chunk_{i:04d}.json"), "Matched 30-second native prefix")
                append_native(combined, chunk, origin, end)
                save_new(path / f"native_chunk_{i:04d}.json", chunk)
                steps.write(json.dumps(dict(start=origin, end=end, reason=reason, command=command, cutoff=cutoff,
                                            response_receipt=response, fan_active=selected,
                                            measured_flow_kg_s=following[FLOW]), allow_nan=False) + "\n")
                steps.flush()
                fan_intervals += int(selected)
                committed += 1
                endpoints.append(following)
                previous, current, prior, active = current, following, response, selected
        require(committed == window.advances and not any(current[f] for f in FLAGS), "Missing verified final native state")
        whole = client.request("PUT", "results", dict(point_names=list(POINTS_30S), start_time=window.start, final_time=window.end))
        zeros = [0] * len(whole["time"])
        thermostat_history = {**whole, FAN_FLAG: zeros}
        if joint_candidate is not None:
            thermostat_history[SUPPLY_FLAG] = zeros
        history(thermostat_history, window.start, window.end)
        require(combined == {k: whole[k] for k in combined}, "Native chunks differ from whole electrical history")
        kpis = client.request("GET", "kpi")
        save_new(path / "official_kpis.json", kpis)
        save_new(path / "energy_audit.json", energy_audit(whole, window.start, window.end, kpis, spec["policy"]))
        save_new(path / "endpoints.json", endpoints)
        save_new(path / "whole_native_results.json", whole)
        status["classification"] = "PASS_VALID_RAW"
    except (Exception, KeyboardInterrupt) as error:
        status["error"] = f"{type(error).__name__}: {error}"
        journal.emit("run_failed", error=status["error"], automatic_retry=False)
    finally:
        if client is not None and client.deploy_attempts:
            try:
                result = client.stop()
                require(result.get("acknowledgement") == "OK" and result.get("instance_removed") is True, "Instance cleanup unconfirmed")
                status.update(cleanup="STOP_ACK_AND_REMOVAL_VERIFIED", cleanup_evidence=result)
            except Exception as error:
                status.update(classification="FAILED", cleanup="STOP_UNCONFIRMED", cleanup_error=str(error))
        status.update(verified_advances=committed, advance_attempts=client.advance_attempts if client else 0,
                      realized_fan_advances=fan_intervals, vetoes=vetoes)
        journal.emit("attempt_closed", classification=status["classification"], cleanup=status["cleanup"])
        save_new(path / "RUN_COMPLETED.json", status)
    return status


def score_pair(a, b, *, fabricated, window=ORIGINAL_WINDOW):
    paths = (a, b)
    completion = [read(p / "RUN_COMPLETED.json") for p in paths]
    require(all(s["fabricated"] is fabricated and s["classification"] == "PASS_VALID_RAW"
                and s["cleanup"] == "STOP_ACK_AND_REMOVAL_VERIFIED" and s["advance_attempts"] == s["verified_advances"] == window.advances
                for s in completion), "Both matched arms must be complete and genuine for a measured result")
    proof = read(b / "MATCH_BEFORE_FAN_COMMAND.json")
    require(proof["source"] == a.name and proof["prefix_advances"] == 6 and proof["origin"] == window.hold_start,
            "Treatment lacks matched native prefix evidence")
    for path in paths:
        chain(path / "receipt_order.jsonl")
    journal = rows(b / "receipt_order.jsonl")
    gate = [r for r in journal if r["kind"] == "match_before_fan_command"]
    advances = [r for r in journal if r["kind"] == "api_request" and r["endpoint"] == "advance"]
    require(len(gate) == 1 and len(advances) == window.advances and proof["cutoff"] < gate[0]["order"] < advances[6]["order"],
            "Native prefix must match before the first treatment advance")
    native, fan = (read(p / "whole_native_results.json") for p in paths)
    compare({k: native[k] for k in ("time", OUTDOOR, SOLAR)}, {k: fan[k] for k in ("time", OUTDOOR, SOLAR)}, "Matched measured weather")
    require(not any(native[FAN_FLAG]), "Baseline contains a fan override")
    schedule = ComfortSchedule.from_fmu()
    windows = {}
    for name, lo, hi in (("intervention", window.hold_start, window.hold_end), ("recovery", window.hold_end, window.end),
                         ("intervention_and_recovery", window.hold_start, window.end), ("full", window.start, window.end)):
        base, trial = (score_window(arm, schedule, lo, hi) for arm in (native, fan))
        for result, arm in ((base, native), (trial, fan)):
            result["mean_indoor_c"] = integrate(arm["time"], arm[TEMP], lo, hi) / (hi - lo) - 273.15
        savings = base["electricity_kwh"] - trial["electricity_kwh"]
        windows[name] = dict(native=base, fan=trial, net_savings_kwh=savings,
                             fan_savings_kwh=base["fan_kwh"]-trial["fan_kwh"],
                             added_cooling_kwh=trial["cooling_kwh"]-base["cooling_kwh"],
                             added_official_kh=trial["official_replayed_kh"]-base["official_replayed_kh"],
                             added_project_kh=trial["project_replayed_kh"]-base["project_replayed_kh"],
                             saved_percent=100 * savings / base["electricity_kwh"] if base["electricity_kwh"] else None)
    reported = [read(p / "official_kpis.json")["tdis_tot"] for p in paths]
    for mode, observed in zip(("native", "fan"), reported, strict=True):
        score = windows["full"][mode]
        require(abs(score["official_replayed_kh"]-observed) <= 1e-8, "Official discomfort replay disagrees with API")
        score["official_reported_kh"] = observed
    resolution = sum(read(p / "energy_audit.json")["official_tolerance_j"] for p in paths) / 3600000
    recovery = _recovery_mark(native, fan, window.hold_end)
    baseline, treatment = (windows["full"][k] for k in ("native", "fan"))
    heating_delta = (integrate(fan["time"], fan[HEAT], window.hold_start, window.end)
                     - integrate(native["time"], native[HEAT], window.hold_start, window.end)) / 3600000
    delivered = [r for r in rows(b / "steps.jsonl") if r["fan_active"]]
    baseline_flow = [v for t, v in zip(native["time"], native[FLOW], strict=True) if window.hold_start < t <= window.hold_end]
    criteria = dict(full_verified_dose=len(delivered) == 6 and not completion[1]["vetoes"],
                    measured_airflow_reduced=bool(delivered and min(baseline_flow) > max(r["measured_flow_kg_s"] for r in delivered)),
                    net_saving_above_reconciliation_bound=windows["intervention_and_recovery"]["net_savings_kwh"] > resolution and
                                                          windows["full"]["net_savings_kwh"] > resolution,
                    no_added_project_discomfort=treatment["project_replayed_kh"] <= baseline["project_replayed_kh"] + COMFORT_TOLERANCE
                    and treatment["occupied_project_violation_minutes"] <= baseline["occupied_project_violation_minutes"],
                    no_project_excursion=windows["intervention_and_recovery"]["fan"]["occupied_project_peak_excursion_k"] <= COMFORT_TOLERANCE,
                    guard_respected=windows["intervention"]["fan"]["maximum_indoor_c"] < TRIAL_HOT_K-273.15,
                    observed_recovery=recovery is not None, no_extra_heating=heating_delta <= resolution)
    return dict(technical_validation="PASS", fabricated=fabricated, windows=windows, criteria=criteria,
                provisional_fan_result=all(criteria.values()) if not fabricated else None, optimizer_enabled=False,
                recovery_marker_min=recovery, reconciliation_bound_kwh=resolution, added_heating_input_kwh=heating_delta,
                intervention_readbacks=delivered, verified_native_release=not bool(fan[FAN_FLAG][-1]), vetoes=completion[1]["vetoes"])


def check_new_native_reference(path, treatment, window=ORIGINAL_WINDOW):
    """Skip the experimental arm if the fresh native arm misses the predeclared entry envelope."""
    endpoints = {row["time"]: row for row in read(path / "endpoints.json")}
    i = (window.hold_start - min(endpoints)) // STEP
    issued = read(path / f"forecast_{i:04d}.json")
    require(issued["issued_at_sim"] == window.hold_start, "Native reference forecast origin differs")
    forecast = issued["data"]
    boundary = {p: forecast[p][0] for p in POINTS}
    ready, reason = choose_fan(treatment, window.hold_start, endpoints[window.hold_start], endpoints[window.hold_start-STEP],
                               boundary, forecast[OCC][1], False, window=window)
    require(ready, f"Fresh native reference did not qualify for the fan treatment. {reason}")


def execute(authorization):
    return execute_campaign(authorization, definition, binding, STATUS, STATE, screen_archive)


def execute_campaign(authorization, describe, bind, authorization_status, state, screen, *,
                     joint_candidate=None, pair_score=score_pair):
    scope = bind()
    expected = dict(scope, status=authorization_status)
    content = Path(authorization).read_bytes()
    received = json.loads(content.decode("utf-8-sig"))
    require(received.keys() == expected.keys() | {"approval_text"} and all(received[k] == v for k, v in expected.items()),
            "Authorization must bind this exact two-arm fan trial")
    require(isinstance(received["approval_text"], str) and received["approval_text"].strip()
            and received["approval_text"].strip().casefold() not in {"pending", "draft", "no"}, "Affirmative authorization text is required")
    require(not state.exists(), "Existing fan trial ledger: no resume or retry")
    require(sha(g218.FMU) == g218.FMU_SHA, "Pinned FMU has changed")
    spec, archive = describe(), screen()
    require((joint_candidate is not None) == ("joint_policy" in spec), "Campaign and joint policy must be bound together")
    window = declared_window(spec)
    campaign = spec["campaign"]
    require(scope["campaign_sha256"] == digest(spec) and scope["campaign"] == campaign,
            "Bound fan campaign differs from execution configuration")
    from hvac_control_expansion_b2g_v1.launcher import real_factory
    from stage4e_d1_v2.runtime import verify_runtime

    runtime = verify_runtime()
    require(runtime["classification"] == "PASS" and bind() == scope, "Pinned runtime or bound files changed")
    state.parent.mkdir(exist_ok=True)
    slots = [dict(run_id=r["run_id"], group_id=r["group_id"], partition="development", category="development",
                  status="UNUSED_NOT_AUTHORIZED", run_sha256=digest(r)) for r in spec["runs"]]
    registry = Registry.create(state, dict(campaign=campaign, slots=slots))
    batch = registry.new_batch(campaign, spec["runs"], dict(scope, authorization_sha256=sha256(content).hexdigest(),
                                                          runtime=runtime, archive_window=archive))
    label = "JOINT" if joint_candidate is not None else "FAN"
    save_new(batch / f"{label}_CONFIGURATION.json", spec)
    paths = []
    try:
        for run in spec["runs"]:
            rid = run["run_id"]
            path = registry.reserve(campaign, run)
            status = collect(spec, run, path, real_factory, paths[0] if paths else None, joint_candidate=joint_candidate)
            seal = batch / f"{rid}_SEALED_MANIFEST.json"
            save_new(seal, dict(run_id=rid, files=inventory(path), training_release=False))
            ok = status["classification"] == "PASS_VALID_RAW"
            registry.finish(rid, "CONSUMED_COMPLETED" if ok else "CONSUMED_FAILED", dict(seal_sha256=sha(seal), raw_result=status))
            registry.verify_evidence()
            require(ok, f"Arm {run['arm']} failed. {status.get('error', status['cleanup'])}")
            paths.append(path)
            if run["arm"] == "A":
                check_new_native_reference(path, spec["runs"][1], window)
        result = pair_score(*paths, fabricated=False, window=window)
    except (Exception, KeyboardInterrupt) as error:
        result = dict(technical_validation="FAIL", automatic_retries=False, error=str(error))
    save_new(batch / f"{label}_COMPARISON.json", result)
    save_new(batch / "BATCH_ARTIFACT_MANIFEST.json", dict(files=inventory(batch)))
    registry.verify_evidence()
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    arguments = parser.add_mutually_exclusive_group(required=True)
    arguments.add_argument("--describe", action="store_true")
    arguments.add_argument("--execute", type=Path, metavar="EXACT_AUTHORIZATION")
    args = parser.parse_args()
    try:
        result = (dict(definition=definition(), binding=binding(), authorization_status=STATUS,
                       ledger_exists=STATE.exists(), archived_window=screen_archive()) if args.describe else execute(args.execute))
    except (OSError, KeyError, ValueError) as error:
        parser.error(str(error))
    print(json.dumps(result, indent=2, allow_nan=False))
    if result.get("technical_validation") == "FAIL":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
