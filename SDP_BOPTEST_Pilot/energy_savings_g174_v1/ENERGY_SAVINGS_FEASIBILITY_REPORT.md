# BOPTEST energy-savings feasibility

The single qualified G174 run used **0.078468 kWh less cooling-plus-fan electricity over 72 h (0.4027%)**. All three overrides were delivered. The campaign decision is **NO-GO for ML dataset expansion** because full-period 20–26°C discomfort severity increased.

## Configuration and qualification

| Item | Setting |
| --- | --- |
| Simulator | Pinned BOPTEST 0.9.0 BESTEST Air, unchanged FMU, occupancy and Denver-Stapleton TMY |
| Scenario | G174 development, custom t=15033600 s, seven-day native warmup, 72 h through t=15292800 s |
| Native reference | B1V01_G174_NREF. Occupied heating 21°C and cooling 24°C |
| Experimental arm | ESV01_G174_WARM45. 24.5°C cooling-only override daily from 11:00 to 11:45 across the three days |
| Budget | One instance, one initialization, 864 five-minute advances, 30-second native history, no retries |
| Safeguards | Exact target and occupied source-schedule checks, at least 0.5 K heat/cool separation, 21.75°C activation and 21.50°C continuation lower margins, 25.5°C upper fallback. Veto latches native through the end of the pulse |
| Comfort | Official benchmark KPI and published bounds retained. Separate project-specific occupied 20–26°C air assessment |
| Go criterion | Full delivery and ≥0.0225 kWh savings both across scheduled holds plus their two-hour recoveries and over 72 h. Zero project-band excursions in the comparison windows and no added project-band burden over 72 h |

Previously, Docker's Linux-engine named pipe was missing. The new preflight found the engine and the pinned container identities, with Redis, MinIO, web and worker stopped. I started those existing containers without a rebuild or pull. The unchanged verifier then passed all six pinned container identities, platform, worker and localhost port checks. [Restoration evidence](../../references/HISTORICAL_LOCATORS.md#evidence-b6f119e2945f)

The frozen D2/B1 guard capped occupied overrides at the published 24°C upper bound, and B1's collector pinned the active readback to 23.75°C. The new campaign uses its own exact command and replay checks while retaining the qualified transport, FMU checks, native event validation, energy reconciliation and one-attempt ledger.

G174 had 19.486 kWh of native cooling-plus-fan electricity versus 8.456 kWh in G146. The qualified B1 45-minute clock provides three active cooling periods and a two-hour recovery window. NREF reproduced D2 G174 native across 865 endpoints, 8,641 native samples, 20,161 warmup samples and 864 forecast origins on shared channels at 1e−7. The historical source check verified 5,248 raw artifact hashes. [Reference equivalence](../../EXCLUDED_FILES_INDEX.md#workspace-only-publication-exclusions)

| Native day, 11:00–11:45 | Cooling / fan / combined kWh | Indoor °C |
| --- | --- | --- |
| 1 | 0.426967 / 0.016688 / 0.443655 | 24.013 to 24.019 |
| 2 | 0.565092 / 0.025538 / 0.590631 | 24.009 to 24.015 |
| 3 | 0.418937 / 0.016310 / 0.435247 | 24.012 to 24.018 |

All 8 offline checks passed, including the fabricated full-budget collection, replay, native release and append-only seal. Implementation SHA-256 **036099ebc352e120990a0b28588cee7b562e25ae6ceccb9d549f113d04d61e2b**. [Frozen campaign](CAMPAIGN.json) · [Qualification](../../references/HISTORICAL_LOCATORS.md#evidence-1535c43e8dc2)

The paired analysis also reproduced the archived G174 B1 C45 increase of 0.041300 kWh as a read-only regression check. [Historical analysis replay](../../references/HISTORICAL_LOCATORS.md#evidence-5b25b36f870f)

The 20–26°C range is a project analysis assumption for this simulator. The 30-second occupied-air statistics use the archived/project limits as indicated. Official comfort is reported independently using the unchanged BOPTEST KPI.

## Measured result

The run used one deployment, one initialization and 864 advances. The replay verified instance removal, deployed FMU, endpoint/native command readbacks, official KPI and energy reconciliation. Shared channels matched through the first action at 133 endpoints and 1321 native samples. Weather and occupancy vintages agreed at all 864 origins. [Execution evidence](../../references/HISTORICAL_LOCATORS.md#evidence-5b5947109669)

| Day | Delivered min | Target K | Actual release s | Vetoes | Recovery marker min |
| --- | --- | --- | --- | --- | --- |
| 1 | 45 | [297.65] | 15075900 | None | 15 |
| 2 | 45 | [297.65] | 15162300 | None | 25 |
| 3 | 45 | [297.65] | 15248700 | None | 20 |

The marker requires three consecutive five-minute paired values within 0.05°C and 0.01 kW. Recovery is searched for 120 minutes from actual release. The matched energy windows below retain the same scheduled clock for each policy.

| Day | Window | Native cooling / fan / combined kWh | Warm cooling / fan / combined kWh | Combined change | Native °C | Warm °C |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | Hold | 0.426967 / 0.016688 / 0.443655 | 0.373803 / 0.012054 / 0.385856 | -0.057798 kWh (-13.0277%) | 24.013 to 24.019 | 24.019 to 24.558 |
| 1 | Scheduled recovery | 1.366862 / 0.058699 / 1.425561 | 1.382100 / 0.059566 / 1.441666 | +0.016105 kWh (+1.1298%) | 24.004 to 24.013 | 23.986 to 24.514 |
| 2 | Hold | 0.565092 / 0.025538 / 0.590631 | 0.507795 / 0.019522 / 0.527317 | -0.063314 kWh (-10.7197%) | 24.009 to 24.015 | 24.015 to 24.543 |
| 2 | Scheduled recovery | 1.673624 / 0.079893 / 1.753517 | 1.691799 / 0.081064 / 1.772862 | +0.019346 kWh (+1.1032%) | 24.001 to 24.009 | 23.988 to 24.510 |
| 3 | Hold | 0.418937 / 0.016310 / 0.435247 | 0.365582 / 0.011711 / 0.377293 | -0.057954 kWh (-13.3153%) | 24.012 to 24.018 | 24.018 to 24.555 |
| 3 | Scheduled recovery | 1.336333 / 0.057030 / 1.393363 | 1.353797 / 0.058036 / 1.411833 | +0.018470 kWh (+1.3256%) | 24.005 to 24.013 | 23.986 to 24.514 |

Full 72 h cooling / fan / combined electricity was **18.693209 / 0.792772 / 19.485982 kWh** for native and **18.624111 / 0.783402 / 19.407514 kWh** for WARM45. The combined change was **-0.078468 kWh (-0.4027%)**, computed as WARM45 minus native. The indoor range was **22.775 to 28.275°C** for native and **22.775 to 28.289°C** for WARM45.

| Comfort over 72 h | Native | WARM45 |
| --- | --- | --- |
| Official BOPTEST tdis_tot (K·h) | 1.404807 | 2.537502 |
| Official 21–24°C, occupied air | 1109.5 min / 1.427884 K·h | 1087.0 min / 2.560631 K·h |
| Project 20–26°C, occupied air | 14.5 min / 0.111461 K·h | 14.5 min / 0.113749 K·h |

| Hold plus two-hour recovery | Native combined kWh | WARM45 combined kWh | Savings kWh | Savings % |
| --- | ---: | ---: | ---: | ---: |
| Day 1 | 1.869215 | 1.827522 | 0.041693 | 2.2305% |
| Day 2 | 2.344148 | 2.300179 | 0.043968 | 1.8757% |
| Day 3 | 1.828610 | 1.789125 | 0.039485 | 2.1593% |

[Paired energy, comfort, and recovery](runtime_state/batches/ESV01_G174_WARM45/PAIRED_ENERGY_COMFORT.json)

## Paired temperature and frozen acceptance

Temperature differences below are **WARM45 minus native** on the same 30-second clock. Window averages use native-grid trapezoids. The last row gives the remaining difference at the end of the scored simulation.

| Window | Mean Δ°C | Min to max Δ°C | End Δ°C |
| --- | --- | --- | --- |
| Day 1 hold | +0.478717 | +0.000000 to +0.540064 | +0.501514 |
| Day 1 two-hour recovery | +0.008196 | -0.027099 to +0.501514 | -0.000108 |
| Day 2 hold | +0.479233 | -0.000017 to +0.528961 | +0.501481 |
| Day 2 two-hour recovery | +0.008000 | -0.020020 to +0.501481 | -0.000122 |
| Day 3 hold | +0.478310 | -0.000026 to +0.538426 | +0.501643 |
| Day 3 two-hour recovery | +0.008333 | -0.026080 to +0.501643 | -0.000129 |
| Full 72 h | +0.021443 | -0.027099 to +0.540064 | +0.014373 |

Release recovery used 0.053921 kWh more than native and offset 30.11% of the 0.179067 kWh saved during the holds. Outside the scheduled hold and recovery windows, WARM45 used 0.046678 kWh more than native. Full 72-hour savings were **0.078468 kWh (0.4027%)**. The official discomfort KPI **deteriorated** by **1.132695 K·h (80.63%)**. The 20–26°C project band is evaluated separately.

| Frozen criterion | Result | Evidence |
| --- | --- | --- |
| Full qualified delivery | PASS | 27/27 verified five-minute intervals |
| At least 0.0225 kWh net savings across holds and recovery | PASS | +0.125146 kWh savings |
| At least 0.0225 kWh net savings across 72 h | PASS | +0.078468 kWh savings |
| Zero 20–26°C excursions in comparison windows | PASS | Read from the frozen occupied-air validation |
| No added 20–26°C comfort burden over 72 h | FAIL | Minutes and degree-hours compared to native |

**NO-GO for further action-conditioned ML dataset expansion.** Both arms recorded 14.5 occupied violation minutes under the project band. The warmer arm increased the severity of those excursions by **0.002288 K·h**, which failed the full-period comfort criterion. The excess came from four short intervals outside the scheduled hold and recovery windows. Occupancy here follows the archived as-issued schedule.

| Scored day | Simulation clock | Additional project-band K·h |
| --- | --- | ---: |
| 1 | 18:05–18:10 | 0.000602 |
| 2 | 08:00–08:01:30 | 0.000149 |
| 2 | 18:04:30–18:10 | 0.000869 |
| 3 | 18:06–18:10 | 0.000668 |

The append-only ledger has one consumed slot. Read-only postflight independently verified the authorization binding, the original implementation and campaign digests, the paired result artifact, and the corrected final package. [Append-only ledger](../../references/HISTORICAL_LOCATORS.md#evidence-69c1ca3e98a6) · [Finalized evidence](../../references/HISTORICAL_LOCATORS.md#evidence-009b8b4fa5d8) · [Authorization record](../../references/HISTORICAL_LOCATORS.md#evidence-197f5b2b4d34)
