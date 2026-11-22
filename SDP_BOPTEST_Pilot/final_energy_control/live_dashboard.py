"""Read-only observation of authorized collector evidence and deterministic archive replay."""

import argparse
import base64
from bisect import bisect_right
from collections import deque
import json
from pathlib import Path
import sys
from threading import Lock
import time
from urllib.parse import urlsplit

from autonomous_hvac_stage1.controller import EnergyController
from autonomous_hvac_stage1.evaluation import ComfortSchedule, SAFETY_VETO_REASONS, score_window
from autonomous_hvac_stage1.g218 import CAMPAIGN, STATE
from core import integrate
from dashboard import make_server
from energy_savings_g174_v1.policy import ARCHIVE, ON, RECOVERY
from hvac_control_expansion_b2f_v1.packaging import inventory
from hvac_control_expansion_v1.registry import safe_id
from stage4e_d0.plan import COOL, FAN, FLAG, FLAGS, HEAT, LOW, OCC, SET, STEP, TEMP, UP, native_command
from stage4e_d1r.proposed_validation import HEAT as HEAT_SETPOINT, near
from stage4e_d2i_1.common import ROOT, read

from .policies import candidates

HERE = Path(__file__).resolve().parent
OUTDOOR = "zon_weaSta_reaWeaTDryBul_y"
WARM_BATCH = ROOT / "energy_savings_g174_v1/runtime_state/batches/ESV01_G174_WARM45"
WARM_TRACE = WARM_BATCH / "ESV01_G174_WARM45"
G218_TRACE = ROOT / "stage4e_d2_prep02/runtime_state/batches/PUBLIC_D2_D2_G218_20261115_01/D2_G218_N"
LIVE_BATCH = STATE / "batches" / CAMPAIGN
SMOKE_ROOT = HERE / "live_smoke_evidence"
SMOKE_STALE_SECONDS = 5


def smoke_run(session):
    safe_id(session)
    return SMOKE_ROOT / session / "batches" / session / session


def measured_g218(batch):
    manifest_path = batch / "BATCH_ARTIFACT_MANIFEST.json"
    if not manifest_path.is_file():
        raise ValueError("Measured G218 replay requires a finalized pair. Use --replay shadow for the archived demo.")
    files = inventory(batch)
    files.pop(manifest_path.name)
    if files != read(manifest_path)["files"]:
        raise ValueError("G218 evidence differs from the finalized manifest")
    paired = read(batch / "PAIRED_VALIDATION.json")
    if paired.get("technical_validation") != "PASS" or paired.get("fabricated") is not False:
        raise ValueError("Measured G218 replay requires a technically verified simulation pair")
    return paired


class JsonLinesTail:
    def __init__(self, path):
        self.path = path
        self.offset = 0

    def new_rows(self):
        if not self.path.is_file():
            return
        with self.path.open("rb") as source:
            source.seek(0, 2)
            if source.tell() < self.offset:
                raise ValueError("Evidence log was truncated")
            source.seek(self.offset)
            for line in source:
                if not line.endswith(b"\n"):
                    break  # Wait for the append to finish.
                row = json.loads(line)
                self.offset += len(line)
                yield row


class EvidenceRun:
    def __init__(self, path, *, archived=False, smoke=False):
        self.path = path
        self.archived = archived
        self.smoke = smoke
        self.steps = []
        self.endpoints = {}
        self.native = {}
        self.status = {}
        self.official = None
        self._steps = JsonLinesTail(path / "steps.jsonl")
        self._receipts = JsonLinesTail(path / "receipt_order.jsonl")
        self._api = JsonLinesTail(path / "raw_api.jsonl")
        self._response_sequences = {}
        self._endpoint_by_sequence = {}
        self._pending = deque()
        self.optimizer_rows = JsonLinesTail(path / "optimizer_decisions.jsonl")
        self.optimization = []
        if archived:
            self.status = read(path / "RUN_COMPLETED.json")
            if self.status["classification"] != "PASS_VALID_RAW":
                raise ValueError("Replay requires a completed verified recording")
            self.steps = list(self._steps.new_rows())
            self.endpoints = {row["time"]: row for row in read(path / "endpoints.json")}
            self.native = read(path / "whole_native_results.json")
            self.official = read(path / "official_kpis.json")["tdis_tot"]

    def refresh(self):
        if self.archived or not self.path.is_dir():
            return
        for row in self._receipts.new_rows():
            if row.get("kind") == "api_received" and row.get("endpoint") in ("initialize", "advance"):
                self._response_sequences[row["order"]] = row["raw_sequence"]
        for row in self._api.new_rows():
            endpoint = urlsplit(row.get("url", "")).path.lstrip("/").split("/", 1)[0]
            if row.get("http_status") != 200 or (row.get("method"), endpoint) not in {
                ("PUT", "initialize"), ("POST", "advance"),
            }:
                continue
            payload = json.loads(base64.b64decode(row["raw_body_base64"]))
            observation = payload.get("payload", payload)
            self._endpoint_by_sequence[row["sequence"]] = observation
            if endpoint == "initialize":
                self.endpoints[observation["time"]] = observation
        self._pending.extend(self._steps.new_rows())
        self.optimization.extend(self.optimizer_rows.new_rows())
        while self._pending:
            row = self._pending[0]
            if self.smoke:
                stage1_path = self.path / f"stage1_{len(self.steps):04d}.json"
                if not stage1_path.is_file():
                    break
                stage1 = read(stage1_path)
                if (stage1["response_receipt"] != row["endpoint_received_order"]
                        or stage1["decision"]["origin"] != row["start"]):
                    raise ValueError("Smoke controller feedback differs from collector commit")
                row = {**row, **stage1}
            sequence = self._response_sequences.get(row["response_receipt"])
            endpoint = self._endpoint_by_sequence.get(sequence)
            chunk = self.path / f"native_chunk_{len(self.steps):04d}.json"
            if endpoint is None or not chunk.is_file():
                break
            if (endpoint["time"] != row["end"] or not near(endpoint[SET], row["actual_cooling_k"])
                    or bool(endpoint[FLAG]) != row["cooling_override_active"]):
                raise ValueError("Collector receipt and effective command disagree")
            samples = read(chunk)
            if (samples["time"][0], samples["time"][-1]) != (row["start"], row["end"]):
                raise ValueError("Verified chunk and control clock disagree")
            if self.steps and self.steps[-1]["end"] != row["start"]:
                raise ValueError("Noncontiguous verified advance")
            if row["end"] != row["start"] + STEP:
                raise ValueError("Verified advance is not five minutes")
            if self.native:
                for name in self.native:
                    self.native[name].extend(samples[name][1:])
            else:
                self.native = samples
            self.endpoints[endpoint["time"]] = endpoint
            self.steps.append(row)
            self._pending.popleft()
        status = self.path / "RUN_COMPLETED.json"
        try:
            if status.is_file():
                self.status = read(status)
                official = self.path / "official_kpis.json"
                if self.status["classification"] in {"PASS_VALID_RAW", "STOPPED_EARLY"} and official.is_file():
                    self.official = read(official)["tdis_tot"]
        except json.JSONDecodeError:
            return  # Collector is publishing its final record.

    def forecast(self, index):
        return read(self.path / f"forecast_{index:04d}.json")

    def committed(self, row):
        if "applied_command" in row:
            return row["applied_command"]
        command = native_command()
        if row["decision"]["warmer"]:
            command[FLAG] = 1
            command[SET] = row["actual_cooling_k"]
        return command

    def has_verified_prefix(self, time_s):
        return bool(self.steps and self.steps[0]["start"] < time_s <= self.steps[-1]["end"])


class ObservationalForecast:
    """O25 and persistence consume only verified history through the decision origin."""

    def __init__(self, directory=None):
        self.model = self.persistence = None
        self.load_error = ""
        sys.path.insert(0, str(ROOT.parent / "ml_research_v1_0_0"))
        try:
            from inference import Predictor
            options = {} if directory is None else {"directory": directory}
            self.persistence = Predictor("persistence", **options)
            self.model = Predictor("observational", **options)
        except (ImportError, OSError, ValueError) as error:
            self.load_error = str(error)
        self.cache = {}

    def for_step(self, run, index, forecast):
        key = (run.path, index)
        if key in self.cache:
            return self.cache[key]
        row = run.steps[index]
        origin = row["start"]
        status = dict(source="unavailable", reason="Waiting for causally verified history", origin=origin, values=[])
        times = run.native["time"]
        end = bisect_right(times, origin)
        begin = bisect_right(times, origin - 2100 - 1)
        cutoff = row["origin_cutoff_order"]
        prior = (run.steps[index - 1].get("response_receipt", run.steps[index - 1].get("endpoint_received_order"))
                 if index else None)
        issued = forecast["received_order"]
        after = row.get("response_receipt", row.get("endpoint_received_order"))
        if (end and times[end - 1] == origin and (begin < end) and times[begin] <= origin - STEP
                and prior is not None and prior < issued < cutoff < after
                and row.get("observation_received_order", prior) == prior
                and row.get("forecast_received_order", issued) == issued):
            history = {name: run.native[name][begin:end] for name in ("time", COOL, FAN, HEAT)}
            endpoints = {t: run.endpoints[t] for t in (origin - 1800, origin - STEP, origin) if t in run.endpoints}
            result = None
            reason = self.load_error or "Insufficient support for the trained model"
            if self.model is not None:
                result = self.model.forecast_observations(origin, endpoints, history, forecast,
                                                          committed=run.committed(row))
                reason = result.get("reason") or reason
            if result and result["valid"]:
                status.update(source="O25 Random Forest", reason="", values=result["predictions"])
            elif self.persistence is not None:
                fallback = self.persistence.forecast_observations(origin, endpoints, history)
                if fallback["valid"]:
                    status.update(source="Persistence", reason=reason, values=fallback["predictions"])
                else:
                    status["reason"] = fallback["reason"]
            else:
                status["reason"] = reason
        self.cache[key] = status
        return status


def shadow_g218(run):
    """Show the first Stage 1 decision on the recorded native prefix only."""
    i = ON // STEP
    index, origin = i - 1, run.steps[i - 1]["start"]
    controller = EnergyController(origin, run.steps[-1]["end"])
    steps = run.steps[index:i + 1]
    cutoffs = {step["origin_cutoff_order"] for step in steps}
    ages = {}
    for event in JsonLinesTail(run.path / "receipt_order.jsonl").new_rows():
        if event["order"] in cutoffs:
            ages[event["order"]] = event["observation_age_s"]
            if set(ages) == cutoffs:
                break
    for step in steps:
        t = step["start"]
        decision = controller.decide(t, run.endpoints[t], step["current_boundary"],
                                     age_s=ages[step["origin_cutoff_order"]],
                                     receipts=(step["observation_received_order"], step["forecast_received_order"],
                                               step["origin_cutoff_order"]))
        if decision.warmer or not decision.advance:
            return {"origin": t, "warmer": decision.warmer, "reason": decision.reason}
        end = t + STEP
        vintage = run.forecast(index)["data"]
        lo, hi = bisect_right(run.native["time"], t - 1), bisect_right(run.native["time"], end)
        controller.confirm(decision, run.endpoints[end],
                           dict(time=end, issued_at=t, lower_k=vintage[LOW][1], upper_k=vintage[UP][1],
                                occupancy=vintage[OCC][1]),
                           response_receipt=step["endpoint_received_order"],
                           native_history={k: a[lo:hi] for k, a in run.native.items()})
    return None


class DashboardState:
    def __init__(self, mode, model_directory=None, *, smoke_session=None, twin_path=None):
        self.mode = mode
        self.lock = Lock()
        self.forecaster = ObservationalForecast(model_directory) if mode not in {"smoke", "digital-twin", "rolling"} else None
        self.schedule = ComfortSchedule.from_fmu()
        self.cursor = ON // STEP - 2
        self.playing = False
        self._last_tick = time.monotonic()
        self.shadow = None
        self.optimization_shadow = None
        if mode == "warm":
            self.run = EvidenceRun(WARM_TRACE, archived=True)
            self.native = EvidenceRun(ARCHIVE, archived=True)
            self.paired = read(WARM_BATCH / "PAIRED_ENERGY_COMFORT.json")
        elif mode == "shadow":
            self.run = EvidenceRun(G218_TRACE, archived=True)
            self.native = None
            self.paired = None
            self.shadow = shadow_g218(self.run)
        elif mode == "g218":
            self.paired = measured_g218(LIVE_BATCH)
            self.run = EvidenceRun(LIVE_BATCH / f"{CAMPAIGN}_B", archived=True)
            self.native = EvidenceRun(LIVE_BATCH / f"{CAMPAIGN}_A", archived=True)
        elif mode == "smoke":
            self.run = EvidenceRun(smoke_run(smoke_session), smoke=True)
            self.native = self.paired = None
        elif mode == "digital-twin":
            self.run = EvidenceRun(twin_path)
            self.native = self.paired = None
        elif mode == "rolling":
            from .rolling_control import SESSION

            batch = HERE / "live_twin_evidence" / SESSION / "batches" / SESSION
            seal = batch / "BATCH_ARTIFACT_MANIFEST.json"
            sealed_files = read(seal)["files"]
            files = inventory(batch)
            files.pop(seal.name)
            if files != sealed_files:
                raise ValueError("Rolling replay evidence differs from the finalized manifest")
            self.run = EvidenceRun(batch / SESSION, archived=True)
            if (self.run.status.get("fabricated") is not False
                    or self.run.status.get("cleanup") != "STOP_ACK_AND_REMOVAL_VERIFIED"
                    or len(self.run.steps) != self.run.status.get("verified_advances")):
                raise ValueError("Rolling replay requires genuine, completed evidence and verified cleanup")
            self.run.optimization = list(self.run.optimizer_rows.new_rows())
            self.cursor = 1
            self.native = self.paired = None
        elif mode == "optimizer":
            from .optimizer import calibrated_model, rank
            from .optimizer_model import make_inputs

            self.run = EvidenceRun(G218_TRACE, archived=True)
            self.native = self.paired = None
            self.cursor = ON // STEP + 1
            origin = self.run.steps[ON // STEP]["start"]
            index = bisect_right(self.run.native["time"], origin)
            native_history = {k: self.run.native[k][index - 11:index] for k in ("time", COOL, FAN)}
            inputs = make_inputs(origin, self.run.endpoints[origin], self.run.forecast(ON // STEP),
                                 native_history, self.schedule)
            original = shadow_g218(self.run)
            model, qualification = calibrated_model()
            self.optimization_shadow = dict(rank(model, qualification, inputs, allowed=bool(original and original["warmer"]),
                                                 stage1_reason=original["reason"] if original else "No Stage 1 start"),
                                            origin=origin, shadow=True)
        elif mode in {"follow-optimizer", "follow-g400"}:
            if mode == "follow-optimizer":
                from .optimizer_campaign import BATCH, CAMPAIGN as session
                arm = "C"
            else:
                from autonomous_hvac_stage1.g400 import STATE as ROOT_STATE, CAMPAIGN as session
                BATCH, arm = ROOT_STATE / "batches" / session, "B"
            self.run = EvidenceRun(BATCH / f"{session}_{arm}")
            self.native = self.paired = None
            self.comparison_file = BATCH / ("OPTIMIZER_COMPARISON.json" if arm == "C" else "PAIRED_VALIDATION.json")
        else:
            self.run = EvidenceRun(LIVE_BATCH / f"{CAMPAIGN}_B")
            self.native = EvidenceRun(LIVE_BATCH / f"{CAMPAIGN}_A")
            self.paired = None

    def submit(self, message):
        if self.mode in {"follow", "smoke", "follow-optimizer", "follow-g400", "digital-twin"}:
            raise ValueError("Read-only live view; the authorized collector owns all advances")
        with self.lock:
            action = message.get("action")
            if action == "seek":
                cursor = message.get("cursor")
                if type(cursor) is not int or not 1 <= cursor <= len(self.run.steps):
                    raise ValueError("Replay cursor is outside the archive")
                self.cursor = cursor
                self.playing = False
            elif action in ("play", "pause"):
                self.playing = action == "play"
            else:
                raise ValueError("Only replay seek, play and pause are supported")
            self._last_tick = time.monotonic()
            return {"replay_only": True}

    def snapshot(self):
        with self.lock:
            try:
                return self._snapshot()
            except (OSError, KeyError, ValueError, IndexError) as error:
                return {"mode": self.mode, "error": str(error),
                        "status": "Waiting for valid recorded evidence", "ready": False}

    def _snapshot(self):
        run = self.run
        connection = None
        if self.mode in {"smoke", "follow-optimizer", "follow-g400", "digital-twin"}:
            run.refresh()
            if run.status:
                connection = "stopped"
            elif not run.steps:
                connection = "waiting"
            elif time.time() - (run.path / "steps.jsonl").stat().st_mtime > SMOKE_STALE_SECONDS:
                connection = "stale"
            else:
                connection = "live"
            if not run.steps:
                return dict(mode=self.mode, connection=connection, ready=False,
                            status=f"{run.path.name} · waiting for first verified advance" if not run.status
                            else f"{run.path.name} · collector stopped before first verified advance",
                            error=run.status.get("error"))
        if self.mode == "follow":
            self.native.refresh()
            self.run.refresh()
            if not self.run.steps:
                run = self.native
            paired_path = LIVE_BATCH / "PAIRED_VALIDATION.json"
            if self.paired is None and paired_path.is_file():
                self.paired = read(paired_path)
            if not run.steps:
                if self.run.status.get("classification") == "FAILED" or self.native.status.get("classification") == "FAILED":
                    return dict(mode=self.mode, ready=False, status="G218 collector stopped",
                                error=self.run.status.get("error") or self.native.status.get("error"))
                return dict(mode=self.mode, ready=False, status="Waiting for authorized G218 collector evidence")
            cursor = len(run.steps)
        elif self.mode in {"smoke", "follow-optimizer", "follow-g400", "digital-twin"}:
            cursor = len(run.steps)
        else:
            if self.playing:
                now = time.monotonic()
                count = int((now - self._last_tick) / .45)
                self.cursor = min(len(run.steps), self.cursor + count)
                self._last_tick += count * .45
                self.playing = self.cursor < len(run.steps)
            cursor = self.cursor
        row = run.steps[cursor - 1]
        start, end = run.steps[0]["start"], row["end"]
        observation = run.endpoints[end]
        forecast = run.forecast(cursor - 1)
        powers = score_window(run.native, self.schedule, start, end)
        other = self.native
        saved = None
        reference = None
        if (other is not None and other is not run and other.has_verified_prefix(end)
                and (self.mode == "warm" or self.paired and self.paired.get("technical_validation") == "PASS")):
            reference = score_window(other.native, self.schedule, start, end)
            saved = reference["electricity_kwh"] - powers["electricity_kwh"]
        lo, hi, occupied = self.schedule.at(end)
        command = run.committed(row)
        if "decision" in row:
            why = row["decision"]["reason"]
            fallback = row["decision"]["fallback"]
        else:
            why = row["reason"]
            fallback = "veto" in why or "fallback" in why
        last_release = next((run.steps[j]["start"] for j in range(cursor - 1, max(0, cursor - 28), -1)
                             if not run.committed(run.steps[j])[FLAG] and run.committed(run.steps[j - 1])[FLAG]), None)
        recovery_remaining = max(0, last_release + RECOVERY - end) if last_release is not None else 0
        recent = [run.endpoints[entry["end"]] for entry in run.steps[max(0, cursor - 72):cursor]]
        signals = [{k: obs[k] for k in ("time", TEMP, OUTDOOR, COOL, FAN)} for obs in recent]
        comparison = None
        if reference is not None and self.mode in {"g218", "follow"}:
            for signal in signals:
                native_endpoint = other.endpoints[signal["time"]]
                signal.update({f"native_{k}": native_endpoint[k] for k in (TEMP, COOL, FAN)})
            comparison = dict(native=reference, native_indoor_c=other.endpoints[end][TEMP] - 273.15,
                              native_official_kh=other.official if end == other.steps[-1]["end"] else None)
        status = ("ARCHIVED REPLAY — fixed warmer experiment" if self.mode == "warm" else
                  "ARCHIVED REPLAY — native G218 with shadow decision" if self.mode == "shadow" else
                  "MEASURED REPLAY — G218 native versus autonomous" if self.mode == "g218" else
                  "MEASURED REPLAY — LIVE_ROLLING_TWIN_01 · single arm" if self.mode == "rolling" else
                  "ARCHIVED NATIVE REPLAY — prediction-based optimizer shadow" if self.mode == "optimizer" else
                  f"{run.path.name} · {connection} · {cursor} verified advances" if connection else
                  ("G218 LIVE COLLECTOR — " + ("native" if run is other else "autonomous") +
                   (" · completed" if run.status.get("classification") == "PASS_VALID_RAW" else "")))
        if run.status.get("classification") == "FAILED":
            status += " · collector stopped: " + run.status.get("error", "failed verification")
        if self.mode == "follow" and run is other and self.run.status.get("classification") == "FAILED":
            status += " · autonomous arm stopped before a verified advance"
        pair_status = None
        if cursor == len(run.steps) and self.paired and run is not other:
            if self.mode == "warm":
                penalty = sum(w["recovery"]["delta_kwh"] for w in self.paired["windows"])
                pair_status = {"result": "G174 frozen NO-GO", "recovery_penalty_kwh": penalty}
            elif self.paired.get("technical_validation") == "PASS":
                penalty = sum(w["recovery_penalty_kwh"] for w in self.paired["windows"])
                label = "G218 acceptance criteria passed" if self.paired["passed_proposed_criteria"] else "G218 acceptance criteria failed"
                pair_status = {"result": label, "recovery_penalty_kwh": penalty}
        forecast_feedback = []
        if self.mode in {"smoke", "digital-twin", "rolling"}:
            prediction = read(run.path / f"rf_{cursor - 1:04d}.json")
            if self.mode in {"digital-twin", "rolling"}:
                forecast_feedback = self._forecast_feedback(run, cursor, end)
        else:
            prediction = self.forecaster.for_step(run, cursor - 1, forecast)
        optimization = self.optimization_shadow if self.optimization_shadow and end > self.optimization_shadow["origin"] else None
        feedback = None
        rolling = None
        if self.mode in {"follow-optimizer", "digital-twin", "rolling"}:
            audit = [r for r in run.optimization if r["origin"] < end]
            optimization = next((r for r in reversed(audit) if "candidates" in r), None)
            feedback = audit[-1] if audit and "candidates" not in audit[-1] else None
            if feedback and "rolling_candidates" in feedback and feedback["origin"] == row["start"]:
                from .live_smoke import forecast_actual

                rolling, feedback = dict(feedback), None
                selected = next(candidate for candidate in rolling["rolling_candidates"] if candidate["id"] == rolling["selected"])
                measured = forecast_actual(run.endpoints, run.native, end)
                predicted = selected["prediction"]
                rolling["measured"] = measured
                rolling["errors"] = (dict(temperature_c=predicted["next_temp_c"] - measured["indoor_temperature"],
                                          cooling_kw=predicted["next_cooling_kw"] - measured["cooling"],
                                          fan_kw=predicted["next_fan_kw"] - measured["fan"]) if predicted else None)
            if self.mode == "follow-optimizer" and self.comparison_file.is_file():
                measured = read(self.comparison_file)
                if measured["technical_validation"] == "PASS" and measured["fabricated"] is False:
                    pair_status = dict(result="Optimizer comfort/energy criteria " + ("PASS" if measured["optimizer_passed"] else "FAIL"),
                                       recovery_penalty_kwh=sum(w["recovery_penalty_kwh"] for w in measured["optimizer_vs_native"]["windows"]),
                                       saved_vs_fixed_kwh=measured["optimizer_saved_vs_fixed_kwh"])
                    saved = measured["optimizer_vs_native"]["full"]["saved_kwh"]
        if optimization:
            offset = (end - optimization["origin"]) // STEP
            applied = "A0" if optimization.get("shadow") else optimization["selected"]
            candidate = next(r for r in optimization["candidates"] if r["id"] == applied)
            pred = candidate["predicted"]
            relevant = [r for r in run.steps[max(0, cursor - min(max(offset, 0), 33)):cursor]]
            verified_path = all(bool(run.committed(r)[FLAG]) == (applied == "A3" and i < 9)
                                for i, r in enumerate(relevant))
            if pred and 0 < offset <= len(pred["trajectory"]) and verified_path:
                comparison_window = score_window(run.native, self.schedule, optimization["origin"], end)
                expected = pred["trajectory"][:offset]
                feedback = dict(feedback or {}, predicted_c=expected[-1][0], measured_c=observation[TEMP] - 273.15,
                                predicted_kwh=sum((r[1] + r[2]) * STEP / 3600 for r in expected),
                                measured_kwh=comparison_window["electricity_kwh"], applied=applied)
        return dict(mode=self.mode, connection=connection, ready=True, status=status, cursor=cursor, total=len(run.steps),
                    playing=self.playing, now=end, indoor=observation[TEMP] - 273.15,
                    outdoor=observation[OUTDOOR] - 273.15, cooling_w=observation[COOL],
                    fan_w=observation[FAN], heating_input_w=observation[HEAT], occupied=occupied,
                    official_band=[lo - 273.15, hi - 273.15], project_band=[20, 26] if occupied else None,
                    requested_c=command[SET] - 273.15 if command[FLAG] else None,
                    effective_c=observation[SET] - 273.15, heating_setpoint_c=observation[HEAT_SETPOINT] - 273.15,
                    override=bool(observation[FLAG]), reason=why, fallback=fallback, safety_veto=why in SAFETY_VETO_REASONS,
                    recovery_min=recovery_remaining / 60, history=signals, energy=powers,
                    heating_input_kwh=integrate(run.native["time"], run.native[HEAT], start, end) / 3600000,
                    saved_kwh=saved, pair_status=pair_status, comparison=comparison,
                    official_kpi=run.official if cursor == len(run.steps) else None,
                    forecast=prediction, forecast_feedback=forecast_feedback,
                    optimization=optimization, optimizer_feedback=feedback, rolling=rolling, morning_guard=row.get("morning_guard"),
                    policy_label={"follow-g400": "Stage 1 + 400 W guard", "follow-optimizer": "Prediction-based optimizer",
                                  "optimizer": "Prediction-based optimizer shadow", "g218": "Original Stage 1",
                                  "digital-twin": "Predictive live optimizer",
                                  "rolling": "Recorded partial receding-horizon controller"}.get(self.mode),
                    weather_30min_c=forecast["data"]["TDryBul"][6] - 273.15,
                    shadow=self.shadow if self.shadow and end >= self.shadow["origin"] else None,
                    qualification=[candidate.__dict__ for candidate in candidates()])

    @staticmethod
    def _forecast_feedback(run, cursor, now):
        from .live_smoke import HORIZONS, forecast_actual

        results = {}
        for i in reversed(range(cursor)):
            forecast = read(run.path / f"rf_{i:04d}.json")
            for predicted in forecast["values"]:
                horizon = predicted["horizon_min"]
                target = forecast["origin"] + horizon * 60
                if horizon not in results and target <= now and target in run.endpoints:
                    measured = forecast_actual(run.endpoints, run.native, target)
                    results[horizon] = dict(lead=horizon, origin=forecast["origin"], target=target,
                                           predicted=predicted, measured=measured)
            if len(results) == len(HORIZONS):
                break
        return [results[h] for h in HORIZONS if h in results]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--replay", choices=("warm", "shadow", "g218", "optimizer", "rolling"))
    mode.add_argument("--follow-g218", action="store_true")
    mode.add_argument("--follow-smoke", metavar="SESSION")
    mode.add_argument("--follow-optimizer", action="store_true")
    mode.add_argument("--follow-g400", action="store_true")
    parser.add_argument("--port", type=int, default=8770)
    parser.add_argument("--model-directory", type=Path, help="Optional refit location with checked O25 provenance")
    args = parser.parse_args()
    try:
        controller = DashboardState(args.replay or ("smoke" if args.follow_smoke else
                                    "follow-optimizer" if args.follow_optimizer else "follow-g400" if args.follow_g400 else "follow"),
                                    args.model_directory, smoke_session=args.follow_smoke)
    except (OSError, KeyError, ValueError) as error:
        parser.error(str(error))
    with make_server(controller, args.port, html_path=HERE / "dashboard.html") as server:
        print(f"http://127.0.0.1:{server.server_port}/  |  {controller.mode}", flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()

