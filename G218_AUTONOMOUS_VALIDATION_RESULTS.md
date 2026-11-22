# G218 autonomous validation results

**Execution and technical validation: PASS. Frozen acceptance criteria: FAIL.** The autonomous arm saved **0.074920 kWh (0.5039%)** of cooling-plus-fan electricity over 72 hours. Whole-period project discomfort increased, so the result demonstrates an energy–comfort trade-off.

The explicit one-run user authorization replaced the advisor gate. The campaign definition and acceptance criteria retained the original SHA-256. Both arms used BOPTEST 0.9.0 BESTEST Air, seven days of native warmup, identical initialization and as-issued forcing, and 864 five-minute advances with 30-second native samples. The collector verified equal warmup and pre-action traces, matched all 864 forecast origins, and confirmed cleanup of both instances. The mandatory 24 offline tests passed. Both slots are consumed. [Execution authorization](SDP_BOPTEST_Pilot/g218_execution_authorization.json) · [Sealed pair result](SDP_BOPTEST_Pilot/autonomous_hvac_stage1/g218_runtime_state/batches/G218_STAGE1_NATIVE_AUTONOMOUS/PAIRED_VALIDATION.json)

## Energy and comfort

| 72-hour measure | Native | Autonomous | Autonomous − native |
| --- | ---: | ---: | ---: |
| Cooling electricity, kWh | 14.308948 | 14.241291 | −0.067657 |
| Fan electricity, kWh | 0.557802 | 0.550539 | −0.007263 |
| Cooling plus fan, kWh | 14.866750 | 14.791830 | −0.074920 |
| Official BOPTEST discomfort, K·h | 1.104555 | 2.240787 | +1.136232 |
| Project 20–26°C discomfort, K·h | 0.052414 | 0.053100 | +0.000686 |
| Occupied minutes outside 20–26°C | 5.0 | 5.0 | 0.0 |
| Maximum occupied temperature, °C | 27.049386 | 27.058743 | +0.009357 |

The holds saved **0.167667 kWh**. Recovery used **0.050383 kWh** more than native, leaving **0.117284 kWh** saved across holds and recovery. The rest of the comparison used an extra **0.042365 kWh**. Benchmark-schedule discomfort replay during the holds was **0.031217 / 1.105083 K·h** (native / autonomous) and during recovery was **0.039333 / 0.098333 K·h**. Project discomfort was **0 K·h** for both arms in those windows. Both arms exceeded 26°C on the same five occupied minutes around 18:05 on day 1, outside the hold and scored recovery. The autonomous arm was slightly warmer during those excursions.

## Verified decisions and acceptance

The controller started a 45-minute hold at **11:00 on each of the three benchmark days**. At entry the zone was **24.011–24.024°C**, both recent endpoints had sustained cooling and positive fan power, the current cooling demand was **271–647 W**, and the occupied zone temperature was nearly steady. The receipt and history records verified **27 intervals at 24.5°C** and three scheduled releases to the native occupied 24°C setpoint at 11:45. The remaining **837 intervals** stayed native, including those outside the qualified window and in the 120-minute recovery lockout. There were **zero safety vetoes or emergency fallbacks**. Paired recovery markers were **20, 15, and 15 minutes** after release.

| Frozen requirement | Result |
| --- | --- |
| Complete verified pair and at least one delivered warmer interval | **PASS** · 864 advances per arm, three holds |
| At least 0.0225 kWh net savings over 72 hours | **PASS** · 0.074920 kWh |
| At least 0.0225 kWh net savings across holds and recovery | **PASS** · 0.117284 kWh |
| Occupied hold at or below 25.5°C | **PASS** · peak 24.567°C |
| No occupied project excursions in holds and recovery | **PASS** · zero minutes |
| Recovery marker within 120 minutes | **PASS** · all three markers verified |
| No added full-period project discomfort or occupied violation minutes | **FAIL** · +0.000686 K·h, unchanged minutes |

G218 is a development scenario. It establishes a measured energy benefit for the tested policy and fails the prespecified comfort requirement. The fixed-warmer comparison remains separate, and the original G174 decision stands. The next technical step is to examine the late-day occupied excursions and test any revised intervention schedule against prospectively fixed comfort criteria in a fresh authorized campaign. [Measured dashboard replay](EXCLUDED_FILES_INDEX.md)

The measured replay checks the finalized artifact manifest and technical result before opening the pair. Eight dashboard and policy regression tests passed. Browser checks verified playback, setpoint readback and final metrics for both G218 and G174.
