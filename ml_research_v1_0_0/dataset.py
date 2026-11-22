"""Build the B3 feature overlay from hash-bound development evidence."""
import csv
import hashlib
import json
import math
import sys
from collections import Counter
from pathlib import Path

import numpy as np

OUT = Path(__file__).resolve().parent
ROOT = OUT.parent
PILOT = ROOT / "SDP_BOPTEST_Pilot"
BASE = ROOT / "experiments/five_model_hvac16_v1_0_0"
V2 = ROOT / "experiments/hvac_16_outputs_v2_0_0"
B3 = PILOT / "action_conditioned_ml_b3_v1"
PUBLIC = PILOT / "stage4e_d2_public/PUBLIC_DEVELOPMENT_VALIDATION_v1_0_0"
H1 = PILOT / "stage4e_d2_h1/SDP_COMPACT_TEAM_HANDOFF_v1_0_0"
sys.path[1:1] = [str(BASE), str(PILOT)]
from config import FEATURES, TARGETS, HORIZONS, QUANTITIES
from action_conditioned_ml_b3_v1.audit import b1_sources, original_sources
from stage4e_d0.plan import Safety, configuration, FLAGS, FLAG, SET, TEMP, COOL, FAN, HEAT
from stage4e_d1_v2.validation import REFERENCE

COMMITTED = ("cooling_override_committed", "cooling_setpoint_change_committed_k")
ACTION = ("a__cooling_delta_from_native_k", "a__activation_offset_s",
          "a__release_offset_s", "c__cooling_veto_latched_before_t")
STATE = tuple(f for f in FEATURES if f not in COMMITTED)
CONTRACTS = {"O25": tuple(FEATURES), "A29": (*FEATURES, *ACTION),
             "S23": STATE, "P27": (*STATE, *ACTION)}
ALL = CONTRACTS["A29"]

def check(condition, message):
    if not condition:
        raise ValueError(message)

def sha(path):
    with path.open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()

def read(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))

def save(path, data):
    path.write_text(json.dumps(data, indent=2, allow_nan=False) + "\n", encoding="utf-8")

def csv_rows(path):
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))

def csv_write(path, rows):
    rows = list(rows)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

def plan_encode(origin, activate=None, release=None, target_k=None, latch=0):
    """Encode one nominal block using only the clock, native schedule and prior latch."""
    check(type(origin) is int and origin >= 0 and origin % 300 == 0, "Invalid origin grid")
    check(type(latch) is int and latch in (0, 1), "Known binary prior latch required")
    if activate is None and release is None and target_k is None:
        check(latch == 0, "Native plan cannot carry a prior latch")
        return (0., 0, 0, 0)
    check(type(activate) is int and type(release) is int and 0 <= activate < release
          and activate % 300 == release % 300 == 0, "Ordered activation/release grid required")
    check(type(target_k) in (int, float) and math.isfinite(target_k), "Missing cooling target")
    left, right = max(origin, activate), min(origin + 1800, release)
    check(latch == 0 or activate < origin < release, "Prior latch belongs to an ongoing block")
    if left >= right:
        return (0., 0, 0, 0)
    delta = round(float(target_k) - REFERENCE.pair(left)[1], 9)
    check(delta in (-.25, -.50) and target_k <= 297.15, "Unsupported cooling target")
    check(all(abs(target_k - REFERENCE.pair(t)[1] - delta) < 1e-8
              for t in range(left, right, 300)), "Native setpoint transition inside active block")
    return (delta, left-origin, right-origin, latch)

def saved_encode(path, origin, latch):
    check(len(path) == 6, "Expected six nominal slots")
    for i, slot in enumerate(path):
        check(slot["start"] == origin + 300*i and slot["end"] == origin + 300*(i+1)
              and slot["source"] == "frozen_nominal_plan" and slot["known_at_sim"] <= origin
              and all(slot["command"][k] == 0 for k in FLAGS if k != FLAG),
              "Unexpected plan knowledge, grid or control")
    active = [i for i, slot in enumerate(path) if slot["command"][FLAG]]
    if not active:
        return plan_encode(origin)
    first, last = active[0], active[-1]
    target = path[first]["command"][SET]
    check(active == list(range(first, last+1)) and all(
        path[i]["command"][SET] == target and path[i]["block_id"] == path[first]["block_id"]
        for i in active), "Unsupported multiple/changing blocks")
    start = origin - 300 if latch else path[first]["start"]
    return plan_encode(origin, start, path[last]["end"], target, latch)

def state_features(t, endpoints, interval_means, forecast):
    """Use observed endpoint mappings, past completed interval means, and one issued vintage."""
    now = endpoints[t]
    phase = 2*math.pi*(t % 86400)/86400
    result = {
        "indoor_temp_c": now[TEMP]-273.15,
        "indoor_temp_5min_ago_c": endpoints[t-300][TEMP]-273.15,
        "indoor_temp_30min_ago_c": endpoints[t-1800][TEMP]-273.15,
        "outdoor_temp_c": now["zon_weaSta_reaWeaTDryBul_y"]-273.15,
        "solar_irradiance_w_m2": now["zon_weaSta_reaWeaHGloHor_y"],
        "cooling_setpoint_current_c": now[SET]-273.15,
        "heating_setpoint_current_c": now["con_oveTSetHea_u"]-273.15,
        "cooling_override_current": now[FLAG],
        "occupancy_now": forecast["Occupancy[1]"][0],
        "occupancy_forecast_30min": forecast["Occupancy[1]"][6],
        "outdoor_temp_forecast_30min_k": forecast["TDryBul"][6],
        "solar_forecast_30min_w_m2": forecast["HGloHor"][6],
        "time_of_day_sin": math.sin(phase),
        "time_of_day_cos": math.cos(phase),
    }
    for suffix, lag in zip(("last_5min", "previous_5min", "30min_ago"), (0, 300, 1800)):
        for quantity, value in zip(QUANTITIES[1:], interval_means[t-lag]):
            result[f"{quantity}_{suffix}_kw"] = value
    return result

def interval_history(native):
    raw_times = np.asarray(native["time"], dtype=float)
    check(raw_times.ndim == 1 and np.isfinite(raw_times).all() and np.all(raw_times % 30 == 0),
          "Native times must be finite 30-second ticks")
    times = raw_times.astype(np.int64)
    check(len(times) >= 11 and times[0] % 300 == 0 and times[-1] % 300 == 0
          and np.all(np.diff(times) == 30), "Qualified 30-second history grid required")
    values = np.column_stack([native[ch] for ch in (COOL, FAN, HEAT)])
    check(values.shape == (len(times), 3) and np.isfinite(values).all(), "Incomplete native signal history")
    areas = .5 * (values[:-1] + values[1:]) * 30
    means = areas.reshape(-1, 10, 3).sum(axis=1) / 300000
    means[:, 2] *= .9
    return dict(zip(times[10::10], means))

def commit_features(t, applied):
    return dict(zip(COMMITTED, (applied[FLAG],
                applied[SET] - REFERENCE.pair(t)[1] if applied[FLAG] else 0.)))

def nominal_boundaries(steps):
    active = np.array([s["proposed_command"][FLAG] for s in steps], dtype=bool)
    changes = np.diff(np.r_[False, active, False].astype(int))
    start = steps[0]["start"]
    return active, start+300*np.flatnonzero(changes == 1), start+300*np.flatnonzero(changes == -1)

def build():
    audit = read(B3 / "AUDIT_RESULTS.json")
    frozen = {**read(B3 / "AUDIT_SOURCE_HASHES.json"), **read(B3 / "B3_SOURCE_HASHES.json")}
    used = {}

    def verified(path):
        path = path.resolve()
        expected = frozen.get(str(path))
        if expected is None:
            expected = frozen.get(path.as_posix())
        actual = sha(path)
        check(expected == actual, f"Source absent from B3 audit or changed: {path}")
        used[path.relative_to(ROOT).as_posix()] = actual
        return path

    base_rows = csv_rows(verified(V2 / "dataset/ml_development_16_outputs.csv"))
    check(all(row["partition"] == "development" for row in base_rows), "Only development allowed")
    original = {row["row_id"]: row for row in base_rows}
    seasons = {row["group_id"]: row["season"] for row in base_rows}
    folds = read(verified(BASE / "run_01/outer_folds.json"))
    check(folds == read(verified(V2 / "evaluation_01/folds.json")), "Fold drift")
    fold_for = {g:f["fold"] for f in folds for g in f["held_groups"]}
    order = []
    xyz = {}
    summaries = []
    max_x = max_y = 0.
    for meta, cfg, source in original_sources() + b1_sources():
        rid = meta["run_id"]
        group = meta["group_id"]
        policies = {"native":"N", "scheduled_variation":"X"}
        policy = policies.get(meta["policy"], meta["policy"])
        check(meta["partition"] == "development" and cfg["partition"] == "development", "Protected run")
        record = next(r for r in audit["runs"] if r["run_id"] == rid)
        raw_manifest = verified(source / "ARTIFACT_MANIFEST.json")
        check(sha(raw_manifest) == record["source_manifest_sha256"], "Raw manifest drift")
        ends = {e["time"]:e for e in read(verified(source / "endpoints.json"))}
        hist = interval_history(read(verified(source / "whole_native_results.json")))
        steps = [json.loads(line) for line in verified(source / "steps.jsonl").read_text().splitlines()]
        receipt_path = verified(source / "receipt_order.jsonl")
        cutoffs = {}
        for line in receipt_path.read_text().splitlines():
            receipt = json.loads(line)
            if "observation_age_s" in receipt:
                cutoffs[receipt["order"]] = receipt["observation_age_s"]
        safety = Safety(configuration())
        proposed, activations, releases = nominal_boundaries(steps)
        n = 0
        for i, step in enumerate(steps):
            t = step["start"]
            path = step["proposed_path"]
            block = path[0]["block_id"]
            latch = int(safety.vetoed and safety.block == block and block is not None)
            if record["first_eligible"] <= t <= record["last_eligible"]:
                forecast = read(verified(source / f"forecast_{i:04d}.json"))
                check(forecast["issued_at_sim"] == t and forecast["received_order"] == step["forecast_received_order"]
                      and step["observation_received_order"] < forecast["received_order"] < step["origin_cutoff_order"],
                      "Origin receipt mismatch")
                state = state_features(t, ends, hist, forecast["data"])
                feat = {**state, **commit_features(t, step["applied_command"]),
                        **dict(zip(ACTION, saved_encode(path, t, latch)))}
                features = np.array([feat[f] for f in ALL])
                horizons = [t + 60*h for h in HORIZONS]
                target = np.r_[[ends[h][TEMP]-273.15 for h in horizons],
                               np.array([hist[h] for h in horizons]).T.ravel()]
                orig_id = f"{rid}:{t}"
                if policy in ("N", "X"):
                    ref = original[orig_id]
                    xref = np.array([float(ref[k]) for k in FEATURES])
                    yref = np.array([float(ref[k]) for k in TARGETS])
                    max_x = max(max_x, float(np.max(abs(features[:25]-xref))))
                    max_y = max(max_y, float(np.max(abs(target-yref))))
                    np.testing.assert_allclose(features[:25], xref, rtol=0, atol=1e-10)
                    np.testing.assert_allclose(target, yref, rtol=0, atol=1e-10)
                    features[:25], target = xref, yref
                clock = t % 86400
                recovery = any(r <= t < r+7200 for r in releases)
                native_event = any(t-300 <= t-clock+k <= t+1800 for k in (28800,64800))
                scheduled_native = not (features[ALL.index(ACTION[2])] or recovery or native_event)
                aux = [t, fold_for[group], int(proposed[i]), int(step["applied_command"][FLAG]),
                       int(recovery), int(t in releases), int(t in activations), int(native_event),
                       int(scheduled_native), int(scheduled_native and abs(features[0]-features[1]) < .1),
                       next((int(r-t) for r in releases if t <= r < t+1800), -1),
                       next((int(a-t) for a in activations if t <= a < t+1800), -1),
                       int(step["origin_cutoff_order"]), cfg["start"]]
                check(orig_id not in xyz, "Duplicate origin")
                xyz[orig_id] = (features, target, (orig_id, rid, group, seasons[group], policy), aux)
                if policy not in ("N","X"):
                    order.append(orig_id)
                n += 1
            command, reason = safety.decide(path[0], step["current_observation"],
                                            step["current_boundary"], cutoffs[step["origin_cutoff_order"]])
            check(command == step["applied_command"] and reason == step["reason"].split(";")[0],
                  "Frozen safety replay mismatch")
        check(n == 852, "Unexpected origin count")
        summaries.append(dict(run_id=rid, group=group, policy=policy, season=seasons[group],
                              starts=cfg["start"], ends=cfg["end"], held_fold=fold_for[group],
                              raw_manifest_sha256=record["source_manifest_sha256"],
                              source=source.relative_to(ROOT).as_posix(), origins=n,
                              eligibility=record["status"]))
        print(f"Adapter verified {rid} ({n} origins)", flush=True)
    keys = [r["row_id"] for r in base_rows] + order
    check(len(keys) == len(set(keys)) == 18744 == len(xyz), "Overlay identity count")
    x,y,ids,aux = zip(*(xyz[i] for i in keys))
    out = OUT / "development_overlay.npz"
    np.savez_compressed(out, X=x, Y=y, ids=ids, aux=aux, features=ALL, targets=TARGETS,
                        id_columns=("row_id","run_id","group","season","policy"),
                        aux_columns=("time","fold","active_nominal","active_delivered","recovery",
                                     "release_origin","activation_origin","native_event","scheduled_native",
                                     "stable_native","next_release_offset","next_activation_offset",
                                     "origin_cutoff_order","scored_start"))
    check(np.isfinite(x).all() and np.isfinite(y).all(), "Nonfinite matrix")
    mdiv = verified(PILOT / "hvac_control_expansion_v1/MATCHED_SIZE_TIMESTAMP_PLAN.json")
    save(OUT / "DATASET_PROVENANCE.json", {
        "overlay_sha256":sha(out), "development_original":13632, "B1_alternatives":3408,
        "B1_NREF_QA_only":1704, "Mdiv_seed":20261118, "Mdiv_plan_sha256":sha(mdiv),
        "max_D2_raw_common25_difference":max_x, "max_D2_raw_target_difference":max_y,
        "runs":summaries, "files":used, "validation_outcome_reads":0,
    })

if __name__ == "__main__":
    build()



