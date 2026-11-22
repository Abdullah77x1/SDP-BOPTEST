"""Load the exact release model and match a genuine recorded O25 forecast."""
from pathlib import Path
import json
import math
import sys

root = Path(__file__).resolve().parents[1]
pilot = root / "SDP_BOPTEST_Pilot"
sys.path[:0] = [str(root / "ml_research_v1_0_0"), str(pilot)]

from dataset import HORIZONS
from inference import Predictor
from stage4e_d0.plan import native_command
from final_energy_control.live_dashboard import DashboardState
from final_energy_control.rolling_control import SESSION
from final_energy_control.rolling_model import calibrated_rolling

run = DashboardState("rolling").run
forecast = run.forecast(7)
origin = forecast["issued_at_sim"]
saved = json.loads((run.path / "rf_0007.json").read_bytes())
assert run.path.name == SESSION and run.status["fabricated"] is False
assert saved["source"] == "O25 Random Forest" and saved["origin"] == origin
stop = run.native["time"].index(origin) + 1
history = {field: values[stop - 71:stop] for field, values in run.native.items()}
endpoints = {t: run.endpoints[t] for t in (origin - 1800, origin - 300, origin)}
observational = Predictor("observational")
persistence = Predictor("persistence")
result = observational.forecast_observations(origin, endpoints, history, forecast, committed=native_command())
assert result["valid"], result["reason"]
assert [p["horizon_min"] for p in result["predictions"]] == HORIZONS
for measured, expected in zip(result["predictions"], saved["values"], strict=True):
    assert measured.keys() == expected.keys()
    for name, value in measured.items():
        assert math.isclose(value, expected[name], rel_tol=1e-9, abs_tol=1e-9), (name, value, expected[name])
assert persistence.forecast_observations(origin, endpoints, history)["valid"]
print("Frozen O25 loaded and reproduced all four saved forecast leads from a genuine native prefix.")
_, qualification = calibrated_rolling()
assert qualification["qualified"] and qualification["maximum_horizon_min"] == 165
print("Rolling HVAC Action-Response Model qualification passed using the included original hash-bound inputs.")
