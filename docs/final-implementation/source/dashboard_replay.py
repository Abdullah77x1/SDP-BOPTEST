"""Play and verify the sealed day-196 recordings through the dashboard tracker."""

import argparse
import json
from collections import Counter
from math import isclose
from pathlib import Path
from threading import Lock

import numpy as np

from autonomous_hvac_stage1.evaluation import ComfortSchedule, score_window
from stage4e_d0.plan import FLAG, FLAGS, SET, STEP, validate_readback
from stage4e_d1_v2.validation import REFERENCE

from . import archive_dataset as archive, forecast_comparison as comparison
from .dashboard_forecast import DATASET, SELECTION, FrozenForecast, QUANTITIES
from .interface import check_metadata, interval_energy
from .native_twin import ForecastTracking, command_status, display

TYPES = {"native": "D2_G196_N", "override": "STEP3C_D2_G196_WARM45"}
REFERENCE_TOLERANCE = 1e-10
KPI_TOLERANCE = 1e-8


class ArchivedReplay:
    def __init__(self, kind):
        self.kind = kind
        self.engine = FrozenForecast()
        self.schedule = ComfortSchedule.from_fmu()
        self.lock = Lock()
        manifest = archive.json_file(DATASET / "manifest.json")
        self.run, = (run for run in manifest["run_sources"] if run["run_id"] == TYPES[kind])
        pilot = archive.REPO.parent / "SDP_BOPTEST_Pilot"
        self.read, self.endpoints, self.history = archive.source_traces(pilot, self.run)
        check_metadata(json.loads(self.read("runtime_metadata.json")))
        self.start, self.stop = self.run["start"], self.run["end"]
        self.steps = [json.loads(raw) for raw in self.read("steps.jsonl").splitlines()]
        self.receipts = {event["order"]: event for event in
                         map(json.loads, self.read("receipt_order.jsonl").splitlines())}
        self.blocks = tuple(archive.scheduled_blocks({
            **self.run, "schedule": archive.WARM_SCHEDULE if kind == "override" else ()
        }).values())
        archive.require(list(self.endpoints) == list(range(self.start, self.stop+1, STEP)) and
                        self.history["time"] == list(range(self.start, self.stop+1, 30)) and
                        [s["start"] for s in self.steps] == list(range(self.start, self.stop, STEP)),
                        "Sealed replay does not cover the full recorded time grid")
        self.reset()

    def reset(self):
        self.tracking = ForecastTracking(self.engine)
        self.index, self.official = 0, 0.0
        self.vetoes, self.latest, self.release, self.events = set(), None, None, []
        self.observe()

    @property
    def now(self):
        return self.start + STEP*self.index

    def known_plan(self):
        return next((block for block in self.blocks if self.now < block[1]), None)

    def observe(self):
        origin = self.now
        issued = None
        if origin < self.stop:
            step = self.steps[self.index]
            issued = json.loads(self.read(f"forecast_{self.index:04d}.json"))
            issue_receipt = self.receipts[issued["received_order"]]
            observed = 0
            if self.index:
                prior = self.steps[self.index-1]
                observed = prior.get("endpoint_received_order") or prior["response_receipt"]
            archive.require(issue_receipt["kind"] == "api_received" and issue_receipt["endpoint"] == "forecast"
                            and observed < issue_receipt["order"] < step["origin_cutoff_order"]
                            and issued["issued_at_sim"] == origin, "Archived forecast is outside its origin cutoff")
        block = self.known_plan()
        self.tracking.observe(self.endpoints[origin], issued, block, bool(block and block[0] in self.vetoes),
                              finished=origin == self.stop)

    def advance(self):
        origin, end = self.now, self.now+STEP
        if end > self.stop:
            raise ValueError("Replay reached its recorded endpoint")
        offset = self.index * (STEP//30)
        chunk = {key: series[offset:offset+11] for key, series in self.history.items()}
        step = self.steps[self.index]
        receipt = step.get("endpoint_received_order") or step["response_receipt"]
        request, response = self.receipts[receipt-1], self.receipts[receipt]
        archive.require(step["end"] == end and step["origin_cutoff_order"] < receipt and
                        request["endpoint"] == response["endpoint"] == "advance" and
                        request["kind"] == "api_request" and response["kind"] == "api_received" and
                        request["method"] == response["method"] == "POST", "Recorded advance receipt differs")
        command = request["request"]
        before, after = self.endpoints[origin], self.endpoints[end]
        validate_readback(command, after)
        archive.require(all(all(v == command[f] for v in chunk[f][1:]) for f in FLAGS)
                        and (not command[FLAG] or all(abs(v-command[SET]) <= 1e-5 for v in chunk[SET][1:])),
                        "Recorded detailed readbacks differ from the issued command")
        plan = self.known_plan()
        reason = step["reason"] if "reason" in step else step["decision"]["reason"]
        self.latest = command_status(origin, command, before, after, reason)
        if plan and plan[0] <= origin < plan[1] and not after[FLAG]:
            self.vetoes.add(plan[0])
        if self.latest["verified_release"]:
            expected_heat, expected_cool = REFERENCE.pair(end)
            archive.require(all(isclose(x, y, abs_tol=1e-5, rel_tol=0) for x, y in
                                ((after[archive.HEAT_SET], expected_heat), (after[SET], expected_cool))),
                            "Archived thermostat did not return to native")
            self.release = self.latest
        if self.latest["verified_release"] or after[FLAG] or (plan and plan[0] <= origin < plan[1]):
            self.events.append(self.latest)
        energy = interval_energy(chunk, origin, end)
        feedback = self.tracking.settle(after, chunk, energy)
        self.official += score_window(chunk, self.schedule, origin, end)["official_replayed_kh"]
        self.index += 1
        self.observe()
        return feedback

    def submit(self, message):
        with self.lock:
            if message == {"action": "step"}:
                self.advance()
            elif (message.get("action") == "seek" and type(message.get("cursor")) is int
                  and 1 <= message["cursor"] <= len(self.steps)+1):
                target = message["cursor"]-1
                if target < self.index:
                    self.reset()
                while self.index < target:
                    self.advance()
            else:
                raise ValueError("Archived replay is read-only. Use recorded steps or seek.")
            return {"replay_only": True}

    def snapshot(self):
        with self.lock:
            tracking = self.tracking
            return display(self.endpoints[self.now], self.schedule, tracking.totals, self.official,
                           tracking.forecasts[self.now], list(tracking.feedback.values()),
                           list(tracking.observations.values())[-37:], mode=f"archive-{self.kind}",
                           cursor=self.index+1, total=len(self.steps)+1, closed=self.now == self.stop,
                           control_plan=self.known_plan(), command_status=self.latest, release=self.release,
                           can_request=False)


def verify_replay(kind, output=None):
    """Compare chronological dashboard results against sealed features, targets and Step 3D predictions."""
    replay = ArchivedReplay(kind)
    run = replay.run["run_id"]
    _, matrix, actual, origins, _ = comparison.load_data(DATASET, "public_validation")
    expected = {int(row["sim_time_s"]): index for index, row in enumerate(origins) if row["run_id"] == run}
    public = SELECTION / "public_validation"
    audit = comparison.read_json(public / "summary.json")
    prediction_path = public / "predictions.npz"
    archive.require(comparison.file_sha(prediction_path) == audit["file_sha256"]["predictions.npz"] and
                    audit["selected_model_sha256"] == replay.engine.metadata["sha256"],
                    "Public replay reference is not bound to the selected model")
    with np.load(prediction_path, allow_pickle=False) as stored:
        archive.require(stored["row_ids"].tolist() == [row["row_id"] for row in origins] and
                        stored["targets"].tolist() == archive.TARGETS, "Public prediction row or target order differs")
        reference = stored["forest_action"]
    tracks = replay.tracking
    methods, settled, scored = Counter(), Counter(), set()
    errors, trace = [], []
    max_features, max_prediction, max_actual = 0., 0., 0.
    lo = replay.start + 10*3600 + 20*60
    hi = replay.start + 13*3600 + 45*60
    for _ in replay.steps:
        now = replay.now
        forecast = tracks.forecasts[now]
        methods[forecast["source"]] += 1
        if forecast["values"]:
            archive.require([row["target"] for row in forecast["values"]] ==
                            [now+h*60 for h in archive.HORIZONS], "Wrong dashboard target times")
        if now in expected:
            i = expected[now]
            archive.require(forecast["source"] == "Random Forest", "Eligible forest forecast missing")
            feature_error = float(np.max(np.abs(np.asarray(forecast["features"])-matrix[i])))
            generated = [row[key] for key in QUANTITIES for row in forecast["values"]]
            prediction_error = float(np.max(np.abs(np.asarray(generated)-reference[i])))
            max_features, max_prediction = max(max_features, feature_error), max(max_prediction, prediction_error)
        feedback = replay.advance()
        if lo <= now <= hi:
            trace.append(dict(origin=now, forecast=forecast, measured=replay.tracking.actual,
                              command=replay.latest, feedback=feedback))
        for result in feedback:
            settled[result["source"]] += 4
            if result["origin"] in expected:
                lead = archive.HORIZONS.index(result["lead"])
                known_actual = actual[expected[result["origin"]], lead::len(archive.HORIZONS)]
                measured = np.array([result["measured"][key] for key in QUANTITIES])
                max_actual = max(max_actual, float(np.max(np.abs(known_actual-measured))))
                scored.add((result["origin"], result["lead"]))
                errors.append([result["lead"], *[result["errors"][key] for key in (*QUANTITIES, "combined")]])
    archive.require(methods == {"Unavailable": 1, "Persistence fallback": 6, "Random Forest": 857} and
                    len(scored) == len(expected)*len(archive.HORIZONS) and
                    max(max_features, max_prediction, max_actual) <= REFERENCE_TOLERANCE, "Replay differs from reference")
    official = json.loads(replay.read("official_kpis.json"))["tdis_tot"]
    archive.require(abs(replay.official-official) <= KPI_TOLERANCE, "Replayed discomfort differs from BOPTEST")
    archived_energy = json.loads(replay.read("energy_audit.json"))["electrical_kwh"]
    archive.require(isclose(tracks.totals["electricity_kwh"], archived_energy, rel_tol=0, abs_tol=1e-9),
                    "Replayed electricity differs from measured energy audit")
    released = [event for event in replay.events if event["verified_release"]]
    applied = [event for event in replay.events if event["verified_active"]]
    archive.require(len(released) == len(replay.blocks) and len(applied) == len(replay.blocks)*9 and
                    all(e["issued_c"] == 24.5 and e["verified_c"] == 24.5 for e in applied),
                    "Recorded command delivery differs")
    for start, release, _ in replay.blocks:
        archive.require([e["issued_at"] for e in applied if start <= e["issued_at"] < release] ==
                        list(range(start, release, STEP)) and any(
                            e["issued_at"] == release and e["readback_at"] == release+STEP for e in released),
                        "Recorded warmer hold or release clock differs")
    errors = np.asarray(errors)
    skills = {}
    for lead in archive.HORIZONS:
        values = errors[errors[:, 0] == lead, 1:]
        skills[lead] = {name: {"mae": float(np.mean(abs(col))), "rmse": float(np.sqrt(np.mean(col*col)))}
                        for name, col in zip((*QUANTITIES, "combined"), values.T, strict=True)}
    report = dict(recording=kind, start=replay.start, end=replay.stop, advances=len(replay.steps),
                  fully_scored_forest_origins=len(expected), forecast_origins=dict(methods),
                  matured_values=dict(settled), max_feature_difference=max_features,
                  max_prediction_difference=max_prediction, max_measured_difference=max_actual,
                  absolute_errors=skills, measured_energy=tracks.totals, official_discomfort_kh=official,
                  measured_discomfort_kh=replay.official, applied_intervals=len(applied), releases=released,
                  model_sha256=replay.engine.metadata["sha256"])
    if output:
        output.mkdir(parents=True)
        comparison.save_json(output/"summary.json", report)
        comparison.save_json(output/"first-morning-trace.json", trace)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("recording", choices=tuple(TYPES))
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    print(json.dumps(verify_replay(args.recording, args.output), indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
