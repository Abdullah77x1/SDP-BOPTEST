"""Prospective 400 W morning screen for the frozen Stage 1 controller."""

from core import integrate
from energy_savings_g174_v1.policy import DURATION, ON
from stage4e_d0.plan import COOL, STEP
from stage4e_d1r.proposed_validation import finite

from .controller import DAY, Decision, EnergyController

VERSION = "SDP_AUTONOMOUS_HVAC_G400_1.0.0"
MORNING_START = 10 * 3600 + 25 * 60
MORNING_END = 10 * 3600 + 55 * 60
NATIVE_STEP = 30
CUTOFF_W = 400.0


def morning_times(day_start):
    return range(day_start + MORNING_START, day_start + MORNING_END + 1, NATIVE_STEP)


def mean_cooling_w(timestamps, powers):
    """Use the archived study's trapezoid mean on an exact 61-sample grid."""
    values = [finite(powers[t]) for t in timestamps]
    if min(values) < -1e-6:
        raise ValueError("invalid_cooling_power")
    return integrate(timestamps, values, timestamps[0], timestamps[-1]) / (MORNING_END - MORNING_START)


class GuardedController(EnergyController):
    def __init__(self, start, end):
        super().__init__(start, end)
        self._morning_samples = {}
        self._daily_screen = None
        self._cutoff_receipt = None
        self.morning_guard_evidence = None

    def accept_verified_history(self, origin, chunk, receipt):
        """Called by the collector only after Stage 1 confirms delivery of this interval."""
        day_start = origin - origin % DAY
        timestamps = morning_times(day_start)
        for stamp, power in zip(chunk["time"], chunk[COOL], strict=True):
            if origin < stamp <= origin + STEP and stamp in timestamps:
                # Use the same ending-side sample as the combined native trace.
                self._morning_samples.setdefault(stamp, (power, receipt))

    def decide(self, origin, current, boundary, *, age_s, receipts):
        self.morning_guard_evidence = None
        self._cutoff_receipt = receipts[2] if len(receipts) == 3 else None
        return super().decide(origin, current, boundary, age_s=age_s, receipts=receipts)

    def _screen(self, day_start):
        timestamps = morning_times(day_start)
        available = {t: self._morning_samples[t] for t in timestamps if t in self._morning_samples}
        mean, receipt = None, None
        if len(available) != len(timestamps):
            reason = "g400_missing_or_stale_morning_history"
        elif any(type(order) is not int or not 0 < order < self._cutoff_receipt
                 for _, order in available.values()):
            reason = "g400_unverified_morning_receipt"
        else:
            receipt = max(order for _, order in available.values())
            try:
                mean = mean_cooling_w(timestamps, {t: power for t, (power, _) in available.items()})
                reason = "g400_high_morning_demand" if mean >= CUTOFF_W else "g400_morning_demand_below_cutoff"
            except (TypeError, ValueError):
                reason = "g400_invalid_morning_power"
        return dict(day_start_s=day_start, window_start_s=timestamps[0], window_end_s=timestamps[-1],
                    samples=len(available), last_history_receipt=receipt, mean_cooling_w=mean,
                    screen_permits=mean is not None and mean < CUTOFF_W, screen_reason=reason)

    def _select(self, origin, context, boundary, age_s):
        original = super()._select(origin, context, boundary, age_s)
        phase = origin % DAY
        if not ON <= phase < ON + DURATION or self._hold_until is not None:
            return original

        day_start = origin - phase
        if self._daily_screen is None or self._daily_screen["day_start_s"] != day_start:
            self._daily_screen = self._screen(day_start)
        screen = self._daily_screen
        blocked_start = original.warmer and not screen["screen_permits"]
        self.morning_guard_evidence = dict(screen, stage1_would_start=original.warmer,
                                           stage1_reason=original.reason, risk_veto=blocked_start)
        if blocked_start:
            return Decision(origin, False, screen["screen_reason"])
        return original
