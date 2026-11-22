"""Pure contracts, integration and scheduling; no network calls at import."""
from __future__ import annotations
import math

TEMP = "zon_reaTRooAir_y"
OUTDOOR = "zon_weaSta_reaWeaTDryBul_y"
COOL = "fcu_reaPCoo_y"
FAN = "fcu_reaPFan_y"
HEAT = "fcu_reaPHea_y"
COOL_U = "con_oveTSetCoo_u"
COOL_A = "con_oveTSetCoo_activate"
FLAGS = [COOL_A, "con_oveTSetHea_activate", "fcu_oveFan_activate", "fcu_oveTSup_activate"]
CORE = [TEMP, OUTDOOR, COOL, FAN, HEAT]


def celsius(kelvin):
    if not math.isfinite(float(kelvin)):
        raise ValueError("Nonfinite temperature")
    return float(kelvin) - 273.15


def validate(observation, previous=None, step=300):
    for key in ["time", *CORE]:
        value = observation.get(key)
        if not isinstance(value, (int, float)) or isinstance(value, bool) or not math.isfinite(value):
            raise ValueError(f"Missing/nonfinite required observation: {key}")
    if previous is not None and abs(observation["time"] - previous - step) > 1e-6:
        raise ValueError("Duplicate, missing or nonmonotonic interval")
    if not 200 < observation[TEMP] < 350 or not 150 < observation[OUTDOOR] < 350:
        raise ValueError("Temperature SI range violation")
    if observation[COOL] < -1e-6 or observation[FAN] < -1e-6:
        raise ValueError("Negative electricity")


def require_metadata(meta):
    for key in CORE:
        expected = "K" if key in (TEMP, OUTDOOR) else "W"
        if key not in meta["measurements"] or meta["measurements"][key].get("Unit") != expected:
            raise ValueError(f"Measurement metadata mismatch: {key}")
    for key in FLAGS + [COOL_U]:
        if key not in meta["inputs"]:
            raise ValueError(f"Missing input: {key}")
    if meta["inputs"][COOL_U].get("Unit") != "K":
        raise ValueError("Cooling setpoint must use kelvin")
    bounds = meta["inputs"][COOL_U]
    if not bounds.get("Minimum", -math.inf) <= 298.15 <= bounds.get("Maximum", math.inf):
        raise ValueError("Intervention outside input limits")


def commands(mode, interval_start, plan):
    command = dict.fromkeys(FLAGS, 0)
    if mode == "intervention" and plan["pulse_start"] <= interval_start < plan["pulse_end"]:
        command.update({COOL_U: plan["native_occupied_cooling_k"] + 1, COOL_A: 1})
    elif mode not in ("baseline", "intervention"):
        raise ValueError("Unknown controller mode")
    return command


def integrate(times, values, start, end):
    """Trapezoid integral, clipped with linear endpoint interpolation. Units value*s."""
    if len(times) != len(values) or len(times) < 2:
        raise ValueError("Incomplete integration series")
    if start < times[0] or end > times[-1] or start >= end:
        raise ValueError("Integration window outside evidence")
    total = 0.0
    for i in range(1, len(times)):
        a, b = times[i-1], times[i]
        va, vb = values[i-1], values[i]
        if b < a or not all(math.isfinite(float(x)) for x in (a, b, va, vb)):
            raise ValueError("Invalid integration data")
        if b == a:
            continue  # Native solver event samples can share a timestamp, with zero duration.
        lo, hi = max(a, start), min(b, end)
        if hi > lo:
            left = va + (vb-va)*(lo-a)/(b-a)
            right = va + (vb-va)*(hi-a)/(b-a)
            total += (left+right)*0.5*(hi-lo)
    return total


class Scheduler:
    """No catch-up bursts: pause/resume and slow requests cannot queue duplicate steps."""
    def __init__(self):
        self.running = False
        self.mode = "accelerated"
        self.due = None

    def start(self, now, mode):
        if mode not in ("accelerated", "realtime"):
            raise ValueError("Unknown pace")
        self.mode, self.running = mode, True
        self.due = now if mode == "accelerated" else now + 300

    def pause(self):
        self.running = False

    def ready(self, now):
        return self.running and self.due is not None and now >= self.due

    def complete(self, now, began):
        self.due = now + 0.2 if self.mode == "accelerated" else max(began + 300, now)


def observed_features(row, metadata):
    """Strict allowlist: forecast payloads, labels and simulated future values cannot enter."""
    return {key: row[key] for key in metadata["measurements"] if key in row}


class PredictionInterfaces:
    """Explicit extension points; never fabricate predictions."""
    def ml_predict(self, observed_history):
        raise NotImplementedError("No ML model trained")

    def rc_predict(self, observed_history, proposed_actions):
        raise NotImplementedError("No RC model identified")

    def optimize(self, predictions, constraints):
        raise NotImplementedError("No optimizer implemented")
