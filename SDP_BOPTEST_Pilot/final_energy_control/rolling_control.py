"""Five-minute replanning within the measured sequences and original actuator guards."""

from dataclasses import asdict

from autonomous_hvac_stage1.controller import DAY, Decision, EnergyController
from autonomous_hvac_stage1.evaluation import ComfortSchedule
from autonomous_hvac_stage1.guard400 import GuardedController
from energy_savings_g174_v1.policy import PROJECT_HOT_FALLBACK
from stage4e_d2i_1.common import require

from .optimizer_model import make_inputs
from .rolling_model import (HOLD, HOURS, MIN_GAIN_KWH, ON, STEP, STEPS, SWITCH_KWH, TERMINAL,
                            TEMP_RESERVE_C, conditions, observed_state, transition)

VERSION = "SDP_HVAC_ROLLING_1.0.0"
SESSION = "LIVE_ROLLING_TWIN_01"
STATUS = "EXPLICITLY_AUTHORIZED_LIVE_ROLLING_TWIN_01"


class RollingController(GuardedController):
    release_requested = False

    def __init__(self, start, end, *, model, validation, issued, record, use_400w=False):
        super().__init__(start, end)
        self.model, self.validation, self.issued, self.record = model, validation, issued, record
        self.schedule = ComfortSchedule.from_fmu()
        self.use_400w = use_400w
        self.history = None

    def accept_verified_history(self, origin, chunk, receipt):
        if self.use_400w:
            super().accept_verified_history(origin, chunk, receipt)
        self.history = (chunk, receipt)

    def decide(self, origin, current, boundary, *, age_s, receipts):
        self.current, self.receipts = current, receipts
        return super().decide(origin, current, boundary, age_s=age_s, receipts=receipts)

    def _prediction(self, candidate, state, weather, path, phase):
        trajectory = self.model.rollout(state, weather, path, phase)
        peak, minimum = float(trajectory[:, 0].max()), float(trajectory[:, 0].min())
        cooling, fan = [float(x) for x in trajectory[:, 1:].sum(axis=0) * HOURS]
        start_recovery = max(0, HOLD - phase)
        recovery = float(trajectory[start_recovery:, 1:].sum() * HOURS) if path else None
        next_temp, next_cool, next_fan = [float(x) for x in trajectory[0]]
        candidate.update(valid=True, transition=transition(path, phase), prediction=dict(
            peak_c=peak, minimum_c=minimum, margin_c=min(26 - peak, minimum - 20),
            cooling_kwh=cooling, fan_kwh=fan, combined_kwh=cooling + fan, recovery_kwh=recovery,
            next_temp_c=next_temp, next_cooling_kw=next_cool, next_fan_kw=next_fan,
            horizon_min=len(trajectory) * 5))
        if candidate["id"] == "A1":
            hold_peak = float(trajectory[:HOLD - phase, 0].max())
            if (hold_peak + TEMP_RESERVE_C >= PROJECT_HOT_FALLBACK - 273.15 or peak + TEMP_RESERVE_C >= 26
                    or minimum - TEMP_RESERVE_C <= 20 or peak > self.validation["observed_peak_c"]):
                candidate["reasons"].append("Predicted temperature exceeds the measured or reserved comfort margin")

    def _select(self, origin, context, boundary, age_s):
        stage1 = (super()._select(origin, context, boundary, age_s) if self.use_400w
                  else EnergyController._select(self, origin, context, boundary, age_s))
        active = self._hold_until is not None
        day_start = origin - origin % DAY
        phase = (origin % DAY - ON) // STEP
        recovering = self._recover_until is not None and origin < self._recover_until
        known_recovery = recovering and self._recover_until == day_start + TERMINAL
        candidates = [dict(id=i, valid=False, feasible=False, prediction=None, transition=None, reasons=[])
                      for i in ("A0", "A1")]
        native, warmer = candidates
        state, invalid = None, ""
        if 0 <= phase < STEPS:
            try:
                chunk, receipt = self.history
                issued = self.issued()
                require(0 < receipt < self.receipts[2] and issued["received_order"] == self.receipts[1],
                        "Forecast or history receipt was not available at the decision cutoff")
                state = observed_state(self.current, chunk)
                weather = conditions(origin, self.current, issued, self.schedule)
            except (KeyError, TypeError, ValueError, IndexError) as error:
                invalid = str(error) or "Required causal history unavailable"
        else:
            invalid = "Outside the measured 11:00–13:45 window"

        if active and phase < HOLD:
            native["reasons"].append("Early release is available for safety; its counterfactual is unqualified")
        elif recovering and not known_recovery:
            native["reasons"].append("Recovery after early release lacks matched evidence")
        elif invalid:
            native["reasons"].append(invalid)
        else:
            try:
                self._prediction(native, state, weather, active or known_recovery, phase)
            except (KeyError, ValueError, TypeError, IndexError) as error:
                native["reasons"].append(str(error))
        native["feasible"] = True  # The existing independent native command guard still applies.

        if not stage1.warmer:
            warmer["reasons"].append(stage1.reason)
        if self.release_requested:
            warmer["reasons"].append("Operator requested native release")
        if not active and phase != 0:
            warmer["reasons"].append("The recorded start is 11:00; later starts and warm reentry are disabled")
        if not self.validation["qualified"]:
            warmer["reasons"].append("Measured stepwise-model qualification failed")
        if invalid:
            warmer["reasons"].append(invalid)
        if not warmer["reasons"]:
            try:
                if phase == 0:
                    entry = make_inputs(origin, self.current, issued, chunk, self.schedule)
                    self.model.entry_reference.predict(entry)  # Preserve the frozen 11:00 entry envelope.
                self._prediction(warmer, state, weather, True, phase)
            except (KeyError, ValueError, TypeError, IndexError) as error:
                warmer["reasons"].append(str(error))
        if phase == 0 and warmer["valid"] and native["valid"]:
            savings = native["prediction"]["combined_kwh"] - warmer["prediction"]["combined_kwh"]
            conservative = savings - self.validation["uncertainty_kwh"] - SWITCH_KWH
            warmer["prediction"].update(predicted_savings_kwh=savings, conservative_savings_kwh=conservative)
            if conservative < MIN_GAIN_KWH:
                warmer["reasons"].append("Net saving after recovery, model uncertainty and switching cost is below 0.0225 kWh")
        elif phase == 0 and not native["valid"]:
            warmer["reasons"].append("An in-envelope native reference is required")
        warmer["feasible"] = warmer["valid"] and not warmer["reasons"]

        if self.release_requested:
            decision = Decision(origin, False, "operator_native_release")
        elif warmer["feasible"]:
            decision = Decision(origin, True, "rolling_continue" if active else "rolling_start_minimum_feasible_energy")
        elif active and stage1.warmer:
            decision = Decision(origin, False, "rolling_safety_or_model_validity_release", fallback=True)
        elif stage1.warmer:
            decision = Decision(origin, False, "rolling_native_selection")
        else:
            decision = stage1
        action = ("continue" if active else "start") if decision.warmer else ("release" if active else "native")
        self.record(dict(version=VERSION, origin=origin, selected="A1" if decision.warmer else "A0", action=action,
                         rolling_candidates=candidates, reason=decision.reason, cutoff=self.receipts[2],
                         state=asdict(state) if state else None,
                         remaining_hold_min=max(0, HOLD - phase) * 5 if decision.warmer else 0,
                         morning_guard=self.morning_guard_evidence))
        return decision
