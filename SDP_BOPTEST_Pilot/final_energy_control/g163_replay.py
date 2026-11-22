"""Interactive three-arm replay of the sealed, measured G163 campaign."""

import argparse
from bisect import bisect_left
from functools import lru_cache
from threading import Lock
import time

from autonomous_hvac_stage1.evaluation import ComfortSchedule, score_window
from dashboard import make_server
from hvac_control_expansion_b2f_v1.packaging import inventory
from stage4e.dataset import NativeElectric
from stage4e_d0.plan import COOL, FAN, FLAG, SET, STEP, TEMP
from stage4e_d2i_1.common import read, require

from .live_dashboard import HERE, DashboardState, EvidenceRun
from .optimizer_campaign import BATCH, CAMPAIGN, definition

ARMS = ("Native", "Fixed warmer", "Predictive optimizer")


class G163Replay(DashboardState):
    def __init__(self, batch=BATCH):
        manifest = batch / "BATCH_ARTIFACT_MANIFEST.json"
        require(manifest.is_file(), "G163 replay requires finalized three-arm evidence")
        files = inventory(batch)
        files.pop(manifest.name)
        require(files == read(manifest)["files"], "G163 evidence differs from the finalized manifest")
        self.measured = read(batch / "OPTIMIZER_COMPARISON.json")
        require(self.measured.get("technical_validation") == "PASS" and self.measured.get("fabricated") is False,
                "G163 replay requires a technically verified measured comparison")

        runs = definition()["runs"]
        self.start, end = runs[0]["start"], runs[0]["end"]
        timeline = list(range(self.start + STEP, end + STEP, STEP))
        self.arms = [EvidenceRun(batch / spec["run_id"], archived=True) for spec in runs]
        for arm, spec in zip(self.arms, runs, strict=True):
            require(arm.status["run_id"] == spec["run_id"] and arm.status.get("fabricated") is False
                    and arm.status.get("cleanup") == "STOP_ACK_AND_REMOVAL_VERIFIED"
                    and [step["end"] for step in arm.steps] == timeline,
                    "G163 arm identity, timeline, or completion status differs")
        self.run = self.arms[2]
        self.rankings = [row for row in self.run.optimizer_rows.new_rows() if "candidates" in row]
        self.origins = [row["origin"] for row in self.rankings]
        require(len(self.origins) == 3 and self.origins == sorted(set(self.origins)), "Missing G163 daily decisions")

        self.mode = "g163"
        self.lock = Lock()
        self.schedule = ComfortSchedule.from_fmu()
        self.total = len(timeline)
        self.cursor = self.frame_at(self.origins[0])
        self.playing = False
        self._last_tick = time.monotonic()
        self.series = []
        for arm in self.arms:
            electricity = NativeElectric(arm.native).cumulative
            self.series.append([
                [arm.endpoints[stamp][TEMP] - 273.15, arm.endpoints[stamp][COOL] + arm.endpoints[stamp][FAN],
                 (electricity[stamp] - electricity[self.start]) / 3_600_000]
                for stamp in [self.start, *timeline]
            ])

    def frame_at(self, origin):
        return (origin - self.start) // STEP + 1

    @lru_cache(maxsize=4)
    def frame(self, cursor):
        end = self.run.steps[cursor - 1]["end"]
        arms = []
        for name, run, series in zip(ARMS, self.arms, self.series, strict=True):
            step = run.steps[cursor - 1]
            obs = run.endpoints[end]
            command = run.committed(step)
            metrics = score_window(run.native, self.schedule, self.start, end)
            arms.append(dict(name=name, temperature_c=obs[TEMP] - 273.15, cooling_w=obs[COOL], fan_w=obs[FAN],
                             requested_c=command[SET] - 273.15 if command[FLAG] else None,
                             verified_c=obs[SET] - 273.15, override=bool(obs[FLAG]),
                             decision=step["decision"]["reason"], fallback=step["decision"]["fallback"],
                             energy_kwh=metrics["electricity_kwh"],
                             official_kh=run.official if cursor == self.total else metrics["official_replayed_kh"],
                             project_kh=metrics["project_replayed_kh"],
                             occupied_violation_min=metrics["occupied_project_violation_minutes"],
                             series=series[:cursor + 1]))
        rank_index = bisect_left(self.origins, end) - 1
        ranking = None
        if rank_index >= 0:
            row = self.rankings[rank_index]
            qualified = [dict(id=c["id"], feasible=c["feasible"], reasons=c["reasons"],
                              predicted={k: v for k, v in c["predicted"].items() if k != "trajectory"}
                              if c["predicted"] else None)
                         for c in row["candidates"] if c["id"] in {"A0", "A3"}]
            ranking = dict(origin=row["origin"], selected=row["selected"], candidates=qualified,
                           uncertainty_kwh=row["net_uncertainty_kwh"], reserve_c=row["temperature_reserve_c"],
                           trigger=row["stage1_reason"])
        savings = [arm["energy_kwh"] - arms[2]["energy_kwh"] for arm in arms[:2]]
        return dict(now=end, arms=arms, rank=ranking, optimizer_saved=savings,
                    official_source="BOPTEST API" if cursor == self.total else "official-schedule replay",
                    decisions=[dict(cursor=self.frame_at(t), origin=t) for t in self.origins])

    def _snapshot(self):
        if self.playing:
            count = int((time.monotonic() - self._last_tick) / .45)
            self.cursor = min(self.total, self.cursor + count)
            self._last_tick += count * .45
            self.playing = self.cursor < self.total
        return dict(mode=self.mode, ready=True, start=self.start, cursor=self.cursor, total=self.total,
                    playing=self.playing, passed=self.measured["optimizer_passed"], **self.frame(self.cursor))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8770)
    args = parser.parse_args()
    try:
        replay = G163Replay()
    except (OSError, KeyError, ValueError) as error:
        parser.error(str(error))
    with make_server(replay, args.port, html_path=HERE / "g163_dashboard.html") as server:
        print(f"http://127.0.0.1:{server.server_port}/ | measured replay | {CAMPAIGN}", flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()
