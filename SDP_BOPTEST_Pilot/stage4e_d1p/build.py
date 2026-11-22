"""Use frozen causal builder, with explicit causal reporting/command adapters."""
import csv,json,math,socket,subprocess
from bisect import bisect_left,bisect_right
from collections import defaultdict
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch
from stage4e.dataset import (FeatureSpec,SIGNALS,Boundary,build_rows,boundary_value,
    validate_partitions,TEMP,OUT,COOL,FAN,HORIZONS)
from stage4e_d1_v2.handoff import read_qualified_run,known_path_annotations
from stage4e_d1_v2.runner import ROOT,HERE,read,save_new,sha,verify_frozen,POINTS,FLAGS,utc
from stage4e_d1_v2.validation import REFERENCE

HOME=Path(__file__).resolve().parent
PACKAGE=HOME/'DEVELOPMENT_ONLY_SDP_STAGE4E_D1P_v1_0_0'
CAMPAIGN=HERE/'campaign_evidence'
STATUS={'dataset_status':'DEVELOPMENT_ONLY_PREVIEW','evaluation_status':'NON_FINAL_EVALUATION',
    'release_status':'LOCAL_REVIEW_ONLY_NOT_APPROVED_FOR_SHARING_OR_TRAINING'}
LAGS=(0,300,600,900,1800)
SELECTED=tuple(s for s in SIGNALS if s not in (COOL,FAN))
SPEC=FeatureSpec(signals=SELECTED,lags=LAGS,interval_power=True,calendar=True,boundaries=())
EXPECTED={300:3408,600:3366,900:3359,1800:3338}

def dump(path,data):save_new(path,{**STATUS,**data})
def jsonline(stream,data):stream.write(json.dumps({**STATUS,**data},allow_nan=False,separators=(',',':'))+'\n')
def independent_interval(data,start,end,key=None):
    ts=data['time'];a=bisect_left(ts,start);b=bisect_right(ts,end)
    if not (a<b and ts[a]==start and ts[b-1]==end):raise ValueError('Missing native integration endpoint')
    keys=(key,) if key else (COOL,FAN)
    return math.fsum((data[k][i]+data[k][i-1])*.5*(ts[i]-ts[i-1]) for k in keys for i in range(a+1,b))/300000.

def measurement_group(name):
    if name==TEMP:return 'indoor_temperature'
    if name==OUT or 'WeaH' in name:return 'weather_measurements'
    if 'RelHum' in name:return 'outdoor_humidity_optional'
    if name.endswith('_activate') or name.endswith('_u'):return 'effective_control_readbacks'
    if 'PLig' in name or 'PPlu' in name:return 'internal_load_measurements'
    if 'FloSup' in name:return 'supply_flow_optional'
    if 'CO2' in name:return 'co2_optional'
    raise ValueError(name)

def schema():
    d={}
    def add(name,role,unit,group,definition,source,**extra):
        d[name]={'role':role,'dtype':'float64' if role in ('feature','target') else 'string',
            'unit':unit,'group':group,'definition':definition,'source':source,**extra}
    for signal in SELECTED:
        alias,offset,scale=SIGNALS[signal]
        unit='degC' if alias.endswith('_c') or alias in ('indoor_c','outdoor_c') else 'kW' if alias.endswith('_kw') else 'W/m2' if alias.endswith('_wm2') else 'kg/s' if alias.endswith('_kgs') else 'ppm' if alias.endswith('_ppm') else 'fraction' if 'fraction' in alias else '0/1'
        for lag in LAGS:
            add('x__'+alias+f'__lag{lag}s','feature',unit,measurement_group(signal),
                f'Actual endpoint at origin-{lag}; (source+{offset})*{scale}. Readbacks precede the newly issued origin command.',signal,
                lag_s=lag,offset=offset,scale=scale,availability='endpoint received before origin cutoff')
    # Humidity is fractional, not a flag.
    for lag in LAGS:d[f'x__outdoor_rh_fraction__lag{lag}s']['unit']='fraction'
    for prefix,key in [('hvac',None),('cooling',COOL),('fan',FAN)]:
        for lag in LAGS:add(f'x__{prefix}_interval_kw__lag{lag}s','feature','kW','historical_electricity',
            f'Native trapezoidal mean over [origin-{lag}-300,origin-{lag}], not endpoint power.',
            'native 30-second '+(key or 'cooling+fan power'),lag_s=lag,availability='history received before origin cutoff')
    for name,unit,definition in [('time_day_sin','1','sin(2*pi*(origin mod 86400)/86400)'),
        ('time_day_cos','1','cos(2*pi*(origin mod 86400)/86400)'),('benchmark_day','benchmark day','floor(origin/86400); may confound weather group')]:
        add('x__'+name,'feature',unit,'calendar',definition,'simulation clock',availability='known at origin')
    for point in POINTS:
        group='weather_forecasts' if point in ('TDryBul','HGloHor') else 'occupancy_schedule' if point=='Occupancy[1]' else 'published_comfort_limits'
        unit='K' if point in ('TDryBul','LowerSetp[1]','UpperSetp[1]') else 'W/m2' if point=='HGloHor' else 'people'
        for off in range(0,1801,300):add(f'x__boundary::{point}__plus{off}s','feature',unit,group,
            f'As-issued forecast/schedule valid at origin+{off}, issued at origin. Benchmark perfect boundary, not future zone truth.',point,
            forecast_offset_s=off,availability='origin forecast receipt before cutoff; actual issued vintage only')
    for lag in LAGS:
        for flag in FLAGS:add(f'x__issued_{flag}__lag{lag}s','feature','0/1','issued_control_commands',
            f'Actual issued command flag at origin-{lag}, effective for following 300 s. Distinct from endpoint readback.',flag,
            lag_s=lag,availability='command committed by that interval origin cutoff')
        add(f'x__issued_cooling_delta_from_native_k__lag{lag}s','feature','K difference','issued_control_commands',
            'Action encoding: active requested cooling target minus source-native cooling reference at command time; exactly zero perturbation when inactive. Not an imputed effective setpoint.',
            'issued command + pinned native reference',lag_s=lag,availability='known command and source schedule at origin')
    for h in HORIZONS:
        add(f'y__indoor_c__plus{h}s','target','degC','indoor_temperature_targets',f'Actual indoor temperature at origin+{h}.',TEMP,horizon_s=h)
        add(f'y__hvac_interval_kw__plus{h}s','target','kW','electrical_demand_targets',
            f'Native mean cooling+fan demand over [origin+{h}-300,origin+{h}]; final 5-minute interval, not mean over whole horizon.',
            'native 30-second cooling+fan power',horizon_s=h)
    return d

def main():
    assert verify_frozen()=='ec9c64f9abffcda7095d537e375eda7bb8f6b6d367aa1aa2238bcc606bcbeb5c'
    results=ROOT/'stage4e_d1_v2_execution/RESULTS_DELIVERY_MANIFEST.json'
    assert sha(results)=='881c880b601f35b5132991935856b7e3b191e004448c5b4d0bde46ccd77dc596'
    for name,digest in read(results)['files'].items():assert sha(ROOT/name)==digest,name
    assert read(CAMPAIGN/'CAMPAIGN_COMPLETED.json')['classification']=='PASS_QUALIFICATION'
    PACKAGE.mkdir()
    definitions=schema();feature_cols=[k for k,v in definitions.items() if v['role']=='feature']
    target_cols=[k for k,v in definitions.items() if v['role']=='target']
    assert len(feature_cols)==168 and len(target_cols)==8
    groups=defaultdict(list)
    for k in feature_cols:groups[definitions[k]['group']].append(k)
    dump(PACKAGE/'FEATURE_GROUPS.json',{'feature_groups':dict(groups),'feature_columns':feature_cols,'target_columns':target_cols,
        'metadata_columns_are_not_features':True,'ablation_preparation_only_no_models_fit':True})
    dump(PACKAGE/'DATA_DICTIONARY.json',{'columns':definitions,'lag_seconds':LAGS,'horizon_seconds':HORIZONS,
        'forecast_temperatures_remain_kelvin':True,'endpoint_temperature_features_and_targets_are_degC':True})
    config=read(HERE/'campaign.json');runs=[];obs_all=[];elig_all=[];counts=[];sources={}
    for name in ['stage4e/dataset.py','stage4e_d0/handoff.py','stage4e_d1_v2/handoff.py','stage4e_d1_v2/FROZEN_MANIFEST.json',
        'stage4e_d1_v2_execution/RESULTS_DELIVERY_MANIFEST.json','stage4e_d1_v2_execution/POSTFLIGHT_AUDIT.json']:
        sources[name]=sha(ROOT/name)
    streams={n:(PACKAGE/n).open('x',encoding='utf-8') for n in ['DEVELOPMENT_ONLY_ACTION_PATHS.jsonl',
        'DEVELOPMENT_ONLY_REALIZED_ACTIONS_POSTHOC.jsonl','DEVELOPMENT_ONLY_ORIGIN_PROVENANCE.jsonl','DEVELOPMENT_ONLY_EVENT_VALIDATION_POSTHOC.jsonl']}
    for cfg in config['runs']:
        run=read_qualified_run(CAMPAIGN,cfg);runs.append(run)
        rows=build_rows(run,SPEC,task='observational');assert len(rows)==852
        directory=CAMPAIGN/cfg['attempt_id'];records={r['start']:r for r in run.control_history}
        for p in directory.iterdir():
            if p.is_file():sources[p.relative_to(ROOT).as_posix()]=sha(p)
        forecast_by_t={t:read(directory/f'forecast_{i:04d}.json') for i,t in enumerate(records)}
        for record in run.control_history:jsonline(streams['DEVELOPMENT_ONLY_REALIZED_ACTIONS_POSTHOC.jsonl'],{
            'role':'POSTHOC_AUDIT_NOT_MODEL_INPUT','run_id':run.run_id,'start':record['start'],'end':record['end'],
            'actual_command_known_at_sim':record['start'],'known_by_cutoff_order':record['origin_cutoff_order'],
            'issued_command':record['applied_command'],'controller_reason':record['reason'],
            'effective_readback_after_advance_k':record['effective_setpoint_k'],
            'readback_available_at_sim':record['end'],'readback_received_order':record['endpoint_received_order']})
        for event in read(directory/'event_resolutions.json'):jsonline(streams['DEVELOPMENT_ONLY_EVENT_VALIDATION_POSTHOC.jsonl'],{
            'role':'POSTHOC_VALIDATION_NOT_MODEL_INPUT','run_id':run.run_id,**event})
        interval_cache={}
        for t in records:
            interval_cache[t]={k:independent_interval(run.native,t,t+300,k) for k in (COOL,FAN)}
        for row in rows:
            t=row['origin_time'];record=records[t];rid=f'{run.run_id}:{t}';forecast=forecast_by_t[t]
            assert forecast['issued_at_sim']==t and forecast['received_order']<record['origin_cutoff_order']
            features={'x__'+name:v for name,v in row['features'].items()}
            vintage=[Boundary(name,t,valid,value) for name in POINTS for valid,value in zip(forecast['data']['time'],forecast['data'][name])]
            view=replace(run,boundaries=vintage)
            for point in POINTS:
                for off in range(0,1801,300):features[f'x__boundary::{point}__plus{off}s']=boundary_value(view,point,t+off,t)
            for lag in LAGS:
                interval=interval_cache[t-lag-300]
                features[f'x__cooling_interval_kw__lag{lag}s']=interval[COOL]
                features[f'x__fan_interval_kw__lag{lag}s']=interval[FAN]
                command=records[t-lag]['applied_command']
                for flag in FLAGS:features[f'x__issued_{flag}__lag{lag}s']=command[flag]
                features[f'x__issued_cooling_delta_from_native_k__lag{lag}s']=(command['con_oveTSetCoo_u']-REFERENCE.pair(t-lag)[1]) if command[FLAGS[0]] else 0.
            targets={'y__'+k:v for k,v in row['targets'].items()}
            assert set(features)==set(feature_cols) and set(targets)==set(target_cols)
            assert all(isinstance(v,(int,float)) and not isinstance(v,bool) and math.isfinite(v) for v in [*features.values(),*targets.values()])
            metadata={**STATUS,'row_id':rid,'run_id':run.run_id,'scenario':run.scenario,'weather_id':run.weather_id,
                'group_id':run.group_id,'control_policy':run.controller,'partition':'development',
                'origin_sim_s':t,'support_start_sim_s':row['support_start'],'support_end_sim_s':row['support_end'],
                'initialization_id':run.initialization_id,'origin_cutoff_order':record['origin_cutoff_order']}
            for h in HORIZONS:
                metadata[f'target_time_plus{h}s']=t+h
                metadata[f'electric_label_interval_start_plus{h}s']=t+h-300
                metadata[f'electric_label_interval_end_plus{h}s']=t+h
            obs_all.append({**metadata,**features,**targets})
            paths,eligible=known_path_annotations(t,record,records)
            elig_all.append({**STATUS,'row_id':rid,'run_id':run.run_id,'origin_sim_s':t,
                'role':'POSTHOC_ELIGIBILITY_NOT_MODEL_INPUT',**{f'eligible_plus{h}s':int(eligible[h]) for h in HORIZONS}})
            jsonline(streams['DEVELOPMENT_ONLY_ACTION_PATHS.jsonl'],{'row_id':rid,'run_id':run.run_id,'origin_sim_s':t,
                'role':'PREDICTION_TIME_PROPOSALS_NOT_REALIZED_FUTURE','origin_cutoff_order':record['origin_cutoff_order'],
                'source_proposed_path':record['proposed_path'],'source_known_path':record['known_path'],
                'effective_available_at_sim_by_step':[t]+[run.analysis_start]*5,
                'availability_note':'current issued command known by origin cutoff; source known_at_sim is inherited nominal-plan annotation; future entries are frozen proposals only',
                'horizon_step_counts':{str(h):h//300 for h in HORIZONS}})
            jsonline(streams['DEVELOPMENT_ONLY_ORIGIN_PROVENANCE.jsonl'],{'row_id':rid,'run_id':run.run_id,'origin_sim_s':t,
                'role':'PROVENANCE_NOT_MODEL_INPUT','source_directory':directory.relative_to(ROOT).as_posix(),
                'forecast_file':f"forecast_{(t-run.analysis_start)//300:04d}.json",'forecast_sha256':sha(directory/f"forecast_{(t-run.analysis_start)//300:04d}.json"),
                'forecast_issued_at_sim':t,'forecast_received_order':forecast['received_order'],
                'observation_received_order':record['observation_received_order'],'origin_cutoff_order':record['origin_cutoff_order'],
                'validation_state_known_at_origin':record['validation_state_at_origin'],
                'lag_endpoint_times_sim_s':[t-lag for lag in LAGS],
                'lag_issued_command_times_sim_s':[t-lag for lag in LAGS],
                'native_results_sha256':sha(directory/'native_results.json'),
                'later_event_resolution_included_in_features':False})
        counts.append({'run_id':run.run_id,'rows':len(rows),'group_id':run.group_id})
        print('Built',run.run_id,len(rows),'origins',flush=True)
    for stream in streams.values():stream.close()
    validate_partitions(runs)
    assert len(obs_all)==3408 and len({r['row_id'] for r in obs_all})==3408
    masks={h:sum(r[f'eligible_plus{h}s'] for r in elig_all) for h in HORIZONS};assert masks==EXPECTED,masks
    for name,data in [('DEVELOPMENT_ONLY_OBSERVATIONAL.csv',obs_all),('DEVELOPMENT_ONLY_ACTION_ELIGIBILITY.csv',elig_all)]:
        with (PACKAGE/name).open('x',encoding='utf-8',newline='') as stream:
            writer=csv.DictWriter(stream,fieldnames=list(data[0]));writer.writeheader();writer.writerows(data)
    dump(PACKAGE/'RAW_SOURCE_HASHES.json',{'path_base':'SDP_BOPTEST_Pilot (original evidence not copied into this package)',
        'only_four_qualified_runs_used_for_examples':True,'files':sources})
    dump(PACKAGE/'BUILD_SUMMARY.json',{'created_utc':utc(),'rows':3408,'feature_count':168,'target_count':8,
        'numeric_label_values':27264,'temperature_label_values':13632,'electrical_label_values':13632,
        'per_run':counts,'horizon_action_eligibility':{str(h):v for h,v in masks.items()},
        'source_campaign':'SDP_STAGE4E_D1_V2_QUALIFICATION_2.1.0',
        'source_proposal_sha256':verify_frozen(),'builder':'unchanged stage4e.dataset.build_rows + documented deterministic adapters',
        'simulations':0,'ML_fitting_tuning_scoring':False,'shared':False})

if __name__=='__main__':
    # Enforce the user's offline-only instruction for all transitive code paths.
    with patch.object(socket.socket,'connect',side_effect=RuntimeError('Network forbidden in D1P')),patch.object(subprocess,'Popen',side_effect=RuntimeError('External process/Docker forbidden in D1P')):
        main()
