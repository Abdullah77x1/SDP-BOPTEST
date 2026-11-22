"""Portable dictionaries, provenance and independent CSV/legacy checks. No fitting."""
import csv,json,hashlib,zipfile
from collections import Counter,defaultdict
from . import HOME,VERSION
from .export import locate
from stage4e_d2i_1.common import ROOT,read,sha,save_new,require
from stage4e_d2i_1.acceptance import public_pair_audit
from stage4e_d0.plan import COOL,FAN,HEAT

def main():
    p=HOME/'PUBLIC_DEVELOPMENT_VALIDATION_v1_0_0'
    qa=read(p/'DATASET_QA_AND_COUNTS.json');included=read(p/'PARTITION_AND_SOURCE_MANIFEST.json')['runs']
    m=read(ROOT/'stage4e_d2i_1/campaign_manifest.json');byid={r['run_id']:r for r in m['runs']}
    defs=read(p/'DATA_DICTIONARY.json')['frozen_168_feature_and_8_target_definitions']
    with (p/'FEATURE_TARGET_DICTIONARY.csv').open('x',newline='',encoding='utf-8') as f:
        w=csv.DictWriter(f,fieldnames=['column','role','unit','group','definition','source','lag_s','forecast_offset_s','horizon_s']);w.writeheader()
        for k,s in defs.items():w.writerow({'column':k,**{name:s.get(name,'') for name in w.fieldnames if name!='column'}})
    # Preserve actual wall-clock receipts separately from numerical predictor views.
    columns=['row_id','run_id','origin_sim_s','observation_received_utc','forecast_received_utc','cutoff_utc','endpoint_received_utc',
        'observation_order','forecast_order','cutoff_order','endpoint_order','latest_required_history_order','validation_state_at_origin']
    provenance_count=0
    with (p/'MODEL_INPUT_AVAILABILITY_PROVENANCE.csv').open('x',newline='',encoding='utf-8') as f:
        w=csv.DictWriter(f,fieldnames=columns);w.writeheader()
        for item in included:
            cfg=byid[item['run_id']];d=locate(cfg)
            journal=[json.loads(s) for s in (d/'receipt_order.jsonl').read_text().splitlines()];orders={r['order']:r for r in journal}
            seq={r['raw_sequence']:r['order'] for r in journal if r['kind']=='api_received'}
            acquired={}
            with (d/'raw_api.jsonl').open() as raw:
                for line in raw:
                    r=json.loads(line)
                    if '/results/' in r['url'] and r['request']['final_time']-r['request']['start_time']==300:
                        end=r['request']['final_time'];order=seq[r['sequence']]
                        acquired[end]=min(acquired.get(end,order),order)
            for step in (json.loads(s) for s in (d/'steps.jsonl').read_text().splitlines()):
                t=step['start']
                if t-2100<cfg['start'] or t+1800>cfg['end']:continue
                required=[acquired[t-lag] for lag in (0,300,600,900,1800)]
                require(max(required)<step['origin_cutoff_order'],'Native historical feature unavailable at prediction cutoff')
                oo,fo,co,eo=(step[k] for k in ('observation_received_order','forecast_received_order','origin_cutoff_order','endpoint_received_order'))
                require(oo<fo<co<eo,'Receipt ordering failed')
                w.writerow(dict(zip(columns,[cfg['run_id']+':'+str(t),cfg['run_id'],t,orders[oo]['utc'],orders[fo]['utc'],orders[co]['utc'],orders[eo]['utc'],
                    oo,fo,co,eo,max(required),step['validation_state_at_origin']])))
                provenance_count+=1
    # Independently re-read saved CSVs, verify counts/unique IDs and D1P compatibility.
    old=ROOT/'stage4e_d1p/DEVELOPMENT_ONLY_SDP_STAGE4E_D1P_v1_0_0/DEVELOPMENT_ONLY_OBSERVATIONAL.csv'
    with old.open(newline='',encoding='utf-8') as f:legacy={r['row_id']:r for r in csv.DictReader(f)}
    legacy_checked=0;max_error=0.;rowcounts={};partition_groups=defaultdict(set);seen=set()
    for partition in ('development','validation'):
        count=0
        with (p/f'ml_engineered_{partition}.csv').open(newline='',encoding='utf-8') as f:
            reader=csv.DictReader(f)
            require(len(reader.fieldnames)==len(set(reader.fieldnames)),'Duplicate columns')
            for row in reader:
                require(row['row_id'] not in seen and row['partition']==partition,'Duplicate origin or wrong partition');seen.add(row['row_id']);count+=1
                partition_groups[partition].add(row['group_id'])
                require(row['row_id']==row['run_id']+':'+row['sim_time_s'],'Unstable row ID')
                if row['row_id'] in legacy:
                    for k in defs:
                        diff=abs(float(row[k])-float(legacy[row['row_id']][k]));require(diff<=1e-10,'D1P numerical compatibility failed');max_error=max(max_error,diff)
                    legacy_checked+=1
        rowcounts[partition]=count
        require(count==qa['per_partition_ML_origins'].get(partition,0),'CSV count differs from build')
    require(legacy_checked==3408 and not(partition_groups['development']&partition_groups['validation']),'Reference rows or grouping changed')
    require(provenance_count==len(seen),'Origin provenance count mismatch')
    # Pair-level acceptance remains unchanged, including inconclusive excitation.
    groups=defaultdict(list)
    for r in included:groups[r['group_id']].append(r)
    coverage=[]
    for gid,items in groups.items():
        items.sort(key=lambda r:r['policy']!='native')
        if len(items)!=2:
            coverage.append({'group_id':gid,'status':'INCOMPLETE_MATCHED_PAIR','runs':[r['run_id'] for r in items]});continue
        cfgs=[byid[r['run_id']] for r in items];dirs=[locate(c) for c in cfgs]
        audit=public_pair_audit(read(dirs[0]/'RUN_COMPLETED.json'),read(dirs[1]/'RUN_COMPLETED.json'),read(dirs[0]/'native_results.json'),
            read(dirs[1]/'native_results.json'),cfgs[0],m['policy'])
        coverage.append({'group_id':gid,'season':items[0]['season'],'partition':items[0]['partition'],
            'status':'COOLING_GROUP_QUALIFIED' if audit['cooling_group_qualified'] else 'INCONCLUSIVE_EXCITATION_FOR_COOLING',**audit})
    save_new(p/'GROUP_ACTIVITY_AND_EXCITATION_QA.json',{'groups':coverage,'protected_collected':False,'whole_D2_campaign_PASS_claimed':False,
        'winter_G020_remains_5_of_6':True,'inconclusive_excitation_does_not_remove_valid_observational_rows':True})
    with (p/'RUN_ENERGY_AND_CONTROL_SUMMARY_POSTHOC.csv').open('x',newline='',encoding='utf-8') as f:
        cols=['run_id','group_id','partition','season','policy','cooling_plus_fan_kWh','gas_J_separate','official_thermal_discomfort_Kh',
            'cooling_active_intervals','full_pulses','recoveries','veto_intervals','occupied_outside_band_origins']
        w=csv.DictWriter(f,fieldnames=cols);w.writeheader()
        for item in included:
            d=locate(byid[item['run_id']]);energy=read(d/'energy_audit.json');status=read(d/'RUN_COMPLETED.json');c=status['coverage']
            w.writerow({**{k:item[k] for k in ('run_id','group_id','partition','season','policy')},
                'cooling_plus_fan_kWh':energy['electrical_kwh'],'gas_J_separate':energy['gas_reported_channel_j_separate'],
                'official_thermal_discomfort_Kh':read(d/'official_kpis.json')['tdis_tot'],
                'cooling_active_intervals':c['cooling_active'],'full_pulses':c['verified_full_pulses'],
                'recoveries':c['verified_recoveries'],'veto_intervals':c['veto_intervals'],
                'occupied_outside_band_origins':c['occupied_outside_band_endpoints']})
    execution=read(HOME/'PUBLIC_EXECUTION_RESULT.json')
    save_new(p/'EXTENDED_QA.json',{'classification':'PASS','saved_CSV_row_counts':rowcounts,'unique_ML_origins':len(seen),
        'legacy_D1P_origins_verified':legacy_checked,'legacy_feature_target_comparisons':legacy_checked*176,'maximum_legacy_error':max_error,
        'native_history_features_received_before_cutoff':provenance_count,'receipt_wall_clock_provenance_rows':provenance_count,
        'group_overlap_between_partitions':False,'additional_collection_classification':execution['classification'],
        'additional_runs_qualified':len(execution['qualified_additional_run_ids']),'additional_successful_advances':execution['successful_scored_advances']})
    source={'building':'bestest_air','BOPTEST':'0.9.0','weather':'Denver-Stapleton DRYCOLD TMY, one source year',
        'collector_manifest_sha256':'c8b25149091419b514e8a65dd1987b624ac296ade6c27e527d616d778a813e86',
        'adapter_manifest_sha256':'44ed53dfb2a2316a9a529d5b7340932d35e4cc4929d52af0e720c82c0ebc2afb',
        'FMU_sha256':m['model']['FMU_sha256'],'target_builder_sha256':sha(ROOT/'stage4e/dataset.py'),
        'feature_dictionary_builder_sha256':sha(ROOT/'stage4e_d1p/build.py'),
        'exporter_sha256':sha(HOME/'export.py'),'dataset_version':VERSION,'authorization_sha256':sha(HOME/'USER_AUTHORIZATION.md')}
    save_new(p/'SOFTWARE_AND_MODEL_PROVENANCE.json',source)
    save_new(p/'RUN_CONFIGURATION_MANIFEST.json',{'runs':[byid[r['run_id']] for r in included],
        'source_frozen_manifest_sha256':sha(ROOT/'stage4e_d2i_1/campaign_manifest.json'),
        'control_policy':{k:v for k,v in m['policy'].items() if k!='base'},'model':m['model'],
        'warmups_are_not_ML_examples':True,'protected_run_configurations_not_included':True})
    text=f'''# Start here — SDP public dataset teammate handoff

**{len(included)} completed runs; {len(seen):,} usable ML origins. Development: {rowcounts['development']:,}; validation: {rowcounts['validation']:,}.**

1. Extract this ZIP into one folder. Run `python load_example.py` (standard library only).
2. ML teammate: use `ml_baseline_development.csv` and `ml_baseline_validation.csv`; x__ columns are inputs, y__ columns are eight targets. The 168-feature engineered views are optional candidates, not required inputs. FEATURE_TARGET_DICTIONARY.csv gives definitions and units. Do not use metadata IDs/time-group labels or posthoc files as predictors. Retain whole original pairs/groups and development/validation assignments.
3. RC teammate: use `rc_intervals.csv` plus BUILDING_SPECIFICATIONS.json. Read the electrical-versus-thermal proxy assumptions in DATA_DICTIONARY.json and README.md before later authorized fitting. End-temperature responses and interval-realized forcing are retrospective fields, not prediction-time future inputs.
4. Optimization teammate: use `prediction_time_action_paths.jsonl` and current/past controls for interface/software preparation. Future proposals differ from realized veto-dependent actions. `action_eligibility_posthoc.csv` is an audit mask, not an input. No optimizer or predictive model was fitted or executed here.
5. Raw variables and forecasts remain in their own CSVs. Nine extra forecasts/gains were not collected for four old reference runs and remain explicitly missing. Do not fabricate zero values or discard useful constants. MODEL_INPUT_AVAILABILITY_PROVENANCE.csv contains actual wall-clock receipt times and verifies that historical native power was acquired before each forecast cutoff.

Read README.md for full methodology. This is one simulated building and one Denver TMY source, with deterministic matched controls; these are not independent weather years or real buildings. No protected test data is present, and no independent final-test performance is claimed. G020 remains excitation-inconclusive; other group classifications are in GROUP_ACTIVITY_AND_EXCITATION_QA.json. Raw validity and excitation qualification are distinct.

RUN_ENERGY_AND_CONTROL_SUMMARY_POSTHOC.csv contains full-run electricity, separate gas energy, discomfort and control/activity summaries for engineering review; these full-run outcomes must not be joined as prediction-time inputs. RUN_CONFIGURATION_MANIFEST.json preserves exact included windows, policies and original reference-group mapping.

`TEAM_PACKAGE_MANIFEST.json` is the complete final checksum list; SHA256_MANIFEST.json separately preserves the core export's checksums. Original simulator evidence remains archived outside this portable package. The initial incomplete eight-run ZIP was preserved before new simulations. No private credentials, unrelated repositories or Docker images are included.

All subsequent ML training/evaluation, RC fitting, optimization and protected collection require separate authorization; this task performed data generation, export and QA only.
'''
    (p/'START_HERE.md').write_text(text,encoding='utf-8')
    files={f.relative_to(p).as_posix():sha(f) for f in p.rglob('*') if f.is_file()}
    save_new(p/'TEAM_PACKAGE_MANIFEST.json',{'version':VERSION,'files':files,'not_independent_final_test':True})
    archive=ROOT/'SDP_PUBLIC_DEVELOPMENT_VALIDATION_TEAM_HANDOFF_v1_0_0.zip'
    with zipfile.ZipFile(archive,'x',zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        for f in sorted(p.rglob('*')):
            if f.is_file():z.write(f,f.relative_to(p).as_posix())
    with zipfile.ZipFile(archive) as z:
        require(z.testzip() is None,'Final ZIP CRC failure')
        for name,h in files.items():require(hashlib.sha256(z.read(name)).hexdigest()==h,'Final ZIP hash mismatch')
    save_new(HOME/'TEAM_HANDOFF_DELIVERY.json',{'archive':str(archive),'archive_sha256':sha(archive),'bytes':archive.stat().st_size,
        'team_manifest_sha256':sha(p/'TEAM_PACKAGE_MANIFEST.json'),'CRC_and_member_hashes':'PASS','auto_sent_to_teammates':False,
        'ML_origins':len(seen),'partition_origins':rowcounts,'additional_runs_completed':len(execution['qualified_additional_run_ids'])})
    print(json.dumps(read(HOME/'TEAM_HANDOFF_DELIVERY.json'),indent=2))

if __name__=='__main__':main()
