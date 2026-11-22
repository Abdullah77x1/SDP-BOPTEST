"""Offline controller, matched-accounting and preserved-archive regressions."""

import json
import unittest

from energy_savings_g174_v1.policy import ARCHIVE, DURATION, ON, RECOVERY, TARGET
from stage4e_d0.plan import COOL, FAN, FLAG, FLAGS, HEAT, LOW, OCC, ROOT, SET, STEP, TEMP, UP, native_command
from stage4e_d1r.proposed_validation import HEAT as HEATING_SETPOINT, Violation
from stage4e_d1_v2.validation import REFERENCE

from .controller import EnergyController
from .evaluation import ComfortSchedule, Trace, _recovery_mark, evaluate_matched, score_window

START, RELEASE, END = ON - STEP, ON + DURATION, ON + DURATION + RECOVERY + 2 * STEP


def state(time, *, temperature=297.15, cooling=200.0, fan=40.0, warm=False):
    heat, cool = REFERENCE.pair(time)
    return {"time": time, TEMP: temperature, COOL: cooling, FAN: fan, HEAT: 0.0,
            HEATING_SETPOINT: heat, SET: TARGET if warm else cool, **native_command(), FLAG: int(warm)}


def boundary(time, occupants=2):
    low, high = REFERENCE.pair(time)
    return {"time": time, LOW: low, UP: high, OCC: occupants}


def next_vintage(origin):
    end = origin + STEP
    row = boundary(end)
    return {"time": end, "issued_at": origin, "lower_k": row[LOW], "upper_k": row[UP], "occupancy": row[OCC]}


def columns(rows):
    return {key: [row[key] for row in rows] for key in rows[0]}


class Fixture:
    def __init__(self, start=START, end=END, **initial):
        self.rule = EnergyController(start, end)
        self.current = state(start, **initial)
        self.receipt = 1

    def decide(self, *, occupancy=2, age=2, issued=None):
        t = self.current["time"]
        return self.rule.decide(t, self.current, boundary(t, occupancy) if issued is None else issued,
                                age_s=age, receipts=(self.receipt, self.receipt + 1, self.receipt + 2))

    def confirm(self, decision, *, post=None, native=None, **end_values):
        t = decision.origin
        if post is None:
            post = state(t + STEP, warm=decision.warmer, **end_values)
        if native is None:
            native = columns([self.current] + [{**post, "time": stamp}
                                               for stamp in range(t + 30, t + STEP + 1, 30)])
        delivered = self.rule.confirm(decision, post, next_vintage(t), response_receipt=self.receipt + 3,
                                      native_history=native)
        self.receipt += 4
        self.current = post
        return delivered

    def prime(self, **end_values):
        self.confirm(self.decide(), **end_values)


class ControllerTests(unittest.TestCase):
    def test_warmer_selected_only_after_sustained_cooling(self):
        case = Fixture()
        first = case.decide()
        self.assertEqual(first.command, native_command())
        case.confirm(first)
        second = case.decide()
        self.assertTrue(second.advance)
        self.assertTrue(second.warmer)
        self.assertEqual(second.command, {**native_command(), FLAG: 1, SET: TARGET})
        self.assertTrue(case.confirm(second).cooling_override_active)

    def test_native_when_cooling_inactive_or_fan_off(self):
        for first, next_value in ((0, {"cooling": 200}), (200, {"cooling": 0}), (200, {"fan": 0})):
            with self.subTest(first=first, next_value=next_value):
                case = Fixture(cooling=first)
                case.prime(**next_value)
                decision = case.decide()
                self.assertTrue(decision.advance)
                self.assertFalse(decision.warmer)
                self.assertEqual(decision.reason, "no_sustained_cooling")

    def test_native_when_unoccupied(self):
        case = Fixture()
        case.prime()
        self.assertEqual(case.decide(occupancy=0).reason, "unoccupied")

    def test_inadequate_hot_cold_and_trend_margins(self):
        for previous, current, reason in ((298.60, 298.65, "hot_margin_or_rising_trend"),
                                           (298.20, 298.50, "hot_margin_or_rising_trend"),
                                           (294.9, 294.89, "cold_margin")):
            with self.subTest(current=current):
                case = Fixture(temperature=previous)
                case.prime(temperature=current)
                self.assertEqual(case.decide().reason, reason)

    def test_clock_window_blocks_action_without_complete_recovery(self):
        case = Fixture(end=RELEASE + RECOVERY - STEP)
        case.prime()
        self.assertEqual(case.decide().reason, "outside_qualified_window_or_recovery_budget")

    def test_stale_missing_and_untrusted_state_stop_without_advance(self):
        for kind in ("stale", "missing", "other_actuator"):
            with self.subTest(kind=kind):
                case = Fixture()
                if kind == "missing":
                    del case.current[FAN]
                if kind == "other_actuator":
                    case.current[FLAGS[1]] = 1
                decision = case.decide(age=30.001 if kind == "stale" else 1)
                self.assertFalse(decision.advance)
                self.assertEqual(decision.command, native_command())
                self.assertTrue(case.rule.stop_reason)
                self.assertFalse(case.decide().advance)

    def test_forty_five_minutes_and_confirmed_native_release(self):
        case = Fixture()
        case.prime()
        for _ in range(9):
            current = case.decide()
            self.assertTrue(current.warmer)
            # A warming action can reduce cooling; warm hold need not requalify measured demand.
            case.confirm(current, cooling=0)
        release = case.decide()
        self.assertEqual((release.origin, release.reason), (RELEASE, "scheduled_release"))
        self.assertFalse(case.confirm(release).cooling_override_active)

    def test_late_entry_still_releases_by_window_close(self):
        case = Fixture(cooling=0)
        case.prime(cooling=0)
        case.confirm(case.decide(), cooling=200)
        case.confirm(case.decide(), cooling=200)
        selected = case.decide()
        self.assertEqual(selected.origin, ON + 2 * STEP)
        self.assertTrue(selected.warmer)
        while case.current["time"] < RELEASE:
            demand = selected if case.current["time"] == selected.origin else case.decide()
            self.assertTrue(demand.warmer)
            case.confirm(demand)
        self.assertEqual(case.decide().reason, "scheduled_release")

    def test_upper_fallback_and_no_repeat_during_recovery(self):
        case = Fixture()
        case.prime()
        case.confirm(case.decide(), temperature=298.65)
        veto = case.decide()
        self.assertTrue(veto.fallback)
        self.assertFalse(veto.warmer)
        case.confirm(veto)
        for _ in range(RECOVERY // STEP - 1):
            decision = case.decide()
            self.assertEqual(decision.reason, "native_recovery_lockout")
            case.confirm(decision)
        self.assertFalse(case.decide().warmer)

    def test_cold_fallback_and_benchmark_schedule_guard(self):
        case = Fixture(temperature=295)
        case.prime(temperature=295)
        case.confirm(case.decide(), temperature=294.64)
        veto = case.decide()
        self.assertEqual(veto.reason, "cold_margin")
        self.assertTrue(veto.fallback)
        case = Fixture()
        case.prime()
        wrong_boundary = {**boundary(ON), UP: 299.15}
        decision = case.decide(issued=wrong_boundary)
        self.assertEqual(decision.reason, "qualified_warm_guard_veto")

    def test_reject_incorrect_effective_target_and_latch_stop(self):
        case = Fixture()
        case.prime()
        decision = case.decide()
        wrong = {**state(ON + STEP, warm=True), SET: 297.5}
        with self.assertRaisesRegex(Violation, "setpoint_readback"):
            case.confirm(decision, post=wrong)
        self.assertFalse(case.decide().advance)

    def test_reject_native_history_override_mismatch(self):
        case = Fixture()
        case.prime()
        decision = case.decide()
        post = state(ON + STEP, warm=True)
        native = columns([case.current] + [{**post, "time": t} for t in range(ON + 30, ON + STEP + 1, 30)])
        native[SET][2] = 297.5
        with self.assertRaisesRegex(Violation, "native_interval_target"):
            case.confirm(decision, post=post, native=native)

    def test_no_future_receipt_timestamp_or_future_actual_feature(self):
        for args in ({"receipts": (1, 3, 2)}, {"boundary": boundary(ON + STEP)}):
            with self.subTest(args=args):
                case = Fixture()
                case.prime()
                kwargs = {"current": case.current, "boundary": boundary(ON), "age_s": 2,
                          "receipts": (5, 6, 7), **args}
                self.assertFalse(case.rule.decide(ON, **kwargs).advance)
        a, b = Fixture(), Fixture()
        a.prime()
        b.prime()
        b.current["future_realized_temperature"] = 400.0
        b.current["future_realized_cooling_electricity"] = 0.0
        self.assertEqual(a.decide(), b.decide())

    def test_no_second_command_before_readback(self):
        case = Fixture()
        first = case.decide()
        self.assertFalse(case.decide().advance)
        with self.assertRaises(Violation):
            case.confirm(first)

    def test_registered_native_event_requires_and_accepts_followup(self):
        event = REFERENCE.occupied_end_s
        for supply_followup in (False, True):
            with self.subTest(supply_followup=supply_followup):
                case = Fixture(start=event - STEP, end=event + STEP)
                old_pair = {**state(event), HEATING_SETPOINT: 294.15, SET: 297.15}
                before = [{**state(t), HEATING_SETPOINT: 294.15, SET: 297.15}
                          for t in range(event - STEP, event + 1, 30)]
                case.confirm(case.decide(), post=old_pair, native=columns(before))
                decision = case.decide(occupancy=0)
                self.assertFalse(decision.warmer)
                after = [state(t) for t in range(event + 30, event + STEP + 1, 30)]
                kwargs = dict(response_receipt=8, native_history=columns([old_pair, *after]))
                if supply_followup:
                    record = case.rule.confirm(decision, after[-1], next_vintage(event),
                                               event_history=columns(before + after), history_receipt=9, **kwargs)
                    self.assertFalse(record.cooling_override_active)
                    self.assertIsNone(case.rule.stop_reason)
                else:
                    with self.assertRaisesRegex(Violation, "missing_required_event_followup"):
                        case.rule.confirm(decision, after[-1], next_vintage(event), **kwargs)

    def test_saved_native_observations_select_without_using_treatment_outcome(self):
        directory = (ROOT / "stage4e_d2_prep02/runtime_state/batches/PUBLIC_D2_D2_G218_20261115_01"
                     / "D2_G218_N")
        endpoints = {row["time"]: row for row in json.loads((directory / "endpoints.json").read_bytes())}
        full = json.loads((directory / "whole_native_results.json").read_bytes())
        native_steps = {}
        with (directory / "steps.jsonl").open(encoding="utf-8") as file:
            start_run = min(endpoints)
            for row in map(json.loads, file):
                if start_run + START <= row["start"] <= start_run + ON:
                    native_steps[row["start"]] = row
        start = start_run + START
        controller = EnergyController(start, start_run + 86400)
        first = controller.decide(start, endpoints[start], native_steps[start]["current_boundary"],
                                  age_s=2, receipts=(1, 2, 3))
        self.assertFalse(first.warmer)
        i = full["time"].index(start)
        observed = {key: values[i:i + 11] for key, values in full.items()}
        controller.confirm(first, endpoints[start + STEP], next_vintage(start), response_receipt=4,
                           native_history=observed)
        decision = controller.decide(start + STEP, endpoints[start + STEP],
                                     native_steps[start + STEP]["current_boundary"],
                                     age_s=2, receipts=(4, 5, 6))
        self.assertTrue(decision.warmer)
        # Replay ends here: the archive contains no outcome for this proposed warmer action.


def paired_fixture(controlled, baseline_cooling=200.0):
    raw = []
    for t in range(START, END + 1, 30):
        warm = controlled and ON < t <= RELEASE
        power = baseline_cooling
        if controlled and ON < t < RELEASE:
            power -= 100.0
        if controlled and RELEASE < t < RELEASE + 900:
            power += 30.0
        raw.append(state(t, cooling=power, warm=warm))
    return columns(raw)


def run_fixture(data):
    controller = EnergyController(START, END)
    records = []
    for idx, t in enumerate(range(START, END, STEP)):
        origin, stop = idx * 10, idx * 10 + 10
        observation = {key: values[origin] for key, values in data.items()}
        next_obs = {key: values[stop] for key, values in data.items()}
        chunk = {key: values[origin:stop + 1] for key, values in data.items()}
        receipt = 4 * idx + 1
        choice = controller.decide(t, observation, boundary(t), age_s=1,
                                   receipts=(receipt, receipt + 1, receipt + 2))
        records.append(controller.confirm(choice, next_obs, next_vintage(t), response_receipt=receipt + 3,
                                          native_history=chunk))
    return records


class EvaluationTests(unittest.TestCase):
    def test_complete_pair_uses_delivered_windows_and_actual_recovery(self):
        native, controlled = paired_fixture(False), paired_fixture(True)
        result = evaluate_matched(Trace(native, 0.0), Trace(controlled, 0.0),
                                  run_fixture(controlled), START, END)
        self.assertFalse(result["passed_proposed_criteria"])
        self.assertEqual([name for name, passed in result["criteria"].items() if not passed],
                         ["complete_72_hour_pair"])
        self.assertEqual(result["behavior"]["warmer_actions_delivered"], 1)
        self.assertEqual(result["behavior"]["warmer_intervals"], 9)
        window, = result["windows"]
        self.assertEqual((window["activation"], window["released_to_native"], window["delivered_minutes"]),
                         (ON, RELEASE, 45))
        self.assertAlmostEqual(window["hold"]["saved_kwh"], 100 * (DURATION - 30) / 3600000)
        self.assertAlmostEqual(window["recovery_penalty_kwh"], 30 * (900 - 30) / 3600000)
        self.assertAlmostEqual(result["full"]["saved_kwh"],
                               window["hold"]["saved_kwh"] - window["recovery_penalty_kwh"])
        self.assertEqual(window["rejoined_after_minutes"], 20)
        self.assertAlmostEqual(result["full"]["controller"]["fan_kwh"], 40 * (END - START) / 3600000)

    def test_native_only_is_reported_and_is_not_an_energy_success(self):
        native_data = paired_fixture(False, baseline_cooling=0.0)
        arm = Trace(native_data, 0.0)
        result = evaluate_matched(arm, arm, run_fixture(native_data), START, END)
        self.assertFalse(result["passed_proposed_criteria"])
        self.assertFalse(result["criteria"]["confirmed_warmer_action"])
        self.assertEqual(result["behavior"]["native_intervals"], (END - START) // STEP)
        self.assertEqual(result["full"]["saved_kwh"], 0.0)

    def test_reject_missing_records_and_unreconciled_official_kpi(self):
        native_data = paired_fixture(False, baseline_cooling=0.0)
        arm = Trace(native_data, 0.0)
        records = run_fixture(native_data)
        with self.assertRaisesRegex(ValueError, "every interval"):
            evaluate_matched(arm, arm, records[:-1], START, END)
        with self.assertRaisesRegex(ValueError, "Official KPI mismatch"):
            evaluate_matched(arm, Trace(native_data, 1.0), records, START, END)

    def test_authoritative_g174_temperature_and_energy_replay(self):
        schedule = ComfortSchedule.from_fmu()
        experimental = (ROOT / "energy_savings_g174_v1/runtime_state/batches/ESV01_G174_WARM45/ESV01_G174_WARM45")
        traces = []
        for path, expected in ((ARCHIVE, (1.404807, 0.102395, 19.485982)),
                               (experimental, (2.537502, 0.104585, 19.407514))):
            with self.subTest(path=path.name):
                data = json.loads((path / "whole_native_results.json").read_bytes())
                traces.append(data)
                score = score_window(data, schedule, data["time"][0], data["time"][-1])
                self.assertEqual(tuple(round(score[k], 6) for k in ("official_replayed_kh",
                                     "project_replayed_kh", "electricity_kwh")), expected)
                official = json.loads((path / "official_kpis.json").read_bytes())["tdis_tot"]
                self.assertAlmostEqual(score["official_replayed_kh"], official, places=12)
        release = traces[0]["time"][0] + RELEASE
        self.assertEqual([_recovery_mark(*traces, release + day * 86400) for day in range(3)],
                         [15, 25, 20])


if __name__ == "__main__":
    unittest.main()

