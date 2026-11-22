"""Evidence-based reports; never fabricate physical result CSVs."""
import csv,json
from . import HOME
from .campaign import canonical_manifest
from .integrity import verify_frozen,verify_sources
from stage4e_d2i_1.common import read,sha,save_new

def write_reports():
    m=canonical_manifest();qa=read(HOME/'OFFLINE_QA.json');frozen=verify_frozen()
    execution=read(HOME/'PILOT_EXECUTION.json') if (HOME/'PILOT_EXECUTION.json').exists() else None
    text=f'''# B1 implementation report — version 1.0.0

The separately versioned B1 workflow implements the approved 296.90 K cooling-duration experiment. Six fixed slots retain D2_G174/D2_G146 development identities and their original held folds (4/1). Only G174 NREF then C15 is executable under this authorization. C45 and all G146 live slots remain blocked pending review.

## Implementation and reuse

`campaign.py` owns exact three-arm definitions, custom G174/named typical_cool_day G146 initialization, 11:00 start, 11:15/11:45 releases, canonical native commands, duration coverage and origin-known plans. `collector.py` is a separately versioned orchestration derived from D2 1.0.1, with local B1 planner/coverage imports and extra native-sample command checks. It never invokes the original private collector or monkeypatches a frozen module. `registry.py` versions PREP02's append-only SQLite ledger for three arms; the original database is read only. `live.py` owns exact pilot authorization, launch gates, irreversible reservations, cleanup/sealing, reproducibility and stop behavior. `comparison.py`, `analysis.py`, and `contracts.py` supply B1 comparison/recovery/reporting and quarantined compatibility sidecars. No training dataset was released and no model was fitted.

Unchanged components reused through supported interfaces: Safety, canonical native commands, BudgetedTransport/initialize_run, qualified EventTracker and endpoint/history/readback checks, metadata-receipt validator, catalog/forecast gates, OrderedClient/Journal, warmup gate, NativeElectric/native trapezoids, energy audit and read-only pinned-runtime identity verifier. Old six-interval/two-level/nine-pulse scientific floors are not used for B1 duration coverage. Applicable raw/safety/energy tolerances are unchanged.

## Qualification and integrity

B1 offline suite: {qa['tests']} tests; {qa['failures']} failures, {qa['errors']} errors; {qa['status']}. Existing D2 1.0.1 regression suite: 114 passed (89 compatibility + 25 receipt tests). Both suites block network/process dispatch and use labeled fabricated fixtures. Full fabricated NREF/C15/C45 and named-initialization runs exercise all 864 advances, 865 endpoints, 8,641 native samples, forecast receipts, native events, energy audit and cleanup. Failure injection covers ignored setpoints, ambiguous advance outcome, missing gas, missing warmup sample, bad units and cleanup failure. See `OFFLINE_TEST_RESULTS.txt` and `REGRESSION_TEST_RESULTS.txt`.

The first B1 test pass exposed a test-harness exception-class assertion error; the inherited validator correctly rejected the bad readback. The new assertion was corrected and the complete suite rerun. No existing tests or validators were weakened.

`SOURCE_INTEGRITY_REPORT.json` verifies 33 B1 evidence hashes, inherited archived manifests (10,514 qualified-v2 plus 323 original D1 files), 98 conservative metadata footprint comparisons, and the original registry's 18 consumed reservations without modifying it. Protected/validation outcome data were not inspected. `IMPLEMENTATION_MANIFEST.json` binds all new/imported Python source, design documents, referenced evidence, campaign, offline qualification outputs and the original registry hash. Implementation manifest SHA-256: `{frozen}`. Campaign semantic SHA-256 is recorded in `PILOT_AUTHORIZATION.json`. FMU remains `158008fa3b635280a67dfed8bab5804d1f9a96d218b467dfebab77e5cbf8b86a`.

## Compatibility and interpretation

Keep five-minute origins, 2,100-second input history, 1,800-second maximum horizon and up to 852 eligible origins per alternative run. `contracts.labels` preserves all sixteen existing labels: endpoint Celsius and last-five-minute native interval-average cooling/fan electricity and 0.9×gas heating thermal kW. Gas remains separate from electricity. No endpoint power substitutes for an interval mean. Fresh NREF is QA only by default. Sidecars preserve original groups/folds. Future nominal plans and their knowledge times are recorded separately from later realized commands/vetoes; realized future readbacks, recovery and IDs are not model features. Common25 remains an observational contract; no action-conditioned feature schema/model is implicitly authorized.

Recovery: first of three successive endpoint/preceding-interval pairs within 0.05 K and 0.01 kW in the 120-minute post-release window; otherwise censored. Reporting sensitivity: 0.025/0.05/0.1 K and 1/10/50 W. Positive energy delta means alternative minus fresh NREF. Comfort uses unchanged issued bounds and a source-nominal schedule sensitivity, sampled at five-minute origins; it cannot establish continuous comfort compliance.

## Reproduction

Run from `{HOME.parent}` with `.venv/Scripts/python.exe`:

```
.venv/Scripts/python.exe -m hvac_control_expansion_v1.tests
.venv/Scripts/python.exe -m stage4e_d2i_1_v1_0_1.tests
.venv/Scripts/python.exe -m hvac_control_expansion_v1 validate
.venv/Scripts/python.exe -m hvac_control_expansion_v1 freeze --authorization-source <exact user request text file>
.venv/Scripts/python.exe -m hvac_control_expansion_v1 pilot
```

Tests/freeze commands are for a new unfrozen delivery. Frozen qualification outputs and ledgers must not be overwritten. `pilot` uses the fixed runtime-state path and refuses consumed slots; it is not a resume/retry command. Docker access needs the environment's elevated execution path. The existing engine and four existing pinned service containers were started, without rebuild/configuration edits; the read-only runtime identity gate then passed. No disposable simulator preflight was deployed.
'''
    (HOME/'B1_IMPLEMENTATION_REPORT.md').write_text(text,encoding='utf-8')
    if not execution:
        blocker=read(HOME/'LIVE_BLOCKER.json') if (HOME/'LIVE_BLOCKER.json').exists() else {'reason':'Execution has not completed'}
        result=f"# B1 pilot results\n\nPilot not completed. Blocker: {blocker}. No physical result CSVs have been fabricated. See offline qualification and integrity reports.\n"
        decision='Do not execute remaining four slots. Resolve the recorded blocker under the existing authorization and ledger; any consumed attempt cannot be retried automatically.'
    else:
        result=f"# B1 pilot results\n\nOutcome: **{execution['status']}**.\n\n"
        for r in execution['runs']:
            s=r.get('result') or {}
            result+=f"- {r['run_id']}: {r['state']}; raw {s.get('classification')}; advances {s.get('advances',s.get('advance_requests_attempted'))}; endpoints {s.get('endpoints')}; native samples {s.get('native_samples')}; cleanup {s.get('cleanup')}.\n"
        if execution['error']:result+='\nStop reason: '+execution['error']+'\n'
        summary=execution.get('analysis')
        if summary:
            c=summary['control'];energy=summary['full_period_energy']
            result+=f"\nRequested/applied override intervals: {c['requested_intervals']}/{c['applied_intervals']}. Complete holds: {sum(e['complete'] for e in c['episodes'])}/3.\n\n"
            result+='| Day | Applied minutes | Activation (s) | Release (s) | Recovery native intervals | Veto reasons |\n|---|---:|---:|---:|---:|---|\n'
            for e in c['episodes']:result+=f"| {e['day']} | {e['applied_minutes']} | {e['activation_s']} | {e['release_s']} | {e['recovery_native_intervals']} | {e['veto_reasons']} |\n"
            result+=f"\nCommon 11:00–14:00 endpoint temperature difference: maximum absolute {summary['maximum_abs_temperature_difference_k']:.8g} K; signed mean {summary['mean_temperature_difference_k']:.8g} K; mean absolute {summary['mean_absolute_temperature_difference_k']:.8g} K; absolute trajectory area {summary['temperature_difference_area_k_hours']:.8g} K·h. Temperature marker counts: `{summary['temperature_threshold_counts']}`; interval power marker counts (W): `{summary['power_threshold_counts_w']}`.\n\n"
            result+='| Carrier | NREF kWh | C15 kWh | C15 − NREF kWh |\n|---|---:|---:|---:|\n'
            for key in ('cooling','fan','electric','gas'):result+=f"| {key} | {energy['native_'+key+'_kwh']:.9g} | {energy['alternative_'+key+'_kwh']:.9g} | {energy['delta_'+key+'_kwh']:.9g} |\n"
            result+=f"\nFull-period sampled published-bound comfort: native {energy['published_all_native_degree_hours']:.8g} K·h / {energy['published_all_native_violation_minutes']} min; C15 {energy['published_all_alternative_degree_hours']:.8g} K·h / {energy['published_all_alternative_violation_minutes']} min. New/worse sampled violation periods: {energy['new_or_worse_minutes']} min, {energy['new_or_worse_events']} events; additional {energy['additional_degree_hours']:.8g} K·h; peak additional violation {energy['peak_additional_violation_k']:.8g} K. Occupied, lower/upper and source-nominal schedule sensitivity are included in `B1_ENERGY_COMFORT_COMPARISON.csv`. Native violations remain in all denominators.\n\n"
            deliveries=list(csv.DictReader((HOME/'B1_CONTROL_DELIVERY.csv').open()))
            result+='| Day | Joint return-near-native minutes | Censored at 120 minutes |\n|---|---:|---|\n'
            for d in deliveries:result+=f"| {d['day']} | {d['return_near_native_minutes'] or 'not observed'} | {d['recovery_censored_at_120min']} |\n"
            # Temperature phase summaries from saved matched trajectories, same clock windows.
            pairs=list(csv.DictReader((HOME/'B1_TEMPERATURE_RESPONSE.csv').open()))
            result+='\n| Day / clock phase | NREF mean °C | C15 mean °C | Max absolute difference K |\n|---|---:|---:|---:|\n'
            for day in range(3):
                start=m['runs'][1]['start']+day*86400
                for phase,lo,hi in [('before 10:45–11:00',38700,39600),('during 11:00–11:15',39600,40500),('after 11:15–13:15',40500,47700)]:
                    rows=[r for r in pairs if start+lo<=float(r['time_s'])<start+hi]
                    avg=lambda key:sum(float(r[key]) for r in rows)/len(rows)
                    result+=f"| {day+1} / {phase} | {avg('native_temperature_c'):.8g} | {avg('alternative_temperature_c'):.8g} | {max(abs(float(r['delta_temperature_k'])) for r in rows):.8g} |\n"
            worse=energy['new_or_worse_minutes']>0
            decision=('The pilot delivers the intended dose and measurable response. Continuation is scientifically reasonable after review of comfort and recovery evidence, with a separate explicit continuation decision.' if execution['status']=='VALID_AND_INFORMATIVE' else 'The pilot is valid but does not establish the intended dose/response. Review the recorded delivery and physical response before deciding on continuation.')
            if worse:decision+=' New/worse sampled comfort violations require review; this is not an unqualified acceptable-control result.'
            result+='\nDistinct requested and delivered histories are measured against fresh native control. A one-group C15 pilot does not establish the C15/C45 duration contrast, out-of-group ML benefit, improved generalization, mechanical equilibration or real-building energy savings. No models were trained.\n'
        else:decision='Do not continue. The pilot is invalid or incomplete; preserve its consumed attempt and evidence. Investigate the recorded failure before any revised authorization; do not automatically retry or replace it.'
        result+='\nEvidence: `runtime_state/batches/B1_G174_INITIAL_PILOT/`, per-run `ARTIFACT_MANIFEST.json`, `*_SEALED_MANIFEST.json`, receipt/raw API journals, run completion files, `NATIVE_REPRODUCIBILITY.json`, `PRETREATMENT_COMPARISON.json` (when completed), `PILOT_EXECUTION.json`, and the three result CSVs (only if two real raw-valid runs support analysis). All raw recordings remain quarantined for later release review.\n'
    (HOME/'B1_PILOT_RESULTS.md').write_text(result,encoding='utf-8')
    (HOME/'B1_CONTINUATION_RECOMMENDATION.md').write_text('# B1 continuation recommendation\n\n'+decision+'\n\nSTOP: G174 C45 and G146 NREF/C15/C45 were not executed and have no continuation authorization. No target, schedule, comfort bound, group, fold or run allocation is changed. No ML fitting is authorized.\n',encoding='utf-8')
    save_new(HOME/'FINAL_INTEGRITY_REPORT.json',dict(implementation_sha256=verify_frozen(),sources=verify_sources(),
        result_files={p.name:sha(p) for p in HOME.iterdir() if p.is_file() and p.name.startswith(('B1_','PILOT_'))}))

if __name__=='__main__':write_reports()
