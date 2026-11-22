"""Publish B2-H reports from the verified real C45 evidence; no simulation calls."""
import csv,json,math
from . import HOME,ROOT,V2,PILOT,RID
from hvac_control_expansion_b2f_v1.packaging import read,sha,require,write_new

def md(name,text):
    with (HOME/name).open('x',encoding='utf-8') as f:f.write(text)

def table_csv(name):
    with (HOME/name).open(newline='',encoding='utf-8') as f:return list(csv.DictReader(f))

def publish():
    verification=read(HOME/'POSTRUN_VERIFICATION.json');require(verification['status']=='PASS','No successful physical report without verification')
    a=read(HOME/'B2H_THREE_ARM_ANALYSIS.json');detail=read(HOME/'COMFORT_DETAIL.json')
    temps=table_csv('B2H_THREE_ARM_TEMPERATURE.csv');energy=a['full_energy'];primary=a['primary_temperature']
    comforts=[c for c in a['comfort'] if c['reference']=='NREF'];c45comfort=next(c for c in comforts if c['policy']=='C45')
    directcomfort=next(c for c in a['comfort'] if c['reference']=='C15')
    checks=read(HOME/'PREEXECUTION_CHECKS.json');raw=verification['actual_run'];final=verification['corrected_finalization']
    approval=HOME/'EXPLICIT_LIVE_C45_APPROVAL.json'
    text=f'''# B2-H execution report — G174 C45

**SUCCESS: one real B1V01_G174_C45 attempt completed and correctly finalized.** All 27 requested cooling intervals were delivered, with no vetoes. No other simulation, retry, model execution or training-data release occurred.

## Qualified execution and prechecks

The exact frozen B2-G v2 CLI was used, with a new approval in the launcher's existing schema. Implementation SHA-256 remains `725408bd1fe98544a89b07d39b54da96f6854988f58a791f52d5fcba1db2f603`; run manifest SHA-256 remains `4842d660bc9de6161fd4a48d78c938dc58c5024a2bcf5e399756d9a3c8ec48f3`. Approval SHA-256: `{sha(approval)}`. The approval's `request_sha256` binds the existing v2 preparation provenance, while its new user-authorization text and `authorization_source_sha256` record this B2-H one-run permission. No schema was bypassed and no frozen code was edited.

All pre-execution checks passed: expected digests and dependency/configuration hashes, existing 42-case qualification, original pilot and B2-F/D2 preservation, consumed NREF/C15 and unused C45 ledger-chain state, G146 nonauthorization, exact C45 schedule/initialization/fold/budget, corrected-finalizer binding, actual local source FMU SHA-256 and current pinned runtime identity. Existing offline preparation was not rerun.

The current Docker images, localhost ports, worker executable/source/dependencies and BOPTEST 0.9.0 identity were checked without deploying a preflight simulation. Source FMU SHA-256 was `158008fa3b635280a67dfed8bab5804d1f9a96d218b467dfebab77e5cbf8b86a`; the qualified collector additionally verified the actual selected-instance FMU before initialization. The local source FMU check is not being substituted for that deployed-instance check. Both passed.

## Actual run and delivery

| Check | Recorded result |
|---|---|
| Deployment / initialization attempts | 1 / 1 |
| Initialization | Original custom G174, start 15033600 s |
| Native warmup | 604800 s, 20,161 recorded samples, all external flags zero |
| Scored start/end | 15033600–15292800 s |
| Scored advances / responses | 864 / 864 |
| Endpoints / native samples | 865 / 8,641 |
| Requested / delivered active intervals | 27 / 27 |
| Complete doses / vetoed intervals | 3 / 0 |
| Effective active readbacks | 296.90 K |
| Noncooling override activations | None |
| Event resolutions / unresolved | 6 / 0 |
| Raw classification | PASS_VALID_RAW |
| Cleanup | STOP_ACK_AND_REMOVAL_VERIFIED |
| Corrected finalization | {final['status']} |
| Outer source scope / per-run seal | {final['source_files']} / {verification['per_run_sealed_files']} files |
| Receipt-chain events | {verification['receipt_chain']['events']} |

'''
    text+='| Day | Activation s | Native release command s | Minutes delivered | Readbacks K | Native recovery intervals |\n|---|---:|---:|---:|---|---:|\n'
    for c in a['control']:
        if c['policy']=='C45':text+=f"| {c['day']} | {c['actual_activation_s']} | {c['actual_release_s']} | {c['actual_minutes']} | {c['readbacks_k']} | {c['native_recovery_intervals']} |\n"
    text+='''
Native releases were commanded at 11:45 each benchmark day and verified through endpoint/readback and native-history checks. Heating, fan and supply-temperature overrides remained off; the canonical four-zero-flag command was used outside holds. Actual equipment activity is separate: cooling was electrically active above the original 10 W threshold in all nine delivered intervals per day, and native equipment could remain active after override release.

The qualified independent replay passed all timestamp, finite-value/unit/catalog, forecast receipt/cutoff ordering, command/readback, safety decision, event, native support, energy, raw/materialized and cleanup checks. NREF/C45 matched whole endpoint vectors through the first 11:00 origin (133 endpoints); C15/C45 matched through the first 11:15 origin (136 endpoints), both at unchanged 1e-7 tolerance. All 864 forecast origins matched. Subsequent-day carryover was retained.

## Integrity, ledgers and preservation

The corrected B2-F finalizer included the nested ARTIFACT_MANIFEST.json. The outer manifest SHA-256 is `'''+final['manifest_sha256']+'''`. The append-only extension has exactly one C45 reservation and one completed terminal event, linked to the original parent ledger. Parent NREF/C15 records were not rewritten. Effective G174 state is three consumed completed slots; the three G146 slots remain UNUSED_NOT_AUTHORIZED.

All 28 original v2 delivery files including its delivery manifest retain their pre-execution hashes. New raw/runtime/ledger/finalization files were appended only at the launcher's planned fixed locations. V1 failure evidence, original NREF/C15, original failed-finalization history, B2-F evidence and D2 source/dataset/partition artifacts passed read-only preservation checks. The old failed finalization still remains failed; the new C45 finalization passed. There was no launch-code change, automatic retry, replacement run or extra scored advance.

## Artifact locations and reproduction

The frozen launcher has fixed output paths. It was not redirected or monkeypatched to move evidence. The B2-H directory contains approval, pre/post checks, indexed raw/ledger/finalizer references, analysis and reports. The actual complete raw recording remains at:

`'''+str(V2/'runtime_state/batches/B2G_G174_C45_ONLY'/RID)+'''`

The raw receipt/command/API journals, all observations/forecasts/native chunks, warmup, KPIs, energy audit, run manifest and run seal are indexed by RAW_C45_ARTIFACT_INDEX.json. Corrected package and its hashes are indexed by CORRECTED_FINALIZATION_REFERENCE.json. The parent/continuation ledger paths, hashes and effective inventory are in CONTINUATION_LEDGER_INDEX.json. No large evidence files were unnecessarily duplicated. User authorization is preserved in USER_AUTHORIZATION_SOURCE.json and EXPLICIT_LIVE_C45_APPROVAL.json.

The command actually executed once, from SDP_BOPTEST_Pilot, was:

```
.venv/Scripts/python.exe -B -m hvac_control_expansion_b2g_v2 execute --approval hvac_control_expansion_b2h_v1/EXPLICIT_LIVE_C45_APPROVAL.json
```

**Do not rerun it: C45 is consumed.** Read-only analysis/verification commands are:

```
.venv/Scripts/python.exe -B -m hvac_control_expansion_b2h_v1.analysis --verify
.venv/Scripts/python.exe -B -m hvac_control_expansion_b2h_v1.comfort_details --verify
.venv/Scripts/python.exe -B -m hvac_control_expansion_b2h_v1.verify
```

These block network/external-process dispatch and only read recorded files. Analysis uses native-history trapezoids, published sampled comfort and the frozen 0.05 K/0.01 kW/three-consecutive-pair return marker. Policy-relative recovery is distinct from equal-clock comparisons. Percentage energy deltas are `(policy − NREF)/NREF ×100`; zero-denominator percentages are blank/undefined. Tiny gas-rate artifacts are reported separately; their percentages have no meaningful heating-savings interpretation. Temperature means use recorded endpoints; comfort uses the original 864 right-open origin samples. No reporting threshold was fitted to C45 outcomes.

See the three-arm CSVs, B2H_OPERATING_RANGE_ASSESSMENT.md and B2H_G146_RECOMMENDATION.md for physical interpretation. STOP after this run and analysis: no G146 preparation/execution, pilot rerun, C45 retry, experiment change, ML execution or revised training dataset is authorized here.
'''
    md('B2H_EXECUTION_REPORT.md',text)
    text='''# B2-H operating-range assessment

**C45 adds useful temporal control and physical-response variation in G174 beyond C15.** It sustains a similar cooling amplitude longer, rather than creating a larger peak excursion or new numerical setpoint level. The effect remains modest in full-period averages and confined to one existing development weather group.

## Temperature: matched common windows

Each common 11:00–14:00 window has 37 five-minute endpoints, for 111 paired comparisons across three dependent days. Positive signed differences mean the alternative is warmer. Reporting sensitivities remain 0.025/0.05/0.1 K and 1/10/50 W; primary markers are at least 0.05 K or 0.01 kW.

| Reference → policy | Signed mean K | Mean absolute K | Maximum absolute K | Endpoints ≥0.05 K | Interval-power pairs ≥10 W | Absolute-temperature area K·h |
|---|---:|---:|---:|---:|---:|---:|
'''
    for p in primary:
        text+=f"| {p['reference']} → {p['alternative']} | {p['mean_signed_temperature_k']:+.9f} | {p['mean_abs_temperature_k']:.9f} | {p['max_abs_temperature_k']:.9f} | {p['endpoints_ge_0_05k']} | {p['intervals_ge_10w']} | {p['absolute_temperature_area_k_hours']:.9f} |\n"
    text+='\n| Day / contrast | Signed mean K | Mean absolute K | Max absolute K | Endpoints ≥0.05 K | Power pairs ≥10 W |\n|---|---:|---:|---:|---:|---:|\n'
    for day in range(1,4):
        for p in temps:
            if p['population']==f'day{day}_common_11to14' and p['alternative']!=p['reference']:
                text+=f"| {day} / {p['reference']} → {p['alternative']} | {float(p['mean_signed_temperature_k']):+.8f} | {float(p['mean_abs_temperature_k']):.8f} | {float(p['max_abs_temperature_k']):.8f} | {p['endpoints_ge_0_05k']} | {p['intervals_ge_10w']} |\n"
    text+='\n## Full-period temperature and energy\n\n| Policy | Mean indoor °C | Min °C | Max °C | Mean signed Δ vs NREF K | Mean absolute Δ K | Peak absolute Δ K |\n|---|---:|---:|---:|---:|---:|---:|\n'
    for p in temps:
        if p['population']=='full_72h' and p['reference']=='NREF':text+=f"| {p['alternative']} | {float(p['alternative_mean_temperature_c']):.9f} | {float(p['alternative_min_temperature_c']):.9f} | {float(p['alternative_max_temperature_c']):.9f} | {float(p['mean_signed_temperature_k']):+.9f} | {float(p['mean_abs_temperature_k']):.9f} | {float(p['max_abs_temperature_k']):.9f} |\n"
    text+='\n| Policy | Cooling kWh (Δ%) | Fan kWh (Δ%) | Combined kWh | Δ combined kWh | Δ combined % | Gas input kWh |\n|---|---:|---:|---:|---:|---:|---:|\n'
    for e in energy:text+=f"| {e['policy']} | {e['cooling_kwh']:.9f} ({e['percentage_cooling_vs_NREF']:+.6f}%) | {e['fan_kwh']:.9f} ({e['percentage_fan_vs_NREF']:+.6f}%) | {e['electric_kwh']:.9f} | {e['delta_electric_vs_NREF_kwh']:+.9f} | {e['percentage_electric_vs_NREF']:+.6f}% | {e['gas_kwh']:.9g} |\n"
    c15e=next(x for x in energy if x['policy']=='C15');c45e=next(x for x in energy if x['policy']=='C45')
    text+=f"\nC45 uses {c45e['electric_kwh']-c15e['electric_kwh']:.9f} kWh more combined electricity than C15. Neither intervention saves electricity over the whole scored period relative to NREF. Cooling, fan and gas are not collapsed into a mixed-carrier savings percentage. Gas input is negligible numerical-scale energy in this context.\n\n"
    text+='| Matched 11:00–14:00 window | Policy | Combined kWh | Δ vs NREF kWh | Δ % |\n|---|---|---:|---:|---:|\n'
    with (HOME/'B2H_THREE_ARM_ENERGY.csv').open() as f:all_energy=list(csv.DictReader(f))
    for e in all_energy:
        if e['window'].endswith('common_11to14'):text+=f"| {e['window']} | {e['policy']} | {float(e['electric_kwh']):.9f} | {float(e['delta_electric_vs_NREF_kwh']):+.9f} | {float(e['percentage_electric_vs_NREF']):+.6f}% |\n"
    text+='''
All energy uses ordered 30-second native W trapezoids. The CSV also evaluates every policy over matched 11:00–11:15 and 11:00–11:45 holds and both recovery clocks (11:15–13:15 and 11:45–13:45), as well as morning/evening context windows. Thus different release times are not hidden in an ostensibly equal-clock comparison. Endpoint watts are never substituted for interval-average demand or energy.

## Comfort against unchanged published bounds

'''
    text+='| Policy | Discomfort K·h | Violation minutes | Episodes | New / eliminated timestamps | Worsened / improved intervals | Max additional K | Additional / reduced K·h |\n|---|---:|---:|---:|---:|---:|---:|---|\n'
    for c in comforts:text+=f"| {c['policy']} | {c['degree_hours']:.9f} | {c['minutes']} | {c['episodes']} | {c['new_violating_timestamps']} / {c['resolved_violating_timestamps']} | {c['worsened_existing_intervals']} / {c['improved_existing_intervals']} | {c['max_additional_violation_k']:.9g} | {c['additional_degree_hours']:.9g} / {c['reduced_degree_hours']:.9g} |\n"
    new=detail['C45_new_timestamp_details'][0] if detail['C45_new_timestamp_details'] else None
    text+=f"\nAll discomfort is above the published upper bound; below-bound degree-hours and durations are zero for every policy. C45's aggregate discomfort is lower, and violation duration falls to 960 minutes. But it introduces {c45comfort['new_violating_timestamps']} new sampled violation versus NREF and {directcomfort['new_violating_timestamps']} versus C15. "
    if new:text+=f"The new point is day {new['day']}, 14:15 benchmark clock (t={new['time_s']} s), only {new['alternative_excess_k']:.12f} K above the bound; it represents five sampled-convention minutes, not a measured continuous five-minute excursion. "
    q=detail['C45_additional_distribution']
    text+=f"Additional excess versus NREF peaks at {c45comfort['max_additional_violation_k']:.9f} K; median {q['p50']:.9g}, p95 {q['p95']:.9g} K. Of 740 paired new/worse minutes, {detail['C45_minutes_additional_below_0_001k']} have additional excess below 0.001 K. No additional interval reaches the retained 0.025/0.05/0.1 K reporting sensitivities. Those are descriptive markers, not comfort acceptance limits.\n\n"
    text+=f"Relative to C15, C45 eliminates {directcomfort['resolved_violating_timestamps']} sampled violations, improves {directcomfort['improved_existing_intervals']} (including eliminated ones), and has {directcomfort['worsened_existing_intervals']} worsened existing samples, with maximum additional excess {directcomfort['max_additional_violation_k']:.9f} K. The new point and all local worsening are retained. B2H_THREE_ARM_COMFORT.csv includes both NREF and direct C15 references; improved counts include eliminated timestamps and are not disjoint categories.\n\n"
    text+='The 9 → 12 episode change under the interventions must be interpreted alongside sampled violation membership and severity, not as evidence of three large new discomfort events. Existing native morning excursions remain in the totals (native peak 2.285 K). Most additional severity is in actual release-relative recovery; small cross-day differences account for many other minutes. No substantial additional sampled comfort problem is demonstrated, but continuous comfort, occupant response and other weather contexts are not established. No-veto delivery alone is not comfort compliance.\n\n'
    text+='## Recovery, equipment activity and carryover\n\n| Policy/day | Before intervention °C | At release °C | Signed recovery ΔT range K | Return marker min | Cooling NREF / policy kWh | Fan NREF / policy kWh | Combined recovery Δ kWh |\n|---|---:|---:|---|---:|---|---|---:|\n'
    for r in a['recovery']:
        text+=f"| {r['policy']}/{r['day']} | {r['alternative_temperature_before_intervention_c']:.6f} | {r['alternative_release_temperature_c']:.6f} | {r['min_recovery_delta_temperature_k']:.6f} to {r['max_recovery_delta_temperature_k']:.6f} | {r['return_marker_minutes']} | {r['native_cooling_recovery_kwh']:.9f} / {r['alternative_cooling_recovery_kwh']:.9f} | {r['native_fan_recovery_kwh']:.9f} / {r['alternative_fan_recovery_kwh']:.9f} | {r['delta_recovery_electric_kwh']:+.9f} |\n"
    text+='''
C15 release is 11:15, C45 release is 11:45. Each descriptive recovery window is its actual release through +120 minutes; NREF is evaluated at that same clock for the relevant policy. The CSV additionally includes NREF temperature before/at release, hold extrema, native command counts, actual active cooling intervals and later-state differences. Release endpoints still contain the cooler hold state; that is not a newly induced post-release undershoot. Three consecutive endpoint/preceding-interval pairs within 0.05 K and 0.01 kW define the frozen return marker; first-pair times are reported, confirmed ten minutes later.

C45 reaches the marker after 15 minutes on all three days; C15 after 15/10/15. There are zero above-NREF five-minute combined-demand intervals, even with a strictly positive sign test, in any two-hour recovery window. Cooling and fan recovery energies individually decrease for both policies. There is therefore no observed above-native electrical-demand rebound on this five-minute scale, even though temperature briefly overshoots the native trajectory by roughly 0.01–0.015 K. Lower recovery use does not cancel the full-period increase.

Actual external control lasts 45 versus 15 minutes/day. Cooling remains electrically active in all nine C45 hold intervals/day (three for C15), so active override time is not mistaken for binary equipment on/off time. Tiny later/cross-day temperature differences persist: C45's maximum before the next daily intervention is about 0.00551/0.00722 K on days two/three, with later-day maxima up to 0.00805 K. Those legitimate carryover states are not forced to match NREF or reset. The daily sign and duration effect are consistent across three dependent days.

## Operating-range contribution and limits

Additional rows: one recording adds 865 scored endpoints, 864 native-integrated intervals and at most 852 future-eligible ML origins after support checks; no training dataset was released. Rows alone are not the evidence of diversity.

Additional control-policy variation: three complete 45-minute histories (135 total externally active minutes) versus three 15-minute histories (45 minutes). The extra 90 minutes use the same 296.90 K target and unchanged weather/occupancy/loads, isolating duration.

Additional physical-response variation: C45 versus C15 has 18 paired endpoints differing by at least 0.05 K and 24 power pairs differing by at least 10 W in common 11:00–14:00 windows. Both versus-native peaks remain near 0.265 K, but C45 has 27 rather than 9 above-marker temperature endpoints and about 2.90 times C15's common-window absolute temperature area. Three response periods and three complete recovery periods are established per alternative; they are not independent weather trials. C45 thus expands time spent in a distinct controlled trajectory, rather than producing a much larger amplitude or a fundamentally different recovery shape.

The original operating-range problem is improved only in this limited temporal-control context. All arms still share one G174 development cohort; global temperature minima and setpoint extrema are essentially unchanged. Most of the 72 hours remains native/stable, with external C45 control only 3.125% of scored time. Duration expansion does not create weather diversity, solve every target-scale problem, establish better ML prediction accuracy, or prove valid counterfactual optimization.

The common25 observational contract still omits the explicit future release plan: C15/C45 may share inputs at the first 11:00 decision but have different +30-minute outcomes. More rows cannot resolve identical-input/different-plan aliasing. Raw as-issued planned-control histories were preserved for a separately specified leakage-safe action-conditioned experiment; future realized vetoes/readbacks must not be backfilled as prediction-time inputs. No model was trained or evaluated here.
'''
    md('B2H_OPERATING_RANGE_ASSESSMENT.md',text)
    md('B2H_G146_RECOMMENDATION.md','''# B2-H G146 recommendation

**YES — the frozen three-arm G146 comparison is worthwhile for separate review and authorization. No G146 preparation or execution is authorized or performed here.**

G174 establishes the intended dose contrast: C45 delivered all 27 intervals without vetoes and produced a sustained, separable trajectory from C15 (18 common-window endpoint differences ≥0.05 K and 24 demand differences ≥10 W). The longer hold improves sampled aggregate discomfort but increases total electricity; its one new violating sample is approximately 0.000019 K above the published bound, and all additional excess is below 0.014 K. This is useful first-of-policy evidence rather than a reason to add simulations solely for more rows.

The remaining NREF/C15/C45 comparison would test whether the duration effect, demand cost, veto feasibility and recovery pattern persist in a second existing development weather context. It would address how much these findings depend on G174's weather and inherited thermal history. G146 remains the original dependency group and fold, with its preserved named initialization and fixed design; it is not three independent weather groups or an untouched validation population. This report creates no G146 launcher, approval, manifest or reservation.

One G174 group cannot establish cross-weather robustness, improved ML generalization, predecision what-if accuracy, real-building physical validity or energy-saving optimization. Three daily holds share weather/state dependencies. Even C45 adds only 90 minutes of external control beyond C15 across 72 scored hours, so broad stable-regime dominance and small target changes remain important.

Eventually, a separately designed experiment with other **feasible** cooling setpoints may broaden response amplitude more than duration alone. Such a study must keep other factors controlled, freeze its own target whitelist and safety/readback checks before outcomes, and respect published bounds/deadband rather than changing comfort limits to force excitation. No new setpoint or scenario is selected, prepared or authorized here. The present experiment remains unchanged.

Next decision: review the valid G174 results and, if the two-context replication is still worth its original cost, issue a separate explicit decision for the three fixed G146 slots. Any future launcher must consult the original parent plus consumed C45 continuation ledger chain. Do not rerun NREF/C15/C45, retry C45, train/evaluate models or release a revised training dataset under B2-H. STOP here.
''')
    sources=list(HOME.glob('*.py'))+[V2/'IMPLEMENTATION_MANIFEST.json',V2/'RUN_MANIFEST.json',V2/'DELIVERY_MANIFEST.json',V2/'launcher.py',
        ROOT/'hvac_control_expansion_b2g_v1/launcher.py',ROOT/'hvac_control_expansion_b2g_v1/validation.py',PILOT/'collector.py',PILOT/'campaign_manifest.json',
        ROOT/'hvac_control_expansion_b2f_v1/packaging.py',PILOT/'DELIVERY_MANIFEST.json',V2/'runtime_state/attempts.sqlite3']
    with (HOME/'SOURCE_HASHES.csv').open('x',newline='',encoding='utf-8') as f:
        w=csv.DictWriter(f,fieldnames=['absolute_path','sha256','bytes']);w.writeheader()
        for p in sources:w.writerow(dict(absolute_path=str(p.resolve()),sha256=sha(p),bytes=p.stat().st_size))
    write_new(HOME/'METHODS.json',dict(temperature='matched scored five-minute endpoints, Celsius and Kelvin deltas',
        energy='30-second native ordered trapezoids; J/3600000 kWh; separate cooling/fan/gas',comfort='published bounds; strict excess >0; origin sample weighted 300s',
        paired_comparison_precision_k=1e-7,response_markers=dict(temperature_k=.05,power_kw=.01),
        response_sensitivities=dict(temperature_k=[.025,.05,.1],power_w=[1,10,50]),recovery_seconds=7200,consecutive_marker_pairs=3,
        simulator_runs=1,ML_models_executed=0,training_dataset_released=False,thresholds_changed_after_outcomes=False))

if __name__=='__main__':
    from hvac_control_expansion_b2f_v1.tests import offline_guard
    with offline_guard():publish()
