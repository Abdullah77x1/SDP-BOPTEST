"""Policy choices for the final demo. Stage 1 and the G218 authorization stay frozen."""

from dataclasses import dataclass

from autonomous_hvac_stage1.controller import DAY, MINIMUM_ENTRY_K, Decision, EnergyController
from autonomous_hvac_stage1.g218 import NativeController
from energy_savings_g174_v1.policy import ON, PROJECT_HOT_FALLBACK, command_guard
from stage4e_d0.plan import TEMP

VERSION = "SDP_FINAL_ENERGY_POLICIES_1.0"
WARM_CANDIDATES_C = (24.5, 25.0, 25.5, 26.0)
QUALIFIED_WARMER_C = 24.5


@dataclass(frozen=True)
class Candidate:
    target_c: float
    qualified: bool
    reason: str


def candidates():
    return (
        Candidate(24.0, True, "native occupied thermostat"),
        Candidate(24.5, True, "qualified only within the Stage 1 guard and clock envelope"),
        Candidate(25.0, False, "requires separate matched response and safety qualification"),
        Candidate(25.5, False, "no qualified response under the current occupied temperature guard"),
        Candidate(26.0, False, "above the current guard; no qualified margin or response"),
    )


class FixedWarmer(EnergyController):
    """Schedule the warmer request at 11:00, with the same safety guard as Stage 1."""

    def __init__(self, start, end, target_c=QUALIFIED_WARMER_C):
        if type(target_c) not in (int, float) or target_c not in WARM_CANDIDATES_C:
            raise ValueError("Choose an explicitly configured warmer candidate")
        super().__init__(start, end)
        self.target_c = target_c

    def _select(self, origin, context, boundary, age_s):
        if self.target_c != QUALIFIED_WARMER_C:
            return Decision(origin, False, "candidate_requires_separate_qualification")
        # Delegate recovery, duration, clock, occupancy, safety and continuation.
        decision = super()._select(origin, context, boundary, age_s)
        if self._hold_until is None and origin % DAY != ON:
            return decision if not decision.warmer else Decision(origin, False, "fixed_schedule_inactive")
        if decision.warmer and self._hold_until is None:
            return Decision(origin, True, "fixed_scheduled_request_with_headroom")
        if decision.reason != "no_sustained_cooling":
            return decision

        # Demand decides the economics of Stage 1 entry. For this comparator
        # drop that gate alone, keeping the remaining Stage 1 safety checks.
        current = context[TEMP]
        if current < MINIMUM_ENTRY_K:
            return Decision(origin, False, "cold_margin")
        if current + max(0, current - self._last_origin[TEMP]) >= PROJECT_HOT_FALLBACK:
            return Decision(origin, False, "hot_margin_or_rising_trend")
        requested = Decision(origin, True, "fixed_scheduled_request_with_headroom")
        try:
            command_guard(requested.command, context, boundary, origin, age_s)
        except ValueError:
            return Decision(origin, False, "qualified_warm_guard_veto")
        return requested


def make_controller(strategy, start, end, *, fixed_c=QUALIFIED_WARMER_C):
    if strategy == "native":
        return NativeController(start, end)
    if strategy == "autonomous":
        return EnergyController(start, end)
    if strategy == "fixed":
        return FixedWarmer(start, end, fixed_c)
    raise ValueError(f"Unknown controller strategy: {strategy}")

