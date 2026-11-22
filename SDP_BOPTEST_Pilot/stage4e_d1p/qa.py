"""Independent raw-response label/feature QA. Offline; no model fitting."""
import base64,csv,json,math,socket,subprocess
from bisect import bisect_left,bisect_right
from collections import Counter
from datetime import datetime
from pathlib import Path
from unittest.mock import patch
from stage4e_d1p.build import HOME,PACKAGE,STATUS,LAGS,EXPECTED
from stage4e.dataset import SIGNALS,COOL,FAN,TEMP,HORIZONS
from stage4e_d1_v2.runner import ROOT,HERE,read,sha,save_new,verify_frozen,POINTS,FLAGS,nominal
from stage4e_d1_v2.validation import REFERENCE

def close(a,b,tolerance=1e-10):
    if isinstance(a,bool) or not isinstance(a,(int,float)) or not math.isfinite(a):raise ValueError('Missing/nonfinite candidate')
    if not isinstance(b,(int,float)) or not math.isfinite(b):raise ValueError('Missing/nonfinite raw truth')
    error=abs(a-b)
    if error>tolerance:raise ValueError(f'Value disagreement {a!r} versus {b!r}')
    return error

def mean_kw(raw,start,end,keys=(COOL,FAN)):
    ts=raw['time'];first=bisect_left(ts,start);last=bisect_right(ts,end)
    if end-start!=300 or first>=last or ts[first]!=start or ts[last-1]!=end:raise ValueError('Missing raw integration support')
    contributions=[]
    for i in range(first+1,last):
        dt=ts[i]-ts[i-1]
        if not 0<=dt<=30:raise ValueError('Raw cadence invalid')
        contributions.append(dt*.5*sum(raw[k][i]+raw[k][i-1] for k in keys))
    return math.fsum(contributions)/300/1000

def main():
    definition=read(PACKAGE/'DATA_DICTIONARY.json')['columns']
    feature_cols=[k for k,v in definition.items() if v['role']=='feature'];target_cols=[k for k,v in definition.items() if v['role']=='target']
    assert len(feature_cols)==168 and len(target_cols)==8
    assert verify_frozen()=='ec9c64f9abffcda7095d537e375eda7bb8f6b6d367aa1aa2238bcc606bcbeb5c'
    for path,digest in read(PACKAGE/'RAW_SOURCE_HASHES.json')['files'].items():assert sha(ROOT/path)==digest,path
    with (PACKAGE/'DEVELOPMENT_ONLY_OBSERVATIONAL.csv').open(newline='',encoding='utf-8') as stream:
        reader=csv.DictReader(stream);headers=reader.fieldnames;rows=list(reader)
    with (PACKAGE/'DEVELOPMENT_ONLY_ACTION_ELIGIBILITY.csv').open(newline='',encoding='utf-8') as stream:elig=list(csv.DictReader(stream))
    assert len(rows)==len(elig)==3408 and len({r['row_id'] for r in rows})==3408
    assert len(set(headers))==len(headers)
    assert set(k for k in headers if k.startswith('x__'))==set(feature_cols)
    assert set(k for k in headers if k.startswith('y__'))==set(target_cols)
    paths={r['row_id']:r for r in (json.loads(x) for x in (PACKAGE/'DEVELOPMENT_ONLY_ACTION_PATHS.jsonl').read_text().splitlines())}
    provenance={r['row_id']:r for r in (json.loads(x) for x in (PACKAGE/'DEVELOPMENT_ONLY_ORIGIN_PROVENANCE.jsonl').read_text().splitlines())}
    masks={r['row_id']:r for r in elig}
    assert set(paths)==set(provenance)==set(masks)=={r['row_id'] for r in rows}
    config=read(HERE/'campaign.json');byrun={};api_counts=0;counts=Counter();maskcounts=Counter();feature_checks=target_checks=0
    max_temperature_error=max_demand_error=max_feature_error=0.;boundary_origins=0
    for cfg in config['runs']:
        d=HERE/'campaign_evidence'/cfg['attempt_id'];raw=[json.loads(x) for x in (d/'raw_api.jsonl').read_text().splitlines()]
        journal=[json.loads(x) for x in (d/'receipt_order.jsonl').read_text().splitlines()]
        prev='0'*64
        for event in journal:
            import hashlib
            x=dict(event);digest=x.pop('sha256')
            assert x['previous_sha256']==prev and hashlib.sha256(json.dumps(x,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()==digest
            prev=digest
        receipts={x['raw_sequence']:x for x in journal if x['kind']=='api_received'}
        issued={};endpoints={};commands={};whole=None
        for item in raw:
            assert item['http_status']==200 and item['attempt']==1
            assert datetime.fromisoformat(item['sent_utc'])<=datetime.fromisoformat(item['received_utc'])
            if '/stop/' in item['url']:continue
            body=json.loads(base64.b64decode(item['raw_body_base64']));body=body.get('payload',body)
            if item['method']=='PUT' and '/scenario/' in item['url']:endpoints[body['time_period']['time']]=body['time_period']
            if item['method']=='POST' and '/advance/' in item['url']:
                endpoints[body['time']]=body;commands[body['time']-300]=item['request']
            if '/forecast/' in item['url']:issued[body['time'][0]]=(body,receipts[item['sequence']]['order'])
            if '/results/' in item['url'] and item['request']['start_time']==cfg['start'] and item['request']['final_time']==cfg['end']:whole=body
        assert whole is not None and len(endpoints)==865 and len(commands)==len(issued)==864
        assert whole==read(d/'whole_native_results.json')
        assert endpoints[cfg['start']]==read(d/'endpoints.json')[0]
        records={x['start']:x for x in (json.loads(s) for s in (d/'steps.jsonl').read_text().splitlines())}
        byrun[cfg['attempt_id']]=(cfg,endpoints,commands,issued,whole,records)
        api_counts+=len(raw)
    for row in rows:
        for key,value in STATUS.items():assert row[key]==value and paths[row['row_id']][key]==value
        assert row['partition']=='development' and all(value!='' for value in row.values())
        cfg,ends,commands,issued,whole,records=byrun[row['run_id']];t=int(row['origin_sim_s']);counts[row['run_id']]+=1
        assert row['row_id']==f"{row['run_id']}:{t}" and row['group_id']==cfg['group_id']
        assert int(row['support_start_sim_s'])==t-2100>=cfg['start'] and int(row['support_end_sim_s'])==t+1800<=cfg['end']
        forecast,fr=issued[t];record=records[t];prov=provenance[row['row_id']]
        assert prov['observation_received_order']<prov['origin_cutoff_order'] and fr==prov['forecast_received_order']<prov['origin_cutoff_order']
        assert prov['origin_cutoff_order']==record['origin_cutoff_order']==int(row['origin_cutoff_order'])
        assert record['endpoint_received_order']>prov['origin_cutoff_order']
        for col in feature_cols:
            v=float(row[col]);spec=definition[col];source=spec['source'];lag=spec.get('lag_s')
            if col.startswith('x__boundary::'):
                valid=t+spec['forecast_offset_s'];j=forecast['time'].index(valid);truth=forecast[source][j]
            elif source in SIGNALS and not col.startswith('x__issued_'):
                truth=(ends[t-lag][source]+spec['offset'])*spec['scale']
            elif 'interval_kw__lag' in col:
                keys=(COOL,) if col.startswith('x__cooling_') else (FAN,) if col.startswith('x__fan_') else (COOL,FAN)
                truth=mean_kw(whole,t-lag-300,t-lag,keys)
            elif source=='simulation clock':
                truth=math.sin(2*math.pi*(t%86400)/86400) if col.endswith('sin') else math.cos(2*math.pi*(t%86400)/86400) if col.endswith('cos') else t//86400
            elif col.startswith('x__issued_'):
                command=commands[t-lag]
                truth=(command['con_oveTSetCoo_u']-REFERENCE.pair(t-lag)[1] if command[FLAGS[0]] else 0.) if 'delta_from_native' in col else command[source]
                assert records[t-lag]['origin_cutoff_order']<=record['origin_cutoff_order']
            else:raise ValueError('Unrecognized feature provenance '+col)
            max_feature_error=max(max_feature_error,close(v,truth));feature_checks+=1
        for h in HORIZONS:
            end=t+h;assert int(row[f'target_time_plus{h}s'])==end
            assert int(row[f'electric_label_interval_start_plus{h}s'])==end-300
            assert int(row[f'electric_label_interval_end_plus{h}s'])==end
            max_temperature_error=max(max_temperature_error,close(float(row[f'y__indoor_c__plus{h}s']),ends[end][TEMP]-273.15))
            max_demand_error=max(max_demand_error,close(float(row[f'y__hvac_interval_kw__plus{h}s']),mean_kw(whole,end-300,end)))
            target_checks+=2
        path=paths[row['row_id']]
        assert path['source_known_path']==record['known_path'] and path['source_proposed_path']==record['proposed_path']
        assert path['effective_available_at_sim_by_step']==[t]+[cfg['start']]*5
        assert path['source_known_path'][0]['command']==commands[t]
        for k,p in enumerate(path['source_known_path']):
            assert p['start']==t+k*300 and p['end']==t+(k+1)*300
            if k:assert p['command']==nominal(cfg,p['start'],config)['command']
        for h in HORIZONS:
            match=all(p['command']==commands[p['start']] for p in path['source_known_path'][:h//300])
            assert int(masks[row['row_id']][f'eligible_plus{h}s'])==int(match)
            maskcounts[h]+=match
        if REFERENCE.event_pairs(t):
            old=REFERENCE.event_pairs(t)[0]
            close(float(row['x__effective_heating_c__lag0s']),old[0]-273.15)
            close(float(row['x__effective_cooling_c__lag0s']),old[1]-273.15)
            assert prov['validation_state_known_at_origin']=='PENDING_EVENT_VERIFICATION'
            boundary_origins+=1
    assert set(counts.values())=={852} and dict(maskcounts)==EXPECTED and boundary_origins==24
    assert feature_checks==3408*168 and target_checks==3408*8
    realized=[json.loads(x) for x in (PACKAGE/'DEVELOPMENT_ONLY_REALIZED_ACTIONS_POSTHOC.jsonl').read_text().splitlines()]
    assert len(realized)==3456
    for r in realized:
        assert r['issued_command']==byrun[r['run_id']][2][r['start']]
        assert r['role']=='POSTHOC_AUDIT_NOT_MODEL_INPUT'
    events=[json.loads(x) for x in (PACKAGE/'DEVELOPMENT_ONLY_EVENT_VALIDATION_POSTHOC.jsonl').read_text().splitlines()]
    assert len(events)==24 and all(e['role']=='POSTHOC_VALIDATION_NOT_MODEL_INPUT' for e in events)
    for path,digest in read(PACKAGE/'RAW_SOURCE_HASHES.json')['files'].items():assert sha(ROOT/path)==digest
    save_new(PACKAGE/'QA_RESULTS.json',{**STATUS,'classification':'PASS','rows':3408,'unique_origin_ids':3408,
        'per_run_rows':dict(counts),'feature_count':168,'feature_values_compared_to_raw':feature_checks,
        'target_count_per_row':8,'target_values_compared_to_raw':target_checks,
        'temperature_labels':13632,'native_integrated_demand_labels':13632,
        'maximum_temperature_error_degC':max_temperature_error,'maximum_electrical_error_kW':max_demand_error,
        'maximum_feature_error':max_feature_error,'numeric_QA_absolute_tolerance':1e-10,
        'tolerance_scope':'CSV/builder floating arithmetic only; no simulator validation tolerance changed',
        'action_eligibility_counts':{str(k):v for k,v in maskcounts.items()},'raw_requests_verified':api_counts,
        'exact_event_readings_preserved':24,'lag_alignment':'PASS','target_timestamps':'PASS',
        'native_30s_units_integration':'PASS','receipt_causality':'PASS','no_run_boundary_crossing':'PASS',
        'no_missing_nonfinite_or_imputed_required_values':'PASS','source_hashes_before_and_after':'PASS',
        'warmup_failed_and_prior_overlapping_data_used_as_examples':False,
        'future_realizations_or_resolution_metadata_in_features':False,'counts_match_frozen_qualification_audit':True,
        'network_or_Docker_execution':False,'ML_fitting_tuning_scoring':False,'shared':False})
    print('QA PASS:',feature_checks,'features and',target_checks,'targets independently checked; masks',dict(maskcounts))

if __name__=='__main__':
    with patch.object(socket.socket,'connect',side_effect=RuntimeError('Network forbidden in D1P')),patch.object(subprocess,'Popen',side_effect=RuntimeError('Docker/process execution forbidden in D1P')):main()
