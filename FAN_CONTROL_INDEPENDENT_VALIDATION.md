# G258 independent fan-control validation

**Executed and verified on pinned BOPTEST 0.9.0.** The selected window is **G258, benchmark day offset 258, 14:00–14:30**. The 0.60 fan override saved **0.006308 kWh (0.2111%)** over the full matched run and increased official discomfort by **0.024559 K·h**. Both arms stayed within the project’s 20–26°C band. G218 remains development evidence, with its original sealed result unchanged. [Native archive](EXCLUDED_FILES_INDEX.md) · [G218 measured result](FAN_CONTROL_FEASIBILITY.md)

## Why this window

The screen used only sealed native records. G020, G074, and G146 had no sustained eligible cooling window at the original fan thresholds. G174, G163, and G218 were part of the initial fan study. G288’s parent archive warmup overlaps a previously exposed cooling footprint. G258 is a development scenario with an independent time and weather footprint for the fan action. Its proposed warmup starts **30 days 13 hours 30 minutes** after the full G218 screening footprint ends and clears the registered protected-window embargo. Both trials use the same FMU and weather year.

Keeping the original **14:00** intervention time, G258 day 258 had the smallest sum of relative differences from G218 in native mean fan and cooling watts. The later same-clock G258 windows averaged 70.55/1,222.74 W and 79.18/1,319.75 W. The selected window had continuous occupancy and cooling, zero heating, and a 24.0044°C native room peak. No fan-control response from G258 was used in selection. [Selection and footprint checks](SDP_BOPTEST_Pilot/final_energy_control/fan_replication.py)

| Archived native measurement, 14:00–14:30 | G218 development | Selected G258 |
| --- | ---: | ---: |
| Mean fan power | 48.43 W | 50.89 W |
| Mean cooling power | 955.26 W | 985.85 W |
| Effective normalized fan command | 0.6532–0.6546 | 0.6634–0.6655 |
| Outdoor temperature | 26.70–27.04°C | 20.60–20.87°C |
| Global horizontal irradiance at recorded endpoints | 757–824 W/m² | 648–718 W/m² |

## Exact frozen scope

| Shared settings | Arm A | Arm B |
| --- | --- | --- |
| Pinned BOPTEST 0.9.0 BESTEST Air. Seven-day native warmup. Both arms initialize at 13:30 and end at 16:30. | Native throughout | Native until 14:00, **0.60** fan command until 14:30, then **120 minutes** native recovery |
| Native 24°C cooling, 21°C heating, and native supply-air-temperature control | 36 five-minute advances | 36 five-minute advances, at most six fan commands |

The upper bound is **two sequential instances, two initializations, 72 total advances, and zero retries or replacements**. The shared collector checks the fresh native arm’s eligibility before reserving Arm B, and verifies the warmup, native prefix, and forcing before actuation. Existing thresholds, readback checks, recovery test, and scoring criteria carry over unchanged. [Shared collector and scorer](SDP_BOPTEST_Pilot/final_energy_control/fan_trial.py)

## Execution verification

The repository recorded the [explicit authorization](g258_fan_trial_authorization.json) against the frozen campaign. The live pinned runtime passed verification. Both arms completed **36 genuine five-minute advances**, with Arm A removed before Arm B started and both removals verified. There were zero retries, safety vetoes, or replacements. The raw evidence matched **20,161 warmup samples**, seven initial and native-prefix endpoints, and the full period’s weather. The treatment delivered six verified intervals at fan command 0.60, with airflow **0.330 kg/s** versus **0.365–0.366 kg/s** in the native hold. The fan override released at 14:30, its flag was clear at the 14:35 readback, and both arms completed the 120-minute recovery. Room setpoints read back at native 21°C heating and 24°C cooling throughout. Supply-air temperature stayed under native control. The archived 23 offline tests passed before this run. Both sealed comparisons were independently replayed from the recorded trajectories, and the official discomfort replay matched the BOPTEST API. [G258 native completion](SDP_BOPTEST_Pilot/final_energy_control/fan_trial_evidence/G258_FAN060_1400_01/batches/G258_FAN060_1400_01/G258_FAN060_1400_01_A/RUN_COMPLETED.json) · [Fan completion](SDP_BOPTEST_Pilot/final_energy_control/fan_trial_evidence/G258_FAN060_1400_01/batches/G258_FAN060_1400_01/G258_FAN060_1400_01_B/RUN_COMPLETED.json) · [Matched prefix](EXCLUDED_FILES_INDEX.md)

## Measured comparison

| Metric | G218 native | G218 fan 0.60 | G258 native | G258 fan 0.60 |
| --- | ---: | ---: | ---: | ---: |
| Intervention fan electricity (kWh) | 0.024215 | 0.018735 | 0.025441 | 0.018744 |
| Intervention cooling electricity (kWh) | 0.477602 | 0.474774 | 0.492884 | 0.489282 |
| Intervention cooling + fan (kWh) | 0.501817 | 0.493509 | 0.518326 | 0.508026 |
| Recovery cooling + fan (kWh) | 1.865682 | 1.868811 | 1.960369 | 1.964360 |
| Full 13:30–16:30 cooling + fan (kWh) | 2.862502 | 2.857323 | 2.987869 | 2.981561 |
| Intervention mean indoor temperature (°C) | 24.0003 | 24.0400 | 24.0015 | 24.0505 |
| Full mean indoor temperature (°C) | 23.9960 | 23.9960 | 23.9962 | 23.9962 |
| Full peak indoor temperature (°C) | 24.0086 | 24.1341 | 24.0100 | 24.1615 |
| Full official BOPTEST discomfort (K·h) | 0.003677 | 0.023761 | 0.004464 | 0.029022 |
| Full project 20–26°C discomfort (K·h) | 0 | 0 | 0 | 0 |
| Project occupied violation minutes | 0 | 0 | 0 | 0 |

G258 saved **0.010300 kWh** during intervention, split between **0.006697 kWh fan** and **0.003602 kWh cooling**. Recovery used **0.003991 kWh** more, including **0.003499 kWh of cooling** and **0.000493 kWh of fan**. Net saving was **0.006308 kWh (0.2111%)**, versus **0.005179 kWh (0.1809%)** in G218 after a **0.003129 kWh** recovery penalty. G258’s largest paired indoor difference was **+0.158°C at 14:04**, versus **+0.131°C** in G218. G258 official discomfort increased **0.024559 K·h**, versus **0.020085 K·h** in G218. Both trials passed the eight frozen provisional fan checks, which use the project band for comfort acceptance. The official discomfort increase is a repeated trade-off. The earlier **0.0055 kWh** G218 figure was a fan-only screening estimate. [G258 sealed comparison](SDP_BOPTEST_Pilot/final_energy_control/fan_trial_evidence/G258_FAN060_1400_01/batches/G258_FAN060_1400_01/FAN_COMPARISON.json) · [G218 sealed comparison](SDP_BOPTEST_Pilot/final_energy_control/fan_trial_evidence/G218_FAN060_1400_01/batches/G218_FAN060_1400_01/FAN_COMPARISON.json)

## Decision and next experiment

Deprioritize additional fan-only trials and keep the action out of the optimizer. The repeatable saving is about 5–6 Wh per three-hour window, with worse official comfort in both trials. In G258, the native controller’s mean supply-air command dropped from **16.02°C to 15.28°C** when airflow was restricted, yet room temperature peaked higher. A sensible-load calculation using recorded native airflow and room and supply temperatures estimates that **15.14–15.20°C** at 0.330 kg/s would match native sensible cooling over that window. At 14:00 the estimate is **15.20°C** versus **16.04°C** native. Those values are calculations from archived measurements. The pinned model sets supply temperature through a separate override and calculates cooling electricity from the air-side enthalpy change with a fixed COP of 3. Earlier supply-temperature compensation could reduce the initial warming while preserving some fan saving. The net effect requires measurement across recovery. [Pinned fan-coil model](SDP_BOPTEST_Pilot/deployment/official_v0.9.0/project1-boptest-0.9.0/testcases/bestest_air/models/BESTESTAir/BaseClasses/FanCoilUnit_T.mo)

The next experiment should be one separately authorized **matched G258 native versus joint control** pair. Use the existing 14:00–14:30 window and two-hour native recovery. Keep the 24°C room target and pair the same 0.60 fan command with a bounded supply-air adjustment calculated from measurements available at the decision time. Verify both readbacks and native fallback. Freeze the criteria before execution, including positive net cooling-plus-fan savings after recovery and no added official or project discomfort.
