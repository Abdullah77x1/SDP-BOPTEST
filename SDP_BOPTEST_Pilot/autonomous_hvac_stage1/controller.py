"""Stage 1 two-action controller. The authorized collector owns all BOPTEST calls."""

from dataclasses import dataclass

from energy_savings_g174_v1.policy import DURATION, ON, PROJECT_HOT_FALLBACK, RECOVERY, TARGET
from energy_savings_g174_v1.policy import command_guard as warm_guard
from stage4e_d0.plan import COOL, FAN, FLAG, FLAGS, OCC, SET, STEP, TEMP, native_command
from stage4e_d1r.proposed_validation import HEAT as HEATING_SETPOINT
from stage4e_d1r.proposed_validation import Violation, finite, near
from stage4e_d1_v2.validation import EventTracker, command_guard, endpoint, history, initial_native

VERSION = "SDP_AUTONOMOUS_HVAC_STAGE1_1.0.0"
DAY = 86400
MAX_ADVANCES = 864
MAX_ACTIONS = 3
COOLING_DEMAND_W = 10.0
MINIMUM_ENTRY_K = 294.90
MINIMUM_HOLD_K = 294.65
CONTEXT_FIELDS = ("time", TEMP, COOL, FAN, SET, HEATING_SETPOINT, *FLAGS)


@dataclass(frozen=True)
class Decision:
    origin: int
    warmer: bool
    reason: str
    advance: bool = True
    fallback: bool = False

    @property
    def command(self):
        """Native is four zero activation flags; only warm requests carry a target."""
        command = native_command()
        if self.warmer:
            command.update({FLAG: 1, SET: TARGET})
        return command


@dataclass(frozen=True)
class VerifiedInterval:
    decision: Decision
    actual_cooling_k: float
    cooling_override_active: bool

    @property
    def end(self):
        return self.decision.origin + STEP


def _check_powers(observation):
    for signal in (COOL, FAN):
        if finite(observation.get(signal)) < -1e-6:
            raise Violation(f"negative_electrical_power:{signal}")


def _check_delivery(origin, command, chunk):
    history(chunk, origin, origin + STEP)
    for i, stamp in enumerate(chunk["time"]):
        if stamp <= origin:
            continue  # At the origin BOPTEST can retain the previous command side.
        if any(chunk[flag][i] != command[flag] for flag in FLAGS):
            raise Violation("native_interval_flags_do_not_match_command")
        if command[FLAG] and not near(chunk[SET][i], TARGET):
            raise Violation("native_interval_target_does_not_match_command")


class EnergyController:
    """One proposal in flight. State and recovery advance only on verified readbacks."""

    def __init__(self, start, end):
        if (type(start) is not int or type(end) is not int or start < 0
                or start % STEP or end % STEP or not 0 < end - start <= MAX_ADVANCES * STEP):
            raise ValueError("Expected a nonempty window of at most 864 five-minute steps")
        self.next_origin = start
        self.end = end
        self.stop_reason = None
        self._pending = None
        self._last_origin = None
        self._confirmed_endpoint = None
        self._last_response_receipt = 0
        self._hold_until = None
        self._recover_until = None
        self._last_attempt_day = None
        self._selected = 0
        self._events = EventTracker()

    def abort(self, reason):
        """Latch stop after lost, missing or unverifiable transport feedback."""
        if self.stop_reason is None:
            self.stop_reason = str(reason)
        self._pending = None

    @property
    def pending_event_time(self):
        """Exact native transition that requires a read-only follow-up history."""
        pending = self._events.pending
        return pending["event_time"] if pending is not None else None

    def decide(self, origin, current, boundary, *, age_s, receipts):
        """Consume a current issued boundary and current readback, plus causal receipts.

        receipts is (observation, boundary forecast, decision cutoff). The next
        endpoint, history and response receipt belong exclusively to confirm().
        """
        if self.stop_reason is not None:
            return Decision(origin, False, self.stop_reason, advance=False)
        try:
            if self._pending is not None or type(origin) is not int or origin != self.next_origin:
                raise Violation("unexpected_origin_or_missing_previous_verification")
            if origin >= self.end:
                return Decision(origin, False, "window_complete", advance=False)
            if (len(receipts) != 3 or any(type(order) is not int for order in receipts)
                    or not 0 < receipts[0] < receipts[1] < receipts[2]
                    or receipts[0] < self._last_response_receipt):
                raise Violation("invalid_or_future_origin_receipt")
            command_guard(native_command(), current, boundary, origin, age_s)
            _check_powers(current)
            context = {key: current[key] for key in CONTEXT_FIELDS}
            if self._confirmed_endpoint is None:
                initial_native(context)
            elif context != self._confirmed_endpoint:
                raise Violation("current_state_differs_from_verified_endpoint")
            decision = self._select(origin, context, boundary, age_s)
            self._events.guard(origin, decision.command, current, age_s, (self.end - origin) // STEP)
        except (ValueError, TypeError, KeyError, AttributeError) as error:
            self.abort(error)
            return Decision(origin, False, self.stop_reason, advance=False,
                            fallback=self._hold_until is not None)
        self._pending = (decision, context, age_s, tuple(receipts))
        if decision.warmer and self._hold_until is None:
            self._last_attempt_day = origin // DAY
            self._selected += 1
        return decision

    def _select(self, origin, context, boundary, age_s):
        active = self._hold_until is not None
        if active and origin >= self._hold_until:
            return Decision(origin, False, "scheduled_release")
        if self._recover_until is not None and origin < self._recover_until:
            return Decision(origin, False, "native_recovery_lockout")

        phase = origin % DAY
        close = origin - phase + ON + DURATION
        if not ON <= phase < ON + DURATION or close + RECOVERY > self.end:
            return Decision(origin, False, "outside_qualified_window_or_recovery_budget")
        if not active and (self._last_attempt_day == origin // DAY or self._selected >= MAX_ACTIONS):
            return Decision(origin, False, "action_budget_exhausted")
        if boundary[OCC] <= 0:
            return Decision(origin, False, "unoccupied", fallback=active)

        prior = self._last_origin
        if prior is None or prior["time"] + STEP != origin:
            return Decision(origin, False, "no_verified_five_minute_history", fallback=active)
        if not active and (min(context[COOL], prior[COOL]) < COOLING_DEMAND_W or context[FAN] <= 0):
            return Decision(origin, False, "no_sustained_cooling")
        if context[TEMP] < (MINIMUM_HOLD_K if active else MINIMUM_ENTRY_K):
            return Decision(origin, False, "cold_margin", fallback=active)

        one_step_rise = max(0.0, context[TEMP] - prior[TEMP])
        if context[TEMP] + one_step_rise >= PROJECT_HOT_FALLBACK:
            return Decision(origin, False, "hot_margin_or_rising_trend", fallback=active)

        wanted = Decision(origin, True, "hold" if active else "sustained_cooling_with_headroom")
        try:
            warm_guard(wanted.command, context, boundary, origin, age_s)
        except ValueError:
            return Decision(origin, False, "qualified_warm_guard_veto", fallback=active)
        return wanted

    def confirm(self, decision, observation, issued_next_boundary, *, response_receipt,
                native_history, event_history=None, history_receipt=None):
        """Verify effective command and native interval before crediting delivery.

        issued_next_boundary is the t+300 boundary from the vintage issued at t.
        event_history is an additional read-only result when the native event
        tracker requires the registered two-interval follow-up.
        """
        try:
            if self.stop_reason is not None or self._pending is None or decision is not self._pending[0]:
                raise Violation("unexpected_command_verification")
            expected, context, age, receipts = self._pending
            origin = expected.origin
            orders = dict(zip(("observation", "forecast", "cutoff", "response"), (*receipts, response_receipt)))
            result = endpoint(origin, expected.command, observation, issued_next_boundary, orders, age)
            _check_powers(observation)
            _check_delivery(origin, expected.command, native_history)
            if self._events.pending is not None:
                if event_history is None or history_receipt is None:
                    raise Violation("missing_required_event_followup")
                self._events.resolve(event_history, observation, result, response_receipt, history_receipt)
            self._events.register(observation, result, response_receipt)
            if origin + STEP == self.end and self._events.pending is not None:
                raise Violation("unresolved_event_at_end_of_budget")
        except (ValueError, TypeError, KeyError, AttributeError) as error:
            self.abort(error)
            raise Violation(str(error)) from error

        if expected.warmer and self._hold_until is None:
            self._hold_until = origin - origin % DAY + ON + DURATION
        elif not expected.warmer and self._hold_until is not None:
            self._hold_until = None
            self._recover_until = origin + RECOVERY

        self._last_origin = context
        self._confirmed_endpoint = {key: observation[key] for key in CONTEXT_FIELDS}
        self._last_response_receipt = response_receipt
        self.next_origin = origin + STEP
        self._pending = None
        return VerifiedInterval(expected, observation[SET], bool(observation[FLAG]))

