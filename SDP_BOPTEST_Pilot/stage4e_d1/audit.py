"""Read-only D1 failure/evidence audit. No network, simulations or dataset export."""
import base64
import hashlib
import json
import math
from collections import Counter
from stage4e_d0.plan import (ROOT,FLAGS,COOL,FAN,HEAT,TEMP,LOW,UP,OCC,SET,
    append_native,coverage,sha,save_new)
from stage4e_d0.runner import verify_frozen
from stage4e_d0.handoff import read_qualified_run
from stage4e.dataset import ContractError,NativeElectric
from core import integrate


def main():
    out=ROOT/'stage4e_d1/evidence';campaign=ROOT/'stage4e_d0/campaign_evidence'
    config=json.loads((ROOT/'stage4e_d0/campaign.json').read_text())
    result=json.loads((campaign/'CAMPAIGN_COMPLETED.json').read_text())
    assert result['classification']=='FAILED' and len(result['runs'])==1
    for manifest,base in [(campaign/'ARTIFACT_MANIFEST.json',campaign),
                          (campaign/'Q01_N/ARTIFACT_MANIFEST.json',campaign/'Q01_N')]:
        for name,digest in json.loads(manifest.read_text())['files'].items():assert sha(base/name)==digest
    d=campaign/'Q01_N'
    records=[json.loads(s) for s in (d/'steps.jsonl').read_text().splitlines()]
    raw=[json.loads(s) for s in (d/'raw_api.jsonl').read_text().splitlines()]
    endpoint_files=sorted(d.glob('endpoint_*.json'))
    endpoints=[json.loads((d/'initialization.json').read_text())['initial_endpoint']]+[json.loads(f.read_text()) for f in endpoint_files]
    assert len(records)==95 and len(endpoint_files)==96 and len(endpoints)==97
    assert all(b['time']-a['time']==300 for a,b in zip(endpoints,endpoints[1:]))
    assert all(isinstance(v,(int,float)) and math.isfinite(v) for e in endpoints for v in e.values())
    advances=[r for r in raw if r['method']=='POST' and '/advance/' in r['url']]
    selects=[r for r in raw if r['method']=='POST' and r['url'].endswith('/select')]
    stops=[r for r in raw if r['method']=='PUT' and '/stop/' in r['url']]
    assert len(advances)==96 and len(selects)==len(stops)==1
    assert all(r['request']==dict.fromkeys(FLAGS,0) for r in advances)
    assert all(r.get('http_status')==200 and 'error' not in r and r['attempt']==1 for r in raw)
    assert base64.b64decode(stops[0]['raw_body_base64']).strip()==b'OK'
    combined={}
    chunks=sorted(d.glob('native_chunk_*.json'));assert len(chunks)==95
    for i,f in enumerate(chunks):
        append_native(combined,json.loads(f.read_text()),config['runs'][0]['start']+i*300,config['runs'][0]['start']+(i+1)*300)
    assert len(combined['time'])==951 and all(b-a==30 for a,b in zip(combined['time'],combined['time'][1:]))
    assert not (d/'native_chunk_0095.json').exists()
    electric=NativeElectric(combined);intervals=[]
    for r in records:
        power=electric.interval(r['start'],r['end'])
        intervals.append({'interval_start':r['start'],'interval_end':r['end'],**power})
    sum_j=math.fsum(r['joules'] for r in intervals)
    separate={n:integrate(combined['time'],combined[n],combined['time'][0],combined['time'][-1]) for n in (COOL,FAN,HEAT)}
    independent_j=separate[COOL]+separate[FAN]
    assert abs(sum_j-independent_j)<=max(.036,1e-8*abs(independent_j))
    cov=coverage(records,combined,config)
    journal=[json.loads(s) for s in (d/'receipt_order.jsonl').read_text().splitlines()]
    previous='0'*64;monotonic=0
    for i,event in enumerate(journal,1):
        digest=event.pop('sha256');assert event['order']==i and event['previous_sha256']==previous and event['monotonic_ns']>=monotonic
        assert hashlib.sha256(json.dumps(event,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()==digest
        previous=digest;monotonic=event['monotonic_ns']
    byorder={r['order']:r for r in journal};cutoffs=[r for r in journal if r['kind']=='origin_cutoff']
    assert len(cutoffs)==96
    ages=[]
    for origin in cutoffs:
        cutoff=origin['order'];ob=origin['observation_received_order'];fc=origin['forecast_received_order']
        assert ob<cutoff and fc<cutoff
        age=(origin['monotonic_ns']-byorder[ob]['monotonic_ns'])/1e9
        assert 0<=age<=30;ages.append(age)
    for r in records:
        assert r['endpoint_received_order']>r['origin_cutoff_order'] and r['readback_verified']
    final=endpoints[-1];forecast=json.loads((d/'forecast_0095.json').read_text())['data']
    assert final['time']==12643200 and forecast['time'][1]==final['time']
    mismatch={'time':final['time'],'benchmark_hour':8.,'forecast_issue_time':forecast['time'][0],
        'actual_cooling_setpoint_k':final[SET],'forecast_upper_k':forecast[UP][1],
        'difference_k':final[SET]-forecast[UP][1],
        'actual_heating_setpoint_k':final['con_oveTSetHea_u'],'forecast_lower_k':forecast[LOW][1],
        'forecast_scheduled_occupancy':forecast[OCC][1],'activation_readbacks':{f:final[f] for f in FLAGS},
        'indoor_c':final[TEMP]-273.15,'following_step_observed':False,
        'interpretation':'Observed exact-boundary native-readback/forecast mismatch. Pre/post-event publication semantics is a hypothesis, not established by another advance.'}
    assert mismatch['difference_k']==6 and all(v==0 for v in mismatch['activation_readbacks'].values())
    eligible_by_horizon={str(h):sum(1 for t in combined['time'][::10] if t-2100>=combined['time'][0] and t+h<=combined['time'][-1]) for h in (300,600,900,1800)}
    assert eligible_by_horizon=={'300':88,'600':87,'900':86,'1800':83}
    try:read_qualified_run(campaign,config['runs'][0])
    except ContractError as exc:builder_denial=str(exc)
    else:raise AssertionError('Quarantined evidence incorrectly admitted')
    counts=Counter(r['method']+' '+r['url'].split('/')[-2] for r in raw)
    audit={'classification':'FAILED_CRITICAL_NATIVE_READBACK_GATE','campaign_decision':'FAILED',
        'fresh_instances':1,'advance_requests':96,'advance_responses_received':96,
        'accepted_intervals':95,'endpoint_observations_received_including_initial':97,
        'accepted_endpoint_observations_including_initial':96,'scored_hours_advanced':8,
        'native_prefix_end':combined['time'][-1],'native_prefix_hours':95/12,
        'canonical_native_samples':951,'native_chunks':95,'missing_failed_interval_native_history':True,
        'api_requests':len(raw),'api_errors':0,'readback_contract_failures':1,'automatic_retries':0,
        'journal_chain_verified':True,'journal_events':len(journal),'origin_cutoffs_verified':96,
        'maximum_observation_age_s':max(ages),'native_only_command_requests_verified':96,
        'coverage_accepted_prefix_only':cov,'mismatch':mismatch,
        'energy_accepted_prefix_only':{'electrical_j':independent_j,'electrical_kwh':independent_j/3600000,
            'sum_interval_j':sum_j,'internal_consistency_pass':True,'channel_integrals_j':separate,
            'official_KPI_audit':'NOT TESTED','full_72h_energy':'NOT AVAILABLE'},
        'usable_approved_forecast_origins':0,'timing_only_quarantined_candidates_by_horizon':eligible_by_horizon,
        'joint_four_horizon_timing_candidates':83,'supervised_rows_constructed_or_exported':False,
        'builder_denial':builder_denial,'pair_matching':'NOT TESTED; intervention arm not started',
        'unused_attempt_ids':result['unused_attempt_ids'],'unused_scored_advance_cap':3456-96,
        'initial_indoor_c':endpoints[0][TEMP]-273.15,'last_accepted_indoor_c':endpoints[-2][TEMP]-273.15,
        'failed_response_indoor_c':final[TEMP]-273.15,
        'stop_ack_verified':True,'D2_execution_authorized':False}
    save_new(out/'QUALIFICATION_AUDIT.json',audit)
    save_new(out/'PREFIX_INTERVAL_ENERGY_DIAGNOSTIC.json',{'classification':'QUARANTINED_DIAGNOSTIC_NOT_TRAINING_DATA',
        'coverage_end':combined['time'][-1],'intervals':intervals})
    save_new(out/'Q01_N_NATIVE_PREFIX_DIAGNOSTIC.json',{'classification':'QUARANTINED_PARTIAL_COPY_ORIGINAL_CHUNKS_UNCHANGED','data':combined})
    ledger=[]
    for r in config['runs']:
        attempted=(campaign/r['attempt_id']/'ATTEMPT_STARTED.json').exists()
        ledger.append({'attempt_id':r['attempt_id'],'status':'CONSUMED_FAILED' if attempted else 'UNUSED_NOT_ATTEMPTED',
            'advance_requests':96 if attempted else 0,'accepted_intervals':95 if attempted else 0,
            'maximum_advances':864,'retry_authorized':False})
    save_new(out/'FINAL_ATTEMPT_BUDGET_AUDIT.json',{'ledger':ledger,'fresh_instances':1,
        'scored_advances':96,'maximum_fresh_instances':4,'maximum_scored_advances':3456,
        'campaign_stopped_on_first_failure':True,'frozen_template_preserved_unchanged':True})
    assert verify_frozen()=='9c033ec022e38479f2f86467d92f3bbd13ee83a1b4b2e987490401ee185d87b8'
    pref=ROOT/'stage4e_runtime_preflight'
    for name,digest in json.loads((pref/'FINAL_ARTIFACT_MANIFEST.json').read_text())['files'].items():assert sha(ROOT/name)==digest
    prior=json.loads((ROOT/'stage4e_d0/PRESERVED_DEPENDENCY_HASHES.json').read_text())
    assert all(sha(ROOT/name)==digest for name,digest in prior.items())
    save_new(out/'PRESERVATION_VERIFICATION.json',{'classification':'PASS','frozen_D0_files_verified':156,
        'earlier_artifacts_unchanged':len(prior),'entire_preflight_delivery_unchanged':True,
        'original_failed_campaign_artifacts_unchanged':True,'D0_protocol_modified':False})
    print(json.dumps(audit,indent=2))


if __name__=='__main__':main()
