"""Independent raw-response checks before continuing to another authorized pair."""
import json,hashlib,math
from pathlib import Path
from .export import decode_truth,interval
from stage4e_d2i_1.common import read,require,sha,ROOT
from stage4e_d0.plan import FLAGS,COOL,FAN,HEAT,Safety,nominal
from stage4e_d1_v2.validation import command_guard,history

def audit_run(d,run,manifest):
    status=read(d/'RUN_COMPLETED.json');require(status['classification']=='PASS_VALID_RAW' and status['cleanup']=='STOP_ACK_AND_REMOVAL_VERIFIED','Raw run failed or cleanup missing')
    require(status['deploy_attempts']==status['initialization_attempts']==1 and status['advance_requests_attempted']==status['advance_responses_received']==864,'Attempt counts')
    require(status['unresolved_events']==0,'Unresolved event')
    for n,h in read(d/'ARTIFACT_MANIFEST.json')['files'].items():require(sha(d/n)==h,'Raw file hash')
    ends,forecasts,native,requests=decode_truth(d,run)
    require(sorted(ends)==list(range(run['start'],run['end']+1,300)),'Endpoint grid')
    require(list(ends.values())==read(d/'endpoints.json'),'Raw/saved endpoint agreement')
    history(native,run['start'],run['end'])
    require(all(native[k]==v for k,v in read(d/'native_results.json').items()),'Whole/chunk agreement')
    required=manifest['reporting']['core_forecasts']+manifest['reporting']['optional_forecasts']
    schema=read(ROOT/'stage4e_d2i_1/schema_manifest.json');metadata=read(d/'runtime_metadata.json')
    receipt=read(d/'METADATA_RECEIPT_VALIDATION.json');require(receipt['sha256']==sha(d/'runtime_metadata.json') and receipt['collector_receipt_writes']==0,'Metadata receipt')
    for key,s in schema['raw_observations'].items():
        actual=(metadata['measurements'] if key in metadata['measurements'] else metadata['inputs'])[key]
        require(actual['Unit']==s['unit'] and all(type(e[key]) in (int,float) and math.isfinite(e[key]) for e in ends.values()),'Raw unit/completeness')
    for t,f in forecasts.items():
        require(f['time']==list(range(t,t+1801,300)) and set(f)=={'time',*required},'Forecast profile/time')
        require(all(len(f[p])==7 and all(type(v) in (int,float) and math.isfinite(v) for v in f[p]) for p in required),'Forecast completeness')
    warm=read(d/'NATIVE_WARMUP_HISTORY.json');support=set(warm['time'])
    require(all(t in support for t in range(run['warmup_start'],run['start']+1,30)),'Warmup support')
    require(all(v==0 for flag in FLAGS for v in warm[flag]),'Warmup override')
    journal=[json.loads(s) for s in (d/'receipt_order.jsonl').read_text().splitlines()];previous='0'*64;byorder={}
    for i,event in enumerate(journal,1):
        body=dict(event);h=body.pop('sha256')
        require(event['order']==i and event['previous_sha256']==previous and hashlib.sha256(json.dumps(body,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()==h,'Receipt hash chain')
        previous=h;byorder[i]=event
    steps=[json.loads(s) for s in (d/'steps.jsonl').read_text().splitlines()];safety=Safety(manifest['policy'])
    require(len(steps)==864,'Step count')
    for step in steps:
        t=step['start'];require(step['observation_received_order']<step['forecast_received_order']<step['origin_cutoff_order']<step['endpoint_received_order'],'Causal receipt order')
        age=byorder[step['origin_cutoff_order']]['observation_age_s']
        cmd,reason=safety.decide(nominal(run,t,manifest['policy']),step['current_observation'],step['current_boundary'],age)
        require(cmd==step['applied_command'] and reason==step['reason'],'Safety decision replay')
        command_guard(cmd,step['current_observation'],step['current_boundary'],t,age)
        require(all(ends[t+300][k]==cmd[k] for k in FLAGS),'Activation readback')
        if cmd[FLAGS[0]]:require(abs(ends[t+300]['con_oveTSetCoo_u']-cmd['con_oveTSetCoo_u'])<=manifest['policy']['readback_tolerance_k'],'Active setpoint readback')
    electrical=interval(native,run['start'],run['end'],(COOL,FAN))*(run['end']-run['start'])
    saved=read(d/'energy_audit.json');require(abs(electrical-saved['electrical_j'])<=saved['internal_tolerance_j'],'Independent electrical energy')
    require(abs(electrical-saved['official_electric_reconstructed_j'])<=saved['official_tolerance_j'],'Official electrical reconciliation')
    return {'run_id':run['run_id'],'classification':'PASS_INDEPENDENT_RAW_AUDIT','advances':864,'raw_observations':len(ends),
        'native_samples':len(native['time']),'warmup_samples':len(warm['time']),'raw_requests_verified':requests,'signal_channels':53,
        'electricity_kWh':electrical/3600000,'independent_energy_difference_J':electrical-saved['electrical_j'],
        'gas_J_separate':interval(native,run['start'],run['end'],(HEAT,))*(run['end']-run['start']),
        'safety_readback_violations':0,'coverage':status['coverage'],'cleanup':status['cleanup']}
