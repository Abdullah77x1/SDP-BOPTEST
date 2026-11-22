"""Constrained enumeration of measured-response actions, with native fallback."""

from dataclasses import asdict, dataclass

from autonomous_hvac_stage1.controller import DAY, Decision, EnergyController
from autonomous_hvac_stage1.evaluation import ComfortSchedule
from autonomous_hvac_stage1.guard400 import GuardedController
from energy_savings_g174_v1.policy import ON, PROJECT_HOT_FALLBACK
from stage4e_d0.plan import STEP, TEMP

from .optimizer_model import HOLD, HOURS, MIN_GAIN_KWH, STEPS, TEMP_RESERVE_C, ResponseModel, electricity, evidence, make_inputs, qualification

VERSION = "SDP_HVAC_PREDICTIVE_1.0.0"


@dataclass(frozen=True)
class Action:
    id: str
    target_c: float | None
    minutes: int


ACTIONS = (Action("A0", None, 0), *(Action(f"A{i}", 24.5, m) for i, m in enumerate((15, 30, 45), 1)),
           *(Action(f"A{i}-{m}", t, m) for i, t in enumerate((25, 25.5, 26), 4) for m in (15, 30, 45)))


def _summarize(series, warm):
    cool, fan = electricity(series)
    peak = float(series[:, 0].max())
    minimum = float(series[:, 0].min())
    return dict(cooling_kwh=float(cool), fan_kwh=float(fan), total_kwh=float(cool + fan),
                recovery_kwh=float(series[HOLD:, 1:].sum() * HOURS) if warm else None,
                peak_c=peak, minimum_c=minimum, minimum_comfort_margin_c=min(26 - peak, minimum - 20),
                trajectory=[[float(v) for v in row] for row in series])


def rank(model, validation, inputs, *, allowed=True, stage1_reason="", failure=""):
    """Score the supported grid once. Predictions never enter the measured energy fields."""
    predicted = None
    if inputs is not None:
        try:
            predicted = model.predict(inputs)
        except (KeyError, ValueError, TypeError, IndexError) as exc:
            failure = str(exc)
    rows = []
    uncertainty = validation["metrics"]["max_net_savings_error_kwh"]
    for action in ACTIONS:
        row = dict(asdict(action), predicted=None, feasible=action.id == "A0", reasons=[])
        rows.append(row)
        if action.id in {"A0", "A3"} and predicted is not None:
            row["predicted"] = _summarize(predicted[action.id == "A3"], action.id == "A3")
        if action.id == "A0":
            continue
        if action.id != "A3":
            row["reasons"].append("No matched release/recovery evidence for this duration" if action.target_c == 24.5
                                  else "Setpoint exceeds the qualified actuator/response domain")
            continue
        if not validation["qualified"]:
            row["reasons"].append("Held-out action-response qualification failed")
        if not allowed:
            row["reasons"].append(stage1_reason or "Stage 1 entry veto")
        if predicted is None:
            row["reasons"].append(failure or "Verified decision-time features unavailable")
        else:
            native, warm = predicted
            plan = row["predicted"]
            if (plan["peak_c"] + TEMP_RESERVE_C >= 26 or plan["minimum_c"] - TEMP_RESERVE_C <= 20
                    or max(warm[:HOLD, 0]) + TEMP_RESERVE_C >= PROJECT_HOT_FALLBACK - 273.15):
                row["reasons"].append("Temperature plus uncertainty exceeds the comfort or hold margin")
            if plan["peak_c"] > validation["observed_peak_limit_c"]:
                row["reasons"].append("Predicted peak is above the hottest measured response")
            plan["recovery_penalty_kwh"] = float((warm[HOLD:, 1:] - native[HOLD:, 1:]).sum() * HOURS)
            plan["saved_kwh"] = rows[0]["predicted"]["total_kwh"] - plan["total_kwh"]
            plan["lower_savings_kwh"] = plan["saved_kwh"] - uncertainty
            if plan["lower_savings_kwh"] < MIN_GAIN_KWH:
                row["reasons"].append("Conservative net benefit below 0.0225 kWh")
        row["feasible"] = not row["reasons"]
    feasible = [r for r in rows if r["feasible"]]
    selected = min(feasible, key=lambda r: r["predicted"]["total_kwh"] if r["predicted"] is not None else 0.0)
    return dict(version=VERSION, stage1_reason=stage1_reason, qualified=validation["qualified"], selected=selected["id"],
                temperature_reserve_c=TEMP_RESERVE_C, net_uncertainty_kwh=uncertainty, candidates=rows)


class PredictiveController(GuardedController):
    """Use the existing verified state machine for delivery, release and recovery."""

    def __init__(self, start, end, *, model, validation, issued, record, use_400w=False):
        super().__init__(start, end)
        self.model, self.validation, self.issued, self.record = model, validation, issued, record
        self.use_400w = use_400w
        self.schedule = ComfortSchedule.from_fmu()
        self._history = None
        self._plan = None

    def accept_verified_history(self, origin, chunk, receipt):
        if self.use_400w:
            super().accept_verified_history(origin, chunk, receipt)
        self._history = (chunk, receipt)

    def decide(self, origin, current, boundary, *, age_s, receipts):
        self._current_full = current
        self._decision_receipts = receipts
        return super().decide(origin, current, boundary, age_s=age_s, receipts=receipts)

    def _select(self, origin, context, boundary, age_s):
        stage1 = (super()._select(origin, context, boundary, age_s) if self.use_400w
                  else EnergyController._select(self, origin, context, boundary, age_s))
        if self._hold_until is not None:
            completed = (origin - self._plan[0]) // STEP
            original = self._plan[1]
            residual = context[TEMP] - 273.15 - original[completed - 1][0]
            remaining = original[completed:]
            peak = max((row[0] for row in remaining), default=context[TEMP] - 273.15) + max(residual, 0)
            projected = sum((row[1] + row[2]) * HOURS for row in remaining)
            if stage1.warmer and peak + TEMP_RESERVE_C >= PROJECT_HOT_FALLBACK - 273.15:
                stage1 = Decision(origin, False, "optimizer_feedback_comfort_release", fallback=True)
            self.record(dict(version=VERSION, origin=origin, selected="A3" if stage1.warmer else "A0",
                             stage1_reason=stage1.reason, feedback_adjusted_remaining_peak_c=peak,
                             estimated_remaining_electricity_kwh=projected,
                             remaining_hold_min=max(0, (self._hold_until - origin) // 60)))
            return stage1
        if origin % DAY != ON:
            return Decision(origin, False, "optimizer_requires_measured_11am_start") if stage1.warmer else stage1
        inputs, note = None, ""
        issued = self.issued()
        try:
            chunk, receipt = self._history
            if not (0 < receipt < self._decision_receipts[2] and issued["received_order"] == self._decision_receipts[1]):
                raise ValueError("History or forecast receipt was unavailable at decision cutoff")
            inputs = make_inputs(origin, self._current_full, issued, chunk, self.schedule)
        except (KeyError, ValueError, TypeError, IndexError) as exc:
            note = str(exc)
        report = rank(self.model, self.validation, inputs, allowed=stage1.warmer,
                      stage1_reason=stage1.reason, failure=note)
        self.record(dict(report, origin=origin, inputs=asdict(inputs) if inputs else None,
                         morning_guard=self.morning_guard_evidence))
        if report["selected"] == "A3":
            self._plan = (origin, next(r for r in report["candidates"] if r["id"] == "A3")["predicted"]["trajectory"])
            return Decision(origin, True, "optimizer_minimum_feasible_net_electricity")
        return Decision(origin, False, "optimizer_native_selection")


def calibrated_model():
    return ResponseModel(evidence()), qualification()
