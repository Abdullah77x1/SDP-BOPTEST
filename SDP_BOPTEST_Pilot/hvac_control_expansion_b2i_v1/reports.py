"""Read-only scientific derivation and new, exclusive B2-I reports."""
import json,math,csv
from pathlib import Path
from . import HOME,ROOT,IDS
from .integrity import manifest,runs,verify_frozen,historical
from .analysis import analyze_group,csv_new
from .metadata import verify_origin_metadata
from hvac_control_expansion_b2f_v1.packaging import read,sha,digest,write_new,require,inventory,verify_package

def derive():
    execution=read(HOME/'LIVE_EXECUTION.json');require(execution['status']=='PASS_ALL_THREE_G146','No inference from incomplete campaign')
    dirs146=[Path(o['run_path']) for o in execution['runs']]
    old=ROOT/'hvac_control_expansion_v1/runtime_state/batches/B1_G174_INITIAL_PILOT'
    dirs174=[old/'B1V01_G174_NREF',old/'B1V01_G174_C15',Path(read(ROOT/'hvac_control_expansion_b2g_v2/LIVE_EXECUTION.json')['run_path'])]
    groups={g:analyze_group(g,ds) for g,ds in [('G174',dirs174),('G146',dirs146)]}
    for g,ds in [('G174',dirs174),('G146',dirs146)]:
        for row,d in zip(groups[g]['full_energy'],ds):
            audit=read(d/'energy_audit.json');require(abs(row['electric_kwh']*3600000-audit['electrical_j'])<=audit['internal_tolerance_j'],'Analysis/audit energy mismatch')
    metadata=[]
    for d,r in zip(dirs174+dirs146,manifest()['runs']):metadata.append(dict(run_id=r['run_id'],**verify_origin_metadata(d,r)))
    return groups,metadata

def table(headers,rows):
    return '| '+' | '.join(headers)+' |\n|'+'|'.join(['---']*len(headers))+'|\n'+'\n'.join('| '+' | '.join(str(x) for x in row)+' |' for row in rows)+'\n'

def text_new(name,text):
    with (HOME/name).open('x',encoding='utf-8',newline='\n') as f:f.write(text+'\n')

def publish():
    groups,metadata=derive();g=groups['G146'];h=groups['G174'];execution=read(HOME/'LIVE_EXECUTION.json')
    for name,rows in g['tables'].items():
        if name in ('B2I_CONTROL_DELIVERY.csv','B2I_RECOVERY_BY_DAY.csv'):rows=h['tables'][name]+rows
        csv_new(name,rows)
    for kind in ('TEMPERATURE','ENERGY','COMFORT'):
        name='B2I_G146_'+kind+'_COMPARISON.csv';csv_new('B2I_BOTH_GROUPS_'+kind+'.csv',h['tables'][name]+g['tables'][name])
    write_new(HOME/'ANALYSIS.json',groups);write_new(HOME/'ORIGIN_METADATA_REVIEW.json',metadata)
    primary=lambda a,ref,alt:next(r for r in a['primary_temperature'] if r['reference']==ref and r['alternative']==alt)
    temps=[];energies=[];comfort=[];recovery=[]
    for label,a in groups.items():
        for ref,alt in [('NREF','C15'),('NREF','C45'),('C15','C45')]:
            r=primary(a,ref,alt);temps.append([label,alt+' − '+ref,f"{r['mean_signed_temperature_k']:.9f}",f"{r['mean_abs_temperature_k']:.9f}",f"{r['max_abs_temperature_k']:.9f}",r['endpoints_ge_0_05k'],f"{r['absolute_temperature_area_k_hours']:.9f}"])
        for e,c in zip(a['full_energy'],a['comfort'][:3]):
            energies.append([label,e['policy'],f"{e['cooling_kwh']:.9f}",f"{e['fan_kwh']:.9f}",f"{e['electric_kwh']:.9f}",f"{e['delta_electric_vs_NREF_kwh']:+.9f}",f"{e['percentage_electric_vs_NREF']:+.6f}%",f"{e['gas_kwh']:.9g}"])
            comfort.append([label,c['policy'],f"{c['degree_hours']:.9f}",c['minutes'],c['episodes'],c['new_violating_timestamps'],c['worsened_existing_intervals'],c['improved_existing_intervals'],c['resolved_violating_timestamps'],f"{c['max_additional_violation_k']:.9g}"])
        for r in a['recovery']:recovery.append([label,r['policy'],r['day'],r['return_marker_minutes'],f"{r['max_abs_recovery_delta_temperature_k']:.9f}" if r['actual_release_s'] else 'not delivered',r['above_native_demand_intervals_gt_10w'],r['max_recovery_delta_power_kw'],r['later_max_abs_temperature_k']])
    comparison='# G174 versus G146: fixed cooling duration\n\nAll comparisons use real, valid, completed recordings. These are two matched development weather groups; days and policy arms are dependent. No G174 rerun was performed.\n\n'
    comparison+='## Temperature, common 11:00–14:00\n\n111 paired endpoints per contrast (37/day), inclusive endpoints. Temperature area uses only consecutive five-minute pairs within each window; no overnight bridging.\n\n'+table(['Group','Contrast','Signed K','MAE K','Peak abs K','Count ≥0.05 K','Absolute area K·h'],temps)
    comparison+='\n## Full 72-hour energy\n\nOrdered 30-second native trapezoids. Positive deltas mean added consumption; gas is separate. Tiny near-zero gas percentages are numerically unstable and have no heating-savings interpretation.\n\n'+table(['Group','Policy','Cooling kWh','Fan kWh','Combined kWh','Δ combined kWh','Δ combined %','Gas kWh'],energies)
    comparison+='\n## Sampled comfort\n\nUnchanged issued bounds, 864 five-minute origin samples. Strict positive excess defines a violation; 1e-7 K remains the paired-change tolerance. Counts include tiny numerical violations, not evidence of continuous comfort compliance. Improved existing counts include resolved timestamps.\n\n'+table(['Group','Policy','K·h','Minutes','Episodes','New','Worse existing','Improved existing','Resolved','Maximum extra K'],comfort)
    comparison+='\n## Recovery and carryover\n\nReturn marker: first of three consecutive pairs within 0.05 K and 0.01 kW, censored after 120 minutes. It includes the release endpoint with its preceding interval, so a zero-minute marker is possible. The marker does not establish exact state equality or absence of later carryover. Electrical rebound counts use post-release native-integrated intervals; temperature overshoot is reported separately.\n\n'+table(['Group','Policy','Day','Marker min','Peak recovery abs K','Intervals >10W above native','Maximum Δ recovery kW','Later peak abs K'],recovery)
    for label,a in groups.items():
        c15=primary(a,'NREF','C15');c45=primary(a,'NREF','C45');contrast=primary(a,'C15','C45')
        ratio=c45['absolute_temperature_area_k_hours']/c15['absolute_temperature_area_k_hours'] if c15['absolute_temperature_area_k_hours'] else None
        comparison+=f"\n{label}: C45/C15 common-window absolute area ratio = {ratio}; C45−C15 differs by ≥0.05 K at {contrast['endpoints_ge_0_05k']} paired endpoints and by ≥10 W at {contrast['intervals_ge_10w']} preceding intervals. Daily hold/recovery/morning/evening statistics and cross-day pretreatment differences are in the CSVs.\n"
    comparison+='\nEnergy CSVs evaluate every policy at both release clocks (11:15–13:15 and 11:45–13:45), both identical hold clocks, common 11:00–14:00 and full 72 hours. Recovery CSV additionally uses actual safety-filtered release times. Matched-clock and release-relative comparisons answer different questions. Vetoed episodes, if present, remain valid evidence with actual delivered duration.\n'
    text_new('B2I_G174_VS_G146_COMPARISON.md',comparison)
    delivered={label:{arm:sum(r['applied_intervals'] for r in a['control'] if r['policy']==arm) for arm in ('C15','C45')} for label,a in groups.items()}
    sep={label:a['C45_C15_response_separation'] for label,a in groups.items()}
    assessment=f"""# Operating-range assessment

All six B1 recordings are valid and finalized; applied interval totals: {json.dumps(delivered)}. Common-window C45/C15 separation under the frozen temperature/power reporting markers: {json.dumps(sep)}.

B1 adds two externally scheduled cooling histories (15 versus 45 minutes at the same 296.90 K target), different known release plans, matched responses and isolated two-hour native recovery periods in two existing development groups. It broadens temporal policy and state-history coverage. It adds no new weather window, independent dependency group, setpoint extreme, heating policy, occupancy regime or physical model. Fresh NREF repeats are QA and matched energy references by default.

There are at most 852 eligible origins per alternative, 3,408 across four alternatives, pending any separately authorized eligibility and data-release protocol. The six raw recordings have 5,190 endpoints and 51,846 native samples; neither quantity is an independent sample count. Matched arms retain their parent groups/folds (G174 fold 4; G146 fold 1); the existing development population still has eight groups. No training view has been changed or released.

The experiment addresses the original limitation locally: duration distinguishes trajectories in the scheduled daytime windows. It does not resolve broad operating-range coverage or establish better ML generalization. Most origins still follow native control, and matched paths remain highly dependent. C15 requests 45 active minutes across 72 hours (1.0417%); C45 requests 135 (3.125%), before any safety veto. The numerical magnitude, peak versus sustained duration, energy cost and sampled comfort tradeoffs for each weather group are reported in B2I_G174_VS_G146_COMPARISON.md.

Further simulations are not required to finish B1. First assess an explicitly approved action-conditioned feature/ML protocol against the existing grouped observational baseline. Any future expansion should address a demonstrated residual coverage gap with one justified factor and a new budget, rather than merely add rows. This report grants no further execution authority.
"""
    text_new('B2I_OPERATING_RANGE_ASSESSMENT.md',assessment)
    text_new('B2I_ML_READINESS_REVIEW.md',f"""# ML readiness review only

All six saved journals passed origin-plan review: {sum(r['origins'] for r in metadata)} scored origins checked. The nominal six-step/30-minute future action path, daily frozen schedule, requested block/release timing, current safety-filtered issued command, simulation timestamps, receipt cutoff and observation/forecast order are preserved. Nominal plans are known from run start. Future realized safety vetoes remain unknown at origin; realized future commands, posthoc event resolutions, response labels and later readbacks cannot be substituted as prediction inputs.

At the first 11:00 origin C15 and C45 share the same pretreatment observations/history/weather and the same current target, but have different known future release times. A common25 observational representation can therefore alias different response targets. Merely appending these rows to ordinary observational training can create unmodeled policy dependence. Before the paths diverge, policy identity and known remaining hold/release time are useful discriminating information, even when current activation matches.

A future action-conditioned contract should encode current issued cooling activation and target (with inactive masks), each horizon's nominal activation/target sequence, time to scheduled release, planned remaining hold duration, current block/veto state known at origin, and provenance/availability masks. A 30-minute saved path does not alone describe all 45 minutes; the frozen full schedule and run definition also preserve later planned release. Reconstruct requested future plans from frozen schedules and as-issued records only. Do not reconstruct future effective actions from realized commands after cutoff.

Information needed for nominal action conditioning is reconstructible without leakage. Future safety actions are conditional, not known facts. A separately approved forecasting protocol must state whether it predicts outcomes under the nominal safety-filtered policy distribution or is conditioned on a specified feasible action plan. Native observational benchmarking can remain a separate reference; inclusion of B1 in either ordinary observational or action-conditioned training needs explicit representation, grouped splits, matching/reweighting and eligibility review. Keep all matched arms/warmup footprints in their original group and fold. Never allocate arms across train/test as independent groups or score the untouched validation set during this review.

Maximum additional alternative origins: 3,408. Fresh native supported origins (1,704) are QA references by default. No feature pipeline, feature matrix, labels, model fitting, prediction evaluation, performance claim or augmented dataset release was implemented. Next step: approve an action-conditioned feature contract and grouped evaluation plan before considering ML execution.
""")
    q=read(HOME/'OFFLINE_QUALIFICATION.json');identity=verify_frozen()
    rows=[]
    for o in execution['runs']:
        s=o['raw_result'];rows.append([o['run_id'],s['deploy_attempts'],s['initialization_attempts'],s['advances'],s['endpoints'],s['native_samples'],s['coverage']['requested_intervals'],s['coverage']['applied_intervals'],s['classification'],o['corrected_finalization']['status']])
    text_new('B2I_EXECUTION_REPORT.md',f"""# B2-I execution report

PASS: three authorized G146 arms completed sequentially with mandatory raw validation and corrected finalization before each next deployment. Offline qualification: {q['tests']} tests, {q['failures']} failures, {q['errors']} errors. No retry or replacement was made.

Frozen implementation SHA-256: `{identity}`. Run manifest SHA-256: `{sha(HOME/'RUN_MANIFEST.json')}`. Approval SHA-256: `{sha(HOME/'AUTHORIZATION.json')}`. Source/FM U pin: `158008fa3b635280a67dfed8bab5804d1f9a96d218b467dfebab77e5cbf8b86a`. Full exact hashes are in IMPLEMENTATION_MANIFEST.json, SOURCE_HASHES.csv and DELIVERY_MANIFEST.json.

{table(['Run','Deploy','Init','Advances','Endpoints','Native','Requested','Delivered','Raw','Finalizer'],rows)}
Initialization remained named typical_cool_day with seven-day native warmup (20,161 regular 30-second samples), scored 12614400–12873600 seconds. Exact G146 source group D2_G146, development fold 1 was preserved. Both current runtime and local source FMU were checked before each deployment; the actual selected FMU was checked before each initialization. These checks are preserved in batch bindings and raw identity artifacts.

Independent replay checked the named scenario request and returned initial endpoint, raw/materialized forecasts/endpoints/native results, safety decisions, effective 296.90 K readbacks, all noncooling flags, receipt/cutoff order, native event handling, warmup, 864 advances, ordered native history, unchanged official-KPI energy reconciliation and cleanup. Metadata checks rejected future realized control information at origin. Fresh NREF reproduced archived G146 using common available channels; the archive's smaller forecast catalog was accepted by the existing contract. Fresh C15/C45 matched NREF through first 11:00, and C45 matched C15 through first 11:15, at unchanged 1e-7 tolerance. Day-two/three carryover was retained.

Each run has an exclusive reservation, immutable terminal ledger record, exhaustive per-run seal, nested manifest and external B2-F corrected package. A new runtime_state/attempts.sqlite3 extension links the original pilot ledger and G174 continuation by hashes, imports all G174 slots consumed, and consumes each G146 slot once. Ten unchanged append-only triggers forbid updates/deletes. Historical datasets, source files, ledgers, G174 evidence and failed-finalization history passed preservation checks.

Raw paths: `{HOME}/runtime_state/batches/B2I_<run_id>/<run_id>`. Validation reports sit beside their raw run. Corrected packages: `{HOME}/finalized/<run_id>`. LIVE_EXECUTION.json links all outputs; REQUEST_SOURCE.json preserves the authorization verbatim. Raw simulation evidence remains quarantined from training release.

Reproduce read-only verification from SDP_BOPTEST_Pilot:
`.venv/Scripts/python.exe -B -m hvac_control_expansion_b2i_v1 verify`
This blocks network/process dispatch. The execution entry is consumed and refuses restart. Do not run it again.

Scientific results are in the comparison report and CSVs. Temperature uses endpoints; electricity uses ordered 30-second trapezoids; comfort uses unchanged issued bounds at five-minute origins. Recovery uses the frozen 0.05 K/0.01 kW/three-pair rule. Tiny numerical violations remain counted separately from magnitude. No ML, new weather, changed setpoint/comfort/physics, dataset release or extra simulation was performed. STOP.
""")
    text_new('B2I_FINAL_RECOMMENDATION.md',"""# Final recommendation

B1's originally designed six-run experiment is complete with valid, sealed and correctly finalized evidence. Both weather groups now have fresh matched NREF/C15/C45 arms. Numerical duration, energy, comfort and recovery findings are in B2I_G174_VS_G146_COMPARISON.md; do not infer identical response magnitude across weather groups or broad population generalization from two development windows.

The next separately approved work should define an action-conditioned forecasting contract and grouped evaluation protocol. The existing common25 features can alias different known future releases. Resolve that representation before training on the alternatives, then compare against the frozen observational baseline while retaining native/stable behavior diagnostics. Further simulation expansion is unnecessary for B1 completion; consider another operating-range dimension only if a concrete residual gap justifies it after that review.

No ML training/evaluation or new dataset release occurred. All six slots are consumed. Stop: no retries, G174 reruns, additional weather, new control settings or physics changes are authorized.
""")
    write_new(HOME/'HISTORICAL_PRESERVATION_FINAL.json',historical())
    paths=read(HOME/'IMPLEMENTATION_MANIFEST.json')['files']
    with (HOME/'SOURCE_HASHES.csv').open('x',newline='',encoding='utf-8') as f:
        w=csv.writer(f);w.writerow(['absolute_path','sha256']);w.writerows(sorted(paths.items()))
    return dict(status='PASS_REPORTS',groups={g:dict(primary_temperature=a['primary_temperature'],full_energy=a['full_energy'],comfort=a['comfort'],recovery=a['recovery']) for g,a in groups.items()})
