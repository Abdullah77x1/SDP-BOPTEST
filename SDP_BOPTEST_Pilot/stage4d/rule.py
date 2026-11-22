"""Deterministic current-information cooling rule. No network or prediction access."""
from dataclasses import asdict, dataclass
import math
from core import COOL_A, COOL_U, FLAGS


def finite(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def current_boundary(payload, expected_time):
    times = payload.get("time", [])
    matches = [i for i, t in enumerate(times) if finite(t) and abs(t-expected_time) <= 1e-6]
    if len(matches) != 1:
        raise ValueError("Missing, stale or ambiguous current schedule timestamp")
    i = matches[0]
    # Never read a later index, even if an API returns additional future boundary points.
    result = {key: payload[key][i] for key in ("LowerSetp[1]", "UpperSetp[1]", "Occupancy[1]")}
    if not all(finite(v) for v in result.values()):
        raise ValueError("Invalid current comfort/occupancy data")
    return result


@dataclass(frozen=True)
class Context:
    expected_time: float
    observation_time: float
    boundary_time: float
    observed_monotonic: float
    decision_monotonic: float
    indoor_k: float
    lower_k: float
    upper_k: float
    occupancy: float
    heating_setpoint_k: float
    actuator_min_k: float
    actuator_max_k: float


@dataclass(frozen=True)
class Decision:
    time: float
    active: bool
    requested_k: float | None
    reason: str
    fatal: bool = False

    def command(self):
        command = dict.fromkeys(FLAGS, 0)
        if self.active:
            command.update({COOL_A: 1, COOL_U: self.requested_k})
        return command

    def to_dict(self):
        return asdict(self)


class ComfortRule:
    def __init__(self, settings):
        self.settings = dict(settings)
        self.active = False
        self.last_switch_time = None

    def release(self, now, reason, fatal=False):
        if self.active:
            self.last_switch_time = now
        self.active = False
        return Decision(now, False, None, reason, fatal)

    def decide(self, context: Context, final_release=False):
        c, p = context, self.settings
        if not all(finite(v) for v in asdict(c).values()):
            return self.release(c.expected_time, "invalid_or_missing_observation", True)
        if abs(c.observation_time-c.expected_time) > 1e-6 or abs(c.boundary_time-c.expected_time) > 1e-6:
            return self.release(c.expected_time, "stale_or_future_simulation_timestamp", True)
        age = c.decision_monotonic-c.observed_monotonic
        if age < 0 or age > p["maximum_wall_age_seconds"]:
            return self.release(c.expected_time, "stale_or_future_wall_timestamp", True)
        if not (200 < c.indoor_k < 350 and 250 < c.lower_k <= c.upper_k < 330
                and c.occupancy >= 0 and c.actuator_min_k < c.actuator_max_k
                and 250 < c.heating_setpoint_k < 330):
            return self.release(c.expected_time, "invalid_operating_requirements", True)
        if self.last_switch_time is not None and c.expected_time < self.last_switch_time:
            return self.release(c.expected_time, "nonmonotonic_controller_time", True)
        if final_release:
            return self.release(c.expected_time, "final_budget_native_release")
        if c.occupancy == 0:
            return self.release(c.expected_time, "unoccupied_native_control")
        target = c.upper_k-p["target_margin_k"]
        safe_min = max(c.lower_k+p["minimum_heat_cool_deadband_k"],
                       c.heating_setpoint_k+p["minimum_heat_cool_deadband_k"], c.actuator_min_k)
        if not safe_min <= target <= min(c.upper_k, c.actuator_max_k):
            return self.release(c.expected_time, "no_feasible_comfort_safe_override")
        elapsed = math.inf if self.last_switch_time is None else c.expected_time-self.last_switch_time
        if self.active:
            if elapsed >= p["minimum_on_seconds"] and c.indoor_k <= c.upper_k-p["release_margin_k"]:
                return self.release(c.expected_time, "hysteresis_release")
            return Decision(c.expected_time, True, target,
                            "minimum_on_dwell" if elapsed < p["minimum_on_seconds"] else "hysteresis_hold")
        if elapsed < p["minimum_off_seconds"]:
            return Decision(c.expected_time, False, None, "minimum_off_dwell_native_control")
        if c.indoor_k >= c.upper_k-p["activation_margin_k"]:
            self.active, self.last_switch_time = True, c.expected_time
            return Decision(c.expected_time, True, target, "near_upper_bound_activate")
        return Decision(c.expected_time, False, None, "below_activation_threshold_native_control")


def validate_command(decision, context, settings):
    command = decision.command()
    if any(command[k] != 0 for k in FLAGS if k != COOL_A):
        raise ValueError("Conflicting non-cooling override")
    if decision.active:
        target = command[COOL_U]
        if not (finite(target) and context.occupancy > 0
                and context.actuator_min_k <= target <= context.actuator_max_k
                and context.lower_k <= target <= context.upper_k
                and target >= context.heating_setpoint_k+settings["minimum_heat_cool_deadband_k"]):
            raise ValueError("Unsafe cooling command")
    return command
