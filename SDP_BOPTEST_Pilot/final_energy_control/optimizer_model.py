"""Causal native-reference fit plus an intervention template from measured pairs."""

from dataclasses import dataclass
from functools import lru_cache

import numpy as np

from autonomous_hvac_stage1.evaluation import ComfortSchedule
from autonomous_hvac_stage1.g218 import CAMPAIGN
from core import integrate
from energy_savings_g174_v1.policy import ARCHIVE, DURATION, ON, RECOVERY
from stage4e_d0.plan import COOL, FAN, FLAGS, OCC, SET, STEP, TEMP
from stage4e_d1r.proposed_validation import finite
from stage4e_d2i_1.common import read, require, sha

OUTDOOR = "zon_weaSta_reaWeaTDryBul_y"
SOLAR = "zon_weaSta_reaWeaHGloHor_y"
HOLD = DURATION // STEP
STEPS = (DURATION + RECOVERY) // STEP
HOURS = STEP / 3600
RIDGE = 4.0
MIN_GAIN_KWH = 0.0225
TEMP_RESERVE_C = 0.5
FEATURES = ("indoor_offset_c", "outdoor_c", "solar_kw_m2", "cooling_kw", "fan_kw",
            "issued_outdoor_change_30min_c", "issued_solar_change_30min_kw_m2")
SCALES = np.array([.5, 8, .5, .5, .03, 3, .4])


@dataclass(frozen=True)
class Inputs:
    origin: int
    features: tuple
    anchor: tuple


def make_inputs(origin, current, issued, native, schedule):
    """Construct the feature vector from the issued vintage and completed history only."""
    require(current["time"] == issued["issued_at_sim"] == origin, "Origin/forecast vintage mismatch")
    data = issued["data"]
    require(data["time"] == list(range(origin, origin + 1801, STEP)), "Forecast exceeds its issued horizon")
    require(not any(current[f] for f in FLAGS) and abs(current[SET] - 297.15) < 1e-5,
            "Action model requires occupied native 24°C at the origin")
    require(all(v > 0 for v in data[OCC]) and all(schedule.at(origin + i * STEP)[2] for i in range(STEPS + 1)),
            "Action model requires a continuously occupied hold and recovery schedule")
    times = native["time"]
    require(times[-1] == origin and times[0] <= origin - STEP and all(t <= origin for t in times),
            "Native power history is incomplete or contains a future sample")
    c, f = (integrate(times, native[k], origin - STEP, origin) / (STEP * 1000) for k in (COOL, FAN))
    indoor, outdoor = current[TEMP] - 273.15, current[OUTDOOR] - 273.15
    features = (indoor - 24, outdoor, current[SOLAR] / 1000, c, f,
                data["TDryBul"][6] - data["TDryBul"][0], (data["HGloHor"][6] - data["HGloHor"][0]) / 1000)
    return Inputs(origin, tuple(finite(x) for x in features), (indoor, c, f))


@dataclass(frozen=True)
class Episode:
    group: str
    inputs: Inputs
    native: np.ndarray
    warm: np.ndarray
    warm_peak_c: float


def _checks(path, names):
    files = read(path / "ARTIFACT_MANIFEST.json")["files"]
    require(all(sha(path / name) == files[name] for name in names), f"Archive hash mismatch at {path.name}")
    completed = read(path / "RUN_COMPLETED.json")
    require(completed["classification"] == "PASS_VALID_RAW" and completed["cleanup"] == "STOP_ACK_AND_REMOVAL_VERIFIED"
            and not completed.get("fabricated", completed.get("data_is_fabricated", True)), "Unverified model evidence")


def _outputs(native, origin, start):
    times = native["time"]
    i = (origin - start) // 30
    rows = []
    for j in range(i + 10, i + STEPS * 10 + 1, 10):
        peak = max(native[TEMP][j - 9:j + 1]) - 273.15
        temperature = native[TEMP][j] - 273.15
        power = [integrate(times[j - 10:j + 1], native[k][j - 10:j + 1], times[j - 10], times[j]) / (STEP * 1000)
                 for k in (COOL, FAN)]
        rows.append((temperature, *power, peak))
    return np.array(rows)


@lru_cache(maxsize=1)
def evidence():
    # Reuse the exact matched native references and warm arms. Never load a synthetic trace.
    from .live_dashboard import LIVE_BATCH, WARM_BATCH, WARM_TRACE, measured_g218

    matched = measured_g218(LIVE_BATCH)
    g174 = read(WARM_BATCH / "PAIRED_ENERGY_COMFORT.json")
    require(g174["delivered"] and g174["full_dose"] and g174["matched_before_first_action_and_weather"],
            "G174 warm/reference match is unverified")
    require(len(matched["windows"]) == len(g174["windows"]) == 3, "Incomplete intervention evidence")
    paths = (("G174", ARCHIVE, WARM_TRACE),
             ("G218", LIVE_BATCH / f"{CAMPAIGN}_A", LIVE_BATCH / f"{CAMPAIGN}_B"))
    schedule = ComfortSchedule.from_fmu()
    episodes = []
    for group, ref, acted in paths:
        for p in (ref, acted):
            _checks(p, ["whole_native_results.json", "endpoints.json", "RUN_COMPLETED.json",
                        *[f"forecast_{i:04d}.json" for i in (132, 420, 708)]])
        a, b = (read(p / "whole_native_results.json") for p in (ref, acted))
        require(a["time"] == b["time"], "Paired native clocks differ")
        start = a["time"][0]
        endpoints = {e["time"]: e for e in read(ref / "endpoints.json")}
        for day in range(3):
            origin = start + 86400 * day + ON
            i, f = (origin - start) // 30, (origin - start) // STEP
            flag = FLAGS[0]
            on = slice(i + 1, i + HOLD * 10 + 1)
            off = slice(i + HOLD * 10 + 1, i + STEPS * 10 + 1)
            require(all(b[flag][on]) and all(abs(k - 297.65) < 1e-5 for k in b[SET][on]) and not any(b[flag][off])
                    and not any(a[flag][i:i + STEPS * 10 + 1]), "Measured 45-minute hold/release missing")
            inputs = make_inputs(origin, endpoints[origin], read(ref / f"forecast_{f:04d}.json"),
                                 {k: a[k][i - 10:i + 1] for k in ("time", COOL, FAN)}, schedule)
            base, warm = (_outputs(n, origin, start) for n in (a, b))
            episodes.append(Episode(group, inputs, base[:, :3], warm[:, :3], float(warm[:, 3].max())))
    return tuple(episodes)


class ResponseModel:
    """Predictions for native and the measured 45-minute/120-minute trajectory only."""

    def __init__(self, episodes):
        values = np.array([row.inputs.features for row in episodes])
        self.center, self.lower, self.upper = values.mean(axis=0), values.min(axis=0), values.max(axis=0)
        x = (values - self.center) / SCALES
        offsets = np.array([r.native - r.inputs.anchor for r in episodes]).reshape(len(episodes), -1)
        self.baseline = offsets.mean(axis=0)
        self.beta = np.linalg.solve(x.T @ x + RIDGE * np.eye(len(FEATURES)), x.T @ (offsets - self.baseline))
        deltas = np.array([r.warm - r.native for r in episodes]).reshape(len(episodes), -1)
        self.increment = deltas.mean(axis=0)
        self.response_beta = np.linalg.solve(x.T @ x + 2 * RIDGE * np.eye(len(FEATURES)), x.T @ (deltas - self.increment))

    def predict(self, inputs, *, validate_support=True):
        x = np.array(inputs.features)
        if validate_support:
            # Allow small measurement/forecast variation around the observed envelope only.
            require(np.all(x >= self.lower - .1 * SCALES) and np.all(x <= self.upper + .1 * SCALES),
                    "Initial state or issued weather outside the measured response envelope")
        z = (x - self.center) / SCALES
        base = (self.baseline + z @ self.beta).reshape(STEPS, 3) + inputs.anchor
        warm = base + (self.increment + z @ self.response_beta).reshape(STEPS, 3)
        for values in (base, warm):
            values[:, 1:] = np.maximum(values[:, 1:], 0)
        return base, warm


def electricity(values):
    return values[:, 1:].sum(axis=0) * HOURS


@lru_cache(maxsize=1)
def qualification():
    episodes = evidence()
    rows, errors, savings_errors, temperature_guards = [], [], [], []
    for test_group in sorted({r.group for r in episodes}):
        model = ResponseModel([r for r in episodes if r.group != test_group])
        for r in (e for e in episodes if e.group == test_group):
            native, warm = model.predict(r.inputs, validate_support=False)
            forecast = electricity(native).sum() - electricity(warm).sum()
            actual = electricity(r.native).sum() - electricity(r.warm).sum()
            delta = np.array([native - r.native, warm - r.warm])
            errors.append(delta)
            savings_errors.append(abs(forecast - actual))
            temperature_guards.append(r.warm_peak_c > 26 and max(warm[:, 0]) + TEMP_RESERVE_C < 26)
            rows.append(dict(group=r.group, origin=r.inputs.origin, predicted_saved_kwh=float(forecast),
                             measured_saved_kwh=float(actual), measured_warm_peak_c=r.warm_peak_c,
                             predicted_warm_peak_c=float(max(warm[:, 0])), ranking_correct=bool((forecast > 0) == (actual > 0))))
    errors = np.array(errors)
    temp = errors[:, :, :, 0]
    energy_errors = errors[:, :, :, 1:].sum(axis=2) * HOURS
    horizons = {}
    for minutes in range(5, STEPS * 5 + 1, 5):
        i = minutes // 5 - 1
        sample = temp[:, :, i]
        energy = errors[:, :, :i + 1, 1:].sum(axis=2) * HOURS
        horizons[minutes] = dict(temperature_mae_c=float(abs(sample).mean()), temperature_rmse_c=float(np.sqrt((sample**2).mean())),
                                 cooling_mae_kwh=float(abs(energy[:, :, 0]).mean()), fan_mae_kwh=float(abs(energy[:, :, 1]).mean()))
    metrics = dict(temperature_mae_c=float(abs(temp).mean()), temperature_rmse_c=float(np.sqrt((temp**2).mean())),
                   max_error_c=float(abs(temp).max()), cooling_mae_kwh=float(abs(energy_errors[:, :, 0]).mean()),
                   fan_mae_kwh=float(abs(energy_errors[:, :, 1]).mean()), max_net_savings_error_kwh=float(max(savings_errors)),
                   matched_peak_error_c=float(max(abs(r["measured_warm_peak_c"] - r["predicted_warm_peak_c"]) for r in rows)),
                   missed_upper_violations=sum(temperature_guards), correct_rankings=sum(r["ranking_correct"] for r in rows))
    gates = dict(thermal_resolution=(metrics["temperature_mae_c"] <= .25 and metrics["temperature_rmse_c"] <= .35
                                     and metrics["matched_peak_error_c"] <= TEMP_RESERVE_C),
                 savings_resolution=metrics["max_net_savings_error_kwh"] <= MIN_GAIN_KWH,
                 ranking=metrics["correct_rankings"] == len(rows), ceiling=not any(temperature_guards))
    return dict(qualified=all(gates.values()), gates=gates, metrics=metrics, horizons=horizons, episodes=rows,
                observed_peak_limit_c=max(r["measured_warm_peak_c"] for r in rows))
