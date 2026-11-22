"""Matched energy and dual-comfort scoring of completed, verified traces."""

import csv
from bisect import bisect_left, bisect_right
from dataclasses import dataclass
from io import StringIO
from math import isclose
from pathlib import Path
from zipfile import ZipFile

from core import integrate
from energy_savings_g174_v1.comparison import energy
from energy_savings_g174_v1.policy import DURATION, MIN_SAVINGS_KWH, ON, PROJECT_HI, PROJECT_HOT_FALLBACK, PROJECT_LO, RECOVERY, TARGET
from stage4e_d0.plan import FLAG, FLAGS, LOW, OCC, SET, STEP, TEMP, UP, sha
from stage4e_d1r.proposed_validation import finite, near
from stage4e_d1_v2.validation import history
from stage4e_d2i_1.common import FMU_SHA
from .controller import DAY, MAX_ACTIONS, MAX_ADVANCES

SIM_YEAR = 31536000
PUBLISHED_SCHEDULE_STEP = 600
FMU = (Path(__file__).resolve().parents[1] / "deployment/official_v0.9.0/project1-boptest-0.9.0"
       / "testcases/bestest_air/models/wrapped.fmu")
COMFORT_TOLERANCE = 1e-7  # Floating point comparison only, not an allowed added burden.
SAFETY_VETO_REASONS = frozenset({"cold_margin", "hot_margin_or_rising_trend", "qualified_warm_guard_veto"})


@dataclass(frozen=True)
class ComfortSchedule:
    times: tuple
    values: tuple

    @classmethod
    def from_fmu(cls, path=FMU):
        """Read the official scoring resource; leave both FMU and CSV unchanged."""
        if sha(path) != FMU_SHA:
            raise ValueError("BESTEST Air FMU identity mismatch")
        with ZipFile(path) as archive:
            csv_text = archive.read("resources/internal_setpoints_occupancy.csv").decode("utf-8-sig")
        rows = list(csv.DictReader(StringIO(csv_text)))
        raw_times = tuple(float(row["time"]) for row in rows)
        if raw_times[0] != 0 or raw_times[-1] != SIM_YEAR or any(
                b <= a for a, b in zip(raw_times, raw_times[1:])):
            raise ValueError("Unexpected evaluation resource time order")
        # Data_Manager first forward-fills all discrete schedules on the pinned
        # 600 s common grid. It then forward-fills this grid at result times.
        times = tuple(range(0, SIM_YEAR + 1, PUBLISHED_SCHEDULE_STEP))
        published = (rows[bisect_right(raw_times, time) - 1] for time in times)
        return cls(times, tuple((float(row[LOW]), float(row[UP]), float(row[OCC]) > 0) for row in published))

    def at(self, time):
        return self.values[bisect_right(self.times, time % SIM_YEAR) - 1]


@dataclass(frozen=True)
class Trace:
    native: dict
    official_discomfort_kh: float


def _window(native, start, end):
    times = native["time"]
    left, right = bisect_left(times, start), bisect_right(times, end)
    if start >= end or left == len(times) or right <= left or times[left] != start or times[right - 1] != end:
        raise ValueError("Scoring requires complete native endpoints")
    return {key: values[left:right] for key, values in native.items()}


def score_window(native, schedule, start, end):
    segment = _window(native, start, end)
    times, temperatures = segment["time"], segment[TEMP]
    official_excess, project_excess, occupied_temperatures = [], [], []
    occupied_slots, project_violation_slots = [], []
    for time, temperature in zip(times, temperatures, strict=True):
        lo, hi, occupied = schedule.at(time)
        official_excess.append(max(0.0, lo - temperature, temperature - hi))
        project_lo, project_hi = (PROJECT_LO, PROJECT_HI) if occupied else (lo, hi)
        project_excess.append(max(0.0, project_lo - temperature, temperature - project_hi))
        occupied_slots.append(occupied)
        project_violation_slots.append(occupied and project_excess[-1] > COMFORT_TOLERANCE)
        if occupied:
            occupied_temperatures.append(temperature)

    cool, fan = energy(segment, start, end)
    outside_minutes = sum(b - a for a, b, outside in zip(times, times[1:], project_violation_slots)
                          if outside) / 60
    return {
        "cooling_kwh": cool,
        "fan_kwh": fan,
        "electricity_kwh": cool + fan,
        "official_replayed_kh": integrate(times, official_excess, start, end) / 3600,
        "project_replayed_kh": integrate(times, project_excess, start, end) / 3600,
        "occupied_project_violation_minutes": outside_minutes,
        "occupied_max_c": max(occupied_temperatures) - 273.15 if occupied_temperatures else None,
        "occupied_project_peak_excursion_k": max((x for x, occupied in zip(project_excess, occupied_slots)
                                                  if occupied), default=0.0),
        "maximum_indoor_c": max(temperatures) - 273.15,
    }


def _verified_episodes(records, native, start, end):
    if [record.decision.origin for record in records] != list(range(start, end, STEP)):
        raise ValueError("One verified decision is required for every interval")
    times = native["time"]
    if any(native[f][0] for f in FLAGS):
        raise ValueError("Controller trace must start native")
    episodes = []
    active_start = None
    for record in records:
        decision = record.decision
        if not decision.advance or record.cooling_override_active != decision.warmer:
            raise ValueError("An unrestored, stopped or unverified interval cannot be scored")
        command = decision.command
        idx = bisect_right(times, decision.origin)
        stop = bisect_right(times, record.end)
        if any(native[f][j] != command[f] for j in range(idx, stop) for f in FLAGS):
            raise ValueError("Native trace differs from recorded command")
        endpoint = bisect_left(times, record.end, idx, stop)
        if not any(near(native[SET][j], record.actual_cooling_k) for j in range(endpoint, stop)):
            raise ValueError("Native trace differs from endpoint readback")
        if record.cooling_override_active:
            if not ON <= decision.origin % DAY < ON + DURATION:
                raise ValueError("Delivered action is outside the qualified clock envelope")
            if any(not near(native[SET][j], TARGET) for j in range(idx, stop)):
                raise ValueError("Native trace does not show 24.5 C")
            if active_start is None:
                active_start = decision.origin
        elif active_start is not None:
            if (decision.origin + RECOVERY > end or
                    (episodes and (active_start < episodes[-1][1] + RECOVERY
                                   or active_start // DAY == episodes[-1][0] // DAY))):
                raise ValueError("Overlapping or incomplete recovery")
            episodes.append((active_start, decision.origin))
            active_start = None
    if active_start is not None:
        raise ValueError("Missing verified release to native")
    if len(episodes) > MAX_ACTIONS:
        raise ValueError("Delivered actions exceed the campaign budget")
    return episodes


def _recovery_mark(native, controlled, release):
    streak = 0
    first = None
    for t in range(release, release + RECOVERY + 1, STEP):
        # Same endpoint/preceding-interval pairing as G174, including t=release.
        i = bisect_left(native["time"], t)
        n = sum(energy(_window(native, t - STEP, t), t - STEP, t))
        c = sum(energy(_window(controlled, t - STEP, t), t - STEP, t))
        quiet = abs(native[TEMP][i] - controlled[TEMP][i]) <= 0.05 and abs(n - c) * 12 <= 0.01
        if quiet:
            if streak == 0:
                first = t
            streak += 1
            if streak == 3:
                return (first - release) // 60
        else:
            streak = 0
    return None


def evaluate_matched(native, controlled, records, start, end):
    """Score a pair after upstream identity, initialization and forcing equivalence checks."""
    history(native.native, start, end)
    history(controlled.native, start, end)
    if native.native["time"] != controlled.native["time"] or any(any(native.native[f]) for f in FLAGS):
        raise ValueError("Expected identical native clocks and a native-only baseline")
    records = tuple(records)
    episodes = _verified_episodes(records, controlled.native, start, end)
    schedule = ComfortSchedule.from_fmu()

    def paired(a, b):
        ref = score_window(native.native, schedule, a, b)
        trial = score_window(controlled.native, schedule, a, b)
        savings = ref["electricity_kwh"] - trial["electricity_kwh"]
        return {"start": a, "end": b, "native": ref, "controller": trial, "saved_kwh": savings,
                "saved_percent": 100 * savings / ref["electricity_kwh"] if ref["electricity_kwh"] else None,
                "added_project_kh": trial["project_replayed_kh"] - ref["project_replayed_kh"]}

    full = paired(start, end)
    for arm, trace in (("native", native), ("controller", controlled)):
        if not isclose(full[arm]["official_replayed_kh"], finite(trace.official_discomfort_kh), rel_tol=0, abs_tol=1e-8):
            raise ValueError(f"Official KPI mismatch for {arm}")
        full[arm]["official_reported_kh"] = trace.official_discomfort_kh

    windows = []
    for a, release in episodes:
        hold = paired(a, release)
        recovery = paired(release, release + RECOVERY)
        total = paired(a, release + RECOVERY)
        windows.append({"activation": a, "released_to_native": release, "delivered_minutes": (release - a) // 60,
                        "recovery_minutes_scored": RECOVERY // 60,
                        "rejoined_after_minutes": _recovery_mark(native.native, controlled.native, release),
                        "hold": hold, "recovery": recovery, "joint": total,
                        "recovery_penalty_kwh": -recovery["saved_kwh"]})

    joint_savings = sum(w["joint"]["saved_kwh"] for w in windows)
    trial, base = full["controller"], full["native"]
    criteria = {
        "complete_72_hour_pair": end - start == MAX_ADVANCES * STEP,
        "confirmed_warmer_action": bool(windows),
        "hold_max_at_or_below_25_5_c": all(
            w["hold"]["controller"]["occupied_max_c"] is not None
            and w["hold"]["controller"]["occupied_max_c"] <= PROJECT_HOT_FALLBACK - 273.15 + COMFORT_TOLERANCE
            for w in windows),
        "no_occupied_project_excursions_in_hold_and_recovery": all(
            w["joint"]["controller"]["occupied_project_peak_excursion_k"] <= COMFORT_TOLERANCE
            for w in windows),
        "no_added_full_period_project_burden": (
            full["added_project_kh"] <= COMFORT_TOLERANCE
            and trial["occupied_project_violation_minutes"] <= base["occupied_project_violation_minutes"]),
        "recovery_marker_within_120_minutes": all(w["rejoined_after_minutes"] is not None for w in windows),
        "material_net_savings": full["saved_kwh"] >= MIN_SAVINGS_KWH and joint_savings >= MIN_SAVINGS_KWH,
    }
    vetoes = [{"time": r.decision.origin, "reason": r.decision.reason} for r in records
              if r.decision.fallback or r.decision.reason in SAFETY_VETO_REASONS]
    fallbacks = [r.decision.origin for r in records if r.decision.fallback]
    return {"passed_proposed_criteria": all(criteria.values()), "criteria": criteria, "full": full,
            "windows": windows, "hold_and_recovery_saved_kwh": joint_savings,
            "behavior": {"total_verified_intervals": len(records),
                         "warmer_actions_delivered": len(windows),
                         "warmer_intervals": sum(r.cooling_override_active for r in records),
                         "native_intervals": sum(not r.cooling_override_active for r in records),
                         "warm_starts_selected": sum(r.decision.reason == "sustained_cooling_with_headroom" for r in records),
                         "safety_veto_count": len(vetoes), "safety_vetoes": vetoes,
                         "fallback_count": len(fallbacks), "fallback_origins": fallbacks}}

