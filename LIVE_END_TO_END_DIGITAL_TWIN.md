# Live end-to-end BOPTEST digital twin

**VERIFIED LIVE.** `LIVE_OPTIMIZER_TWIN_01` completed **41 of 41 authorized five-minute advances** on one fresh pinned BOPTEST 0.9.0 BESTEST Air instance. The live optimizer selected one **24.5°C, 45-minute** intervention, verified delivery, returned to native **24°C** cooling, and monitored the full **120-minute** recovery window. The instance acknowledged Stop and its removal was verified. The session is consumed. [Run and cleanup evidence][run] · [Sealed run manifest][seal]

## What the live session verified

| Component | Status | Evidence |
| --- | --- | --- |
| BOPTEST and feedback | **VERIFIED LIVE** | 41 successful POSTs and 41 verified responses from 10:20 to 13:45 on benchmark day offset 218. There were 411 native 30-second samples and 415 verified journal entries. Each decision cutoff and forecast record preceded its advance. |
| O25 Random Forest | **VERIFIED LIVE** | 25 valid origins at +5/+10/+15/+30 minutes and 92 forecast–observation pairs with targets inside the run. Seven origins lacked the required 35 minutes of history. Nine warmer commitments were outside the O25 training domain. Three forecast pairs from the 10:55 native origin crossed the later action change and show actual response under that changed command. |
| Optimization | **VERIFIED LIVE** | Both qualified candidates were scored at 11:00. A3 passed the safety and model checks and had the lowest feasible predicted energy. Shorter holds and higher setpoints were shown as rejected, with reasons. Verified observations informed the hold decisions and confirmed the scheduled release. |
| HVAC action and recovery | **VERIFIED LIVE** | Nine advances held 24.5°C, first verified at 11:05. The 11:45 release command was verified at 11:50 with the override flag cleared and 24°C cooling restored. Heating stayed at 21°C. The remaining decisions held native control through 13:45. No safety fallback was triggered. |
| Dashboard and controls | **VERIFIED LIVE** | Headless Chrome showed automatic updates for time, temperatures, occupancy, cooling and fan power, forecasts and actuals, optimizer decisions, readbacks, cumulative energy, and recovery. Start launched the instance. Pause held 10:30, Resume reverified that endpoint before advancing to 10:35, and Stop was accepted after advance 41 was issued, allowing it to finish before cleanup. |
| Early Stop during override and invalid-readback path | **VERIFIED OFFLINE ONLY** | Covered by the 19 passing offline tests. The live Stop was issued after native recovery was underway and the last permitted advance was in flight. |
| Energy and comfort | **VERIFIED LIVE** | Measured simulator consumption and discomfort are below. Electricity savings relative to native control are **NOT VERIFIED** because this demonstration had a single arm. |

[Raw API receipts][api] · [Ordered journal][journal] · [Optimizer decisions][decisions] · [Chrome verification transcript][chrome] · [Integration tests](SDP_BOPTEST_Pilot/final_energy_control/test_digital_twin.py)

## Optimizer prediction at 11:00

The two predictions cover the same 165 minutes. A3’s predicted energy advantage was **0.04058 kWh**, or **0.03425 kWh** after subtracting the model’s energy uncertainty. The predicted peak also passed the retained temperature reserve. These values are model outputs. [Candidate records][decisions]

| Candidate | Predicted cooling + fan | Predicted peak indoor temp | Decision |
| --- | ---: | ---: | --- |
| A0 · Native control | 2.16308 kWh | 24.017°C | Feasible |
| A3 · 24.5°C for 45 minutes | 2.12250 kWh | 24.555°C | Selected |

## Actual BOPTEST measurements

| Window | Cooling kWh | Fan kWh | Combined kWh | Indoor temperature at start → end |
| --- | ---: | ---: | ---: | ---: |
| Native before hold, 10:20–11:00 | 0.40388 | 0.01625 | 0.42013 | 24.016 → 24.018°C |
| 24.5°C hold, 11:00–11:45 | 0.46436 | 0.01687 | 0.48123 | 24.018 → 24.519°C |
| Native recovery, 11:45–13:45 | 1.73163 | 0.08336 | 1.81499 | 24.519 → 24.006°C |
| **Full run, 10:20–13:45** | **2.59987** | **0.11648** | **2.71635** | **24.016 → 24.006°C** |

At the first 24.5°C readback, indoor temperature reached **24.469°C** and cooling/fan power changed from **647.4/26.9 W** at 11:00 to **550.3/18.8 W** at 11:05. At the verified native release at 11:50, the indoor temperature was **24.058°C** and power was **796.0/36.4 W**. The occupied peak was **24.549°C**. Official discomfort was **0.424717 K·h**. The separate occupied 20–26°C project replay recorded **0 K·h** and **0 violation minutes**. [30-second results][native] · [Official BOPTEST KPIs][kpis] · [Electricity reconciliation][energy]

## Genuine Chrome screenshots

[Paused at 10:30][paused] · [Decision and 24.5°C readback at 11:05][action] · [Live response during the hold][response] · [O25 forecasts and native recovery at 11:50][recovery] · [Stopped after 41 advances][stopped]

In the recovery screenshot, the optimizer summary shows the current native action beside the timestamp of the original 11:00 candidate evaluation. The candidate row preserves A3 as the selection at that origin. The readback and recovery panel show the current state. [Live recovery frame][recovery]

## Launch and authorization

The frozen scope was one instance, one seven-day native warmup, 41 maximum advances, at most one 45-minute hold, the optional 400 W guard off, and no retries. The session’s browser displays day 219 because it numbers days starting at one. G174, G218, G299 and G163 records were preserved. [User authorization](live_optimizer_twin_authorization.json) · [Frozen configuration][config]

The Chrome automation used the existing launcher from the SDP workspace root, with `-NoBrowser` because it opened headless Chrome itself.

```powershell
.\run_live_digital_twin.ps1 -AuthorizationFile .\live_optimizer_twin_authorization.json -NoBrowser
```

For an interactive run the launcher opens Chrome or the Windows default browser when `-NoBrowser` is omitted. This session’s authorization is consumed. A fresh live demo requires a new unused session binding and explicit authorization.

[run]: SDP_BOPTEST_Pilot/final_energy_control/live_twin_evidence/LIVE_OPTIMIZER_TWIN_01/batches/LIVE_OPTIMIZER_TWIN_01/LIVE_OPTIMIZER_TWIN_01/RUN_COMPLETED.json
[seal]: references/HISTORICAL_LOCATORS.md#evidence-174ca72efc86
[api]: references/HISTORICAL_LOCATORS.md#evidence-0971bbcafbf4
[journal]: references/HISTORICAL_LOCATORS.md#evidence-31bd0ce7cd28
[decisions]: references/HISTORICAL_LOCATORS.md#evidence-698531363d03
[chrome]: SDP_BOPTEST_Pilot/final_energy_control/live_twin_browser/LIVE_OPTIMIZER_TWIN_01/BROWSER_VERIFICATION.json
[native]: references/HISTORICAL_LOCATORS.md#evidence-0c0122c8cc13
[kpis]: SDP_BOPTEST_Pilot/final_energy_control/live_twin_evidence/LIVE_OPTIMIZER_TWIN_01/batches/LIVE_OPTIMIZER_TWIN_01/LIVE_OPTIMIZER_TWIN_01/official_kpis.json
[energy]: references/HISTORICAL_LOCATORS.md#evidence-85118485beb7
[config]: SDP_BOPTEST_Pilot/final_energy_control/live_twin_evidence/LIVE_OPTIMIZER_TWIN_01/batches/LIVE_OPTIMIZER_TWIN_01/LIVE_CONFIGURATION.json
[paused]: references/HISTORICAL_LOCATORS.md#evidence-7674ef5b5050
[action]: report/figures/23_fixed_live_screen.png
[response]: references/HISTORICAL_LOCATORS.md#evidence-e178938f71a8
[recovery]: references/HISTORICAL_LOCATORS.md#evidence-29b9027fa10f
[stopped]: references/HISTORICAL_LOCATORS.md#evidence-c23575b6f006
