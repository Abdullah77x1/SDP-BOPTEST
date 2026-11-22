"""One pre-arm compatibility probe using the existing frozen pilot implementation."""
import hashlib
import json
from pathlib import Path
from client import Client, utc
from core import COOL_U, FLAGS, commands, require_metadata, validate
from experiment import ROOT, initialize, prepare_forecast, write_json


def main():
    directory = ROOT / "evidence" / "verified_local_preflight"
    directory.mkdir(parents=True, exist_ok=True)
    raw = (ROOT / "plan.json").read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    assert digest == "65bd76278f2273e83283150ed2690074a75007cc7fe931f3bb9700a202bb49ce"
    plan = json.loads(raw)
    # This is a compatibility probe, not either experimental arm.
    with (directory / "PREFLIGHT_STARTED.json").open("x", encoding="utf-8") as f:
        json.dump({"utc": utc(), "plan_sha256": digest, "maximum_native_advances": 1,
                   "external_intervention": False, "transport_timeout_seconds": 120}, f)
    client = Client("http://127.0.0.1:80", directory, timeout=120, read_retries=1)
    result = {"classification": "INCOMPLETE", "plan_sha256": digest}
    try:
        client.request("GET", "testcases", instance=False)
        client.deploy()
        metadata = client.discover()
        require_metadata(metadata)
        initial = initialize(client, plan)
        forecast = prepare_forecast(client, metadata, plan)
        write_json(directory / "initialization.json", initial)
        write_json(directory / "boundary_forecast_NOT_ML.json", forecast)
        command = commands("baseline", initial["time"], plan)
        assert all(command[k] == 0 for k in FLAGS)
        observation = client.request("POST", "advance", command)
        validate(observation, initial["time"], 300)
        write_json(directory / "single_native_advance.json", {"command": command, "observation": observation})
        readback = client.request("PUT", "results", {
            "point_names": [COOL_U], "start_time": initial["time"], "final_time": observation["time"]})
        write_json(directory / "initial_setpoint_readback.json", readback)
        if not readback.get(COOL_U) or abs(readback[COOL_U][-1] - 303.15) > 1e-5:
            raise ValueError("Native midnight cooling readback conflicts with documented 303.15 K")
        result.update(classification="COMPATIBLE", scenario_start=initial["time"],
                      next_time=observation["time"], accepted_step=300,
                      warmup_evidence="Pinned testcase.py uses days[peak_cool_day]-7 days and 7-day warmup",
                      native_occupied_cooling_k=297.15, intervention_k=298.15,
                      central_peak_day=289, first_scenario_day=282,
                      heating_channel="Source FanCoilUnit_T delivered heating / 0.9, GasPower tag; raw channel separate from electricity")
    except Exception as exc:
        result.update(classification="BLOCKED_COMPATIBILITY", error=f"{type(exc).__name__}: {exc}")
        raise
    finally:
        try:
            client.stop()
            result["cleanup"] = "STOPPED_OR_NOT_DEPLOYED"
        except Exception as exc:
            result["cleanup"] = "UNCONFIRMED"
            result["cleanup_error"] = str(exc)
        write_json(directory / "compatibility.json", result)


if __name__ == "__main__":
    main()
