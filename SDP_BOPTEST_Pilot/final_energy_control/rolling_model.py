"""Five-minute empirical dynamics for the measured BESTEST Air control sequences."""

from collections import Counter
from dataclasses import dataclass
from functools import lru_cache

import numpy as np

from autonomous_hvac_stage1.evaluation import ComfortSchedule
from core import integrate
from stage4e_d0.plan import COOL, FAN, FLAG, OCC, SET, TEMP
from stage4e_d2i_1.common import read, require, sha

from .optimizer_model import (DURATION, HOLD, HOURS, MIN_GAIN_KWH, ON, OUTDOOR, RECOVERY, SOLAR,
                              STEP, STEPS, TEMP_RESERVE_C, ResponseModel, _checks, evidence)

SCALES = np.array([.5, .4, .5, .035, 8, .5])
EXTRA = np.array([.12, .15, .12, .01, .8, .08])
SWITCH_KWH = .002
FIT_GROUPS = ("G174", "G218")
TERMINAL = ON + DURATION + RECOVERY


@dataclass(frozen=True)
class State:
    temperature: float
    trend: float
    cooling: float
    fan: float
    warmer: bool

    def features(self, weather):
        return np.array((self.temperature, self.trend, self.cooling, self.fan, *weather))


def observed_state(current, native):
    stamp = current["time"]
    times = native["time"]
    require(times[0] == stamp - STEP and times[-1] == stamp and all(t <= stamp for t in times),
            "A completed causal five-minute history is required")
    require(abs(current[SET] - (297.65 if current[FLAG] else 297.15)) <= 1e-5,
            "Applied setpoint is outside the measured occupied domain")
    indoor = current[TEMP] - 273.15
    mean = [integrate(times, native[k], stamp - STEP, stamp) / (STEP * 1000) for k in (COOL, FAN)]
    state = State(indoor, indoor - (native[TEMP][0] - 273.15), *mean, bool(current[FLAG]))
    require(np.isfinite(state.features((0, 0))).all(), "Nonfinite observed state")
    return state


def conditions(origin, current, issued, schedule):
    require(current["time"] == issued["issued_at_sim"] == origin, "Forecast vintage does not match the origin")
    data = issued["data"]
    horizon = TERMINAL - origin % 86400
    require(0 < horizon <= STEPS * STEP and data["time"] == list(range(origin, origin + 1801, STEP)),
            "Decision is outside the measured clock or issued forecast grid")
    require(all(v > 0 for v in data[OCC][:1 + min(6, horizon // STEP)])
            and all(schedule.at(t)[2] and abs(schedule.at(t)[1] - 297.15) <= 1e-5
                    for t in range(origin, origin + horizon + 1, STEP)), "Occupied native schedule does not qualify")
    weather = [(current[OUTDOOR] - 273.15, current[SOLAR] / 1000)]
    weather += [(t - 273.15, s / 1000) for t, s in zip(data["TDryBul"][1:], data["HGloHor"][1:], strict=True)]
    require(len(weather) == 7 and np.isfinite(weather).all(), "Weather vintage is invalid")
    return weather


@dataclass(frozen=True)
class Trace:
    group: str
    origin: int
    warm_path: bool
    states: tuple
    weather: tuple
    peaks: tuple


def _archive_trace(group, path, origin, warm_path, native, endpoints, schedule):
    start = native["time"][0]
    states, weather, peaks = [], [], []
    for index in range(STEPS + 1):
        t = origin + index * STEP
        j = (t - start) // 30
        current = endpoints[t]
        chunk = {key: native[key][j - 10:j + 1] for key in ("time", TEMP, COOL, FAN)}
        state = observed_state(current, chunk)
        require(state.warmer == (warm_path and 0 < index <= HOLD), "Unexpected actuation in archived sequence")
        states.append(state)
        if index < STEPS:
            forecast = read(path / f"forecast_{(t-start)//STEP:04d}.json")
            weather.append(conditions(t, current, forecast, schedule))
            peaks.append(max(native[TEMP][j + 1:j + 11]) - 273.15)
    return Trace(group, origin, warm_path, tuple(states), tuple(weather), tuple(peaks))


@lru_cache(maxsize=1)
def measured_traces():
    from autonomous_hvac_stage1 import g218

    from .live_dashboard import LIVE_BATCH, WARM_BATCH, WARM_TRACE
    from .optimizer_campaign import BATCH, CAMPAIGN
    from .optimizer_model import ARCHIVE

    evidence()  # Existing G174/G218 matched-evidence gate.
    measured = read(BATCH / "OPTIMIZER_COMPARISON.json")
    require(measured["technical_validation"] == "PASS" and measured["fabricated"] is False,
            "Independent G163 comparison is unavailable")
    require(sha(BATCH / "OPTIMIZER_COMPARISON.json") ==
            read(BATCH / "BATCH_ARTIFACT_MANIFEST.json")["files"]["OPTIMIZER_COMPARISON.json"],
            "G163 comparison does not match its seal")
    groups = (("G174", ARCHIVE, WARM_TRACE),
              ("G218", LIVE_BATCH / f"{g218.CAMPAIGN}_A", LIVE_BATCH / f"{g218.CAMPAIGN}_B"),
              ("G163", BATCH / f"{CAMPAIGN}_A", BATCH / f"{CAMPAIGN}_B"))
    schedule = ComfortSchedule.from_fmu()
    traces = []
    for group, native_path, warm_path in groups:
        for path, is_warm in ((native_path, False), (warm_path, True)):
            checked_files = ["whole_native_results.json", "endpoints.json", "RUN_COMPLETED.json"]
            checked_files += [f"forecast_{day * 288 + ON // STEP + i:04d}.json"
                              for day in range(3) for i in range(STEPS)]
            _checks(path, checked_files)
            native = read(path / "whole_native_results.json")
            endpoints = {row["time"]: row for row in read(path / "endpoints.json")}
            traces.extend(_archive_trace(group, path, native["time"][0] + day * 86400 + ON,
                                         is_warm, native, endpoints, schedule) for day in range(3))
    return tuple(traces)


def transition(path, phase):
    if not path:
        return "native"
    if phase == 0:
        return "start"
    if phase < HOLD:
        return "continue"
    return "release" if phase == HOLD else "recovery"


class StepModel:
    """Empirical single-zone state transition with pooled ridge slopes and measured phase means."""

    def __init__(self, traces):
        buckets = {(path, i): [] for path in (False, True) for i in range(STEPS)}
        for trace in traces:
            for i, current in enumerate(trace.states[:-1]):
                following = trace.states[i + 1]
                target = 24.5 if following.warmer else 24.0
                output = (following.temperature - target, following.cooling - current.cooling, following.fan - current.fan)
                buckets[trace.warm_path, i].append((current.features(trace.weather[i][0]), output))
        self.phase = {}
        centered_x, centered_y = [], []
        for key, rows in buckets.items():
            x, y = [np.asarray(values) for values in zip(*rows, strict=True)]
            self.phase[key] = (x.mean(axis=0), y.mean(axis=0), x.min(axis=0), x.max(axis=0))
            centered_x.extend((x - x.mean(axis=0)) / SCALES)
            centered_y.extend(y - y.mean(axis=0))
        x, y = np.array(centered_x), np.array(centered_y)
        self.beta = np.linalg.solve(x.T @ x + 1.5 * np.eye(len(SCALES)), x.T @ y)

    def supports(self, state, weather, path, phase):
        _, _, lower, upper = self.phase[path, phase]
        current = state.features(weather)
        return bool((current >= lower - EXTRA).all() and (current <= upper + EXTRA).all())

    def rollout(self, state, weather, path, phase, *, check_support=True):
        require(0 <= phase < STEPS, "Phase is outside the measured horizon")
        require(state.warmer == bool(path and 0 < phase <= HOLD), "Transition from this applied command is unsupported")
        if check_support:
            require(self.supports(state, weather[0], path, phase), "State or weather is outside the measured phase envelope")
        results = []
        for i in range(phase, STEPS):
            mean, response, _, _ = self.phase[path, i]
            future_weather = weather[min(i - phase, 6)]  # Hold the last issued conditions past +30 min.
            features = state.features(future_weather)
            offset, cooling_delta, fan_delta = response + ((features - mean) / SCALES) @ self.beta
            warm = path and i < HOLD
            temperature = (24.5 if warm else 24.0) + offset
            state = State(temperature, temperature - state.temperature, max(0.0, state.cooling + cooling_delta),
                          max(0.0, state.fan + fan_delta), warm)
            results.append((state.temperature, state.cooling, state.fan))
        require(np.isfinite(results).all(), "Nonfinite rollout")
        return np.array(results)


def _values(trace, phase):
    return np.array([(s.temperature, s.cooling, s.fan) for s in trace.states[phase + 1:]])


def _rejoin(native, warm):
    streak = 0
    for i in range(HOLD - 1, STEPS):
        quiet = abs(native[i, 0] - warm[i, 0]) <= .05 and abs((native[i, 1:] - warm[i, 1:]).sum()) <= .01
        streak = streak + 1 if quiet else 0
        if streak == 3:
            return (i - HOLD - 1) * 5
    return None


def _evaluate(model, traces):
    errors = {"one_step": [], "30_min": [], "60_min": [], "165_min": []}
    step_errors, counts, ranking, recovery, missed = {}, Counter(), [], [], 0
    predictions = {}
    excluded = 0
    for trace in traces:
        for i, vintage in enumerate(trace.weather):
            state = trace.states[i]
            if not model.supports(state, vintage[0], trace.warm_path, i):
                excluded += 1
                continue
            prediction = model.rollout(state, vintage, trace.warm_path, i)
            actual = _values(trace, i)
            delta = prediction - actual
            key = transition(trace.warm_path, i)
            counts[key] += 1
            step_errors.setdefault(key, []).append(delta[0])
            missed += int(max(trace.peaks[i:]) > 26 and prediction[:, 0].max() + TEMP_RESERVE_C < 26)
            for label, n in (("one_step", 1), ("30_min", 6), ("60_min", 12), ("165_min", STEPS)):
                if len(delta) >= n:
                    errors[label].append((delta[n-1, 0], *delta[:n, 1:].sum(axis=0) * HOURS))
            if i == 0:
                predictions[trace.origin, trace.warm_path] = (prediction, actual, state, vintage)
    for origin in sorted({key[0] for key in predictions}):
        if (origin, False) in predictions and (origin, True) in predictions:
            _, actual_native, native_state, _ = predictions[origin, False]
            warm, actual_warm, decision_state, vintage = predictions[origin, True]
            if not model.supports(decision_state, vintage[0], False, 0):
                continue
            # Both counterfactuals use the same decision state and issued weather.
            native = model.rollout(decision_state, vintage, False, 0)
            predicted_gain = float((native[:, 1:] - warm[:, 1:]).sum() * HOURS)
            actual_gain = float((actual_native[:, 1:] - actual_warm[:, 1:]).sum() * HOURS)
            ranking.append(dict(origin=origin, predicted_kwh=predicted_gain, actual_kwh=actual_gain,
                                measured_entry_temp_delta_c=decision_state.temperature - native_state.temperature,
                                correct=(predicted_gain > 0) == (actual_gain > 0)))
            recovery.append(dict(origin=origin, predicted_min=_rejoin(native, warm), actual_min=_rejoin(actual_native, actual_warm),
                                 predicted_kwh=float((warm[HOLD:, 1:] - native[HOLD:, 1:]).sum() * HOURS),
                                 actual_kwh=float((actual_warm[HOLD:, 1:] - actual_native[HOLD:, 1:]).sum() * HOURS)))

    def metrics(values):
        if not values:
            return None
        values = np.asarray(values)
        return dict(n=len(values), temp_mae_c=float(np.abs(values[:, 0]).mean()),
                    temp_rmse_c=float(np.sqrt(np.mean(values[:, 0]**2))),
                    cooling_mae_kwh=float(np.abs(values[:, 1]).mean()), fan_mae_kwh=float(np.abs(values[:, 2]).mean()))

    transitions = {k: metrics([(t, c * HOURS, f * HOURS) for t, c, f in rows]) for k, rows in step_errors.items()}
    return dict(horizons={label: metrics(rows) for label, rows in errors.items()}, transitions=transitions,
                excluded=excluded, counts=dict(counts), ranking=ranking, recovery=recovery, missed_hot_forecasts=missed,
                actual_hot_intervals=sum(sum(p > 26 for p in t.peaks) for t in traces))


@lru_cache(maxsize=1)
def calibrated_rolling():
    traces = measured_traces()
    training = tuple(t for t in traces if t.group in FIT_GROUPS)
    model = StepModel(training)
    model.entry_reference = ResponseModel(evidence())
    folds = {group: _evaluate(StepModel([t for t in training if t.group != group]), [t for t in training if t.group == group])
             for group in FIT_GROUPS}
    folds["G163"] = _evaluate(model, [t for t in traces if t.group == "G163"])
    # G163 is independent of the actual two-scenario fit. Single-scenario folds diagnose
    # envelope coverage but do not qualify deployment of a different fitted model.
    independent = folds["G163"]
    ranking = independent["ranking"]
    uncertainty = max((abs(r["predicted_kwh"] - r["actual_kwh"]) for r in ranking), default=None)
    scores = independent["horizons"]
    thermal = bool(scores["one_step"] and scores["one_step"]["temp_mae_c"] <= .25
                   and scores["30_min"] and scores["30_min"]["temp_rmse_c"] <= .35
                   and not independent["missed_hot_forecasts"])
    ranked = len(ranking) >= 2 and all(r["correct"] for r in ranking)
    recovery = all(r["actual_min"] is not None and r["predicted_min"] is not None
                   and abs(r["actual_min"] - r["predicted_min"]) <= 20
                   for r in independent["recovery"])
    horizon_ok = bool(scores["165_min"] and scores["165_min"]["temp_rmse_c"] <= .35)
    coverage = all(independent["counts"].get(name, 0) >= 2 for name in ("native", "start", "continue", "release", "recovery"))
    gate = dict(thermal=thermal, ranked=ranked, recovery=recovery, horizon=horizon_ok,
                coverage=coverage, paired_energy=uncertainty is not None and uncertainty <= MIN_GAIN_KWH)
    observed_peak = max(p for t in training if t.warm_path for p in t.peaks)
    return model, dict(qualified=all(gate.values()), gates=gate, folds=folds, uncertainty_kwh=uncertainty,
                       observed_peak_c=observed_peak, maximum_horizon_min=STEPS * 5)
