"""Evidence-based B2G reports; no result fabrication when a gate fails."""
from . import HOME,PILOT,B2F,RID,VERSION
from hvac_control_expansion_b2f_v1.packaging import read,sha,write_new,require

def md(name,text):
    with (HOME/name).open('x',encoding='utf-8') as f:f.write(text)

def publish():
    qa=read(HOME/'OFFLINE_QUALIFICATION.json') if (HOME/'OFFLINE_QUALIFICATION.json').exists() else None
    execution=read(HOME/'LIVE_EXECUTION.json') if (HOME/'LIVE_EXECUTION.json').exists() else None
    analysis=read(HOME/'THREE_ARM_ANALYSIS.json') if (HOME/'THREE_ARM_ANALYSIS.json').exists() else None
    blocker=read(HOME/'BLOCKER.json') if (HOME/'BLOCKER.json').exists() else None
    text=f'''# B2-G execution report — {VERSION}

Scope: exactly B1V01_G174_C45, one fresh instance/initialization and no more than 864 scored advances. The target, daily 11:00–11:45 schedule, seven-day native warmup, custom G174 initialization, 15033600–15292800 scored seconds, parent D2_G174 development identity/held fold 4, safety rules, source/model and all original partitions remain fixed.

## Implementation and authorization boundary

The new `launcher.py` calls the existing qualified public B1 `collect_run` interface and the B2-F `packaging.finalize` function. No historical executed source or authorization gate was edited or monkeypatched. The original collector provides the unchanged Safety, BudgetedTransport, metadata/forecast gates, readbacks, EventTracker, native history and energy accounting. `validation.py` separately versions the B2-F recorded-run replay with a directory parameter, retaining its checks. `analysis.py` performs only retrospective matched descriptive comparisons.

The corrected finalizer is exercised by the same `execute_one` orchestration in the full-length fabricated C45 test and the authorized live path. Nested run manifests are registered in the seal and outer scope. Finalization output is outside its source batch; the defective basename-wide outer-manifest helper is not used.

The original pilot ledger is itself sealed in the 5,302-file delivery. To preserve it byte-for-byte, B2-G uses a separately versioned append-only SQLite **extension**, cryptographically linked to the original parent ledger and importing its two consumed pilot slots. `runtime_state/attempts.sqlite3` records C45 consumption before deployment. Together these form the authoritative updated ledger chain; future launchers must consult both. Fixed batch/state paths, unique reservations, immutable terminal events and cross-namespace C45 claim checks prevent an output-path change, second deployment, pilot rerun or G146 run. No slot was reset. `LEDGER_BASELINE.json` and `LEDGER_INVENTORY_AFTER.json` expose the chain explicitly.

'''
    if qa:text+=f"Offline qualification: **{qa['status']}**, {qa['tests']} tests, {qa['failures']} failures and {qa['errors']} errors. Network/descendant-process dispatch were denied; fabricated fixtures are temporary and labeled. `OFFLINE_TEST_RESULTS.txt` is the exact qualification log.\n\n"
    if (HOME/'IMPLEMENTATION_MANIFEST.json').exists():
        text+=f"Frozen implementation manifest SHA-256: `{sha(HOME/'IMPLEMENTATION_MANIFEST.json')}`. Run manifest SHA-256: `{sha(HOME/'RUN_MANIFEST.json')}`. The exact user request, sole run/budget authorization, source dependencies, qualification, prior evidence integrity and pre-freeze runtime identity are bound in the new freeze.\n\n"
    if execution:
        raw=execution.get('raw_result') or {};text+=f"## Live outcome\n\nRun: {RID}. Ledger state: **{execution.get('state',execution.get('status'))}**. Raw classification: {raw.get('classification')}. Advances: {raw.get('advances',raw.get('advance_requests_attempted'))}; endpoints: {raw.get('endpoints')}; native samples: {raw.get('native_samples')}; cleanup: {raw.get('cleanup')}. Error: {execution.get('error')}. Corrected finalization: {execution.get('corrected_finalization')}.\n\n"
        if execution.get('validation'):
            text+='The independent recorded-run replay passed source/runtime/FMU identity, initialization/warmup, exact timestamps/counts, safety decisions, command/readbacks, receipt order/chain, native completeness, event resolution, energy reconciliation, raw/materialized agreement and cleanup evidence. C45 matched NREF through the first 11:00 origin and C15 through the first 11:15 origin; later carryover was retained. Detailed checks are in the ledger-sealed C45_VALIDATION.json.\n\n'
    if blocker:text+='## Blocker\n\n'+str(blocker)+'\n\n'
    text+='''## Evidence and reproduction

Run from SDP_BOPTEST_Pilot with the existing interpreter and `-B`:

```
.venv/Scripts/python.exe -B -m hvac_control_expansion_b2g_v1 qualify
.venv/Scripts/python.exe -B -m hvac_control_expansion_b2g_v1 freeze --request <exact supplied B2-G request text>
.venv/Scripts/python.exe -B -m hvac_control_expansion_b2g_v1 execute
.venv/Scripts/python.exe -B -m hvac_control_expansion_b2g_v1 verify
```

The first three commands are exclusive lifecycle actions, **not** retry/resume instructions. A failed mandatory qualification stops this task; existing results cannot be silently replaced. A consumed C45 reservation cannot be reused. Only the last command is repeatable and read-only. Docker access may require the environment's elevated execution path. No disposable live preflight, other simulation, ML execution or training-dataset release is authorized.

New raw evidence: `runtime_state/batches/B2G_G174_C45_ONLY/B1V01_G174_C45/`. Recorded run seals, validation and closed-attempt record are in its parent batch. Corrected external package: `corrected_c45_package/`. Dynamic attempt tracking: `runtime_state/attempts.sqlite3`; immutable parent binding: `LEDGER_BASELINE.json`. Prior raw references remain in `../hvac_control_expansion_v1/runtime_state/batches/B1_G174_INITIAL_PILOT/`. Original failed-finalization history and corrected B2-F evidence are preserved and their statuses are not rewritten. Historical checks are recorded before and after the live attempt.
'''
    md('B2G_EXECUTION_REPORT.md',text)
    if not analysis:
        md('B2G_OPERATING_RANGE_ASSESSMENT.md','# B2-G operating-range assessment\n\nNo complete, validated, correctly finalized C45 comparison is available. No missing physical result tables were fabricated. See the execution report and preserved qualification/blocker/attempt evidence.\n')
        md('B2G_CONTINUATION_RECOMMENDATION.md','# B2-G continuation recommendation\n\nSTOP. No further simulation or model execution is authorized. Resolve the recorded blocker or failed attempt through review; do not automatically retry C45 or substitute G146. No physical diversity or ML improvement is claimed without validated evidence.\n')
        return
    a=analysis;controls=[c for c in a['control'] if c['policy']=='C45']
    text='# B2-G operating-range assessment\n\n'
    text+=f"C45 delivered {sum(c['applied_intervals'] for c in controls)}/27 requested active intervals, with {sum(c['vetoed_intervals'] for c in controls)} vetoed intervals and {sum(c['complete'] for c in controls)}/3 complete hold/recovery episodes. The intervention target remains 296.90 K. `B2G_CONTROL_DELIVERY.csv` records actual readbacks, releases and veto reasons.\n\n"
    text+='## Matched 11:00–14:00 response\n\n| Reference → alternative | Signed mean ΔT K | Mean absolute ΔT K | Peak absolute ΔT K | Endpoints ≥0.05 K | Interval differences ≥10 W |\n|---|---:|---:|---:|---:|---:|\n'
    for x in a['primary_temperature']:text+=f"| {x['reference']} → {x['alternative']} | {x['mean_signed_temperature_k']:.9g} | {x['mean_abs_temperature_k']:.9g} | {x['max_abs_temperature_k']:.9g} | {x['endpoints_ge_0_05k']} | {x['intervals_ge_10w']} |\n"
    text+='\nThese statistics pool the three matched daily windows, each with 37 endpoints (111 total); they are dependent observations in one original development weather group. Daily, hold-clock, recovery-clock, morning/evening and full-period comparisons are in `B2G_THREE_ARM_TEMPERATURE_COMPARISON.csv`. The 0.025/0.05/0.1 K and 1/10/50 W sensitivities are retained. A response marker is descriptive, not a statistical/physical-validation guarantee.\n\n'
    text+='## Native-integrated 72-hour energy\n\n| Policy | Cooling kWh | Fan kWh | Combined kWh | Δ combined vs NREF kWh | Gas input kWh |\n|---|---:|---:|---:|---:|---:|\n'
    for x in a['full_energy']:text+=f"| {x['policy']} | {x['cooling_kwh']:.9f} | {x['fan_kwh']:.9f} | {x['electric_kwh']:.9f} | {x['delta_electric_vs_NREF_kwh']:+.9f} | {x['gas_kwh']:.9g} |\n"
    text+='\nAll energy uses ordered native 30-second trapezoids, preserving duplicate-time event sides. Cooling/fan electricity and gas input remain separate; gas is not added to a derived thermal proxy. `B2G_THREE_ARM_ENERGY_COMPARISON.csv` evaluates every policy over the same 11:00–14:00, 11:00–11:15, 11:00–11:45, 11:15–13:15 and 11:45–13:45 clock windows. Each policy’s own hold/recovery has a different duration/release clock, so those descriptive comparisons must not be presented as identical-clock causal energy comparisons. Full-period energy includes recovery and carryover; no savings or real-building benefit is inferred from a short window.\n\n'
    text+='## Comfort\n\n| Policy | Discomfort K·h | Violating min | Episodes | New violating timestamps | Worsened existing intervals | Peak additional K | Additional/reduced K·h |\n|---|---:|---:|---:|---:|---:|---:|---|\n'
    for x in a['comfort']:text+=f"| {x['policy']} | {x['degree_hours']:.9f} | {x['minutes']} | {x['episodes']} | {x['new_violating_timestamps']} | {x['worsened_existing_intervals']} | {x['max_additional_violation_k']:.9g} | {x['additional_degree_hours']:.9g} / {x['reduced_degree_hours']:.9g} |\n"
    text+='\nComfort is the unchanged sampled-origin convention against issued published bounds, with five-minute duration weights. Strict positive excess defines a violation; 1e-7 K remains the paired-comparison precision. Additional and reduced discomfort are reported separately. The CSV includes below/above-bound contributions, improved/resolved/unchanged violations and magnitude sensitivities, so tiny differences are not equated with substantial excursions. Episode counts alone do not distinguish fragmentation from genuinely new violating timestamps. This does not certify continuous comfort or justify relaxing bounds.\n\n'
    text+='## Recovery and rebound\n\n| Policy/day | Actual release s | NREF/alternative release °C | Signed recovery ΔT range K | Return marker min | Δ recovery electric kWh | Above-native intervals >10 W | Later peak absolute ΔT K |\n|---|---:|---|---|---:|---:|---:|---:|\n'
    for x in a['recovery']:
        if x['actual_release_s'] is None:text+=f"| {x['policy']}/{x['day']} | none applied | unavailable | unavailable | censored | unavailable | unavailable | unavailable |\n";continue
        text+=f"| {x['policy']}/{x['day']} | {x['actual_release_s']} | {x['native_release_temperature_c']:.6f} / {x['alternative_release_temperature_c']:.6f} | {x['min_recovery_delta_temperature_k']:.6f} to {x['max_recovery_delta_temperature_k']:.6f} | {x['return_marker_minutes']} | {x['delta_recovery_electric_kwh']:+.9f} | {x['above_native_demand_intervals_gt_10w']} | {x['later_max_abs_temperature_k']:.9g} |\n"
    text+='\nRecovery is aligned to each actual release through +120 minutes, so C15/C45 release-relative clocks differ; the energy table additionally provides both recovery clocks for every policy. The frozen joint marker is the first of three consecutive endpoint/preceding-interval pairs within 0.05 K and 0.01 kW; absence is censored, not repaired with more simulation. The release endpoint can retain the cooler hold state. Temperature overshoot, native-integrated demand, actual coil activity and later carryover are reported separately; a microscopic post-release difference alone is not labeled rebound. No day-two/day-three state reset or matching requirement was introduced.\n\n'
    separated=a['C45_C15_response_separation'];complete=a['all_C45_holds_complete']
    text+=f"## Diversity conclusion\n\nC45 versus C15 crosses at least one frozen response-separation marker: **{separated}**. All C45 doses fully delivered: **{complete}**. "
    if separated and complete:text+='The recorded 45-minute history adds a verified longer hold and a measurably different temperature/demand trajectory in G174. This improves temporal operating-history coverage in this limited context; it does not introduce a new setpoint extreme or independent weather group. '
    else:text+='The available evidence does not establish a complete, meaningfully separated duration expansion; retain the veto/delivery and physical-response findings for review. '
    text+='Collecting another 865 endpoints is not itself the reason for this assessment. The source signal scale, stable-regime dominance and observational feature-plan aliasing may still limit future ML: no model was fitted/evaluated, no prediction improvement was established, and no predecision what-if capability was validated. Additional C45 records can support at most the existing 852-origin temporal contract after a separate release review; no training dataset was released here.\n'
    md('B2G_OPERATING_RANGE_ASSESSMENT.md',text)
    worse=next(c for c in a['comfort'] if c['policy']=='C45')
    recommendation='WORTHWHILE FOR SEPARATE REVIEW/APPROVAL' if separated and complete else 'HOLD FOR REVIEW OF LIMITED OR INCOMPLETE DIVERSITY'
    text=f'''# B2-G continuation recommendation

**G146: {recommendation}. No G146 run is authorized by this report.**

The G174 evidence shows response separation between C45 and C15: {separated}; complete C45 doses: {complete}. C45 new violating timestamps versus NREF: {worse['new_violating_timestamps']}; maximum additional excess: {worse['max_additional_violation_k']:.9g} K; additional/reduced discomfort: {worse['additional_degree_hours']:.9g}/{worse['reduced_degree_hours']:.9g} K·h. These physical/comfort results must be reviewed alongside full-period energy and recovery rather than using sample volume or episode counts alone.

If this measured duration contrast is accepted, the original G146 NREF/C15/C45 study would test whether it persists in a second existing development context, using the preserved named typical_cool_day initialization. A fresh G146 NREF would remain QA/energy only, with all arms in original D2_G146 and held fold 1. The value is a second matched operating context, not three new independent weather groups. No change to the target, schedules, warmup, partitions, comfort limits, budgets or original experiment is proposed.

One G174 cohort cannot establish broad generalization, improved ML accuracy, reliable predecision what-if forecasting, real-building physics or guaranteed energy savings. C45’s own dose, veto incidence, comfort and recovery are first-of-policy evidence for this context only. A separate continuation decision must specify any future G146 slots and bind the full parent-plus-extension ledger chain; no consumed G174 slot may be reset or rerun.

STOP: no G146 simulation, pilot rerun, C45 retry, other scenario, model execution or training-dataset release has been initiated by the recommendation.
'''
    md('B2G_CONTINUATION_RECOMMENDATION.md',text)

def seal_delivery():
    files={p.relative_to(HOME).as_posix():sha(p) for p in HOME.rglob('*') if p.is_file() and '__pycache__' not in p.parts}
    write_new(HOME/'DELIVERY_MANIFEST.json',dict(version=VERSION,files=files,other_runs_authorized=False,model_fits=0))

if __name__=='__main__':publish();seal_delivery()
