"""New D1 v2 collector. CLI defaults to offline verification; never auto-runs."""
import argparse,json,time
from dataclasses import asdict
from pathlib import Path
from stage4e_d0.plan import (ROOT,STEP,FLAGS,POINTS,LOW,UP,OCC,TEMP,COOL,FAN,HEAT,
    sha,save_new,nominal,action_path,Safety,validate_observation,validate_forecast,
    append_native,energy_audit,coverage,campaign_gate)
from stage4e_d0.runner import Journal,OrderedClient,metadata_gate,files_manifest,pair_gate,utc
from stage4e.dataset import ContractError
from stage4e_runtime_preflight.preflight import model_identity,verify_removed,warmup_gate
from .validation import (VERSION,EventTracker,HISTORY_POINTS,REFERENCE,NATIVE,
    endpoint,initial_native,history,command_guard)

HERE=Path(__file__).resolve().parent
CAMPAIGN_ID='SDP_STAGE4E_D1_V2_QUALIFICATION_2.1.0'
def read(path):return json.loads(Path(path).read_text(encoding='utf-8-sig'))

class BoundedClient(OrderedClient):
    def __init__(self,*args):
        super().__init__(*args);self.deploy_attempts=0;self.scenario_attempts=0;self.advance_attempts=0
    def deploy(self):
        if self.deploy_attempts:raise ContractError('No deployment retry')
        self.deploy_attempts+=1;return super().deploy()
    def request(self,method,key,data=None,instance=True):
        if key=='initialize':raise ContractError('No custom/replacement initialization')
        if method=='PUT' and key=='scenario':
            if self.scenario_attempts:raise ContractError('No scenario retry')
            self.scenario_attempts+=1
        if method=='PUT' and key=='step' and data!={'step':300}:raise ContractError('Wrong step')
        if method=='POST' and key=='advance':
            from .validation import command_schema
            command_schema(data)
            if not data[FLAGS[0]] and data!=NATIVE:raise ContractError('Noncanonical native body')
            if self.advance_attempts>=864:raise ContractError('Advance budget exhausted')
            self.advance_attempts+=1
        return super().request(method,key,data,instance)

def verify_frozen():
    manifest=HERE/'FROZEN_MANIFEST.json'
    for name,digest in read(manifest)['files'].items():
        if sha(ROOT/name)!=digest:raise ContractError('New proposal dependency changed: '+name)
    # Deep-check preserved evidence as well as top-level manifest bytes.
    for name in ('stage4e_d0/FROZEN_MANIFEST.json','stage4e_d1/FINAL_ARTIFACT_MANIFEST.json',
                 'stage4e_d1r/FINAL_ARTIFACT_MANIFEST.json','stage4e_d1r_bm01/FINAL_ARTIFACT_MANIFEST.json',
                 'stage4e_runtime_preflight/FINAL_ARTIFACT_MANIFEST.json'):
        for path,digest in read(ROOT/name)['files'].items():
            if sha(ROOT/path)!=digest:raise ContractError('Preserved evidence changed: '+path)
    return sha(manifest)

def authorize(path,digest,config):
    a=read(path)
    if (a.get('status')!='EXPLICITLY_AUTHORIZED' or a.get('campaign_id')!=CAMPAIGN_ID
        or a.get('proposal_sha256')!=digest or a.get('maximum_advances')!=3456
        or a.get('attempt_ids')!=[r['attempt_id'] for r in config['runs']]
        or not a.get('user_authorization_text') or not a.get('authorized_utc')):
        raise ContractError('New manifest-bound four-run authorization required')
    return {'campaign_id':CAMPAIGN_ID,'proposal_sha256':digest,'approval_sha256':sha(path)}

def collect_one(run,config,directory,reference,binding,client_factory=BoundedClient,
                identity_checker=model_identity,cleanup_checker=verify_removed):
    directory=Path(directory);directory.mkdir()
    save_new(directory/'ATTEMPT_STARTED.json',{'run':run,'binding':binding,'started_utc':utc()})
    save_new(directory/'QUARANTINE.json',{'training_release':False,'default':'quarantined pending complete campaign and separate release review'})
    journal=Journal(directory/'receipt_order.jsonl');client=client_factory(config['base'],directory,journal)
    status={'attempt_id':run['attempt_id'],'classification':'FAILED','cleanup':'NOT_CONFIRMED'}
    tracker=EventTracker();records=[];endpoints=[];combined={};attempts=responses=0;testid=None
    try:
        testid=client.deploy();meta=client.discover();metadata_gate(meta,reference)
        identity=identity_checker(testid);save_new(directory/'DEPLOYED_FMU_IDENTITY.json',identity)
        if identity['sha256']!=read(ROOT/'stage4e_d0/RUNTIME_REFERENCE_IDENTITIES.json')['building_fmu_sha256']:
            raise ContractError('Selected FMU identity mismatch')
        result=client.request('PUT','scenario',{'time_period':run['scenario'],'electricity_price':'constant'})
        current=result.get('time_period');current_receipt=client.last_receipt_order
        validate_observation(current,run['start'],meta);initial_native(current)
        observed_at=time.monotonic();origin_status='VERIFIED_REFERENCE'
        client.request('PUT','step',{'step':STEP})
        if float(client.request('GET','step'))!=300:raise ContractError('Step readback failed')
        scenario=client.request('GET','scenario')
        if (scenario.get('time_period')!=run['scenario'] or scenario.get('electricity_price')!='constant'
            or any(scenario.get(k) is not None for k in ('temperature_uncertainty','solar_uncertainty','seed'))):
            raise ContractError('Scenario readback mismatch')
        save_new(directory/'initialization.json',{'run':run,'actual_scenario':scenario,'initial_endpoint':current,
            'initial_receipt_order':current_receipt,'interpretation':'fresh native seven-day warmup'})
        warm=client.request('PUT','results',{'point_names':[COOL,FAN,HEAT,*FLAGS],
            'start_time':run['warmup_start'],'final_time':run['start']})
        save_new(directory/'warmup_native_history.json',warm);warmup_gate(warm,run['start'])
        endpoints.append(current);safety=Safety(config)
        for i in range(run['maximum_advances']):
            t=run['start']+i*300
            if current['time']!=t:raise ContractError('Origin clock mismatch')
            forecast=client.request('PUT','forecast',{'point_names':list(POINTS),'horizon':1800,'interval':STEP})
            fr=client.last_receipt_order;boundary=validate_forecast(forecast,t)
            save_new(directory/f'forecast_{i:04d}.json',{'issued_at_sim':t,'received_order':fr,
                'boundary_kind':'perfect benchmark weather / known schedule, not future indoor truth','data':forecast})
            age=time.monotonic()-observed_at
            at_origin_status=origin_status
            proposal=nominal(run,t,config)
            command,reason=safety.decide(proposal,current,boundary,age)
            command_guard(command,current,boundary,t,age)
            tracker.guard(t,command,current,age,run['maximum_advances']-i)
            if tracker.pending:reason+=';pending_event_scheduled_native_verification'
            proposed_path=action_path(run,t,config);known_path=[dict(p) for p in proposed_path]
            known_path[0]=dict(known_path[0],command=dict(command),source='issued_current_command')
            cutoff=journal.emit('origin_cutoff',sim_time=t,forecast_received_order=fr,
                observation_received_order=current_receipt,proposed=proposal,issued_command=command,
                known_path=known_path,reason=reason,validation_state_at_origin=origin_status,
                observation_age_s=age,pending_event_at_origin=tracker.pending is not None)
            before=current;attempts+=1
            current=client.request('POST','advance',command);responses+=1
            observed_at=time.monotonic();receipt=client.last_receipt_order
            save_new(directory/f'endpoint_{i+1:04d}.json',current)
            validate_observation(current,t+300,meta)
            result=endpoint(t,command,current,{'time':t+300,'issued_at':t,'lower_k':forecast[LOW][1],
                'upper_k':forecast[UP][1],'occupancy':forecast[OCC][1]},
                {'observation':current_receipt,'forecast':fr,'cutoff':cutoff,'response':receipt},age)
            chunk=client.request('PUT','results',{'point_names':list(HISTORY_POINTS),'start_time':t,'final_time':t+300})
            save_new(directory/f'native_chunk_{i:04d}.json',chunk);history(chunk,t,t+300)
            append_native(combined,chunk,t,t+300)
            if tracker.pending:
                e=tracker.pending['event_time']
                # Passive query: event is inside the window, retaining returned duplicates.
                followup=client.request('PUT','results',{'point_names':list(HISTORY_POINTS),'start_time':e-300,'final_time':e+300})
                hr=client.last_receipt_order
                save_new(directory/f'pending_history_{int(e)}.json',followup)
                resolution=tracker.resolve(followup,current,result,receipt,hr)
                save_new(directory/f'event_resolution_{int(e)}.json',resolution)
                journal.emit('pending_event_resolved',event_time=e,resolved_at_sim=t+300,history_received_order=hr)
            tracker.register(current,result,receipt)
            origin_status=result.status
            record={'start':t,'end':t+300,'origin_cutoff_order':cutoff,'forecast_received_order':fr,
                'endpoint_received_order':receipt,'observation_received_order':current_receipt,
                'current_observation':before,'current_boundary':boundary,'proposed_command':proposal['command'],
                'applied_command':command,'reason':reason,'proposed_path':proposed_path,'known_path':known_path,
                'future_safety_veto_unknown_at_origin':True,'effective_setpoint_k':current['con_oveTSetCoo_u'],
                'readback_verified':result.status!='PENDING_EVENT_VERIFICATION',
                'validation_state_at_origin':at_origin_status,
                'setpoint_validation_at_receipt':asdict(result),
                'response_temperature_k':current[TEMP]-before[TEMP]}
            records.append(record);endpoints.append(current);current_receipt=receipt
            with (directory/'steps.jsonl').open('a',encoding='utf-8') as f:f.write(json.dumps(record,allow_nan=False)+'\n')
            journal.emit('step_collected',start=t,end=t+300,validation_at_receipt=result.status)
        if tracker.pending:raise ContractError('Run ended with unresolved event')
        if current['time']!=run['end'] or any(current[f] for f in FLAGS):raise ContractError('Final native release/budget mismatch')
        if len(records)!=864 or len(endpoints)!=865:raise ContractError('Incomplete 72-hour coverage')
        for r in records:
            if not r['observation_received_order']<r['origin_cutoff_order']<r['endpoint_received_order'] or not r['forecast_received_order']<r['origin_cutoff_order']:
                raise ContractError('Causal cutoff mismatch')
        whole=client.request('PUT','results',{'point_names':list(HISTORY_POINTS),'start_time':run['start'],'final_time':run['end']})
        save_new(directory/'whole_native_results.json',whole);history(whole,run['start'],run['end'])
        if combined!={k:whole[k] for k in combined}:raise ContractError('Power chunk/whole history disagreement')
        kpi=client.request('GET','kpi');save_new(directory/'official_kpis.json',kpi)
        save_new(directory/'energy_audit.json',energy_audit(combined,run['start'],run['end'],kpi,config))
        save_new(directory/'endpoints.json',endpoints);save_new(directory/'native_results.json',combined)
        save_new(directory/'event_resolutions.json',tracker.resolutions)
        status.update(classification='PASS_VALID_RAW',coverage=coverage(records,combined,config),
            advances=len(records),endpoints=len(endpoints),native_samples=len(combined['time']),
            pending_events_resolved=len(tracker.resolutions),unresolved_events=0)
    except Exception as exc:
        status.update(classification='FAILED',error=f'{type(exc).__name__}: {exc}',advances_collected=len(records))
        journal.emit('run_failed',error=status['error'],quarantine=True,no_retry=True)
    finally:
        try:
            client.stop()
            if not testid:raise ContractError('Selected identity not available for cleanup')
            status['cleanup_observations']=cleanup_checker(testid);status['cleanup']='STOP_ACK_VERIFIED'
        except Exception as exc:status.update(classification='FAILED',cleanup='STOP_UNCONFIRMED',cleanup_error=str(exc))
        status.update(advance_requests_attempted=attempts,advance_responses_received=responses,
            unresolved_events=int(tracker.pending is not None),training_release=False)
        journal.emit('attempt_closed',classification=status['classification'],unresolved_events=status['unresolved_events'])
        save_new(directory/'RUN_COMPLETED.json',status)
        save_new(directory/'ARTIFACT_MANIFEST.json',{'files':files_manifest(directory)})
    return status

def execute(approval):
    digest=verify_frozen();config=read(HERE/'campaign.json');binding=authorize(approval,digest,config)
    from .runtime import verify_runtime
    runtime=verify_runtime() # Read only, after authorization; no new preflight simulation.
    campaign=HERE/'campaign_evidence';campaign.mkdir()
    save_new(campaign/'RUNTIME_IDENTITY.json',runtime)
    save_new(campaign/'CAMPAIGN_STARTED.json',{'binding':binding,'started_utc':utc(),'attempt_ids':[r['attempt_id'] for r in config['runs']]})
    reference=read(ROOT/'evidence/local_matched_AB/A/runtime_metadata.json');summaries=[];error=None
    for r in config['runs']:
        summary=collect_one(r,config,campaign/r['attempt_id'],reference,binding);summaries.append(summary)
        if summary['classification']!='PASS_VALID_RAW':break
        if r['mode']=='scheduled_variation':
            try:pair_gate(campaign/config['runs'][len(summaries)-2]['attempt_id'],campaign/r['attempt_id'],r)
            except Exception as exc:error=str(exc);break
    result={'classification':'FAILED' if error else campaign_gate(summaries,config),'campaign_id':CAMPAIGN_ID,
        'runs':summaries,'pair_error':error,'binding':binding,'training_release':False,'no_retries':True,
        'unused_attempt_ids':[r['attempt_id'] for r in config['runs'][len(summaries):]]}
    save_new(campaign/'CAMPAIGN_COMPLETED.json',result)
    save_new(campaign/'ARTIFACT_MANIFEST.json',{'files':files_manifest(campaign)})
    return result

def main():
    p=argparse.ArgumentParser();p.add_argument('--execute',action='store_true');p.add_argument('--authorization',type=Path)
    args=p.parse_args()
    if not args.execute:print(json.dumps({'status':'OFFLINE_VERIFY_ONLY','proposal_sha256':verify_frozen(),'runtime_execution':False}));return
    if not args.authorization:p.error('New explicit manifest-bound authorization required')
    print(json.dumps(execute(args.authorization),indent=2))

if __name__=='__main__':main()
