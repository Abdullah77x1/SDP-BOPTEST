# G218 BESTEST Air fan-control result

**Completed and passed the frozen trial criteria.** `G218_FAN060_1400_01` saved **0.005179 kWh (0.1809%)** of cooling-plus-fan electricity over the full matched period. Both arms stayed within the project’s occupied 20–26°C band. Official BOPTEST discomfort increased by **0.020085 K·h**. This was one measured simulator case. The fan command remains outside the autonomous optimizer. [Sealed comparison][comparison]

## What the pinned model does

- The wrapper selects `TestCase_Ideal` and its `FanCoilUnit_T`. `fcu_oveFan_u` specifies a fraction of **0.55 kg/s** design flow. The gain feeds an ideal `FlowControlled_m_flow` mover against a fixed air resistance with **185 Pa** nominal drop. The reported fan electricity is `fan.P`. The library uses fluid power and mover efficiency or performance characteristics. Cubic scaling is a useful local estimate along the fixed-resistance operating curve. The sealed measurements supply the comparison. [Wrapped interface][wrapper] · [Active fan-coil model][fcu] · [Modelica Buildings v8 mover equations](https://simulationresearch.lbl.gov/modelica/releases/v8.0.0/help/Buildings_Fluid_Movers_UsersGuide.html)
- The native thermostat clips the summed heating and cooling PI outputs to `[0,1]` for the fan. It separately maps the cooling PI signal to **24–12°C** supply temperature and the heating signal to **21–40°C**. The API exposes fan fraction **0–1** and supply setpoint **285.15–313.15 K**. These are interface limits. `/advance` and `/results` report the effective overwrite output under the `_u` name. The trial checks this readback, its activation flag, and the independent mass-flow measurement. [Thermostat][thermostat] · [Signal-to-temperature mapping][mapping] · [BOPTEST effective input readbacks][readback]
- The ideal `PropertySource_T` imposes supply temperature. Cooling electricity is `max(0, ṁ × (h_return − h_supply)) / 3`. Fan heat is excluded from the air. Lower airflow initially reduces sensible delivery at the same supply temperature. The native PI can lower supply temperature as the room warms and restore part of that load. Fixed COP, no coil-condensation model, and later recovery limit what these results can say about real equipment. [Fan-coil energy equations][fcu] · [Pinned testcase assumptions][case]

## Measured native operating points

Screened sealed G174, G218 and G163 native recordings for occupied 30-minute periods with active cooling, no heating, native control, and indoor endpoints no higher than 24.15°C. These representative high-fan periods use 30-second power integration. [Native G174][g174] · [Native G218][g218] · [Native G163][g163]

| Scenario and benchmark time | Mean fan W | Mean cooling W | Native normalized fan command |
| --- | ---: | ---: | ---: |
| G174, day offset 175, 13:40–14:10 | 42.36 | 869.62 | 0.6251–0.6258 |
| **G218, day offset 218, 14:00–14:30** | **48.43** | **955.26** | **0.6532–0.6546** |
| G163, day offset 164, 13:25–13:55 | 30.01 | 693.53 | 0.5572–0.5578 |

The native G218 selection window measured **0.3592–0.3600 kg/s**, **16.145–16.162°C** supply setpoint and a **24.004°C** room peak. Before execution, cubic scaling estimated **0.0055 kWh of fan-only savings** for a 30-minute command at 0.60. The trial measured **0.005480 kWh of fan savings during the hold**, or **22.63%** of native fan electricity during that interval. The full-period cooling-plus-fan result is below.

## Verified execution

Both genuine pinned BOPTEST **0.9.0 BESTEST Air** instances initialized at **13:30** on benchmark day offset 218 after seven native warmup days. Each completed **36 five-minute advances**, **72 total**, with no retries. The journals verified 321 and 322 receipts and one Stop per arm. BOPTEST confirmed both instances were removed. The ledger is `CONSUMED_COMPLETED` for both arms. [Authorization](g218_fan_trial_authorization.json) · [Runtime and source binding][binding] · [Arm A cleanup][close-a] · [Arm B cleanup][close-b] · [Batch seal][seal]

The arms matched across **20,161 warmup samples**, seven initial and pre-intervention endpoints, six native-prefix advances and their 30-second histories, and the issued forcing at all 36 origins. Arm A sent only native commands. Arm B verified **0.60** on all six advances from **14:00 to 14:30**, with endpoint airflow **0.330 kg/s**. All room and supply-temperature override flags stayed released. The effective occupied room targets remained **24°C cooling and 21°C heating**. Release was commanded at 14:30 and the 14:35 readback verified native fan operation. Both arms observed the full **120-minute recovery**, with no vetoes, readback failures, or additional heating input. [Pre-intervention equivalence][match] · [Treatment commands][cmd-b] · [Arm A measurements][native-a] · [Arm B measurements][native-b]

## Measured electricity

All values are kWh integrated from 30-second signals. Positive savings mean lower electricity than Arm A. [Sealed energy and comfort scores][comparison]

| Period | Native cooling | Fan-arm cooling | Native fan | Fan-arm fan | Native combined | Fan-arm combined | Combined saving |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Hold, 14:00–14:30 | 0.477602 | 0.474774 | 0.024215 | 0.018735 | 0.501817 | 0.493509 | +0.008308 |
| Recovery, 14:30–16:30 | 1.778472 | 1.781224 | 0.087210 | 0.087587 | 1.865682 | 1.868811 | −0.003129 |
| Hold + recovery, 14:00–16:30 | 2.256074 | 2.255998 | 0.111425 | 0.106322 | 2.367499 | 2.362320 | **+0.005179 (0.2188%)** |
| Full matched run, 13:30–16:30 | 2.727371 | 2.727294 | 0.135131 | 0.130029 | 2.862502 | 2.857323 | **+0.005179 (0.1809%)** |

During the hold, average effective supply temperature fell from **16.151°C to 15.539°C** as the native thermostat responded. Cooling electricity still fell by **0.002828 kWh** during the hold. Recovery added **0.002752 kWh cooling** and **0.000377 kWh fan**. This offset **37.7%** of the hold’s combined savings. The net reduction exceeded the **0.0000572 kWh** energy-reconciliation bound. The observed recovery marker was **10 minutes** after release. [30-second native trace][native-a] · [30-second fan trace][native-b] · [Frozen scoring criteria][comparison]

## Measured comfort

| Metric | Native | Fan 0.60 | Fan minus native |
| --- | ---: | ---: | ---: |
| Hold mean indoor temperature (°C) | 24.0003 | 24.0400 | +0.0397 |
| Hold peak indoor temperature (°C) | 24.0036 | 24.1341 | +0.1305 |
| Recovery mean indoor temperature (°C) | 23.9923 | 23.9823 | −0.0099 |
| Full-run mean indoor temperature (°C) | 23.9960 | 23.9960 | <0.000001 |
| Full-run peak indoor temperature (°C) | 24.0086 | 24.1341 | +0.1255 |
| Official BOPTEST discomfort (K·h) | 0.003677 | 0.023761 | +0.020085 |
| Project 20–26°C discomfort (K·h) | 0 | 0 | 0 |
| Occupied project-band violation minutes | 0 | 0 | 0 |

Means are time-weighted. The largest pointwise warming was **0.131°C at 14:04**. The extra official discomfort accumulated during the hold despite the unchanged room cooling target. Both arms met the separate project comfort band. All eight frozen trial checks passed. [Official and project comfort scores][comparison] · [Measured temperatures][native-b]

**Repeat the same 0.60 candidate** in one independently authorized, matched occupied cooling scenario. Check whether the small net saving survives recovery and quantify the official comfort cost again. Defer additional fan settings, joint fan/supply-temperature optimization, and optimizer integration until that comparison is available.

The frozen configuration SHA-256 is `05b76ee9d150e4b9c84368b3aa549d0760c9803657806cda3578bf7b3b5fe47b`. The implementation SHA-256 is `df9b3553e817d6cf68ffffd5063d0e06e12e433b82a0c243827da593e0a62139`. Earlier campaigns and simulator, O25, optimizer and dashboard sources were preserved. The pinned model’s fixed COP and ideal supply-temperature source limit transfer to real equipment. [Bound implementation](SDP_BOPTEST_Pilot/final_energy_control/fan_trial.py) · [Bound execution receipt][binding]

[wrapper]: SDP_BOPTEST_Pilot/deployment/official_v0.9.0/project1-boptest-0.9.0/testcases/bestest_air/models/wrapped.mo
[fcu]: SDP_BOPTEST_Pilot/deployment/official_v0.9.0/project1-boptest-0.9.0/testcases/bestest_air/models/BESTESTAir/BaseClasses/FanCoilUnit_T.mo
[case]: SDP_BOPTEST_Pilot/deployment/official_v0.9.0/project1-boptest-0.9.0/testcases/bestest_air/models/BESTESTAir/TestCases/TestCase_Ideal.mo
[thermostat]: SDP_BOPTEST_Pilot/deployment/official_v0.9.0/project1-boptest-0.9.0/testcases/bestest_air/models/BESTESTAir/BaseClasses/Thermostat_T.mo
[mapping]: SDP_BOPTEST_Pilot/deployment/official_v0.9.0/project1-boptest-0.9.0/testcases/bestest_air/models/BESTESTAir/BaseClasses/ControlToTemperature.mo
[readback]: SDP_BOPTEST_Pilot/deployment/official_v0.9.0/project1-boptest-0.9.0/testcase.py
[g174]: assets/calibration-and-rolling.tar.xz
[g218]: assets/g218-sealed-histories.tar.xz
[g163]: assets/calibration-and-rolling.tar.xz
[comparison]: SDP_BOPTEST_Pilot/final_energy_control/fan_trial_evidence/G218_FAN060_1400_01/batches/G218_FAN060_1400_01/FAN_COMPARISON.json
[binding]: SDP_BOPTEST_Pilot/final_energy_control/fan_trial_evidence/G218_FAN060_1400_01/batches/G218_FAN060_1400_01/BATCH_STARTED.json
[seal]: SDP_BOPTEST_Pilot/final_energy_control/fan_trial_evidence/G218_FAN060_1400_01/batches/G218_FAN060_1400_01/BATCH_ARTIFACT_MANIFEST.json
[close-a]: SDP_BOPTEST_Pilot/final_energy_control/fan_trial_evidence/G218_FAN060_1400_01/batches/G218_FAN060_1400_01/G218_FAN060_1400_01_A/RUN_COMPLETED.json
[close-b]: SDP_BOPTEST_Pilot/final_energy_control/fan_trial_evidence/G218_FAN060_1400_01/batches/G218_FAN060_1400_01/G218_FAN060_1400_01_B/RUN_COMPLETED.json
[match]: references/HISTORICAL_LOCATORS.md#evidence-61123dbe24b0
[cmd-b]: references/HISTORICAL_LOCATORS.md#evidence-a1b047ce8724
[native-a]: references/HISTORICAL_LOCATORS.md#evidence-135cebcbb31d
[native-b]: references/HISTORICAL_LOCATORS.md#evidence-2a01a4e04772
