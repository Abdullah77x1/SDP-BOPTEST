# EnergyPlus v26.2.0 baseline runtime verification

13 November 2026, Asia/Dubai. **VERIFIED: installation, original-timestep baseline, five-minute baseline, required observations and Python discovery. CONDITIONAL readiness for a separately authorized controlled HVAC pilot.** Exactly two baseline simulations were executed; neither is an A/B/A2 intervention experiment.

## Scope, authorization and evidence classes

The November experiment covered the packaged single-zone baseline, an otherwise equivalent five-minute baseline, and read-only Python interface discovery.

VERIFIED means observed in these executions; FAILED identifies an assumption/check that did not hold; INCONCLUSIVE means evidence is insufficient for a scientific conclusion; NOT TESTED means deliberately unperformed. All data are simulator outputs, not real-building measurements.

## Installation and software identity

- Official release/build: **EnergyPlus 26.2.0-4bd7a1f26f**, source commit `4bd7a1f26fb749a83257855aba6760e26c8a3c8f`.
- Distribution: standard Windows x86_64 ZIP, downloaded from the [official release](https://github.com/NatLabRockies/EnergyPlus/releases/tag/v26.2.0). Published [asset SHA-256](https://github.com/NatLabRockies/EnergyPlus/releases/expanded_assets/v26.2.0) matched the complete downloaded archive.
- Portable installation: `EnergyPlus_V26_Runtime_2026-11-13/installation\EnergyPlus-26.2.0-4bd7a1f26f-Windows-x86_64`. No global PATH change or system-wide installer was used; bundled native dependencies were retained.
- Host: `Windows-11-10.0.26300-SP0`, x64. Existing external CPython **3.12.10**, MSC v.1943 AMD64, 64-bit: `python.exe`. No new Python packages were installed.
- Matching bundled `pyenergyplus`, native `energyplusapi.dll` and API version **0.2** loaded. `verify_api_version_match` passed separately in both states. Packaged `python312.dll` was retained; external runtime callbacks were used, not a PythonPlugin.
- Windows TLS and repository-venv launching failed within the sandbox. The already authorized download and external Python execution succeeded through the host execution tool. No certificate verification was disabled. This was not a simulator failure or version substitution.

## Reference provenance and exact changes

The model and weather came from the verified distribution's ExampleFiles/WeatherData directories. Packaged files use Windows line endings. After CRLF→LF normalization, their Git blob identities exactly match the frozen source: IDF `881886edec78ebdb253b0be356464635dbbe523f`; EPW `c48d6ffdc7f64ebd7a1293515ffd6154c6a6dd68`. Raw-file SHA-256 values below preserve their actual bytes. Pristine copies are byte-identical to the untouched installed originals. See `EnergyPlus_V26_Runtime_2026-11-13/source_provenance.json`.

The 15-minute copy changes only the RunPeriod to July 3–11 inclusive, begin/end year 2023, Monday start, and adds reporting. All original holiday/DST/weekend/rain/snow flags and special days remain intact. Added outputs: the 29 inventory variables at Timestep, ten system variables also at Detailed frequency, and `Output:SQLite,SimpleAndTabular`. Existing hourly/dictionary/sizing reports remain. The object-level preparation assertion preserves all original non-RunPeriod objects. Removing RunPeriod field comments in the copy is formatting only.

The five-minute copy differs from the staged 15-minute copy by **one line only**, `Timestep,4;` → `Timestep,12;`. HVAC/lighting/occupancy/envelope/curves/sizing inputs were not edited. Complete diffs are `EnergyPlus_V26_Runtime_2026-11-13/inputs\baseline_15min.diff` and `EnergyPlus_V26_Runtime_2026-11-13/inputs\baseline_5min.diff`. Autosized *results* differ with resolution; the comparison report quantifies this.

Both API runs used arguments `-d <separate run/engine directory> -w <installed Chicago EPW> <staged IDF>`. Exact absolute arguments, interpreter identity, start timestamp and software/input hashes are preserved in each `manifest.json`. Its legacy field named `start_utc` contains an explicit `+04:00` ISO timestamp; interpret that offset as written, not as UTC.

## Baseline outcomes

| Check | 15-minute baseline | 5-minute baseline | Finding |
|---|---|---|---|
| Engine return | 0 | 0 | VERIFIED: both successful |
| Warnings / severe / fatal | 2 / 0 / 0 | 2 / 0 / 0 | VERIFIED; warnings retained below |
| Completed native intervals | 864 | 2592 | VERIFIED: nine days, no missing/duplicate intervals |
| Seconds per native interval | 900 | 300 | VERIFIED from SQL and normalized API |
| API system records | 879 | 2609 | VERIFIED: shorter HVAC steps retained |
| Required signals | 29 | 29 | VERIFIED in each run |
| Cooling actuator handle | 15 | 15 | VERIFIED discovery only; independently resolved |
| External actuator writes | 0 | 0 | VERIFIED: no set/reset calls in observer |
| Simulation wall seconds | 1.2217 | 2.9573 | Observed API-run wall time, including observer callbacks |


Both SQL databases passed `PRAGMA integrity_check`. Every required signal has 864 or 2,592 finite official Timestep observations over 216 hours. The first completed intervals end July 3 00:15/00:05; the last ends July 12 00:00. No sizing/warm-up records enter the nine-day observation series. The July 10–11 diagnostic evaluation slice contains 192/576 native intervals.

## Warnings, numerical convergence and calendar

The same two warnings occur in both preserved `eplusout.err` files:

1. Ground-temperature values outside the suggested 15–25°C range. These are retained source inputs, not silently repaired. Physical suitability of this example's ground boundary is not certified by a successful run.
2. Single-speed DX standard ratings calculated outside AHRI curve bounds. Standard-rating results should not be presented as validated AHRI performance; no coil curves were altered.

There are zero severe errors, zero fatal errors, zero warm-up warnings/severe errors, successful branch/path integrity checks and no node connection errors. The source also reports three unused schedules. `sqlite.err` contains only its open-for-processing message, not an SQL failure.

Weather-environment warm-up took six days in each run. EIO marks maximum/minimum temperature and heating/cooling load convergence **Pass**. Average warm-up temperature differences were 0.03358435379°C (15 min) and 0.01138445461°C (5 min); average load differences 0.08055325282 W and 0.03180167307 W. These are native convergence diagnostics, not newly approved experimental tolerances.

SQL and Python `calendar_year()` verify synthetic **2023**; `year()` returns the July EPW source year **1986**. Monday July 3/10, Tuesday July 11, DST disabled and the explicit July 4 Holiday are verified. Python `holiday_index()` returns **1** on July 4; its wrapper subtracts seven from the internal day-type code. Do not use EPW year or internal code 8 as the Python calendar/holiday contract.

## Python observation and actuator verification

`EnergyPlus_V26_Runtime_2026-11-13/ENERGYPLUS_V26_SIGNAL_INVENTORY.csv` contains 60 rows: 29 measured variables plus one actuator discovery per run. It records actual runtime names, keys, API handles/units, SQL units/timestep/store type, count/range, timing and role. A legitimate outdoor-temperature handle is **0**; only −1 denotes missing variable discovery. All handles were acquired independently in each fresh state.

Cooling actuator `Schedule:Compact` / `Schedule Value` / `CLG-SCHED` was discovered with unit metadata `[ ]`, semantic °C, handle 15 in both states. **Write, effective intervention response and release are NOT TESTED.** The native cooling schedule and effective thermostat match; during July 10 `[12:00,14:00)` cooling remains 24°C and heating 21°C in both baselines.

The table below includes preparation callbacks as well as weather callbacks; counts are not counts of completed observations. Actual weather streams contain 864/2,592 completed zone records, 879/2,609 completed system records and 888/2,618 post-predictor records. Extra predictor records occur during shortened/retried steps; never sum those records as delivered energy.

| Callback / stream | 15-minute observed count | 5-minute observed count |
|---|---|---|
| callback_begin_zone_timestep_before_init_heat_balance | 2790 | 8358 |
| callback_begin_system_timestep_before_predictor | 2790 | 8358 |
| callback_end_system_timestep_after_hvac_reporting | 2863 | 8438 |
| callback_end_zone_timestep_after_zone_reporting | 2790 | 8358 |
| callback_after_new_environment_warmup_complete | 3 | 3 |
| callback_begin_new_environment | 1 | 1 |
| callback_after_predictor_before_hvac_managers | 1464 | 4346 |


## Timing correction found at runtime

**FAILED assumption:** `current_time()` (or API minutes) always equals a completed native-zone boundary at the end-zone reporting callback. Nine records per run are offset after shortened HVAC steps: up to 450 seconds at 15 minutes and 150 seconds at five minutes. Example: the true July 5 06:10 five-minute boundary reports raw `current_time=6.1833333333` (06:11).

**VERIFIED replacement for these baselines:** native endpoint = calendar date + `hour()` hours + `zone_time_step_number() × zone_time_step()` hours. It matches every SQL interval, without omissions/duplicates. Subtract 900 or 300 seconds for interval start. Raw logs are unchanged; separate `api_zone_normalized.csv` files preserve the derived boundaries and original clock offsets. Use this native interval identity for the later control proposal, not a floating-point raw clock threshold. Actual intervention onset/release still requires its own verification.

**VERIFIED energy semantics:** each system-step API energy sum grouped by native interval matches official zone Sum output; rates are duration-weighted. Largest per-interval discrepancies are approximately 5.83×10⁻¹¹ J and 1.14×10⁻¹³ W. A single end-zone read of system power/energy need not equal the whole interval's value: observed DX power differences reach 157.36 W / 343.24 W at 15/5 minutes. Completed-zone temperature, weather, occupancy, gains, lights and daylight API values match their corresponding official reports. Use official interval totals or verified system aggregation for evaluation; do not relabel joules as instantaneous watts.

## Occupancy, lighting and exposure boundary

VERIFIED: scheduled count ranges 0–1.9 people and equals 2×OCC-SCHED; activity is 120 W/person; total people gain equals count×activity, ranging 0–228 W. Sensible plus latent equals total; convective plus radiant equals sensible to about 1.43×10⁻¹⁴ W. Sensible/latent split depends on the simulated conditions, so those components are internal truth rather than an independent measured schedule.

VERIFIED native-light observability: daylight ranges 0–130.2265/130.3093 lux; native multiplier ranges 0.770766/0.770620 to 1. Lamp power equals design power×LIGHT-SCHED×multiplier in every interval. This is native EnergyPlus dimming, not our optimizer. Daylight lux excludes electric-light contribution; total task-plane illumination/comfort and external lamp control remain NOT TESTED.

Indoor temperature, completed weather and daylight are DT-observable candidates. Exact occupancy/gains, schedule values, delivered sensible thermal energy and native multiplier remain simulator-internal diagnostics unless explicitly admitted later. Coil/fan/lighting electricity are evaluation streams under the current contract. All streams here are observer logs, not inputs to a trained controller.

## Hash manifest and preserved artifacts

| File relative to runtime root | SHA-256 |
|---|---|
| downloads\EnergyPlus-26.2.0-4bd7a1f26f-Windows-x86_64.zip | `15ab698803f459444ec3e97ee52ab9f99db93a583819c7821b17dfcd7b4461e7` |
| installation\EnergyPlus-26.2.0-4bd7a1f26f-Windows-x86_64\energyplus.exe | `71278a62c9c3871922b3f7ee28a3c7c9f658caa995a934fccb92e8f8965a3977` |
| installation\EnergyPlus-26.2.0-4bd7a1f26f-Windows-x86_64\energyplusapi.dll | `d018859a87c38276ff1cfef49487b32cfa1db0a4aa2d6ec3e7949d1bcd448d83` |
| installation\EnergyPlus-26.2.0-4bd7a1f26f-Windows-x86_64\python312.dll | `789a42ac160cef98f8925cb347473eeeb4e70f5513242e7faba5139ba06edf2d` |
| installation\EnergyPlus-26.2.0-4bd7a1f26f-Windows-x86_64\Energy+.idd | `c307d88afba83fba3603c04899b0ec063f7472879d80d5cfa75020202707d55f` |
| installation\EnergyPlus-26.2.0-4bd7a1f26f-Windows-x86_64\ExampleFiles\CmplxGlz_Daylighting_SouthVB45deg.idf | `9eb1a3646c17baad4cc84d8626542653a0c4f56edfdc87caf44776266273f2be` |
| installation\EnergyPlus-26.2.0-4bd7a1f26f-Windows-x86_64\WeatherData\USA_IL_Chicago-OHare.Intl.AP.725300_TMY3.epw | `c7d4efcf93ba316a1d874352e743df5cf137ba5c0e3459eb2dc4b5442d5b7f5c` |
| inputs\baseline_15min.idf | `61ed998a2392a9d4d26c0ec6dd102396515f4183dc8054d51894f2f6d7f39389` |
| inputs\baseline_5min.idf | `4e7d43d36149ffe72dc8f6897a84b5746e5c5aa9b0d5adb2aeebf483988ea265` |
| baseline_verify.py | `cf8ed75d5eafcadd01d2d62729b108c05bc3406940418cb770e2844c81261b20` |


Full interpreter/wrapper/dictionary/source/logger identities are in both manifests. `runtime_artifact_hashes.json` covers retained outputs and reports; it intentionally does not hash itself. Both run folders preserve SQL, ESO, ERR, END, EIO, RDD/MDD, audit, sizing CSVs (`epluszsz.csv`, `eplusssz.csv`), table output, API discovery/handles, raw callback/system/zone/predictor logs, normalized API observations and official zone exports. Console logs, model diffs and provenance JSON are retained. Raw outputs were not replaced by postprocessed summaries.

## Decision

**VERIFIED:** the frozen model runs at five-minute native zone resolution and exposes the required baseline signals through a compatible Python API. **INCONCLUSIVE:** which timestep is physically more accurate; only two resolutions of one synthetic scenario were tested. **NOT TESTED:** external control, A/A2 repeatability, safe operating envelope, intervention effect/release and lighting optimization.

Proceed only through a separate five-minute HVAC-pilot authorization using the readiness document. No external control or additional simulation was performed after these baseline checks.
