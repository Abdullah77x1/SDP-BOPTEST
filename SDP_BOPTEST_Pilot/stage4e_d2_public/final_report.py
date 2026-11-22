"""Final preservation and actual public handoff report; never executes simulations."""
import json,shutil,csv
from collections import Counter
from . import HOME
from stage4e_d2i_1.common import ROOT,read,sha,save_new,require,verify_preservation
from stage4e_d2_prep02.adapter import identity,STATE,BASELINE
from stage4e_d2_prep02.registry import Registry

def main():
    package=HOME/'PUBLIC_DEVELOPMENT_VALIDATION_v1_0_0'
    qa=read(package/'DATASET_QA_AND_COUNTS.json');extra=read(package/'EXTENDED_QA.json');delivery=read(HOME/'TEAM_HANDOFF_DELIVERY.json')
    execution=read(HOME/'PUBLIC_EXECUTION_RESULT.json');sources=read(package/'PARTITION_AND_SOURCE_MANIFEST.json')
    require(qa['classification']=='PASS_DATASET_QA' and extra['classification']=='PASS','Dataset QA failed')
    require(read(HOME/'runtime_startup/STACK_CLEANUP_VERIFICATION.json')['classification']=='VERIFIED_REMOVED','Stack cleanup unverified')
    require(sha(delivery['archive'])==delivery['archive_sha256'],'Teammate ZIP changed')
    for name,h in read(package/'TEAM_PACKAGE_MANIFEST.json')['files'].items():require(sha(package/name)==h,'Dataset member changed')
    initial=read(HOME/'INITIAL_INCOMPLETE_DEVELOPMENT_v1_0_1_DELIVERY.json');require(sha(initial['archive'])==initial['sha256'],'Initial fallback changed')
    reg=Registry(STATE,read(BASELINE));proof=reg.verify_evidence();inventory=reg.inventory()
    before={s['run_id']:s for s in read(HOME/'INITIAL_INTEGRITY_AND_AUTHORITY.json')['inventory']}
    after={s['run_id']:s for s in inventory};named=read(HOME/'PUBLIC_EXECUTION_ENTRY.json')['run_ids']
    require(all(before[k]==after[k] for k in before if k not in named),'Unrelated slot changed')
    require(all(after[k]['status']=='PROTECTED_UNAUTHORIZED' for k in after if after[k].get('category')=='protected_final_test'),'Protected slot changed')
    actual_advances=actual_deploys=0;outcomes=[]
    from .export import locate
    m=read(ROOT/'stage4e_d2i_1/campaign_manifest.json')
    for rid in named:
        cfg=next(c for c in m['runs'] if c['run_id']==rid);d=locate(cfg)
        if d is not None and (d/'RUN_COMPLETED.json').exists():
            r=read(d/'RUN_COMPLETED.json');actual_advances+=r.get('advance_requests_attempted',0);actual_deploys+=r.get('deploy_attempts',0)
            outcomes.append({'run_id':rid,'classification':r['classification'],'advance_attempts':r.get('advance_requests_attempted',0),'cleanup':r['cleanup']})
    require(actual_deploys<=16 and actual_advances<=13824,'Additional budget exceeded')
    shutil.copyfile(STATE/'attempts.sqlite3',HOME/'FINAL_REGISTRY_SNAPSHOT.sqlite3')
    save_new(HOME/'FINAL_ATTEMPT_AND_REGISTRY_AUDIT.json',{'additional_deployment_attempts':actual_deploys,'additional_advance_attempts':actual_advances,
        'outcomes':outcomes,'inventory':inventory,'registry_verification':proof,'protected_and_historical_slots_unchanged':True,
        'database_snapshot_sha256':sha(HOME/'FINAL_REGISTRY_SNAPSHOT.sqlite3')})
    print('Final registry/evidence verification PASS',flush=True)
    preservation=verify_preservation();require(identity()=='44ed53dfb2a2316a9a529d5b7340932d35e4cc4929d52af0e720c82c0ebc2afb','Adapter changed')
    checked={}
    for mfile in (ROOT/'stage4e_d2_pair01/v1_0_0/FINAL_EVIDENCE_MANIFEST_v1_0_1.json',ROOT/'stage4e_d2_pair02/v1_0_0/FINAL_EVIDENCE_MANIFEST.json'):
        for name,h in read(mfile)['files'].items():require(sha(ROOT/name)==h,'Original completed evidence changed')
        checked[mfile.relative_to(ROOT).as_posix()]={'sha256':sha(mfile),'verified_files':len(read(mfile)['files'])}
    for name,h in read(HOME/'EXECUTION_SUPPORT_FREEZE.json')['files'].items():require(sha(HOME/name)==h,'Execution support changed')
    save_new(HOME/'FINAL_PRESERVATION_AUDIT.json',{'classification':'PASS','prior_experiments':preservation,'prior_pair_manifests':checked,
        'unchanged_adapter_sha256':identity(),'only_expected_prior_file_byte_change':'Persistent registry append; historical rows unchanged',
        'initial_fallback_preserved':True,'protected_outcomes_accessed':False,'model_physics_controls_thresholds_dates_unchanged':True})
    runs=sources['runs'];season=Counter();seasonorigins=Counter()
    for r in runs:season[(r['season'],r['partition'])]+=1;seasonorigins[(r['season'],r['partition'])]+=r['ML_origins']
    with (package/'GROUP_ACTIVITY_AND_EXCITATION_QA.json').open() as f:coverage=json.load(f)['groups']
    cooling_limited=[g['group_id'] for g in coverage if not g.get('cooling_group_qualified',False)]
    coolqualified=[g['group_id'] for g in coverage if g.get('cooling_group_qualified',False)]
    heatqualified=[g['group_id'] for g in coverage if g.get('heating_group_qualified',False)]
    rows=['| Season | Development runs / ML origins | Validation runs / ML origins |','|---|---:|---:|']
    for s in ('winter','spring','summer','autumn'):rows.append(f"| {s} | {season[(s,'development')]} / {seasonorigins[(s,'development')]} | {season[(s,'validation')]} / {seasonorigins[(s,'validation')]} |")
    tables=qa['tables'];summary=['| Data product | Rows | Columns |','|---|---:|---:|']
    for name in ('raw_observations','issued_forecasts','native_history','commands_posthoc','ml_baseline_development','ml_baseline_validation','ml_engineered_development','ml_engineered_validation','rc_intervals','action_eligibility_posthoc'):
        st=tables[name];summary.append(f"| {name}.csv | {st['rows']:,} | {st['columns']} |")
    complete=execution['classification']=='ALL_16_PUBLIC_RUNS_COMPLETE'
    report=f'''# SDP Stage 4E-D2 — public dataset generation and teammate delivery

**{'COMPLETE_PUBLIC_COLLECTION_AND_DATASET_QA_PASS' if complete else 'INCOMPLETE_COLLECTION_VALID_DATA_PACKAGED'}**. A usable initial package was preserved before new simulation. Actual authorized collection and a documented raw/ML/RC package are finished. No models were trained, evaluated or fitted; no protected simulation occurred.

## Actual execution

Additional successful runs: **{len(execution['qualified_additional_run_ids'])} / 16**. Additional deployment attempts: **{actual_deploys}**; scored advance attempts: **{actual_advances:,} / 13,824**. All completed runs used their unchanged canonical windows, seven-day warmups, 72 scored hours, 300-second advances, native/safe-cooling policies and original safety/event/readback criteria. Eight separate matched-pair batches were executed in authorized order through unchanged collector 1.0.1 and adapter 1.1.0; no retry/replacement or extra scenario was used. Insufficient excitation was recorded separately from raw validity and did not prompt a changed experiment.

The frozen staged startup and full runtime identity gates passed. Every successful run passed mandatory initialization, full 53-channel collection, native history, metadata/receipt ordering, source/units, control/readback, event validation, original energy reconciliation and instance cleanup. Independent raw-response/safety-decision/energy audits passed before continuing. Exact per-run results and seals remain in their original versioned evidence directories; new companion approvals/audits are in batch_authorizations/. Docker cleanup removed the task stack/network and retained images/volumes; unrelated resources were untouched.

The final dataset includes **{len(runs)} total successful public runs**: the eight pre-existing qualified raw/reference runs plus {len(execution['qualified_additional_run_ids'])} newly collected runs. Reused references are the four qualified D1 v2 identities only. Preflights, failed D1, old overlapping C/D evidence and all eight protected runs are excluded. G020 valid raw evidence remains included with its original five-versus-six excitation limitation. Data release/export here is explicitly authorized by the new user instruction; historical no-release markers in frozen raw records were not edited.

## Actual dataset sizes

{chr(10).join(summary)}

Total usable ML origins: **{qa['total_ML_origins']:,}**, computed from actual lag/native-history/horizon support. Development **{qa['per_partition_ML_origins'].get('development',0):,}**, validation **{qa['per_partition_ML_origins'].get('validation',0):,}**. Eight labels per origin. The engineered view has 168 optional D1P feature candidates plus eight targets and provenance metadata; baseline has 64 candidate inputs plus the same targets and metadata. Neither view requires all candidates in future models. Raw CSV column counts include identity/time metadata; raw observations retain all 39 numeric API fields and issued_forecasts has 14 forecast columns plus issue/valid provenance.

Native-history CSV contains scored samples only, with explicit sample indices retaining order and any source duplicates. Original seven-day warmup histories remain preserved separately and are not training examples. Static 66-parameter specifications remain separate. Raw values, constants, original units, source rounding, tiny residues and sentinels were not clipped or imputed.

## Seasonal and operating-condition coverage

{chr(10).join(rows)}

One bestest_air building, one Denver-Stapleton DRYCOLD TMY source, deterministic matched native/variation policies. Twelve completed public dependency groups represent 36 distinct scored weather days when all public runs complete, not 24 independent weather years or buildings. Native/control pairs remain together; original development/validation assignments and full warmup-footprint/3,600-second embargo checks passed. No random adjacent-row split or final independent test partition was created.

Cooling-qualified groups: **{', '.join(coolqualified)}**. Cooling-excitation-limited groups: **{', '.join(cooling_limited)}**. Heating-proxy-qualified groups: **{', '.join(heatqualified)}**. GROUP_ACTIVITY_AND_EXCITATION_QA.json contains exact per-group activity, applied levels, pulses/recoveries, vetoes and source-derived heating proxies. An excitation-limited group may still supply valid observational forecasting rows; this does not reclassify it or establish control qualification. G020 remains five full pulses/recoveries versus six required. The complete original D2 campaign/partition coverage requirements are not declared satisfied because protected runs were not collected and private protected custody is outside scope.

## QA, missingness, units and leakage

Dataset QA **PASS**: every feature and target independently compared with original raw responses/native histories ({qa['feature_target_values_independently_compared']:,} numerical comparisons); maximum discrepancy {qa['maximum_numeric_error']:.3g}, within unchanged 1e-10 CSV arithmetic tolerance. Saved CSV counts/unique origins were independently re-read. All 3,408 reused D1P origins ×176 feature/target values matched the prior preview within tolerance. Historical native-power receipts were verified before each origin cutoff and actual UTC receipt ordering is exported separately.

Required ML features/labels have no missing or nonfinite values. Exact per-file missing counts and constant columns are in DATASET_QA_AND_COUNTS.json. Nine additional forecasts were not collected in four historical reference runs; those cells and their scheduled-gain RC fields stay blank with per-run availability metadata. Inactive command setpoints remain absent while flag=0; actual effective setpoints/readbacks are separate. These intentional absences are not fabricated zeros. All newly collected runs retained all 14 forecast channels.

Targets: indoor °C at +5/+10/+15/+30 minutes and cooling-plus-fan mean electrical kW over the final five-minute interval ending at each horizon. Native 30-second trapezoids, not endpoint watts or whole-horizon means, supply electrical labels. Gas stays separate. Only current/past observations, historical native electricity and legitimately as-issued benchmark boundary vintages/current committed actions enter features. Future realized observations, commands/vetoes, labels and later event resolutions remain excluded. Prediction-time proposals and posthoc horizon eligibility masks are separate files. Exact event-boundary readings were retained.

RC interval data distinguishes electrical W from model-specific thermal proxies: Qcool=3*Pcool_electric; Qheat=0.9*Pheat_gas; signed Q=Qheat-Qcool, using the pinned model COP/efficiency. These are not independently measured zone sensible heat flows or evidence of RC identifiability. Interval-realized power/end temperatures are retrospective identification fields and must not be used as future predictors. Full equations, assumptions, units and temporal roles are documented.

## Teammate handoff

**Final ZIP:** `{delivery['archive']}`

SHA-256: `{delivery['archive_sha256']}`. ZIP CRC and all member hashes passed. The ZIP contains usable raw, ML and RC CSVs, specifications, dictionaries, provenance/partitions, missing/constant/activity QA, methodology, START_HERE.md and a working standard-library Python loader. No credentials, Docker images or unrelated repository files are included. No automatic message or upload was sent to teammates.

ML teammate: start with ml_baseline_development.csv and ml_baseline_validation.csv, x__ inputs/y__ targets; inspect optional engineered candidates and feature groups only after understanding definitions. Keep development/validation groups intact and fit preprocessing only on development in future authorized modeling.

RC teammate: start with rc_intervals.csv and BUILDING_SPECIFICATIONS.json; verify units, temporal roles, missing historical gains and source-specific thermal-proxy assumptions before any separately authorized fitting.

Optimization teammate: start with current/past controls and prediction_time_action_paths.jsonl; future paths are proposals, not realized veto-dependent outcomes. Eligibility is posthoc metadata. Observational forecasting evidence does not itself establish counterfactual control performance or authorize optimizer execution.

Initial safeguard ZIP remains `{initial['archive']}`: eight runs, 6,816 origins, explicitly incomplete development data, created and verified before any additional simulation. Two offline export-adapter/ZIP-verifier corrections were recorded without modifying raw data or frozen code; the incomplete failed first export folder is preserved but excluded from delivery.

No further simulation, protected evaluation, model training/scoring, RC fitting, optimization or Git push was performed or initiated. **The requested public data package is ready for teammate use and review.**
'''
    (HOME/'STAGE4E_D2_PUBLIC_DATASET_RESULTS.md').write_text(report,encoding='utf-8')
    handoff=f'''# ChatGPT handoff — public dataset generation completed

Please review the attached results; do not infer authorization for model training or protected evaluation.

Additional public simulations completed: {len(execution['qualified_additional_run_ids'])}/16, with {actual_deploys} deployment attempts and {actual_advances:,} scored advances; no retries/replacements. All 24 public runs (including eight pre-existing/reference runs) are packaged if complete. Eight protected runs remain uncollected/excluded. Frozen collector/adapter/physics/control policy/windows/criteria and earlier evidence were preserved; instance and stack cleanup verified.

Actual usable ML origins: {qa['total_ML_origins']:,}; development {qa['per_partition_ML_origins'].get('development',0):,}, validation {qa['per_partition_ML_origins'].get('validation',0):,}. Raw observations {tables['raw_observations']['rows']:,}×{tables['raw_observations']['columns']}; engineered ML {tables['ml_engineered_development']['columns']} columns (168 optional features+8 targets+metadata); baseline {tables['ml_baseline_development']['columns']} columns (64 inputs+8 targets+metadata); RC {tables['rc_intervals']['rows']:,}×{tables['rc_intervals']['columns']}. Native 30-second history, all raw channels and actual issue/valid forecast vintages are included. Older references lack nine extra forecasts/gains; missingness is explicit, no zero backfilling.

Independent feature/target/raw-native QA, saved CSV uniqueness/counts, D1P compatibility for 3,408 prior origins, native-power availability before cutoff, causal alignment and group/partition embargo checks passed. No required ML missing/nonfinite values, future realized predictor leakage, random adjacent splits or protected data. G020 retains five-versus-six INCONCLUSIVE_EXCITATION; other limited groups: {', '.join(cooling_limited)}. Valid observational rows are retained without claiming excitation qualification.

Final teammate ZIP: {delivery['archive']}
SHA-256: {delivery['archive_sha256']}

One simulated building and one Denver TMY source, not independent climates/years/buildings or an independent final test. RC thermal proxies use fixed model-specific COP=3 and heating efficiency=0.9; electrical and thermal quantities remain distinct, and no RC parameters were fitted. Initial eight-run incomplete ZIP was preserved before collection. No ML training/evaluation, optimization or automatic external sharing occurred. Please review dataset readiness and recommend the next separately bounded modeling authorization only after inspecting dictionaries, coverage and limitations.
'''
    (HOME/'CHATGPT_PUBLIC_DATASET_HANDOFF.md').write_text(handoff,encoding='utf-8')
    files={f.relative_to(ROOT).as_posix():sha(f) for f in HOME.rglob('*') if f.is_file() and '__pycache__' not in f.parts and f.suffix!='.zip' and 'INITIAL_INCOMPLETE_DEVELOPMENT_v1_0_0' not in f.parts}
    save_new(HOME/'TASK_DELIVERY_AND_EVIDENCE_MANIFEST.json',{'files':files,'teammate_zip_sha256':delivery['archive_sha256'],'classification':'PUBLIC_HANDOFF_COMPLETE' if complete else 'INCOMPLETE_COVERAGE_HANDOFF'})
    print(json.dumps({'additional_runs':len(execution['qualified_additional_run_ids']),'advances':actual_advances,'ML_origins':qa['total_ML_origins'],
        'raw_observations':tables['raw_observations']['rows'],'cooling_limited_groups':cooling_limited,'zip':delivery['archive']},indent=2))

if __name__=='__main__':main()
