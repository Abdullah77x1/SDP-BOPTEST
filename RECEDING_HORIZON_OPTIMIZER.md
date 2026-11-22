# Five-minute receding-horizon HVAC optimizer

**B · Partial receding-horizon control verified live.** `LIVE_ROLLING_TWIN_01` completed all **41** authorized five-minute advances on genuine BOPTEST. The optimizer started at 24.5°C, recalculated eight continuation forecasts from verified observations, released to native 24°C on schedule, and observed 120 minutes of recovery. **A · Full economic switching still requires matched branch evidence.** **C · The original fixed-hold optimizer remains the launcher default.** [Sealed completion][completion] · [Stepwise model](SDP_BOPTEST_Pilot/final_energy_control/rolling_model.py) · [Decision policy](SDP_BOPTEST_Pilot/final_energy_control/rolling_control.py)

## What the controller can decide

| Verified state and proposed step | Autonomous status |
| --- | --- |
| Native → native | Forecast during the supported occupied window. Native remains the safe choice outside it. |
| Native → 24.5°C | Eligible at 11:00 only. Both plans start from the same measured state. Entry requires the original envelope and safety checks, plus at least 0.0225 kWh predicted savings after the modeled recovery, measured ranking error, and a 0.002 kWh switching cost. |
| 24.5°C → 24.5°C | A new rollout at each origin uses the latest temperature, trend, prior powers, applied setpoint, and issued weather. Continue is allowed only while the updated prediction and original safeguards pass. |
| 24.5°C → native at 11:45 | Scheduled release and native recovery have measured support. The release and setpoint are verified. |
| Early release for economic optimization, later start, or restart | Disabled. An early release remains available for safety, operator Stop, or loss of model validity. It starts the existing 120-minute native lockout, and its unqualified recovery forecasts stay unavailable. |

The step model uses empirical phase means and pooled ridge slopes for indoor temperature and changes in cooling and fan power. The applied setpoint and proposed setpoint determine the permitted transition. Features use verified history through the current origin and the weather forecast issued at that origin. Weather beyond +30 minutes uses the last issued values. The longest tested action path runs **165 minutes**, including **120 minutes of recovery**. At 11:05 the rollout is rebuilt from the new state and covers the **160 minutes** remaining to 13:45. The clock and recovery rules prevent re-entry and repeated switches. O25 stays separate at **+5/+10/+15/+30 minutes**. The 25.5°C guard, optional 400 W screen, verified command handling, official schedule, and separate project 20–26°C evaluation are reused. The 18:00 thermostat versus 18:10 comfort schedule is preserved.

## Validation on measured BOPTEST archives

The model was fitted on G174 and G218 and evaluated on the held-out G163 native and fixed trajectories. The G163 rows are forecast origins, with repeated origins within one development scenario. Single-scenario transfer checks excluded 198/198 G174 origins and 182/198 G218 origins when fitted on the other scenario alone. This supports keeping the measured envelope strict.

| Lead | Evaluation origins | Indoor MAE / RMSE (°C) | Cooling / fan cumulative MAE (kWh) |
| --- | ---: | ---: | ---: |
| 5 minutes | 198 | 0.00581 / 0.00705 | 0.000268 / 0.000018 |
| 30 minutes | 168 | 0.00598 / 0.00716 | 0.005759 / 0.000356 |
| 60 minutes | 132 | 0.00634 / 0.00754 | 0.022188 / 0.001360 |
| 165 minutes | 6 | 0.00872 / 0.01125 | 0.175528 / 0.011345 |

The held-out set included 99 native steps, 3 starts, 24 warmer continuations, 3 scheduled releases and 69 recovery steps. The paired savings direction was correct on **3/3** recorded entries, with a worst error of **0.00504 kWh**. Predicted recovery rejoin was 15 minutes in each pair, versus 15/20/20 minutes measured. The common-slope model gave nearly the same predicted entry savings for all three pairs, so those results establish the direction in that scenario and leave the ability to rank opportunities across days unverified. The qualified windows contained **zero actual 26°C violations**, so they cannot establish violation-detection sensitivity or full-day comfort. [Reproducible validation](SDP_BOPTEST_Pilot/final_energy_control/rolling_model.py)

## Fabricated-transport integration tests

Before live execution, **50 automated tests passed**, including seven focused rolling-controller tests. Chrome verified fresh forecasts, unsupported-candidate reasons, readback handling, and one-step errors with explicitly fabricated transport. These tests cover fault handling and early safety release. [Automated tests](SDP_BOPTEST_Pilot/final_energy_control/test_rolling.py)

## Genuine BOPTEST live verification

The launcher checked the pinned BOPTEST **0.9.0** runtime and deployed BESTEST Air FMU. One instance ran from **10:20 to 13:45** on benchmark day offset 218 after its seven-day native warmup. The sealed evidence contains **41 paired advance requests and responses**, **411 samples at 30-second intervals**, and **446 verified receipt-journal entries**. The ledger is `CONSUMED_COMPLETED`. BOPTEST acknowledged Stop and verified instance removal. [Configuration and authorization receipt][bound] · [Raw API receipts][raw] · [Ordered journal][journal] · [Completion and cleanup][completion]

- **Rolling decisions.** Both candidate statuses were recorded at all 41 origins. The eight pre-window decisions stayed native. The 33 in-window origins each had a fresh forecast for the selected action. At 11:00, the 165-minute prediction was **2.23787 kWh** for native and **2.19515 kWh** for warmer cooling, a **0.03568 kWh** predicted advantage after uncertainty and switching cost. The 24.5°C command read back at 11:05. The next prediction used the new measured 24.469°C and had a 160-minute horizon. [Decision log][decisions] · [Entry decision in Chrome][entry]
- **Continuation and recovery.** The eight fresh continuation forecasts led to eight more verified warmer commands. For example, at 11:05 the predicted remaining energy was **2.11996 kWh**, and the next predicted indoor temperature was **24.555°C** versus **24.548°C** measured. At 11:15 the updated 150-minute forecast predicted **2.03884 kWh** remaining and **24.519°C** at the next step, versus **24.521°C** measured. The scheduled 11:45 release read back at 11:50 with the override flag cleared. Heating stayed at 21°C. Native recovery continued through 13:45, with zero safety fallbacks and no delivery failure. [Fresh continuation in Chrome][continue] · [Scheduled release in Chrome][release]
- **O25 and Chrome.** O25 produced **25 valid live forecast origins**, beginning at 10:55, with 92 targets observed before the run ended. Seven initial origins lacked sufficient history and the nine 24.5°C commitments were outside O25’s domain. Chrome showed changing simulation time, temperatures and power, candidate restrictions, selected actions, readbacks, forecast feedback, and cumulative electricity. Start launched the instance. Pause held 10:30, Resume reverified the endpoint and advanced to 10:35, and Stop was accepted while the final authorized advance was in flight. [Live O25][o25] · [Pause][pause] · [O25 and recovery][recovery] · [Stopped at 41 advances][stopped] · [Chrome transcript][chrome]

| Measurement | Result |
| --- | ---: |
| Cooling electricity | 2.599870 kWh |
| Fan electricity | 0.116477 kWh |
| **Total cooling + fan electricity** | **2.716347 kWh** |
| Hold / recovery electricity | 0.481225 / 1.814991 kWh |
| Peak occupied indoor temperature | 24.549°C |
| Official BOPTEST discomfort | 0.424717 K·h |
| Project 20–26°C discomfort | 0 K·h, 0 occupied violation minutes |

This single-arm demo establishes live control and measured consumption. Determining electricity savings requires a matched native baseline. The candidate energy and savings figures above remain model predictions. [30-second observations][native] · [Electricity reconciliation][energy] · [Official KPIs][kpis]

## Windows launch and remaining evidence

Run from the SDP workspace root. The first command prints the binding without deploying anything. The second is the verified launcher command. Chrome automation used it with `-NoBrowser` because it opened headless Chrome itself. In an interactive session, click **Start** in the dashboard once it opens. This authorization and ledger are consumed. A fresh run requires a separately bound unused session.

```powershell
.\run_live_digital_twin.ps1 -Rolling -Describe
.\run_live_digital_twin.ps1 -Rolling -AuthorizationFile .\live_rolling_twin_authorization.json
```

The recorded authorization used the exact bound configuration, one instance and initialization, 41 advances, one qualified 24.5°C start with at most nine warmer advances, the 400 W guard off, and zero retries. The configuration SHA-256 is `2a077d1be5b21d287f693d23a53a8bd330b54c571efe023fd9164398a09c46c0`. The implementation SHA-256 is `15e6fe4cd3fb319206f5b488a0f6f3c171bd1d4814dc1a45fade83e460b548d6`. [Recorded user authorization](live_rolling_twin_authorization.json) · [Bound execution receipt][bound]

## 11:15 continue-versus-release experiment

**Implemented and verified offline. Live execution awaits exact authorization.** G174, G218, both controlled G163 arms, and `LIVE_ROLLING_TWIN_01` contain 12 verified releases, all commanded at 11:45. None contains a matched release at 11:15. The prior fixed-hold and rolling live demonstrations reproduced 12 common endpoints, all 11 pre-fork commands and 30-second histories, issued forcing through 11:15, and the seven-day native warmup. Both continued warming at the fork. The pinned FMU does not declare state cloning or serialization support. [Collector and scorer](SDP_BOPTEST_Pilot/final_energy_control/release_branch.py)

`G218_RELEASE_BRANCH_1115_01` reuses benchmark day offset 218, with a seven-day native warmup and identical commands from 10:20 through 11:15. The two fresh arms differ in **one** five-minute command. Arm A keeps 24.5°C through 11:20 and then releases. Arm B releases at 11:15. Both remain native through 13:45. There are **41 advances per arm, 82 total**, with one instance running at a time, verified cleanup, and no retries. The recorder checks Arm A against the sealed live reference through the fork, then checks Arm B against Arm A before allowing its different command. The check covers initialization, commands, readbacks, observations, 30-second histories, and issued forcing. A mismatch prevents branching and triggers cleanup.

The scorer preserves the causal fork inputs and 30 five-minute target rows per arm. It compares actual cooling and fan energy in the first five minutes and over the common post-fork horizon, including recovery, and reports temperature and both comfort scores. **No new matched measurements, measured energy or temperature differences, or branch prediction errors are available yet.** The rolling controller remains unchanged. It recalculates supported forecasts every five minutes, while independent economic continue-versus-release ranking is still disabled. One measured pair would supply candidate-specific fit targets for that decision time. Qualification requires a separate held-out matched pair and comparison of energy ranking, temperature prediction, and comfort feasibility. Later starts and re-entry remain disabled.

**11 focused tests passed**, including four branch tests and seven rolling-controller tests. The pinned BOPTEST runtime passed its read-only check. The new campaign ledger is unused. [Focused branch tests](SDP_BOPTEST_Pilot/final_energy_control/test_release_branch.py)

From the SDP workspace root, print the exact binding. Use the execution command only after the campaign has fresh affirmative authorization. The JSON uses the printed `binding` fields plus `status` set to `EXPLICITLY_AUTHORIZED_G218_RELEASE_BRANCH_1115_01` and the affirmative `approval_text` for the two-arm, 82-advance scope.

```powershell
Set-Location .\SDP_BOPTEST_Pilot
$python = '..\experiments\five_model_hvac16_v1_0_0\.venv\Scripts\python.exe'
& $python -B -m final_energy_control.release_branch --describe
& $python -B -m final_energy_control.release_branch --execute ..\g218_release_branch_authorization.json
```

The campaign SHA-256 is `e041d436fbf6e15c0415abbd234434612b63c19320fa64213e9e371f4f93c818`. The implementation SHA-256 is `64248b3e5c97b882c7d7cd453ccf6e0a482f331e8aabff42fd96c4964a08099d`.

[bound]: SDP_BOPTEST_Pilot/final_energy_control/live_twin_evidence/LIVE_ROLLING_TWIN_01/batches/LIVE_ROLLING_TWIN_01/BATCH_STARTED.json
[completion]: SDP_BOPTEST_Pilot/final_energy_control/live_twin_evidence/LIVE_ROLLING_TWIN_01/batches/LIVE_ROLLING_TWIN_01/LIVE_ROLLING_TWIN_01/RUN_COMPLETED.json
[raw]: assets/calibration-and-rolling.tar.xz
[journal]: assets/calibration-and-rolling.tar.xz
[decisions]: assets/calibration-and-rolling.tar.xz
[native]: assets/calibration-and-rolling.tar.xz
[energy]: assets/calibration-and-rolling.tar.xz
[kpis]: SDP_BOPTEST_Pilot/final_energy_control/live_twin_evidence/LIVE_ROLLING_TWIN_01/batches/LIVE_ROLLING_TWIN_01/LIVE_ROLLING_TWIN_01/official_kpis.json
[chrome]: SDP_BOPTEST_Pilot/final_energy_control/live_twin_browser/LIVE_ROLLING_TWIN_01/BROWSER_VERIFICATION.json
[pause]: references/HISTORICAL_LOCATORS.md#evidence-062e0330a772
[o25]: SDP_BOPTEST_Pilot/final_energy_control/live_twin_browser/LIVE_ROLLING_TWIN_01/02-live-o25.png
[entry]: SDP_BOPTEST_Pilot/final_energy_control/live_twin_browser/LIVE_ROLLING_TWIN_01/03-live-entry-decision.png
[continue]: SDP_BOPTEST_Pilot/final_energy_control/live_twin_browser/LIVE_ROLLING_TWIN_01/04-recomputed-continuation.png
[release]: SDP_BOPTEST_Pilot/final_energy_control/live_twin_browser/LIVE_ROLLING_TWIN_01/06-live-release.png
[recovery]: SDP_BOPTEST_Pilot/final_energy_control/live_twin_browser/LIVE_ROLLING_TWIN_01/07-live-recovery-o25.png
[stopped]: references/HISTORICAL_LOCATORS.md#evidence-f77d0f9e33d6
