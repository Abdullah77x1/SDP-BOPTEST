"""Bounded, frozen A/B experiment and discovery commands. No automatic reruns."""
from __future__ import annotations
import argparse
import csv
import hashlib
import json
import math
from pathlib import Path
from client import Client, APIError, utc
from core import (CORE, COOL, FAN, HEAT, TEMP, COOL_U, COOL_A, commands,
                  integrate, require_metadata, validate)

ROOT = Path(__file__).resolve().parent


def write_json(path, value):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(value, indent=2, allow_nan=False), encoding="utf-8")


def frozen_plan(directory):
    data = (ROOT / "plan.json").read_bytes()
    plan = json.loads(data)
    digest = hashlib.sha256(data).hexdigest()
    target = Path(directory) / "frozen_plan.json"
    if target.exists() and target.read_bytes() != data:
        raise ValueError("Frozen plan changed")
    target.write_bytes(data)
    (Path(directory) / "PLAN_SHA256.txt").write_text(digest + "\n", encoding="ascii")
    return plan, digest


def initialize(client, plan):
    scenario = client.request("PUT", "scenario", {
        "time_period": plan["scenario"], "electricity_price": plan["electricity_price"]})
    initial = scenario.get("time_period") if isinstance(scenario, dict) else None
    if not isinstance(initial, dict):
        raise APIError("Scenario unavailable or missing initialization payload")
    validate(initial)
    if abs(initial["time"] - plan["scenario_start"]) > 1e-6:
        raise APIError("Scenario start differs from frozen v0.9 contract")
    client.request("PUT", "step", {"step": plan["step"]})
    step = client.request("GET", "step")
    if float(step) != plan["step"]:
        raise APIError("Control step not accepted")
    current = client.request("GET", "scenario")
    if current.get("time_period") != plan["scenario"]:
        raise APIError("Scenario readback mismatch")
    return initial


def prepare_forecast(client, metadata, plan):
    """Corroborate the fixed +1K interpretation before any controlled stepping."""
    names = [n for n in ("UpperSetp[1]", "LowerSetp[1]", "Occupancy[1]", "TDryBul", "HGloHor")
             if n in metadata["forecast_points"]]
    if "UpperSetp[1]" not in names:
        raise ValueError("Cannot corroborate native occupied cooling setpoint")
    forecast = client.request("PUT", "forecast", {
        "point_names": names, "horizon": plan["evaluation_seconds"], "interval": plan["step"]})
    in_pulse = [i for i, t in enumerate(forecast["time"])
                if plan["pulse_start"] <= t < plan["pulse_end"]]
    if len(in_pulse) != 24 or any(abs(forecast["UpperSetp[1]"][i] -
                                      plan["native_occupied_cooling_k"]) > 1e-6 for i in in_pulse):
        raise ValueError("Documented +1K interpretation not supported by forecast metadata")
    return forecast


def run_arm(mode, directory, base=None, client_factory=Client):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    plan, digest = frozen_plan(directory)
    # Exclusive creation: a lost response must never cause an automatic second attempt.
    with (directory / "ATTEMPT_STARTED.json").open("x", encoding="utf-8") as stream:
        json.dump({"mode": mode, "started_utc": utc(), "plan_sha256": digest}, stream)
    client = client_factory(base or plan["endpoint"], directory)
    status = {"mode": mode, "classification": "INCOMPLETE", "plan_sha256": digest}
    history = []
    try:
        client.deploy()
        metadata = client.discover()
        require_metadata(metadata)
        initial = initialize(client, plan)
        # Forecasts are stored separately as benchmark future boundary conditions, never ML output.
        forecast = prepare_forecast(client, metadata, plan)
        write_json(directory / "boundary_forecast_NOT_ML.json", forecast)
        history.append(initial)
        with (directory / "steps.jsonl").open("x", encoding="utf-8") as stream:
            for _ in range(plan["evaluation_seconds"] // plan["step"]):
                before = history[-1]["time"]
                command = commands(mode, before, plan)
                sent = utc()
                observation = client.request("POST", "advance", command)
                validate(observation, before, plan["step"])
                record = {"interval_start": before, "interval_end": observation["time"],
                          "sent_utc": sent, "received_utc": utc(), "command": command,
                          "observation": observation}
                stream.write(json.dumps(record, allow_nan=False) + "\n")
                stream.flush()
                history.append(observation)
        write_json(directory / "observations.json", history)
        points = list(metadata["measurements"]) + list(metadata["inputs"])
        results = client.request("PUT", "results", {"point_names": points,
            "start_time": initial["time"], "final_time": history[-1]["time"]})
        write_json(directory / "native_results.json", results)
        write_json(directory / "kpis.json", client.request("GET", "kpi"))
        # BOPTEST results exposes effective input values, including native when not overridden.
        if COOL_U not in results:
            raise ValueError("Missing effective cooling setpoint in results")
        for t, value in zip(results["time"], results[COOL_U]):
            if plan["pulse_start"] < t < plan["pulse_end"]:
                expected = 298.15 if mode == "intervention" else 297.15
                if abs(value - expected) > 1e-5:
                    raise ValueError("Effective cooling setpoint disagrees with declared action")
        if mode == "intervention":
            released = [(t, v) for t, v in zip(results["time"], results[COOL_U])
                        if plan["pulse_end"] + plan["step"] <= t < plan["pulse_end"] + 3600]
            if not released or any(abs(v-297.15) > 1e-5 for t, v in released):
                raise ValueError("Native setpoint did not resume after explicit release")
        status["classification"] = "VERIFIED_COLLECTION"
        status["steps"] = len(history)-1
    except Exception as exc:
        status["error"] = f"{type(exc).__name__}: {exc}"
        raise
    finally:
        try:
            client.stop()
            status["cleanup"] = "STOPPED_OR_NOT_DEPLOYED"
        except Exception as exc:
            status["cleanup"] = "STOP_FAILED; instance may expire by service timeout"
            status["cleanup_error"] = str(exc)
        write_json(directory / "status.json", status)


def compare(directory):
    directory = Path(directory)
    a, b = directory/"A", directory/"B"
    if (a/"PLAN_SHA256.txt").read_bytes() != (b/"PLAN_SHA256.txt").read_bytes():
        raise ValueError("Unmatched plans")
    plan = json.loads((a/"frozen_plan.json").read_text())
    for arm in (a, b):
        if json.loads((arm/"status.json").read_text())["classification"] != "VERIFIED_COLLECTION":
            raise ValueError("Incomplete experiment arm")
    ah = json.loads((a/"observations.json").read_text())
    bh = json.loads((b/"observations.json").read_text())
    if len(ah) != len(bh):
        raise ValueError("Unmatched observation counts")
    deltas = []
    max_pre = 0.0
    for left, right in zip(ah, bh):
        if left.keys() != right.keys() or left["time"] != right["time"]:
            raise ValueError("Unmatched times/measurement keys")
        if left["time"] <= plan["pulse_start"]:
            max_pre = max(max_pre, *(abs(left[k]-right[k]) for k in left))
        deltas.append(right[TEMP]-left[TEMP])
    if max_pre > 1e-7:
        raise ValueError("Pretreatment equality failed; interpretation blocked")
    windows = {"pretreatment": (plan["scenario_start"], plan["pulse_start"]),
               "intervention": (plan["pulse_start"], plan["pulse_end"]),
               "recovery": (plan["pulse_end"], plan["scenario_start"]+86400),
               "total": (plan["scenario_start"], plan["scenario_start"]+86400)}
    summary = {"classification": "BOUNDED_SYNTHETIC_COMPARISON", "pretreatment_max_abs": max_pre,
               "max_abs_temperature_difference_k": max(map(abs, deltas)), "windows": {}}
    for arm_name, arm in (("A", a), ("B", b)):
        result = json.loads((arm/"native_results.json").read_text())
        ts = result["time"]
        power = [x+y for x, y in zip(result[COOL], result[FAN])]
        for window, (start, end) in windows.items():
            metric = {"hvac_electric_kwh": integrate(ts, power, start, end)/3.6e6,
                      "cooling_electric_kwh": integrate(ts, result[COOL], start, end)/3.6e6,
                      "fan_electric_kwh": integrate(ts, result[FAN], start, end)/3.6e6,
                      "heating_reported_channel_kwh": integrate(ts, result[HEAT], start, end)/3.6e6,
                      "mean_zone_c": integrate(ts, result[TEMP], start, end)/(end-start)-273.15}
            # Fixed case schedule only, clearly an engineering diagnostic rather than learned occupancy.
            hot = [max(t-297.15, 0) if 8 <= (time % 86400)/3600 < 18 else 0
                   for time, t in zip(ts, result[TEMP])]
            cold = [max(294.15-t, 0) if 8 <= (time % 86400)/3600 < 18 else 0
                    for time, t in zip(ts, result[TEMP])]
            metric["scheduled_occupied_discomfort_kh_sampled"] = (
                integrate(ts, hot, start, end)+integrate(ts, cold, start, end))/3600
            summary["windows"].setdefault(window, {})[arm_name] = metric
        summary[f"{arm_name}_official_kpis"] = json.loads((arm/"kpis.json").read_text())
    for window in summary["windows"].values():
        window["B_minus_A"] = {k: window["B"][k]-v for k, v in window["A"].items()}
    summary["interpretation"] = "Native-results trapezoid integration; finite sampling error remains. Not optimization, field validation, statistical significance or annual savings. Official KPI totals may combine energy carriers and are not our electrical boundary. Heating raw channel is excluded from electricity: documentation calls it thermal, but v0.9.0 FanCoilUnit_T computes delivered heating divided by 0.9 and tags GasPower; do not relabel it delivered heat without a separate runtime/source audit."
    write_json(directory/"comparison.json", summary)
    return summary


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("operation", choices=["discover", "baseline", "intervention", "both", "compare"])
    parser.add_argument("--base", default="https://api.boptest.net")
    parser.add_argument("--output", default=str(ROOT/"evidence"/"pilot"))
    args = parser.parse_args(argv)
    root = Path(args.output)
    root.mkdir(parents=True, exist_ok=True)
    if args.operation == "compare":
        print(json.dumps(compare(root), indent=2)); return
    # Reachability check is read-only and occurs before any deployment/experiment slot.
    client = Client(args.base, root/"connection")
    try:
        client.request("GET", "testcases", instance=False)
        if args.operation == "discover":
            try:
                client.deploy()
                print(json.dumps(client.discover(), indent=2))
            finally:
                client.stop()
            return
        if args.operation in ("baseline", "both"):
            run_arm("baseline", root/"A", args.base)
        if args.operation in ("intervention", "both"):
            status = json.loads((root/"A"/"status.json").read_text())
            if status["classification"] != "VERIFIED_COLLECTION":
                raise ValueError("Matched complete baseline required")
            run_arm("intervention", root/"B", args.base)
            print(json.dumps(compare(root), indent=2))
    except Exception as exc:
        write_json(root/"BLOCKER.json", {"utc": utc(), "classification": "BLOCKED",
                                       "error": str(exc), "endpoint": args.base})
        raise


if __name__ == "__main__":
    main()
