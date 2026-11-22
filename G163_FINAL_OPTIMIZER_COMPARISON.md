# G163 final optimizer comparison

**All three real BOPTEST arms completed.** The predictive optimizer used **0.055221 kWh less than native (0.3342%)** and **0.019459 kWh more than fixed warmer (0.1183%)**. The optimizer’s frozen outcome was **ENERGY PASS / COMFORT FAIL**. It reduced discomfort relative to fixed warmer, while still increasing it relative to native. [Sealed comparison][results]

## Execution and provenance

The authorized `OPTIMIZER_G163_NATIVE_FIXED_PREDICTIVE` campaign ran once on pinned BOPTEST **0.9.0 BESTEST Air**. All arms shared the seven-day native warmup, the same 72-hour period (`14,083,200–14,342,400` benchmark seconds), and matched weather and occupancy. Each arm completed **864 five-minute advances** and recorded **8,641 thirty-second samples**. Both pair checks verified warmup and pre-intervention equivalence and matched forcing across all 864 forecast origins. All three instances acknowledged Stop and were removed. The ledger closed all three arms as `CONSUMED_COMPLETED` with zero retries. G174, G218, G299, and the live demo were preserved. [Bound execution receipt][binding] · [Evidence manifest][seal] · [User authorization](SDP_BOPTEST_Pilot/optimizer_g163_authorization.json)

| Frozen identity | SHA-256 |
| --- | --- |
| Campaign | `5a2afed5fca32872b821513196d5d95e7642ebb473e0410ed7bfc6099eb80034` |
| Implementation | `67dae8d5b867328682b3db4dcc134baaa02caa0e1de60874f25227efa1401a6f` |
| BESTEST Air FMU | `158008fa3b635280a67dfed8bab5804d1f9a96d218b467dfebab77e5cbf8b86a` |

## Measured results

| Metric | A · Native | B · Fixed warmer | C · Predictive optimizer |
| --- | ---: | ---: | ---: |
| Cooling electricity (kWh) | 15.899675 | 15.832631 | 15.850229 |
| Fan electricity (kWh) | 0.623608 | 0.615971 | 0.617833 |
| **Cooling + fan (kWh)** | **16.523282** | **16.448602** | **16.468062** |
| Official BOPTEST discomfort (K·h) | 1.298754 | 2.431626 | 2.054106 |
| Project 20–26°C discomfort (K·h) | 0.053918 | 0.055653 | 0.055002 |
| Occupied project violation minutes | 11.5 | 11.5 | 11.5 |
| Maximum occupied indoor temperature (°C) | 26.697 | 26.708 | 26.708 |
| Verified 45-minute interventions / native releases | 0 / 0 | 3 / 3 | 2 / 2 |
| Controller safety vetoes / safety fallbacks | 0 / 0 | 0 / 0 | 0 / 0 |

Savings are reference consumption minus trial consumption. The intervention and recovery columns use each arm’s own delivered windows, paired with native at the same times. A positive recovery penalty means extra consumption after release. [Energy and comfort breakdown][results]

| Comparison | 72-hour savings | During holds | Recovery penalty | Net holds + recovery |
| --- | ---: | ---: | ---: | ---: |
| Fixed warmer vs native | +0.074680 kWh (+0.4520%) | +0.169823 kWh | 0.051367 kWh | +0.118455 kWh |
| Optimizer vs native | +0.055221 kWh (+0.3342%) | +0.118238 kWh | 0.034923 kWh | +0.083315 kWh |
| Optimizer vs fixed warmer | −0.019459 kWh (−0.1183%) | | | |

## Frozen criteria

Both controlled arms passed the **0.0225 kWh** minimum for full-period savings and for net hold-plus-recovery savings. All overrides and native releases were verified. Holds stayed below **25.5°C**, and no occupied project-band excursions occurred in the delivered holds or their recovery windows. Fixed rejoined the native trajectory at the frozen recovery marker after **15, 20, and 20 minutes**. The optimizer rejoined after **20 minutes** for each hold.

Both controlled arms **failed the full-period comfort criterion**. The identical 11.5 violation minutes were more severe against the project band. Fixed added **0.001735078 K·h** and the optimizer added **0.001084487 K·h** versus native, both above the **0.0000001 K·h** comparison tolerance. The official BOPTEST KPI also rose in both controlled arms. [Frozen checks and window scores][results]

## Did prediction add value?

| 11:00 decision | Fixed warmer | Optimizer | Optimizer evidence |
| --- | --- | --- | --- |
| Day 1 | 24.5°C | Native | The action model rejected the initial state or issued weather as outside its measured envelope. Candidate energy estimates were unavailable. |
| Day 2 | 24.5°C | 24.5°C | Predicted 165-minute energy was 1.90058 kWh native and 1.86050 kWh warmer. |
| Day 3 | 24.5°C | 24.5°C | Predicted 165-minute energy was 1.66561 kWh native and 1.62516 kWh warmer. |

The two controllers issued different commands in nine intervals, all during the Day 1 hold. The optimizer never warmed when fixed stayed native. Day 1 optimizer consumption matched native and was **0.028271 kWh higher than fixed**. Across all 72 hours, the optimizer had **0.000650592 K·h less project discomfort** and **0.377520 K·h less official discomfort** than fixed, with the same violation duration. The model’s eligibility check changed behavior. Both controllers failed the comfort requirement, and fixed saved more electricity. These results apply to one development scenario. [Recorded decisions][decisions] · [Measured comparison][results]

## Dashboard and SDP closeout

The measured G163 replay opens at the Day 1 decision and supports play, pause, scrubbing, decision jumps, and a final comparison. It displays the three measured temperature, power, and energy trajectories, requested and verified setpoints, candidate predictions, two savings comparisons, and both comfort scores. Chrome verified the Day 1 decision split, Day 2 optimizer selection, plotting, playback controls, and the final 864-interval table. The replay checks the completed evidence manifest before displaying results. **41 regression tests passed.** The existing G174/G218 replay and live-demo entry points retain their existing source. [G163 replay code](SDP_BOPTEST_Pilot/final_energy_control/g163_replay.py)

From the SDP workspace root, open the measured replay at [localhost](http://127.0.0.1:8770/).

```powershell
Set-Location .\SDP_BOPTEST_Pilot
& ..\experiments\five_model_hvac16_v1_0_0\.venv\Scripts\python.exe -B -m final_energy_control.g163_replay
```

Finish the SDP with the verified live-integration demo and this measured comparison. Record the tested optimizer as **NO-GO for comfort-preserving deployment under the frozen criteria**. A claim of comfort-preserving savings or superiority over fixed control would require separate matched validation that passes the comfort gate.

[results]: SDP_BOPTEST_Pilot/final_energy_control/optimizer_runtime_state/batches/OPTIMIZER_G163_NATIVE_FIXED_PREDICTIVE/OPTIMIZER_COMPARISON.json
[binding]: SDP_BOPTEST_Pilot/final_energy_control/optimizer_runtime_state/batches/OPTIMIZER_G163_NATIVE_FIXED_PREDICTIVE/BATCH_STARTED.json
[seal]: SDP_BOPTEST_Pilot/final_energy_control/optimizer_runtime_state/batches/OPTIMIZER_G163_NATIVE_FIXED_PREDICTIVE/BATCH_ARTIFACT_MANIFEST.json
[decisions]: references/HISTORICAL_LOCATORS.md#evidence-5acf2d7ed4da
