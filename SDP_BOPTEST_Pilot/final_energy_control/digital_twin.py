"""Single-owner live optimizer demonstration with explicit one-shot authorization."""

import argparse
from dataclasses import asdict
import json
from pathlib import Path
from threading import Condition, Thread
import time
import webbrowser

from autonomous_hvac_stage1 import g218
from autonomous_hvac_stage1.controller import CONTEXT_FIELDS, DAY, Decision
from dashboard import make_server
from hvac_control_expansion_b2f_v1.packaging import inventory
from hvac_control_expansion_v1.registry import Registry
from stage4e_d0.plan import COOL, FAN, FLAG, FLAGS, HEAT, LOW, OCC, POINTS, STEP, UP, append_native, energy_audit
from stage4e_d0.runner import Journal, files_manifest, utc
from stage4e_d1_v2.validation import HISTORY_POINTS, history, initial_native
from stage4e_d2i_1.common import ROOT, digest, read, require, save_new, sha
from stage4e_d2i_1.schema import canonical_schema, catalog_gate, forecast_gate, observation_gate, validate_schema
from stage4e_d2i_1.transport import BudgetedTransport, initialize_run
from stage4e_d2i_1_v1_0_1.metadata import validate_metadata_receipt
from stage4e_runtime_preflight.preflight import warmup_gate

from .live_dashboard import HERE, DashboardState, ObservationalForecast
from .live_smoke import record_o25
from .optimizer import VERSION, PredictiveController, calibrated_model
from .optimizer_model import OUTDOOR, SOLAR

SESSION = "LIVE_OPTIMIZER_TWIN_01"
STATUS = "EXPLICITLY_AUTHORIZED_LIVE_OPTIMIZER_TWIN_01"
STATE = HERE / "live_twin_evidence" / SESSION
RUN_PATH = STATE / "batches" / SESSION / SESSION
START = 218 * DAY + 10 * 3600 + 20 * 60
ADVANCES = 41  # 35 min O25 history, one native forecast before 11:00, then hold/recovery.
PACE_S = 1.25


def definition(use_400w=False, *, rolling=False):
    session, version = SESSION, VERSION
    if rolling:
        from .rolling_control import SESSION as session, VERSION as version

    source = g218.definition()
    run = dict(source["runs"][1], run_id=session, group_id="LIVE_OPTIMIZER_DEMONSTRATION",
               start=START, end=START + ADVANCES * STEP, warmup_start=START - 7 * DAY, maximum_advances=ADVANCES,
               initialization=dict(method="custom", start_time=START, warmup_period=7 * DAY, scenario_key=None))
    return dict(session=session, model=source["model"], policy=source["policy"], run=run, optimizer_version=version,
                allowed_actions=["native", "24.5°C each five minutes within one qualified 45-minute window" if rolling
                                 else "24.5°C for one qualified 45-minute hold"], use_400w=use_400w,
                automatic_retries=False, training_release=False, measurement_only=True,
                budgets=dict(instances=1, initializations=1, advances=ADVANCES, warmer_starts=1, warmer_advances=9),
                stop_release_within_budget=True, pace_seconds=PACE_S)


def binding(use_400w=False, *, rolling=False):
    sources = ("digital_twin.py", "test_digital_twin.py", "live_dashboard.py", "live_smoke.py", "dashboard.html",
               "optimizer.py", "optimizer_model.py")
    model = ROOT.parent / "ml_research_v1_0_0"
    spec = definition(use_400w, rolling=rolling)
    validation = None
    if rolling:
        from .rolling_model import calibrated_rolling

        sources += ("rolling_control.py", "rolling_model.py", "test_rolling.py")
        _, validation = calibrated_rolling()
    return dict(session=spec["session"], config_sha256=digest(spec), budgets=spec["budgets"],
                implementation_sha256=digest(dict(stage1=g218.approval_binding()["implementation_sha256"],
                    application={name: sha(HERE / name) for name in sources},
                    ml={name: sha(model / name) for name in ("inference.py", "dataset.py", "MODEL_PROVENANCE.json")},
                    ml_contract=sha(ROOT.parent / "experiments/five_model_hvac16_v1_0_0/config.py"),
                    launcher=sha(ROOT.parent / "run_live_digital_twin.ps1"),
                    dashboard_server=sha(ROOT / "dashboard.py"), validation=digest(validation) if rolling else None)),
                automatic_retries=False)


class SessionControl:
    """Commands queue at verified interval boundaries. The browser never sees a simulator client."""

    def __init__(self, work, pace=PACE_S):
        self.condition = Condition()
        self.phase = "ready"
        self.thread = None
        self.result = None
        self.work, self.pace = work, pace

    def submit(self, message):
        require(isinstance(message, dict) and set(message) == {"action"}, "Use a single demo lifecycle action")
        action = message["action"]
        with self.condition:
            if action == "start" and self.phase == "ready":
                self.phase = "starting"
                self.thread = Thread(target=self._run, name="BOPTEST-owner")
                self.thread.start()
            elif action == "pause" and self.phase == "running":
                self.phase = "pausing"
            elif action == "resume" and self.phase == "paused":
                self.phase = "resuming"
            elif action == "stop" and self.phase in {"starting", "running", "pausing", "paused", "resuming"}:
                self.phase = "stopping"
            else:
                raise ValueError(f"{action!r} unavailable while {self.phase}")
            self.condition.notify_all()
            return {"phase": self.phase}

    def _run(self):
        try:
            result = self.work(self)
        except Exception as exc:
            result = dict(classification="FAILED", error=f"{type(exc).__name__}: {exc}", cleanup="see_run_evidence")
        with self.condition:
            self.result = result
            self.phase = "failed" if result["classification"] == "FAILED" else "stopped"
            self.condition.notify_all()

    def initialized(self):
        with self.condition:
            if self.phase == "starting":
                self.phase = "running"
            self.condition.notify_all()

    def boundary(self, index):
        """Return whether to stop and whether the recorded endpoint needs a fresh read."""
        with self.condition:
            if index and self.phase == "running":
                self.condition.wait_for(lambda: self.phase != "running", timeout=self.pace)
            paused = self.phase == "pausing"
            if paused:
                self.phase = "paused"
                self.condition.notify_all()
                self.condition.wait_for(lambda: self.phase != "paused")
            if self.phase == "resuming":
                self.phase = "running"
                self.condition.notify_all()
            return self.phase == "stopping", paused

    def close(self):
        with self.condition:
            if self.thread and self.phase not in {"stopped", "failed"}:
                self.phase = "stopping"
                self.condition.notify_all()
        if self.thread:
            self.thread.join()


class DemoPolicy(PredictiveController):
    release_requested = False

    def _select(self, origin, context, boundary, age_s):
        if self.release_requested:
            return Decision(origin, False, "operator_native_release")
        return super()._select(origin, context, boundary, age_s)


def refresh_endpoint(client, current):
    """After pause, re-read the unchanged simulation state without advancing it."""
    stamp = current["time"]
    names = tuple(k for k in CONTEXT_FIELDS if k != "time") + (OUTDOOR, SOLAR)
    data = client.request("PUT", "results", dict(point_names=list(names), start_time=stamp, final_time=stamp))
    require(data["time"] == [stamp] and all(data[k] == [current[k]] for k in names),
            "Paused endpoint readback did not match the last verified observation")
    return client.last_receipt_order


def collect_session(path, control, factory, model, validation, predictor, *, fabricated=False, use_400w=False, rolling=False):
    """Compose the qualified transport, Stage 1 state machine and verification gates."""
    manifest = definition(use_400w, rolling=rolling)
    run = manifest["run"]
    path.mkdir()
    save_new(path / "ATTEMPT_STARTED.json", dict(run=run, config_sha256=digest(manifest), started_utc=utc(), fabricated=fabricated))
    journal = Journal(path / "receipt_order.jsonl")
    issued, native, endpoints = {}, {}, {}
    status = dict(classification="FAILED", cleanup="NOT_CONFIRMED", release="not_needed", fabricated=fabricated)
    client = None

    def record(row):
        with (path / "optimizer_decisions.jsonl").open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(row, allow_nan=False) + "\n")
        journal.emit("optimizer_decision_recorded", origin=row["origin"], selected=row["selected"], record_sha256=digest(row))

    policy = DemoPolicy
    if rolling:
        from .rolling_control import RollingController

        policy = RollingController
    controller = policy(run["start"], run["end"], model=model, validation=validation,
                        issued=lambda: issued, record=record, use_400w=manifest["use_400w"])
    committed = 0
    try:
        client = BudgetedTransport(factory(manifest["policy"]["base"], path, journal, run, manifest), run)
        client.deploy()
        metadata = client.discover()
        save_new(path / "METADATA_RECEIPT_VALIDATION.json", validate_metadata_receipt(path, metadata))
        schema = canonical_schema()
        validate_schema(schema)
        optional = list(schema["optional_collected_variables"])
        save_new(path / "CATALOG_AVAILABILITY.json", catalog_gate(metadata, schema, optional))
        identity = client.fmu_identity()
        require(identity["sha256"] == g218.FMU_SHA, "Deployed FMU hash mismatch")
        save_new(path / "DEPLOYED_FMU_IDENTITY.json", identity)
        current = initialize_run(client, run)
        observed_at, prior = time.monotonic(), client.last_receipt_order
        observation_gate(current, run["start"], metadata)
        initial_native(current)
        endpoints[run["start"]] = current
        client.request("PUT", "step", {"step": STEP})
        client.request("GET", "step")
        scenario = client.request("GET", "scenario")
        require(scenario.get("electricity_price") == "constant" and all(scenario.get(k) is None for k in
                ("time_period", "seed", "solar_uncertainty", "temperature_uncertainty")), "Unexpected scenario")
        save_new(path / "SCENARIO.json", scenario)
        warmup = client.request("PUT", "results", dict(point_names=[COOL, FAN, HEAT, *FLAGS],
                                start_time=run["warmup_start"], final_time=run["start"]))
        warmup_gate(warmup, run["start"])
        require(set(range(run["warmup_start"], run["start"] + 1, 30)) <= set(warmup["time"]), "Incomplete warmup")
        save_new(path / "NATIVE_WARMUP_HISTORY.json", warmup)
        control.initialized()
        with (path / "steps.jsonl").open("x", encoding="utf-8") as steps:
            for index, origin in enumerate(range(run["start"], run["end"], STEP)):
                stop, refreshed = control.boundary(index)
                if stop and not current[FLAG]:
                    break
                if refreshed or time.monotonic() - observed_at > 20:
                    prior = refresh_endpoint(client, current)
                    observed_at = time.monotonic()
                    journal.emit("paused_endpoint_reverified", origin=origin, receipt=prior)
                controller.release_requested = stop
                forecast = client.request("PUT", "forecast", dict(point_names=[*schema["core_forecasts"], *optional],
                                          horizon=1800, interval=STEP))
                issued.update(issued_at_sim=origin, received_order=client.last_receipt_order, data=forecast)
                forecast_gate(forecast, origin, schema, optional)
                save_new(path / f"forecast_{index:04d}.json", issued)
                boundary = dict(time=origin, **{k: forecast[k][0] for k in POINTS})
                age = time.monotonic() - observed_at
                cutoff = journal.emit("origin_cutoff", sim_time=origin, observation_receipt=prior,
                                      forecast_receipt=issued["received_order"], observation_age_s=age)
                decision = controller.decide(origin, current, boundary, age_s=age,
                                             receipts=(prior, issued["received_order"], cutoff))
                journal.emit("controller_decision", decision=asdict(decision), command=decision.command, cutoff=cutoff)
                require(decision.advance, decision.reason)
                rf_receipt = record_o25(path, journal, index, origin, decision.command, cutoff, run["start"],
                                        native, endpoints, issued, predictor, event="twin_o25_before_advance")
                require(time.monotonic() - observed_at <= 30, "Observation became stale before actuation")
                status["release"] = "unverified" if current[FLAG] or decision.warmer else status["release"]
                following = client.request("POST", "advance", decision.command)
                observed_at, response = time.monotonic(), client.last_receipt_order
                end = origin + STEP
                observation_gate(following, end, metadata)
                chunk = client.request("PUT", "results", dict(point_names=list(HISTORY_POINTS), start_time=origin, final_time=end))
                chunk_receipt = client.last_receipt_order
                extra = {}
                event = controller.pending_event_time
                if event is not None:
                    followup = client.request("PUT", "results", dict(point_names=list(HISTORY_POINTS),
                                              start_time=event - STEP, final_time=event + STEP))
                    save_new(path / f"pending_history_{event}.json", followup)
                    extra = dict(event_history=followup, history_receipt=client.last_receipt_order)
                checked = controller.confirm(decision, following, dict(time=end, issued_at=origin, lower_k=forecast[LOW][1],
                                             upper_k=forecast[UP][1], occupancy=forecast[OCC][1]), response_receipt=response,
                                             native_history=chunk, **extra)
                if current[FLAG] and not checked.cooling_override_active:
                    status["release"] = "verified"
                controller.accept_verified_history(origin, chunk, chunk_receipt)
                append_native(native, chunk, origin, end)
                save_new(path / f"native_chunk_{index:04d}.json", chunk)
                steps.write(json.dumps(dict(asdict(checked), start=origin, end=end, response_receipt=response,
                                            origin_cutoff_order=cutoff, rf_before_advance_receipt=rf_receipt,
                                            current_boundary=boundary), allow_nan=False) + "\n")
                steps.flush()
                committed += 1
                endpoints[end] = following
                current, prior = following, response
                if stop:
                    break
        require(not any(current[f] for f in FLAGS), "Unable to verify native release within the authorized budget")
        status["classification"] = "PASS_VALID_RAW" if committed == ADVANCES else "STOPPED_EARLY"
        if committed and controller.pending_event_time is None:
            finish = current["time"]
            whole = client.request("PUT", "results", dict(point_names=list(HISTORY_POINTS),
                                   start_time=run["start"], final_time=finish))
            history(whole, run["start"], finish)
            require(native == {k: whole[k] for k in native}, "Verified native chunks differ from whole history")
            kpis = client.request("GET", "kpi")
            save_new(path / "energy_audit.json", energy_audit(native, run["start"], finish, kpis, manifest["policy"]))
            save_new(path / "official_kpis.json", kpis)
            save_new(path / "endpoints.json", list(endpoints.values()))
            save_new(path / "whole_native_results.json", whole)
    except (Exception, KeyboardInterrupt) as error:
        controller.abort(error)
        status.update(classification="FAILED", error=f"{type(error).__name__}: {error}")
        journal.emit("run_failed", error=status["error"], automatic_retry=False)
    finally:
        if client is not None and client.deploy_attempts:
            try:
                cleanup = client.stop()
                require(cleanup.get("acknowledgement") == "OK" and cleanup.get("instance_removed") is True,
                        "Cleanup acknowledgement or instance removal unverified")
                status.update(cleanup="STOP_ACK_AND_REMOVAL_VERIFIED", cleanup_evidence=cleanup)
            except Exception as error:
                status.update(classification="FAILED", cleanup="STOP_UNCONFIRMED", cleanup_error=str(error))
        status.update(verified_advances=committed, advance_attempts=client.advance_attempts if client else 0)
        journal.emit("attempt_closed", classification=status["classification"], cleanup=status["cleanup"])
        save_new(path / "RUN_COMPLETED.json", status)
        save_new(path / "ARTIFACT_MANIFEST.json", dict(files=files_manifest(path)))
    return status


class LiveApplication:
    def __init__(self, control, path, *, fabricated=False, use_400w=False, rolling=False):
        self.control, self.fabricated = control, fabricated
        self.use_400w = use_400w
        self.rolling = rolling
        self.dashboard = DashboardState("digital-twin", twin_path=path)

    def submit(self, message):
        return self.control.submit(message)

    def snapshot(self):
        view = self.dashboard.snapshot()
        with self.control.condition:
            view.update(lifecycle=self.control.phase, session_result=self.control.result, fabricated=self.fabricated,
                        use_400w=self.use_400w, rolling_mode=self.rolling)
        return view


def create_application(authorization, *, use_400w=False, rolling=False):
    session, status, calibrate = SESSION, STATUS, calibrated_model
    if rolling:
        from .rolling_control import SESSION as session, STATUS as status
        from .rolling_model import calibrated_rolling as calibrate

    scope = binding(use_400w, rolling=rolling)
    receipt = g218._approval(authorization, dict(scope, status=status))
    state = STATE.parent / session
    run_path = state / "batches" / session / session
    require(not state.exists(), "Existing live twin ledger: no resume or retry")
    require(sha(g218.FMU) == g218.FMU_SHA, "Local FMU source drift")
    from hvac_control_expansion_b2g_v1.launcher import real_factory
    from stage4e_d1_v2.runtime import verify_runtime

    runtime = verify_runtime()
    model, validation = calibrate()
    require(runtime["classification"] == "PASS" and validation["qualified"] and binding(use_400w, rolling=rolling) == scope,
            "Runtime, action-model qualification, or source binding failed")
    predictor = ObservationalForecast()
    require(predictor.model is not None, f"Pinned O25 artifact did not load: {predictor.load_error}")

    def work(control):
        runtime = verify_runtime()
        require(runtime["classification"] == "PASS", "Pinned runtime failed the Start check")
        require(binding(use_400w, rolling=rolling) == scope, "Live twin implementation changed since authorization")
        config = definition(use_400w, rolling=rolling)
        run = config["run"]
        state.parent.mkdir(exist_ok=True)
        slot = dict(run_id=session, group_id=run["group_id"], partition="development", category="development",
                    status="UNUSED_NOT_AUTHORIZED", run_sha256=digest(run))
        registry = Registry.create(state, dict(campaign=session, slots=[slot]))
        batch = registry.new_batch(session, [run], dict(scope, authorization_sha256=receipt, runtime=runtime))
        save_new(batch / "LIVE_CONFIGURATION.json", config)
        if rolling:
            save_new(batch / "MEASURED_MODEL_VALIDATION.json", validation)
        require(registry.reserve(session, run) == run_path, "Unexpected live evidence path")
        result = collect_session(run_path, control, real_factory, model, validation, predictor,
                                 use_400w=use_400w, rolling=rolling)
        seal = batch / f"{session}_SEALED_MANIFEST.json"
        save_new(seal, dict(run_id=session, files=inventory(run_path), training_release=False))
        registry.finish(session, "CONSUMED_FAILED" if result["classification"] == "FAILED" else "CONSUMED_COMPLETED",
                        dict(seal_sha256=sha(seal), raw_result=result))
        save_new(batch / "BATCH_ARTIFACT_MANIFEST.json", dict(files=inventory(batch)))
        registry.verify_evidence()
        return result

    return LiveApplication(SessionControl(work), run_path, use_400w=use_400w, rolling=rolling)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--describe", action="store_true")
    group.add_argument("--serve", metavar="AUTHORIZATION", type=Path)
    group.add_argument("--validate-rolling", action="store_true")
    parser.add_argument("--port", type=int, default=8770)
    parser.add_argument("--open-browser", action="store_true")
    parser.add_argument("--use-400w", action="store_true", help="Requires the separately bound guarded configuration")
    parser.add_argument("--rolling", action="store_true", help="Use the separately bound partial rolling controller")
    args = parser.parse_args()
    if args.validate_rolling:
        from .rolling_model import calibrated_rolling

        print(json.dumps(calibrated_rolling()[1], indent=2))
        return
    if args.describe:
        status = STATUS
        if args.rolling:
            from .rolling_control import STATUS as status

        print(json.dumps(dict(definition=definition(args.use_400w, rolling=args.rolling),
                              binding=binding(args.use_400w, rolling=args.rolling), authorization_status=status), indent=2))
        return
    try:
        app = create_application(args.serve, use_400w=args.use_400w, rolling=args.rolling)
    except (OSError, ValueError, KeyError) as error:
        parser.error(str(error))
    try:
        with make_server(app, args.port, html_path=HERE / "dashboard.html") as server:
            url = f"http://127.0.0.1:{server.server_port}/"
            print(f"{url} | authorized live demo, click Start", flush=True)
            if args.open_browser:
                webbrowser.open(url)
            server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        app.control.close()
        if app.control.result:
            print(json.dumps(app.control.result, indent=2), flush=True)


if __name__ == "__main__":
    main()
