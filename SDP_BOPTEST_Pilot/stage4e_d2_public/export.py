"""Public data export using unchanged D1P feature/target primitives. No simulation or fitting."""
import base64,csv,json,math,shutil,zipfile,hashlib
from pathlib import Path
from bisect import bisect_left,bisect_right
from collections import Counter,defaultdict
from stage4e_d2i_1.common import ROOT,read,sha,save_new,require,digest
from stage4e.dataset import Run,build_rows,validate_partitions,SIGNALS,HORIZONS,TEMP,OUT,COOL,FAN
from stage4e_d1p.build import SPEC,LAGS,schema,independent_interval
from stage4e_d0.plan import POINTS,FLAGS,HEAT,LOW,UP,OCC
from stage4e_d1_v2.validation import REFERENCE
from stage4e_d0.handoff import known_path_annotations
from . import HOME,VERSION

MANIFEST=ROOT/'stage4e_d2i_1/campaign_manifest.json'
def locate(cfg):
    rid=cfg['run_id']
    if cfg['reused']:return ROOT/cfg['source_run']
    if cfg['group_id']=='D2_G020':return ROOT/'stage4e_d2i_1_v1_0_1/future_production_evidence'/rid
    matches=list((ROOT/'stage4e_d2_prep02/runtime_state/batches').glob('*/'+rid))
    require(len(matches)<=1,'Duplicate physical run directories')
    return matches[0] if matches else None

def interval(data,start,end,keys):
    ts=data['time'];a=bisect_left(ts,start);b=bisect_right(ts,end)
    require(a<b and ts[a]==start and ts[b-1]==end,'Native support absent')
    return math.fsum((ts[i]-ts[i-1])*.5*sum(data[k][i]+data[k][i-1] for k in keys) for i in range(a+1,b))/(end-start)

def close(a,b):
    require(type(a) in (int,float) and math.isfinite(a) and math.isfinite(b) and abs(a-b)<=1e-10,'Independent feature/target disagreement')
    return abs(a-b)

def decode_truth(d,cfg):
    endpoints={};forecasts={};whole=None;requests=0
    with (d/'raw_api.jsonl').open() as f:
        for line in f:
            item=json.loads(line);requests+=1
            require(item['http_status']==200 and item.get('attempt',1)==1,'Raw failed/retried request')
            route=item['url'].split('://',1)[-1].split('/',1)[-1].split('/')[0]
            if route not in ('initialize','scenario','advance','forecast','results'):continue
            decoded=json.loads(base64.b64decode(item['raw_body_base64']));value=decoded.get('payload',decoded)
            if route=='initialize' or route=='advance':endpoints[value['time']]=value
            if route=='scenario' and item['method']=='PUT':
                value=value.get('time_period');
                if isinstance(value,dict) and 'time' in value:endpoints[value['time']]=value
            if route=='forecast':forecasts[value['time'][0]]=value
            if route=='results' and item['request']['start_time']==cfg['start'] and item['request']['final_time']==cfg['end']:whole=value
    require(whole is not None and len(endpoints)==865 and len(forecasts)==864,'Incomplete raw truth')
    return endpoints,forecasts,whole,requests

class Table:
    def __init__(self,path,columns):
        self.path=path;self.columns=list(columns);self.stream=path.open('x',encoding='utf-8',newline='');self.writer=csv.DictWriter(self.stream,fieldnames=self.columns)
        self.writer.writeheader();self.rows=0;self.missing=Counter();self.first={};self.nonconstant=set()
    def add(self,row):
        require(set(row)==set(self.columns),'CSV schema differs')
        self.writer.writerow(row);self.rows+=1
        for k,v in row.items():
            if v is None or v=='':self.missing[k]+=1;continue
            if type(v) in (float,int):require(math.isfinite(v),'Nonfinite CSV numeric value')
            if k not in self.first:self.first[k]=v
            elif v!=self.first[k]:self.nonconstant.add(k)
    def finish(self):
        self.stream.close()
        return {'rows':self.rows,'columns':len(self.columns),'missing_counts':dict(self.missing),
            'constant_columns':{k:v for k,v in self.first.items() if k not in self.nonconstant}}

def build(package,initial=False):
    package=Path(package);package.mkdir();config=read(MANIFEST);defs=schema()
    features=[k for k,v in defs.items() if v['role']=='feature'];targets=[k for k,v in defs.items() if v['role']=='target']
    require(len(features)==168 and len(targets)==8,'Frozen D1P schema cardinality changed')
    rawkeys=list(read(ROOT/'stage4e_d2i_1/schema_manifest.json')['raw_observations'])
    fcpoints=config['reporting']['core_forecasts']+config['reporting']['optional_forecasts']
    meta=['dataset_status','row_id','run_id','group_id','partition','season','policy','sim_time_s']
    status='INITIAL_INCOMPLETE_DEVELOPMENT' if initial else 'PUBLIC_DEVELOPMENT_VALIDATION_NOT_FINAL_TEST'
    mlmeta=meta+['support_start_sim_s','support_end_sim_s','origin_cutoff_order']
    baseline=[k for k in features if (k.startswith('x__indoor_c__') or k.startswith('x__hvac_interval_kw__') or k.startswith('x__boundary::')
        or ('__lag0s' in k and not any(s in k for s in ('co2','mass_flow','issued_'))) or k in ('x__time_day_sin','x__time_day_cos'))]
    table={}
    table['raw_observations']=Table(package/'raw_observations.csv',meta+rawkeys)
    table['issued_forecasts']=Table(package/'issued_forecasts.csv',meta+['valid_sim_s','forecast_received_order']+fcpoints)
    nativekeys=['time',TEMP,*FLAGS,'con_oveTSetCoo_u','con_oveTSetHea_u',COOL,FAN,HEAT]
    table['native_history']=Table(package/'native_history.csv',meta+['native_sample_index']+[k for k in nativekeys if k!='time'])
    controlcols=meta+['end_sim_s','proposed_cooling_activate','proposed_cooling_setpoint_K','issued_cooling_activate','issued_cooling_setpoint_K',
        'reason','readback_after_K','readback_available_at_sim_s','observation_received_order','forecast_received_order','origin_cutoff_order','endpoint_received_order']
    table['commands_posthoc']=Table(package/'commands_posthoc.csv',controlcols)
    table['ml_engineered_development']=Table(package/'ml_engineered_development.csv',mlmeta+features+targets)
    table['ml_engineered_validation']=Table(package/'ml_engineered_validation.csv',mlmeta+features+targets)
    table['ml_baseline_development']=Table(package/'ml_baseline_development.csv',mlmeta+baseline+targets)
    table['ml_baseline_validation']=Table(package/'ml_baseline_validation.csv',mlmeta+baseline+targets)
    table['action_eligibility_posthoc']=Table(package/'action_eligibility_posthoc.csv',meta+[f'eligible_plus{h}s' for h in HORIZONS])
    rccols=meta+['end_sim_s','indoor_start_C','indoor_end_C_response','outdoor_start_C','solar_global_start_W_m2','occupancy_people',
        'published_lower_K','published_upper_K','scheduled_internal_convective_W','scheduled_internal_radiative_W','scheduled_internal_latent_W',
        'lighting_start_W','plug_start_W','effective_cooling_start_K','effective_heating_start_K','issued_cooling_activate','issued_cooling_setpoint_K',
        'cooling_electric_mean_W','fan_electric_mean_W','heating_gas_mean_W','cooling_removed_proxy_mean_W','heating_added_proxy_mean_W','signed_HVAC_thermal_proxy_mean_W']
    table['rc_intervals']=Table(package/'rc_intervals.csv',rccols)
    paths=(package/'prediction_time_action_paths.jsonl').open('x',encoding='utf-8')
    events=(package/'event_validation_posthoc.jsonl').open('x',encoding='utf-8')
    runs=[];summary=[];sources={};maxerr=0.;counts=Counter();maskcounts=Counter();raw_requests=0;numeric_checks=0
    units={};forecast_availability={};excluded=[]
    for cfg in config['runs']:
        if cfg['partition']=='protected_final_test':continue
        d=locate(cfg)
        if d is None or not (d/'RUN_COMPLETED.json').exists():excluded.append({'run_id':cfg['run_id'],'reason':'NOT_COMPLETED'});continue
        completed=read(d/'RUN_COMPLETED.json')
        if completed['classification']!='PASS_VALID_RAW' or completed.get('unresolved_events',0)!=0 or completed['cleanup'] not in ('STOP_ACK_VERIFIED','STOP_ACK_AND_REMOVAL_VERIFIED'):
            excluded.append({'run_id':cfg['run_id'],'reason':'FAILED_OR_UNQUALIFIED_RAW','classification':completed['classification']});continue
        require(completed.get('advances',completed.get('advance_responses_received',864))==864,'Run budget not complete')
        manifest=read(d/'ARTIFACT_MANIFEST.json')
        for name,h in manifest['files'].items():require(sha(d/name)==h,'Raw source hash mismatch')
        sources[(d/'ARTIFACT_MANIFEST.json').relative_to(ROOT).as_posix()]=sha(d/'ARTIFACT_MANIFEST.json')
        ends=read(d/'endpoints.json');native=read(d/'whole_native_results.json');meta_source=read(d/'runtime_metadata.json')
        records=[json.loads(s) for s in (d/'steps.jsonl').read_text().splitlines()];bytime={s['start']:s for s in records}
        truth_ends,truth_fc,truth_native,req=decode_truth(d,cfg);raw_requests+=req
        require([truth_ends[e['time']] for e in ends]==ends,'Saved endpoints differ from actual API')
        require(all(truth_native[k]==native[k] for k in native),'Native source differs from API')
        forecasts={s['start']:read(d/f'forecast_{i:04d}.json') for i,s in enumerate(records)}
        for t,f in forecasts.items():require(f['data']==truth_fc[t] and f['issued_at_sim']==t,'Forecast source differs from API')
        run=Run(cfg['run_id'],cfg['initialization']['scenario_key'] or 'custom_fixed_window',cfg['mode'],cfg['group_id']+'_fixed_initialization',
            'bestest_air_v090_Denver_Stapleton_TMY',cfg['group_id'],cfg['partition'],cfg['start'],cfg['end'],cfg['warmup_start'],ends,native,
            provenance=d.relative_to(ROOT).as_posix(),control_history=records)
        runs.append(run)
        season=next(g['calendar_bin'] for g in config['groups'] if g['group_id']==cfg['group_id'])
        def metadata(t):return dict(zip(meta,[status,cfg['run_id']+':'+str(t),cfg['run_id'],cfg['group_id'],cfg['partition'],season,cfg['mode'],t]))
        for e in ends:
            require(set(e)==set(rawkeys)|{'time'},'Unexpected endpoint catalog')
            table['raw_observations'].add({**metadata(e['time']),**{k:e[k] for k in rawkeys}})
        for i,t in enumerate(native['time']):table['native_history'].add({**metadata(t),'native_sample_index':i,**{k:native[k][i] for k in nativekeys if k!='time'}})
        for kind in ('measurements','inputs'):
            for key,val in meta_source[kind].items():units[key]=val['Unit']
        availability={p:all(p in f['data'] for f in forecasts.values()) for p in fcpoints};forecast_availability[cfg['run_id']]=availability
        power_cache={t:{k:interval(truth_native,t,t+300,(k,)) for k in (COOL,FAN,HEAT)} for t in bytime}
        for step in records:
            t=step['start'];f=forecasts[t];cmd=step['applied_command'];planned=step['proposed_command'];boundary=f['data']
            require(step['observation_received_order']<step['forecast_received_order']<step['origin_cutoff_order']<step['endpoint_received_order'],'Causal receipt order failed')
            require(boundary['time']==list(range(t,t+1801,300)),'Forecast time grid')
            for j,valid in enumerate(boundary['time']):table['issued_forecasts'].add({**metadata(t),'row_id':cfg['run_id']+':'+str(t)+':'+str(valid),
                'valid_sim_s':valid,'forecast_received_order':f['received_order'],**{p:boundary[p][j] if p in boundary else None for p in fcpoints}})
            table['commands_posthoc'].add({**metadata(t),'end_sim_s':t+300,'proposed_cooling_activate':planned[FLAGS[0]],
                'proposed_cooling_setpoint_K':planned.get('con_oveTSetCoo_u'),'issued_cooling_activate':cmd[FLAGS[0]],'issued_cooling_setpoint_K':cmd.get('con_oveTSetCoo_u'),
                'reason':step['reason'],'readback_after_K':truth_ends[t+300]['con_oveTSetCoo_u'],'readback_available_at_sim_s':t+300,
                **{k:step[k] for k in ('observation_received_order','forecast_received_order','origin_cutoff_order','endpoint_received_order')}})
            p=power_cache[t];e=truth_ends[t]
            table['rc_intervals'].add({**metadata(t),'end_sim_s':t+300,'indoor_start_C':e[TEMP]-273.15,'indoor_end_C_response':truth_ends[t+300][TEMP]-273.15,
                'outdoor_start_C':e[OUT]-273.15,'solar_global_start_W_m2':e['zon_weaSta_reaWeaHGloHor_y'],
                'occupancy_people':boundary[OCC][0],'published_lower_K':boundary[LOW][0],'published_upper_K':boundary[UP][0],
                'scheduled_internal_convective_W':boundary.get('InternalGainsCon[1]',[None])[0],
                'scheduled_internal_radiative_W':boundary.get('InternalGainsRad[1]',[None])[0],
                'scheduled_internal_latent_W':boundary.get('InternalGainsLat[1]',[None])[0],
                'lighting_start_W':e['zon_reaPLig_y'],'plug_start_W':e['zon_reaPPlu_y'],'effective_cooling_start_K':e['con_oveTSetCoo_u'],
                'effective_heating_start_K':e['con_oveTSetHea_u'],'issued_cooling_activate':cmd[FLAGS[0]],'issued_cooling_setpoint_K':cmd.get('con_oveTSetCoo_u'),
                'cooling_electric_mean_W':p[COOL],'fan_electric_mean_W':p[FAN],'heating_gas_mean_W':p[HEAT],
                'cooling_removed_proxy_mean_W':3*p[COOL],'heating_added_proxy_mean_W':.9*p[HEAT],'signed_HVAC_thermal_proxy_mean_W':.9*p[HEAT]-3*p[COOL]})
        rows=build_rows(run,SPEC,task='observational');require(len({r['origin_time'] for r in rows})==len(rows),'Duplicate ML origins')
        for row in rows:
            t=row['origin_time'];step=bytime[t];f=forecasts[t]['data'];fx={'x__'+k:v for k,v in row['features'].items()}
            for p in POINTS:
                for off in range(0,1801,300):fx[f'x__boundary::{p}__plus{off}s']=f[p][off//300]
            for lag in LAGS:
                p=power_cache[t-lag-300];fx[f'x__cooling_interval_kw__lag{lag}s']=p[COOL]/1000;fx[f'x__fan_interval_kw__lag{lag}s']=p[FAN]/1000
                cmd=bytime[t-lag]['applied_command']
                for flag in FLAGS:fx[f'x__issued_{flag}__lag{lag}s']=cmd[flag]
                fx[f'x__issued_cooling_delta_from_native_k__lag{lag}s']=cmd['con_oveTSetCoo_u']-REFERENCE.pair(t-lag)[1] if cmd[FLAGS[0]] else 0.
            y={'y__'+k:v for k,v in row['targets'].items()};require(set(fx)==set(features) and set(y)==set(targets),'D1P feature compatibility')
            for key,spec in defs.items():
                source=spec['source'];lag=spec.get('lag_s');value=(fx if spec['role']=='feature' else y)[key]
                if spec['role']=='target':
                    end=t+spec['horizon_s'];truth=truth_ends[end][TEMP]-273.15 if 'indoor_c' in key else interval(truth_native,end-300,end,(COOL,FAN))/1000
                elif key.startswith('x__boundary::'):truth=truth_fc[t][source][spec['forecast_offset_s']//300]
                elif source in SIGNALS and not key.startswith('x__issued_'):truth=(truth_ends[t-lag][source]+spec['offset'])*spec['scale']
                elif 'interval_kw__lag' in key:
                    keys=(COOL,) if key.startswith('x__cooling_') else (FAN,) if key.startswith('x__fan_') else (COOL,FAN)
                    truth=interval(truth_native,t-lag-300,t-lag,keys)/1000
                elif source=='simulation clock':truth=math.sin(2*math.pi*(t%86400)/86400) if key.endswith('sin') else math.cos(2*math.pi*(t%86400)/86400) if key.endswith('cos') else t//86400
                elif key.startswith('x__issued_'):
                    c=bytime[t-lag]['applied_command'];truth=(c['con_oveTSetCoo_u']-REFERENCE.pair(t-lag)[1] if c[FLAGS[0]] else 0.) if 'delta_from_native' in key else c[source]
                else:raise ValueError('Unknown feature provenance')
                maxerr=max(maxerr,close(value,truth));numeric_checks+=1
            mm={**metadata(t),'support_start_sim_s':row['support_start'],'support_end_sim_s':row['support_end'],'origin_cutoff_order':step['origin_cutoff_order']}
            require(t-2100==row['support_start']>=cfg['start'] and row['support_end']==t+1800<=cfg['end'],'Cross-boundary support/leakage')
            table['ml_engineered_'+cfg['partition']].add({**mm,**fx,**y})
            table['ml_baseline_'+cfg['partition']].add({**mm,**{k:fx[k] for k in baseline},**y})
            _,eligible=known_path_annotations(t,step,bytime)
            table['action_eligibility_posthoc'].add({**metadata(t),**{f'eligible_plus{h}s':int(eligible[h]) for h in HORIZONS}})
            for h in HORIZONS:maskcounts[str(h)]+=eligible[h]
            paths.write(json.dumps({**metadata(t),'role':'PREDICTION_TIME_PROPOSED_PATHS_NOT_REALIZED_FUTURE',
                'current_issued_command':step['applied_command'],'future_proposals':[{'start':a['start'],'end':a['end'],'command':a['command']} for a in step['known_path'][1:]],
                'future_safety_veto_unknown':True},allow_nan=False)+'\n')
        for e in read(d/'event_resolutions.json'):events.write(json.dumps({'run_id':cfg['run_id'],'group_id':cfg['group_id'],'role':'POSTHOC_NOT_PREDICTOR',**e})+'\n')
        summary.append({'run_id':cfg['run_id'],'group_id':cfg['group_id'],'partition':cfg['partition'],'season':season,'policy':cfg['mode'],
            'source':d.relative_to(ROOT).as_posix(),'ML_origins':len(rows),'raw_observations':len(ends),'native_samples':len(native['time']),
            'raw_status':completed['classification'],'coverage':completed['coverage'],'forecast_channels_available':[p for p,v in availability.items() if v]})
        counts[cfg['partition']]+=len(rows);print('Exported',cfg['run_id'],len(rows),'ML origins',flush=True)
    paths.close();events.close();validate_partitions(runs)
    stats={k:t.finish() for k,t in table.items()}
    require(len(runs)>=8,'Initial completed evidence missing')
    require(sum(s['ML_origins'] for s in summary)==sum(counts.values()),'Counts disagree')
    for key in ('ml_engineered_development','ml_engineered_validation','ml_baseline_development','ml_baseline_validation'):
        require(not stats[key]['missing_counts'],'Required ML feature/label missing')
    shutil.copyfile(ROOT/'stage4e_d2p/BUILDING_SPECIFICATIONS.json',package/'BUILDING_SPECIFICATIONS.json')
    save_new(package/'DATA_DICTIONARY.json',{'version':VERSION,'frozen_168_feature_and_8_target_definitions':defs,'baseline_features':baseline,
        'features_are_candidates_not_mandatory':True,'raw_units':units,'forecast_units':{p:meta_source['forecast_points'][p]['Unit'] for p in fcpoints},
        'metadata_columns':meta,'posthoc_files':['commands_posthoc.csv','action_eligibility_posthoc.csv','event_validation_posthoc.jsonl'],
        'electrical_targets':'Mean cooling+fan kW over [origin+horizon-300,origin+horizon], not whole horizon; native 30-second trapezoids',
        'RC_proxies':{'cooling_removed_proxy_mean_W':'3.0 * cooling_electric_mean_W','heating_added_proxy_mean_W':'0.9 * heating_gas_mean_W',
            'signed_HVAC_thermal_proxy_mean_W':'0.9*heating_gas_mean_W - 3.0*cooling_electric_mean_W'},
        'RC_proxy_assumptions':'Pinned ideal FCU COP=3 and heater efficiency=0.9; model-specific airside proxy, not independently measured zone sensible thermal flow. Fan heat and envelope/internal gains not included in this proxy.',
        'RC_temporal_roles':'Start-state/weather/schedules are origin-known; interval mean forcing and end temperature are retrospective identification records, unavailable as future forecast inputs.',
        'nullable_fields':'Nine extra forecasts and scheduled gains absent in old references remain blank with availability metadata. Inactive issued setpoint is absent (flag zero), not fabricated effective setpoint.'})
    save_new(package/'PARTITION_AND_SOURCE_MANIFEST.json',{'status':status,'runs':summary,'excluded_unavailable_public_runs':excluded,'sources':sources,
        'forecast_availability':forecast_availability,'one_building_one_Denver_TMY':True,'protected_runs_collected_or_included':False,
        'random_row_split_permitted':False,'paired_runs_remain_together':True,'raw_evidence_unchanged':True})
    result={'status':status,'classification':'PASS_DATASET_QA','completed_runs_included':len(runs),'per_partition_ML_origins':dict(counts),
        'total_ML_origins':sum(counts.values()),'tables':stats,'action_path_eligibility':dict(maskcounts),
        'raw_API_requests_verified':raw_requests,'feature_target_values_independently_compared':numeric_checks,'maximum_numeric_error':maxerr,
        'numeric_QA_absolute_tolerance':1e-10,'source_integrity':'PASS','temporal_alignment':'PASS','receipt_causality':'PASS','group_overlap_partition_check':'PASS',
        'warmup_failed_or_protected_used_as_training_rows':False,'models_fit_or_scored':False,'frozen_builder':'stage4e.dataset.build_rows + D1P schema, unchanged'}
    save_new(package/'DATASET_QA_AND_COUNTS.json',result)
    write_docs(package,status,result,initial)
    files={p.relative_to(package).as_posix():sha(p) for p in package.rglob('*') if p.is_file()}
    save_new(package/'SHA256_MANIFEST.json',{'files':files,'status':status})
    archive=package.with_suffix('.zip')
    with zipfile.ZipFile(archive,'x',zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        for p in sorted(package.rglob('*')):
            if p.is_file():z.write(p,p.relative_to(package).as_posix())
    with zipfile.ZipFile(archive) as z:
        require(z.testzip() is None,'ZIP failure')
        for name,h in files.items():require(hashlib.sha256(z.read(name)).hexdigest()==h,'ZIP member mismatch')
    save_new(package.parent/(package.name+'_DELIVERY.json'),{'archive':str(archive),'sha256':sha(archive),'bytes':archive.stat().st_size,'QA':'PASS'})
    return result

def write_docs(p,status,result,initial):
    text=f'''# SDP public simulated-building dataset

Status: **{status}**. {result['completed_runs_included']} completed runs; {result['total_ML_origins']} usable observational forecast origins. This package is authorized public development/validation data, not an independent final test or a model-performance claim. No models were trained. {'This is the initial incomplete development safeguard package created BEFORE any new simulations.' if initial else 'Consult PARTITION_AND_SOURCE_MANIFEST.json for actual included/excluded runs; incomplete or excitation-limited groups are not silently replaced.'}

Start with DATASET_QA_AND_COUNTS.json and DATA_DICTIONARY.json. Read CSV files using the included load_example.py (standard Python, optional pandas example). All times are benchmark simulation seconds. Add a non-leap Jan-1 epoch only for descriptive display; do not claim real calendar-year weather. Temperature feature/target conversions to Celsius are documented; boundary forecast temperatures remain Kelvin. Source raw values, units, constants and sentinels remain unchanged.

## Files and availability

raw_observations.csv retains all 39 raw numeric fields plus identity metadata at 865 endpoints per run. issued_forecasts.csv stores actual issue/valid times and all 14 channel columns; the four old reference runs have only five collected core channels, so nine others remain blank, explicitly marked in the availability manifest. Do not impute these blanks to zero. native_history.csv retains ordered 30-second scored temperatures, setpoints/flags and power channels. commands_posthoc.csv stores actual proposed/applied commands, receipt ordering and subsequent readbacks; it is an audit table, not a future-predictor matrix. Static BUILDING_SPECIFICATIONS.json contains the 66 source-supported parameters separately.

## ML teammate

Use ml_baseline_development.csv and ml_baseline_validation.csv for the compact raw/physics-input view. Use ml_engineered_* only as an optional D1P-compatible 168-feature candidate view; all features are not required. Columns prefixed x__ are inputs, y__ are the eight targets; every other column is metadata and must be excluded from predictors. Select inputs/normalization on development only in future authorized modeling. Keep whole dependency groups/pairs in their frozen partitions. Never randomly split adjacent rows or promote validation to an independent final test.

Targets are indoor temperature at +300/+600/+900/+1800 s and average cooling-plus-fan electrical kW in the LAST five-minute interval ending at each target time. Electricity uses actual native 30-second trapezoids, not endpoint W and not gas. A 35-minute support buffer plus 30-minute target horizon is enforced; actual eligible origins are computed per run. As-issued boundary forecasts are perfect benchmark weather/schedule vintages, distinguished from measured historical weather; real forecast uncertainty is not modeled.

prediction_time_action_paths.jsonl preserves the current issued action and frozen FUTURE PROPOSALS; later vetoes are unknown. action_eligibility_posthoc.csv is a horizon-specific later audit mask and must not be a predictor. commands_posthoc.csv, event_validation_posthoc.jsonl, labels and future raw/native records must never be joined into model inputs at earlier origins. Actual event-boundary readbacks remain unchanged; later verification metadata are separate.

## RC teammate

Use rc_intervals.csv and the specifications. Rows align start state/weather/schedules, 300-second interval power integrals and end-temperature responses. Electrical W differs from thermal W. Model-specific proxies are Qcool=3*Pcool_electric, Qheat=0.9*Pheat_gas and signed Q=Qheat-Qcool, from pinned COP/efficiency. These are not independent zone sensible heat measurements, do not include all envelope/ventilation/fan/internal-gain effects, and do not establish RC identifiability. Interval realized power and end-temperature response are retrospective identification fields, unavailable as prediction-time future inputs. Scheduled gains are missing for legacy references where uncollected. No parameter fitting was performed.

## Optimization teammate

Use the prediction-time proposed paths, current/past control fields, separate observational targets and horizon eligibility masks for software preparation. The safe-cooling policy is fixed excitation, not an optimizer; energy may increase. Do not treat future realized vetoes as available commands, assume observational forecasts establish counterfactual control performance, or silently act on the simulator. Optimizer implementation/execution, model training and protected evaluation need separate authorization.

## Methodology and limits

One bestest_air simulated building, one Denver-Stapleton DRYCOLD TMY weather source and deterministic schedules. Paired runs share weather/initialization and are not independent years. G020 remains excitation-inconclusive (five pulses versus six), while valid raw observational examples remain included with provenance. Other groups retain measured activity/qualification; raw validity and excitation coverage are separate. Eight protected runs remain uncollected and excluded. No final independent-test performance, real-building generalization or comfort compliance is claimed.

Frozen source evidence stays separate and unchanged. This usable package contains exports, definitions and SHA-256 checksums rather than infrastructure credentials, Docker images or unrelated repositories. New task authorization permits this public export; historical no-release markers in immutable raw records are preserved, not rewritten. Initial incomplete data remain separately preserved even after a later expanded package is built.
'''
    (p/'README.md').write_text(text,encoding='utf-8')
    (p/'load_example.py').write_text('''"""Load without training or executing a simulator."""
import csv,json
from pathlib import Path
ROOT=Path(__file__).resolve().parent
qa=json.loads((ROOT/'DATASET_QA_AND_COUNTS.json').read_text())
print(qa['total_ML_origins'],qa['per_partition_ML_origins'])
with (ROOT/'ml_baseline_development.csv').open(newline='',encoding='utf-8') as f:
    first=next(csv.DictReader(f));print('run',first['run_id'],'origin',first['sim_time_s'])
    X={k:float(v) for k,v in first.items() if k.startswith('x__')}
    y={k:float(v) for k,v in first.items() if k.startswith('y__')}
    print('input/target columns',len(X),len(y))
# Optional future analysis with pandas (not required for this example):
# dev=pd.read_csv(ROOT/'ml_baseline_development.csv')
# val=pd.read_csv(ROOT/'ml_baseline_validation.csv')
# Xdev=dev.filter(regex=r'^x__'); ydev=dev.filter(regex=r'^y__')
# Preserve partitions/groups; do not randomly split rows. No fitting here.
''',encoding='utf-8')

if __name__=='__main__':
    import sys
    def guard(event,args):
        if event in ('socket.connect','socket.bind','socket.getaddrinfo','subprocess.Popen','os.system','os.exec','os.spawn','os.posix_spawn'):raise AssertionError('OFFLINE_EXPORT_ONLY')
    sys.addaudithook(guard)
    initial='--initial' in sys.argv
    result=build(HOME/('INITIAL_INCOMPLETE_DEVELOPMENT_v1_0_1' if initial else 'PUBLIC_DEVELOPMENT_VALIDATION_v1_0_0'),initial)
    print(json.dumps({'classification':result['classification'],'runs':result['completed_runs_included'],'ML_origins':result['total_ML_origins']},indent=2))
