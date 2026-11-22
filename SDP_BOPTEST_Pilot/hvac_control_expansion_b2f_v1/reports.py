"""Publish the B2-F review from verified recorded evidence and freeze new outputs."""
import csv,json
from . import HOME,PILOT,BATCH,VERSION
from .packaging import read,sha,write_new,require,verify_package

def md(name,text):
    with (HOME/name).open('x',encoding='utf-8') as f:f.write(text)

def publish():
    qa=read(HOME/'FINAL_QUALIFICATION.json');v=read(HOME/'PILOT_VERIFICATION.json');r=read(HOME/'COMFORT_REVIEW.json')
    require(qa['status']==v['status']=='PASS','Qualification/verification incomplete')
    package=verify_package(BATCH,HOME/'corrected_pilot_package')
    md('B2F_FINALIZATION_CORRECTION_REPORT.md',f'''# B2-F finalization correction — 1.0.0

The new offline packaging workflow passes its end-to-end tests and finalized an exhaustive, separately located package for the recorded pilot. No original pilot file was edited. No simulator call or model fit was performed.

## Root cause and exact correction

The executed B1 `live.py` called `stage4e_d0.runner.files_manifest(batch)`. That helper excludes every file named `ARTIFACT_MANIFEST.json`, including the two nested run manifests. The append-only registry correctly expected those files and raised `Batch file set changed`. The original per-run seals already included both nested manifests. Original finalization remains **FAILED**; its code, failed record, manifest, seals and ledger remain preserved.

The separately versioned `packaging.py` includes all registered source artifacts without any basename-wide exclusion. It writes the new outer manifest outside the historical batch, so there is no source-tree self-exclusion at all. A declared scope plan anchors batch-level files and original ledger-bound per-run seals. Required raw files, nested manifests and receipt chains are verified before publication. An exclusive external output directory, pending file, readback verification and explicit completion marker prevent an interrupted output from being accepted or overwritten. Read-only verification is repeatable.

Corrected package: `corrected_pilot_package/`. Scope plan: `PACKAGING_SCOPE_PLAN.json`. New outer manifest: `corrected_pilot_package/BATCH_ARTIFACT_MANIFEST.json`, covering {package['source_files']} historical source files. Manifest SHA-256: `{package['manifest_sha256']}`. The historical imperfect outer manifest is itself included as preserved evidence, not silently replaced.

## Scope and other findings

Independent read-only reconstruction reproduced exactly the two missing outer-manifest entries. All other registered hashes and artifact scopes matched. No broader observed path, evidence-discovery, hash, receipt-chain, raw-recording or finalization-data defect was found in the saved pilot. The new validator additionally rejects noncanonical/traversing paths, case-colliding and duplicate registrations, missing required files, unexpected files, malformed hashes and broken receipt chains. These checks address invalid-input handling; they are not claims of additional historical corruption.

Only packaging and offline review code was added. Controller, collector, transport, safety, event, ML and frozen experimental factors were not refactored. Integrating this finalizer into a future separately authorized continuation launcher requires binding its new source hash; the original pilot-only launcher remains unchanged and cannot authorize C45.

See `B2F_OFFLINE_TEST_RESULTS.md`, `B2F_PILOT_INTEGRITY_VERIFICATION.md`, `B2F_CONTINUATION_READINESS.md`, and `REPRODUCTION.md`.
''')
    md('B2F_OFFLINE_TEST_RESULTS.md',f'''# B2-F offline qualification

**PASS: {qa['tests']} tests, {qa['failures']} failures, {qa['errors']} errors; process exit 0.** Network and descendant-process dispatch were denied throughout. No BOPTEST or training execution occurred.

The suite comprises 13 new packaging tests, four numerical comfort/review tests, and six unchanged relevant regressions (three original packaging tests plus B1 recovery-marker, native-energy/duplicate-time and sampled-comfort tests). See `FINAL_QUALIFICATION.txt` for individual outcomes.

| Required scenario | Test | Result |
|---|---|---|
| Two completed fabricated runs, seals, receipt chains and nested manifests through final verification | 01 | PASS |
| Missing nested manifest | 02 | REJECTED |
| Missing required raw artifact | 03 | REJECTED |
| Unexpected artifact | 04 | REJECTED |
| Tampered artifact | 05 | REJECTED |
| Incorrect relative path | 06 | REJECTED |
| Incorrect hash | 07 | REJECTED |
| Duplicate registration / duplicate JSON key | 08 | REJECTED |
| Interrupted finalization, missing completion, no overwrite | 09 | REJECTED |
| Repeated unchanged read-only verification | 10 | PASS, byte-identical outputs |

Additional tests reject altered receipt chains even after fixture file hashes are updated, unexpected package files, and output under the evidence root. Numerical fixtures check episode splitting, unchanged comfort bounds, quantile calculation and phase boundaries. All fabricated run artifacts live only in temporary fixture directories with explicit FABRICATED labels; none is included in real raw evidence or observation counts.

The initial focused 16-test run passed. The expanded 23-test run also passed; a first attempt to record the expanded result encountered the intentionally exclusive existing test-log filename. The runner now supports read-only test execution by default and explicit fresh record names; the final recorded qualification exited zero. No existing test was weakened.

The real read-only pilot verification and corrected external packaging also passed. Those are saved-evidence checks, not new simulations and not retrospective success of the original failed finalization.
''')
    text='''# B2-F pilot integrity verification

| Status being assessed | Result |
|---|---|
| Original executed batch finalization | FAILED; original failure preserved |
| Original NREF/C15 raw-run validity | PASSED; independently replayed offline |
| Supplemental exhaustive integrity audit | PASSED; independently reproduced |
| Corrected fabricated end-to-end finalization | PASSED |
| New corrected external package of the recorded historical batch | PASSED |

'''
    text+=f"All {v['historical_delivery']['files']} files in the historical delivery retain their recorded hashes. Its original delivery manifest, executed-source snapshot, ledger and supplemental manifest are unchanged. Original source/dependency manifest SHA-256: `{v['executed_source_manifest_sha256']}`.\n\n"
    text+='| Run | Advances | Endpoints | Native samples | Warmup samples | Resolved events | Receipt events |\n|---|---:|---:|---:|---:|---:|---:|\n'
    for x in v['runs']:text+=f"| {x['run_id']} | {x['advances']} | {x['endpoints']} | {x['native_samples']} | {x['warmup_samples']} | {x['resolved_events']} | {x['receipt_chain']['events']} |\n"
    text+='''
Saved runtime images match the pinned reference, and the saved worker executable/source/dependency identity matches the original recorded worker reference. Both deployed FMU hashes remain `158008fa3b635280a67dfed8bab5804d1f9a96d218b467dfebab77e5cbf8b86a`. This is verification of recorded runtime identity, not a query of the current Docker engine.

Both runs retain custom initialization at 15033600 s, seven native warmup days (604800 s), scored end 15292800 s, deterministic null uncertainties/seed, and their original G174 development group/fold. Warmup flag and regular-sample checks passed. All 864 origin/endpoint clocks, observation/forecast receipt orders, safety decisions, commands, active readbacks, releases, 30-second histories and six event resolutions per run were replayed using pinned pure validators. No pending event or extra advance remained. Raw API responses match materialized endpoints, forecasts, whole history, warmup and official KPIs. Energy reconciliation was reproduced against the saved official KPIs using the original tolerances and integration formulas. Both recorded cleanup acknowledgements include instance-removal proof.

Fresh NREF reproducibility was rechecked against the archived G174 native recording over all 865 endpoints and 864 forecast origins. NREF/C15 pretreatment matching was rechecked through the first 11:00 origin. The comparison tolerance remains 1e-7; legitimate subsequent carryover is not rejected. All nine active intervals were delivered at 296.90 K with no safety veto, followed by native release.

`PILOT_VERIFICATION.json` contains machine-readable verification details. `PACKAGING_SCOPE_PLAN.json` anchors nine batch-level files plus 5,250 sealed run files. `corrected_pilot_package/` contains the new successful offline finalization only. The original 5,259-file batch, its imperfect outer manifest, per-run seals and append-only ledger remain intact. Four remaining B1 slots remain unused. No protected/validation outcomes were opened for analysis.
'''
    md('B2F_PILOT_INTEGRITY_VERIFICATION.md',text)
    a,b=r['totals'];q=r['additional_excess_distribution_k']
    text=f'''# B2-F comfort and recovery review

The pilot remains valid and informative. The reviewed C15 evidence shows no new sampled violating timestamps and only small additional excess within pre-existing violations. It does not certify continuous comfort or the unexecuted C45 policy.

## Frozen definitions and reproduced results

The primary convention is the existing five-minute origin temperature against its unchanged issued LowerSetp/UpperSetp, weighted by 300 s per right-open interval. A violation uses strictly positive excess; the original 1e-7 K numerical comparison precision determines paired worsening/improvement. Native-history trapezoids at 30 s provide energy, never endpoint watts. Absolute Celsius differences equal Kelvin differences.

| Published-bound measure | NREF | C15 |
|---|---:|---:|
| Discomfort K·h | {a['degree_hours']:.12f} | {b['degree_hours']:.12f} |
| Violating minutes | {a['minutes']} | {b['minutes']} |
| Episodes | {a['episodes']} | {b['episodes']} |
| Above-upper-bound K·h | {a['above_degree_hours']:.12f} | {b['above_degree_hours']:.12f} |
| Below-lower-bound K·h | 0 | 0 |
| Peak absolute violation K | {a['peak_k']:.9f} | {b['peak_k']:.9f} |

All totals reproduce the original reports. All recorded violations are occupied according to issued occupancy. Source-nominal 08:00–18:00 schedule sensitivity gives 0.678242066 / 0.667153004 K·h, 1090 / 1030 minutes and 6 / 9 episodes. The publication-timing distinction changes totals but not the qualitative conclusion. These sampled calculations do not prove continuous compliance.

## Why episodes increased while discomfort decreased

There were **zero new sampled violations**: every C15 violating timestamp was already violating under NREF. Twelve native-violating samples became compliant, removing 60 minutes. Three native episodes (one on each day, original episode IDs 2, 5 and 8) were split into two C15 episodes by a compliant gap following the cooling intervention. Hence 9 became 12 even though the set of violating samples shrank. `B2F_COMFORT_EPISODES.csv` records every episode and its overlap IDs. An increased episode count alone would mischaracterize this result.

| Paired classification at unchanged 1e-7 K precision | Samples | Minutes |
|---|---:|---:|
| New violation where NREF compliant | 0 | 0 |
| Worsened existing violation | 164 | 820 |
| Improved violation (including 12 resolved samples) | 21 | 105 |
| Existing violation unchanged within precision | 36 | 180 |
| Both compliant | 643 | 3215 |

Of the improved samples, 12 resolved completely (60 minutes), and nine remained violating with reduced excess (45 minutes). The full positive additional excess is {r['additional_degree_hours']:.12f} K·h; reductions total {r['improved_degree_hours']:.12f} K·h, giving the net decrease. Eight paired worsening streaks are not eight new comfort episodes.

## Meaning of the 820 minutes

These are 164 five-minute comparisons where existing excess increased by more than 1e-7 K. They are not 820 newly violating minutes. Additional excess has median {q['p50']:.9g} K, p90 {q['p90']:.9g} K, p95 {q['p95']:.9g} K, p99 {q['p99']:.9g} K and maximum {q['max']:.9g} K.

| Additional excess bin | Minutes |
|---|---:|
| >1e-6 to 1e-5 K | 290 |
| >1e-5 to 1e-4 K | 390 |
| >1e-4 to 0.001 K | 110 |
| >0.001 to 0.01 K | 15 |
| >0.01 to 0.025 K | 15 |
| ≥0.025 / ≥0.05 / ≥0.1 K reporting sensitivities | 0 / 0 / 0 |

Thus 790 of 820 minutes (96.34%) have additional excess below 0.001 K. Histogram bins and quantiles describe the distribution; they do not redefine comfort acceptance. No new material-comfort threshold was fitted to these outcomes. The smallest predeclared temperature reporting sensitivity is 0.025 K; additional excess never reached it, but that reporting marker is not a certified comfort limit.

The absolute C15 excess during worsened periods has median 0.0124172 K and p95 0.0215313 K; the maximum is 0.634088 K during a pre-existing excursion. It would therefore be inaccurate to call every absolute violation negligible, even though the *additional* effect is small. The original larger morning excursions remain in the totals.

'''
    text+='| Clock phase | Worsened minutes | Additional K·h | Peak additional K |\n|---|---:|---:|---:|\n'
    for name,x in r['byphase'].items():text+=f"| {name} | {x['minutes']} | {x['additional_degree_hours']:.9g} | {x['peak_additional_k']:.9g} |\n"
    text+='\nAbout 97.5% of additional degree-hours occur during the two-hour recovery windows, although tiny persistent differences account for many minutes elsewhere. The ten minutes labeled hold consist of the day-two/day-three 11:00 origin states, before the new command can affect the next endpoint; they are carryover, not evidence that the fresh hold had already warmed the room.\n\n## Per-day intervention and recovery\n\n'
    text+='Temperature at 11:00 is the last native endpoint available immediately before issuing the override. The CSV also includes the 10:55 endpoint. Hold endpoint extrema include [11:00,11:15]; recovery endpoint extrema include [11:15,13:15]. Energy uses disjoint intervals [11:00,11:15] and [11:15,13:15]. Including the release endpoint in recovery reports the remaining cool state at release; it is not a newly caused recovery undershoot.\n\n'
    text+='| Day | NREF/C15 temperature before °C | NREF/C15 at release °C | Peak absolute hold ΔT K | Recovery signed ΔT range K | Return marker min |\n|---|---|---|---:|---|---:|\n'
    for d in r['recovery']:
        text+=f"| {d['day']} | {d['native_temperature_at_activation_c']:.6f} / {d['c15_temperature_at_activation_c']:.6f} | {d['native_temperature_at_release_c']:.6f} / {d['c15_temperature_at_release_c']:.6f} | {d['hold_max_abs_delta_temperature_k']:.6f} | {d['recovery_min_delta_temperature_k']:.6f} to {d['recovery_max_delta_temperature_k']:.6f} | {d['return_near_native_minutes']:.0f} |\n"
    text+='\nThe frozen joint return marker is the **first** of three consecutive five-minute endpoint/preceding-interval pairs within 0.05 K and 0.01 kW; it is confirmed ten minutes later (25, 20 and 25 minutes after release). All episodes have 24 native recovery intervals. It is not a promise that differences become exactly zero.\n\n'
    text+='| Day / window | Cooling NREF/C15 kWh | Fan NREF/C15 kWh | Combined ΔE kWh | Comfort NREF/C15 K·h |\n|---|---|---|---:|---|\n'
    for d in r['recovery']:
        for w in ('hold','recovery'):
            text+=f"| {d['day']} / {w} | {d['native_'+w+'_cooling_kwh']:.9f} / {d['c15_'+w+'_cooling_kwh']:.9f} | {d['native_'+w+'_fan_kwh']:.9f} / {d['c15_'+w+'_fan_kwh']:.9f} | {d['delta_'+w+'_electric_kwh']:+.9f} | {d['native_'+w+'_discomfort_k_hours']:.9f} / {d['c15_'+w+'_discomfort_k_hours']:.9f} |\n"
    text+='''
All nine requested cooling-override intervals were delivered. Both policies also had cooling and fan consumption above the original 10 W activity threshold in all three hold intervals per day and all 24 recovery intervals per day. Therefore, command activation is not confused with equipment operation: the equipment remained active after the external override was released. Complete activity counts, matched energy and comfort windows are in `B2F_RECOVERY_BY_DAY.csv`.

## Rebound and persistence

The hold adds approximately 0.0120 / 0.0130 / 0.0121 kWh of combined electricity. During each following two hours, combined energy is lower than native by 0.004679 / 0.005177 / 0.005035 kWh. Every five-minute combined-power difference within these recovery intervals is negative; even the largest signed differences are −0.631 / −0.861 / −0.822 W. Cooling and fan recovery energies separately decrease. There is no observed above-native five-minute electrical-demand rebound in the two-hour recovery windows.

Temperature does show a small warm overshoot relative to the native trajectory: maxima +0.014946 / +0.010420 / +0.014354 K, after the cooler release states. This is an observed post-release temperature compensation pattern, not evidence of a large demand rebound or a solver defect. Later 13:15–24:00 maximum absolute temperature differences are only 0.001837 / 0.002485 / 0.002574 K; later combined-energy differences are negative on all three days. Day-two/day-three pre-11:00 maximum differences are 0.001760 / 0.002314 K, so small carryover persists and must not be forced to zero or treated as a pretreatment failure. Day one is identical before intervention. The signs and small scale are consistent across the three dependent days.

Complete 72-hour electricity still **increases** by 0.0134096 kWh. Lower recovery consumption does not turn this into an energy-saving result. No causal claim is made that every subsequent microscopic difference constitutes rebound.

## Comfort interpretation and remaining uncertainty

No substantial additional sampled comfort problem is demonstrated here: there are no new violating timestamps, no below-bound violations, and the additional above-bound excess stays below 0.015 K. Most worsening is extremely small, with severity concentrated in recovery. Aggregate improvement and fragmented episodes support this conclusion together; neither statistic alone certifies comfort safety. Continuous behavior between samples, occupant comfort and other weather groups remain unestablished.

The unchanged safety decision logic was replayed against every recorded origin and produced exactly the saved commands and reasons. All nine requested intervals were admissible, with no veto. This shows correct operation on the observed admissible states, not live exercise of adverse-state veto branches. Relevant prior fabricated safety tests remain unchanged. C45 may have a larger cooling dose, stronger undershoot or different recovery; C15 cannot qualify it physically. Existing latched vetoes, canonical native fallback and reporting rules remain suitable for a bounded first-of-policy qualification, subject to separate approval. This review does not introduce safeguards, relax thresholds or alter the design.
'''
    md('B2F_COMFORT_RECOVERY_REVIEW.md',text)
    md('B2F_CONTINUATION_READINESS.md','''# B2-F continuation readiness

**Recommendation: GO FOR SEPARATE APPROVAL. This is not authorization.**

| Area | Assessment |
|---|---|
| Software | New corrected offline finalizer and its end-to-end qualification pass; external historical packaging also passes. Original executed finalization remains failed and preserved. The new implementation is frozen by B2F_IMPLEMENTATION_MANIFEST.json. |
| Control/data | C15 delivered three exact 15-minute holds; temperature and demand exceeded the predeclared response markers. Raw histories, logs, energy, source identities, comparisons and cleanup independently pass. No unresolved data-integrity defect remains in the saved pilot. |
| Comfort | No new sampled violating timestamps; episode increase is fragmentation. Additional excess ≤0.014946 K and mostly <0.001 K. No substantial additional sampled problem was identified, but neither continuous comfort nor C45 behavior is certified. |
| Experimental | The fixed 15-versus-45-minute contrast remains reasonable to investigate. The pilot supports considering C45; it does not establish the duration contrast or generalization across G146. |

The appropriate next live run to consider is **B1V01_G174_C45**, as the first-of-policy qualification under the unchanged 296.90 K target, 11:00–11:45 schedule, native warmup and original G174 initialization. Do not skip directly to G146 or repeat NREF/C15. The longer hold may change dose, cold-margin veto incidence, undershoot and recovery; those outcomes remain unknown until actually recorded.

Before any execution, a separate continuation decision must explicitly approve that exact slot and budget. A separately frozen continuation launcher must bind the corrected finalizer to the unchanged qualified collection components, exact campaign/run/source/runtime identities and append-only slot inventory. The original pilot-only launcher and authorization must not be repurposed, bypassed or monkeypatched. Any future required runtime identity checks belong to that separately authorized execution task; none was contacted here.

Keep all existing safety vetoes, native fallback, published comfort bounds, raw readback/event/history/energy gates and immutable evidence accounting. Treat C45 as an unqualified policy until its own delivery/recovery/comfort evidence is reviewed. Do not demand identical day-two/day-three starting thermal states or add makeup pulses. No additional safeguard or factor change is supported as necessary by this pilot; if a future conflict arises, stop for review.

STOP: no C45 or G146 simulation is authorized or initiated by B2-F. No ML model was run or trained. Original partitions, folds, datasets, protected reservations and experimental factors remain unchanged.
''')
    md('REPRODUCTION.md',f'''# Offline reproduction and evidence paths

Working directory: `{HOME.parent}`. Use the existing `.venv/Scripts/python.exe` with `-B` to avoid writing bytecode into historical source directories.

```
.venv/Scripts/python.exe -B -m hvac_control_expansion_b2f_v1 test
.venv/Scripts/python.exe -B -m hvac_control_expansion_b2f_v1 verify
```

Both commands block network and descendant-process dispatch; neither performs simulator or model execution. The default test command does not overwrite qualification records. `tests --record-stem <fresh-name>` records a fresh offline-test log; existing names cannot be overwritten. The optional `package --output <fresh-directory-inside-B2F>` action uses the frozen scope plan to create a new external offline package; it cannot write in the original pilot tree and cannot overwrite an interrupted or completed package.

Original preserved batch: `{BATCH}`.
Original ledger: `{PILOT/'runtime_state/attempts.sqlite3'}` (opened mode=ro only).
Original failed finalization: `{PILOT/'FINALIZATION_EXCEPTION.json'}`.
Original supplemental manifest: `{PILOT/'SUPPLEMENTAL_BATCH_MANIFEST.json'}`.
New corrected package: `{HOME/'corrected_pilot_package'}`.

Machine-readable results: `PILOT_VERIFICATION.json`, `COMFORT_REVIEW.json`, `FINAL_QUALIFICATION.json`, `PACKAGING_SCOPE_PLAN.json`. `B2F_COMFORT_PAIRED_INTERVALS.csv` is an additional derived analysis table, not newly collected observations or an ML feature matrix. Source hashes and frozen output hashes are in `SOURCE_HASHES.csv` and `B2F_IMPLEMENTATION_MANIFEST.json`. No evidence-discovery step is used to silently register unexpected files.
''')
    # Freeze new outputs and record primary historical input bindings, without any historical write.
    sources=list(HOME.glob('*.py'))+[PILOT/'DELIVERY_MANIFEST.json',PILOT/'IMPLEMENTATION_MANIFEST.json',
        PILOT/'SUPPLEMENTAL_BATCH_MANIFEST.json',PILOT/'runtime_state/attempts.sqlite3',PILOT/'FINALIZATION_EXCEPTION.json',
        HOME.parent.parent/'hvac_expansion_design_B1_2026-11-18/EVALUATION_PLAN.md']
    with (HOME/'SOURCE_HASHES.csv').open('x',newline='',encoding='utf-8') as f:
        w=csv.DictWriter(f,fieldnames=['absolute_path','sha256','bytes']);w.writeheader()
        for p in sources:w.writerow(dict(absolute_path=str(p.resolve()),sha256=sha(p),bytes=p.stat().st_size))
    files={p.relative_to(HOME).as_posix():sha(p) for p in HOME.rglob('*') if p.is_file() and '__pycache__' not in p.parts}
    write_new(HOME/'B2F_IMPLEMENTATION_MANIFEST.json',dict(version=VERSION,files=files,
        historical_delivery_sha256=sha(PILOT/'DELIVERY_MANIFEST.json'),corrected_offline_status='PASS',
        original_finalization_status='FAILED_PRESERVED',continuation_recommendation='GO FOR SEPARATE APPROVAL',
        continuation_authorized=False,simulator_calls=0,model_fits=0))
    print(json.dumps(dict(status='B2F_COMPLETE',tests=qa['tests'],corrected_files=package['source_files'],new_frozen_files=len(files),
        manifest_sha256=sha(HOME/'B2F_IMPLEMENTATION_MANIFEST.json'),recommendation='GO FOR SEPARATE APPROVAL',simulator_calls=0),indent=2))

if __name__=='__main__':
    from .tests import offline_guard
    with offline_guard():publish()
