"""Live BOPTEST monitoring, frozen forecasts and read-only archived replay."""

import argparse
from datetime import datetime, timezone
import json
from math import isclose
from pathlib import Path
from threading import Lock
from time import monotonic

from autonomous_hvac_stage1.controller import MINIMUM_ENTRY_K, MINIMUM_HOLD_K
from autonomous_hvac_stage1.evaluation import ComfortSchedule, score_window
from dashboard import make_server
from energy_savings_g174_v1.policy import (DURATION, ON, PROJECT_HOT_FALLBACK, TARGET,
                                           command_guard as warmer_guard)
from stage4e_d0.plan import (COOL, FAN, FLAG, FLAGS, HEAT, LOW, OCC, SET, STEP, TEMP, UP, WARMUP,
                              native_command, save_new, validate_readback)
from stage4e_d1_v2.validation import REFERENCE
from stage4e_d0.runner import Journal, OrderedClient
from stage4e_runtime_preflight.preflight import model_identity, verify_removed, warmup_gate

from .collect import RUNTIME
from . import archive_dataset as archive
from .dashboard_forecast import DATASET, FrozenForecast, completed_power
from .interface import BASE, HISTORY_POINTS, MAX_AGE_S, PINNED_FMU, WEATHER, Interface, cooling_command, interval_energy

PILOT = Path(__file__).resolve().parents[1]
HTML = Path(__file__).with_name("native_dashboard.html")
COMMAND_EVIDENCE = PILOT.parent / "report/native-control/verified-command-replay.json"
ORIGIN = 196*86400 + 10*3600
MAX_STEPS = 48
HEATING_SETPOINT = "con_oveTSetHea_u"
HORIZONS = archive.HORIZONS


def actual_for(endpoint, energy):
    return {"indoor_temperature":endpoint[TEMP]-273.15, "cooling":12*energy["cooling_kwh"],
            "fan":12*energy["fan_kwh"], "combined":12*energy["electricity_kwh"],
            "heating":0.9*12*energy["boiler_gas_input_kwh"]}


def feedback_at(now, forecasts, actual, previous):
    """Match a frozen lead to the endpoint actually observed at its valid time."""
    outputs = dict(previous)
    for lead in HORIZONS:
        saved = forecasts.get(now-lead*60, {})
        point = next((row for row in saved.get("values", [])
                      if row["horizon_min"] == lead and row.get("target", now) == now), None)
        if point:
            outputs[lead] = dict(lead=lead, origin=saved["origin"], target=now, source=saved["source"],
                                 predicted=point, measured=actual,
                                 errors={key:point[key]-actual[key] for key in actual})
    return outputs


class ForecastTracking:
    def __init__(self, engine):
        self.engine = engine
        self.observations, self.intervals, self.forecasts, self.feedback = {}, {}, {}, {}
        self.totals = dict(cooling_kwh=0.0, fan_kwh=0.0, electricity_kwh=0.0, boiler_gas_input_kwh=0.0)
        self.actual = None

    def settle(self, endpoint, chunk, energy):
        now = int(endpoint["time"])
        if now != next(reversed(self.observations)) + STEP or chunk["time"][0] != now-STEP or chunk["time"][-1] != now:
            raise ValueError("Measurements are outside the completed five-minute interval")
        if (power := completed_power(chunk, now)) is not None:
            self.intervals[now] = power
        self.actual = actual_for(endpoint, energy)
        for key, value in energy.items():
            self.totals[key] += value
        matched = feedback_at(now, self.forecasts, self.actual, {})
        self.feedback.update(matched)
        return list(matched.values())

    def observe(self, endpoint, issued, block=None, veto=False, *, finished=False):
        now = int(endpoint["time"])
        self.observations[now] = endpoint
        if finished:
            result = {"source": "Unavailable", "origin": now, "values": [], "reason": "End of recorded observations"}
        else:
            result = self.engine.at(now, self.observations, self.intervals, issued, block, veto, self.actual)
        self.forecasts[now] = result
        return result


def command_status(origin, command, before, after, reason=None):
    verified = bool(after[FLAG])
    released = bool(before[FLAG]) and not verified
    return dict(issued_at=origin, issued_c=command[SET]-273.15 if command[FLAG] else None,
                readback_at=int(after["time"]), verified_active=verified, verified_c=after[SET]-273.15,
                verified_release=released, reason=reason)


class OperatorInterface(Interface):
    """Use the archived warmer guard with a manually armed, fixed morning hold."""

    def _choose_command(self, target_c, forecast):
        if target_c is None:
            return super()._choose_command(target_c, forecast)
        current, previous = self.current, self.previous
        origin = int(current["time"])
        if previous is None or previous["time"] != origin-STEP:
            return native_command(), "Missing verified five-minute history", None
        temperature = current[TEMP]
        minimum = MINIMUM_HOLD_K if current[FLAG] else MINIMUM_ENTRY_K
        if temperature < minimum or temperature + max(0, temperature-previous[TEMP]) >= PROJECT_HOT_FALLBACK:
            return native_command(), "Warmer experiment temperature guard vetoed the command", None
        command = cooling_command(target_c)
        boundary = {"time": origin, **{key: forecast[key][0] for key in (LOW, UP, OCC)}}
        try:
            warmer_guard(command, current, boundary, origin, monotonic()-self.observed_at)
        except ValueError as error:
            return native_command(), str(error), None
        return command, None, None


class NativeTwin:
    def __init__(self, directory, *, client_factory=OrderedClient, inspect=model_identity, cleanup=verify_removed):
        self.tracking = ForecastTracking(FrozenForecast())
        directory.mkdir(parents=True)
        self.directory = directory
        self.client = client_factory(BASE, directory, Journal(directory/"receipt_order.jsonl"))
        self.interface = OperatorInterface(self.client)
        self.inspect, self.cleanup = inspect, cleanup
        self.lock = Lock()
        self.schedule = ComfortSchedule.from_fmu()
        self.block, self.requested_at, self.last_command, self.release = None, None, None, None
        self.vetoed = False
        self.official = 0.0
        self.error, self.closed, self.count = "", False, 0
        self.testid = None
        self.cleanup_status = None
        try:
            if self.client.request("GET", "version", instance=False) != {"version":"0.9.0"}:
                raise ValueError("Pinned loopback BOPTEST 0.9.0 is required")
            self.testid = self.client.deploy()
            identity = self.inspect(self.testid)
            if identity["sha256"] != PINNED_FMU:
                raise ValueError("Invalid BESTEST Air FMU identity")
            save_new(directory/"fmu_identity.json", identity)
            initial = self.interface.initialize(ORIGIN)
            warmup = self.interface.results(HISTORY_POINTS, ORIGIN-WARMUP, ORIGIN)
            save_new(directory/"warmup.json", warmup_gate(warmup, ORIGIN))
            self._observe(initial)
        except Exception:
            self.close()
            raise

    def _append(self, name, row):
        with (self.directory/name).open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(row, allow_nan=False)+"\n")

    def _observe(self, endpoint):
        origin = int(endpoint["time"])
        try:
            raw = self.interface.read_forecast()
            self.issued = {"issued_at_sim":origin, "received_order":self.client.last_receipt_order, "data":raw}
        except (KeyError, TypeError, ValueError):
            self.issued = None
        self._issue(endpoint)

    def _issue(self, endpoint):
        supersedes = int(endpoint["time"]) in self.tracking.forecasts
        result = self.tracking.observe(endpoint, self.issued, self.block, self.vetoed)
        self._append("predictions.jsonl", {**result, "operator_requested_at":self.requested_at,
                     "issued_forecast_receipt":self.issued["received_order"] if self.issued else None,
                     "replaces_origin_forecast":supersedes})

    def _refresh_paused_observation(self):
        """Re-verify a paused, unchanged endpoint before any further advance."""
        if monotonic()-self.interface.observed_at <= MAX_AGE_S:
            return
        observation = self.interface.current
        origin = int(observation["time"])
        fields = tuple(key for key in observation if key != "time")
        values = self.interface.results(fields, origin, origin+STEP)
        if values.get("time") != [origin] or not all(isclose(observation[k],values[k][0],rel_tol=1e-12,abs_tol=1e-9)
                                                     for k in fields):
            raise ValueError("Paused observation could not be verified as the latest simulator state")
        self.interface.observed_at = monotonic()
        self.interface.observation_receipt = self.client.last_receipt_order

    def submit(self, message):
        with self.lock:
            if message == {"action":"stop"}:
                self.close()
                return {"status":"stopped"}
            if message == {"action":"request-warmer"} and self._can_request():
                endpoint = self.interface.current
                self.requested_at = int(endpoint["time"])
                start = ORIGIN - ORIGIN % archive.DAY + ON
                self.block = (start, start+DURATION, TARGET)
                self._append("control.jsonl", {"requested_at":self.requested_at, "plan":self.block})
                self._issue(endpoint)
                return {"requested_at":self.requested_at, "scheduled_start":start, "scheduled_release":self.block[1]}
            if message != {"action":"step"} or self.closed or self.count >= MAX_STEPS:
                raise ValueError("The warmer experiment can only be requested once, before or at 11:00")
            try:
                self._refresh_paused_observation()
                origin = int(self.interface.current["time"])
                scheduled = self.block is not None and self.block[0] <= origin < self.block[1]
                target = 24.5 if scheduled and not self.vetoed else None
                step = self.interface.advance(target_c=target, remaining_advances=MAX_STEPS-self.count)
                self.count += 1
                endpoint = step.observation_after
                self.official = self.interface.kpis()["tdis_tot"]
                now = int(endpoint["time"])
                matched = self.tracking.settle(endpoint, step.native, step.energy)
                reason = step.veto or ("Cooling veto remains latched for this hold" if scheduled and self.vetoed else None)
                self.last_command = command_status(origin, step.command, step.observation_before, endpoint, reason)
                if target is not None and step.veto:
                    self.vetoed = True
                if self.last_command["verified_release"]:
                    self.release = self.last_command
                if scheduled or self.last_command["verified_release"]:
                    self._append("control.jsonl", self.last_command)
                self._append("verified_outcomes.jsonl", {"endpoint":endpoint, "energy":step.energy,
                             "actual":self.tracking.actual, "official_discomfort_kh":self.official,
                             "receipts":step.receipts, "forecast_feedback":matched})
                self._observe(endpoint)
                if self.count == MAX_STEPS:
                    self.close()
                return {"verified_time":now}
            except Exception as error:
                self.error = str(error)
                issued = self.interface.last_issued
                if issued and issued["origin"] == int(self.interface.current["time"]):
                    self.last_command = dict(issued_at=issued["origin"], readback_at=None,
                                             issued_c=issued["command"].get(SET, 273.15)-273.15
                                             if issued["command"][FLAG] else None,
                                             reason=f"Verification failed: {error}")
                    self._append("control.jsonl", self.last_command)
                self.close()
                raise

    def _can_request(self):
        return (not self.closed and self.block is None and
                int(self.interface.current["time"]) % archive.DAY <= ON)

    def snapshot(self):
        with self.lock:
            tracking = self.tracking
            obs = next(reversed(tracking.observations.values()))
            now = int(obs["time"])
            return display(obs, self.schedule, tracking.totals, self.official, tracking.forecasts[now],
                           list(tracking.feedback.values()), list(tracking.observations.values())[-37:],
                           mode="native-twin", cursor=self.count, total=MAX_STEPS, error=self.error,
                           closed=self.closed, cleanup=self.cleanup_status, can_request=self._can_request(),
                           control_plan=self.block, requested_at=self.requested_at,
                           command_status=self.last_command, release=self.release)

    def close(self):
        if self.cleanup_status is not None:
            return
        self.closed = True
        status = "no instance"
        try:
            self.client.stop()
            if self.testid is not None:
                self.cleanup(self.testid)
                status = "verified removed"
        except Exception as error:
            status = "cleanup unconfirmed"
            self.error = f"{self.error} {error}".strip()
            raise
        finally:
            self.cleanup_status = status
            save_new(self.directory/"status.json", dict(cleanup=status, verified_advances=self.count, error=self.error))


def display(obs, schedule, energy, official, forecast, feedback, history, *, mode, cursor, total, **kwargs):
    now = int(obs["time"])
    low, high, occupied = schedule.at(now)
    return dict(mode=mode, ready=True, now=now, cursor=cursor, total=total, indoor=obs[TEMP]-273.15,
                outdoor=obs[WEATHER[0]]-273.15, cooling_w=obs[COOL], fan_w=obs[FAN], heating_input_w=obs[HEAT],
                heating_thermal_w=.9*obs[HEAT],
                occupied=occupied, official_band=[low-273.15,high-273.15], project_band=None,
                official_excursion_k=max(0.0, low-obs[TEMP], obs[TEMP]-high), requested_c=None,
                effective_c=obs[SET]-273.15, heating_setpoint_c=obs[HEATING_SETPOINT]-273.15,
                hvac_mode="Cooling" if obs[COOL]>=100 else "Heating" if obs[HEAT]>=100 else "Low demand",
                override=bool(obs[FLAG]), reason="native thermostat active", fallback=False, safety_veto=False,
                status="Native control · verified measurements", official_kpi=official,
                energy={**energy,"official_replayed_kh":official,"project_replayed_kh":0.0},
                heating_input_kwh=energy["boiler_gas_input_kwh"], forecast=forecast,
                forecast_feedback=feedback, history=history, playing=False, saved_kwh=None, **kwargs)


class CommandReplay:
    def __init__(self, path=COMMAND_EVIDENCE):
        evidence = json.loads(path.read_bytes())
        if evidence["format"] != "verified thermostat smoke v1" or len(evidence["steps"])!=13:
            raise ValueError("Unexpected command evidence")
        self.steps = evidence["steps"]
        self.cursor = 1
        self.lock = Lock()
        self.schedule = ComfortSchedule.from_fmu()

    def submit(self, message):
        with self.lock:
            action = message.get("action")
            if action == "step" and self.cursor < len(self.steps):
                self.cursor += 1
            elif action == "seek" and type(message.get("cursor")) is int and 1<=message["cursor"]<=len(self.steps):
                self.cursor = message["cursor"]
            else:
                raise ValueError("Replay supports recorded steps and seeking only")
            return {"replay_only":True}

    def snapshot(self):
        with self.lock:
            elapsed = self.steps[:self.cursor]
            step = elapsed[-1]
            endpoint = step["endpoint"]
            forecast = {"values":[], "source":"Command verification replay", "origin":step["origin"],
                        "reason":"This recorded demonstration has no intervention forecast"}
            energy = {k:sum(row["energy"][k] for row in elapsed) for k in step["energy"]}
            shown = display(endpoint,self.schedule,energy,step["official_discomfort_kh"],forecast,[],
                            [row["endpoint"] for row in elapsed],mode="command-replay",cursor=self.cursor,
                            total=len(self.steps), closed=False)
            requested = step["command"].get(SET)
            shown.update(status="Archived command verification · recorded BOPTEST", reason="recorded thermostat command",
                         requested_c=requested-273.15 if requested is not None else None)
            return shown


def export_command_replay():
    base = RUNTIME/"prompt1/interface-smoke"
    verification = json.loads((base/"smoke_verification.json").read_bytes())
    if verification["status"]!="PASS" or verification["official_discomfort_kh"]!=0:
        raise ValueError("Expected completed zero-discomfort recorded command check")
    data = []
    for raw in (base/"steps.jsonl").read_bytes().splitlines():
        step = json.loads(raw)
        obs = step["observation_after"]
        if any(obs[flag]!=step["command"][flag] for flag in FLAGS):
            raise ValueError("Archived command and readback differ")
        data.append(dict(origin=step["origin"], command=step["command"], energy=step["energy"],
                         endpoint={k:obs[k] for k in ("time",TEMP,*WEATHER,COOL,FAN,HEAT,SET,HEATING_SETPOINT,*FLAGS)},
                         official_discomfort_kh=0))
    if len(data)!=13:
        raise ValueError("Expected all 13 recorded advances")
    save_new(COMMAND_EVIDENCE, {"format":"verified thermostat smoke v1", "steps":data})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument("--live", action="store_true")
    modes.add_argument("--replay", choices=("native", "override"))
    modes.add_argument("--replay-commands", action="store_true")
    modes.add_argument("--export-command-replay", action="store_true")
    modes.add_argument("--verify-model", action="store_true")
    parser.add_argument("--port", type=int, default=8770)
    args = parser.parse_args()
    if args.export_command_replay:
        export_command_replay()
        return
    if args.verify_model:
        model = FrozenForecast()
        print(f"Verified Random Forest {model.metadata['sha256']} | 27 inputs | 16 outputs")
        return
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    if args.replay:
        from .dashboard_replay import ArchivedReplay
        controller = ArchivedReplay(args.replay)
    else:
        controller = NativeTwin(RUNTIME/"native-twin"/stamp) if args.live else CommandReplay()
    server = None
    try:
        server = make_server(controller,args.port,HTML)
        print(f"SDP dashboard: http://127.0.0.1:{server.server_port}/",flush=True)
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        if server:
            server.server_close()
        if args.live:
            controller.close()


if __name__ == "__main__":
    main()
