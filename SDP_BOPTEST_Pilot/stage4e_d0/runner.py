"""Executable future collector. Default entry point is offline verification.

Real execution requires both explicit manifest-bound approval and separately
qualified runtime prerequisites. No deployment occurs at import or verification.
"""
from __future__ import annotations
import argparse
import json
import time
from datetime import datetime,timezone
from pathlib import Path
from compat_v1.transport import Client
from stage4e.dataset import ContractError
from .plan import (ROOT,HERE,STEP,FLAGS,POINTS,HEAT,COOL,FAN,TEMP,LOW,UP,OCC,
    sha,save_new,nominal,action_path,Safety,validate_observation,validate_readback,
    validate_forecast,append_native,energy_audit,coverage,campaign_gate)


def utc():return datetime.now(timezone.utc).isoformat()


class Journal:
    def __init__(self,path):
        self.path=Path(path);self.order=0;self.previous='0'*64
        self.path.open('x',encoding='utf-8').close()
    def emit(self,kind,**fields):
        import hashlib
        self.order+=1
        event=dict(order=self.order,utc=utc(),monotonic_ns=time.monotonic_ns(),
                   kind=kind,previous_sha256=self.previous,**fields)
        encoded=json.dumps(event,sort_keys=True,separators=(',',':'),allow_nan=False)
        event['sha256']=hashlib.sha256(encoded.encode()).hexdigest()
        with self.path.open('a',encoding='utf-8') as f:
            f.write(json.dumps(event,allow_nan=False)+'\n');f.flush()
        self.previous=event['sha256']
        return event['order']


class OrderedClient(Client):
    def __init__(self,base,directory,journal):
        super().__init__(base,directory,timeout=120,read_retries=0)
        self.journal=journal;self.last_receipt_order=None
    def request(self,method,endpoint,data=None,instance=True):
        self.journal.emit('api_request',method=method,endpoint=endpoint,request=data,
                          expected_raw_sequence=self.sequence+1)
        try:
            result=super().request(method,endpoint,data,instance)
        except Exception as exc:
            self.journal.emit('api_error',raw_sequence=self.sequence,error=f'{type(exc).__name__}: {exc}')
            raise
        self.last_receipt_order=self.journal.emit('api_received',raw_sequence=self.sequence,
            method=method,endpoint=endpoint)
        return result


def verify_frozen():
    manifest=HERE/'FROZEN_MANIFEST.json'
    data=json.loads(manifest.read_text())
    for name,digest in data['files'].items():
        if sha(ROOT/name)!=digest:raise ContractError('Frozen dependency changed: '+name)
    return sha(manifest)


def authorize(approval,preflight,digest,config):
    """Read-only gate, BEFORE campaign/attempt creation or client construction."""
    a=json.loads(Path(approval).read_text())
    p=json.loads(Path(preflight).read_text())
    ids=[r['attempt_id'] for r in config['runs']]
    if (a.get('status')!='EXPLICITLY_AUTHORIZED' or a.get('proposal_sha256')!=digest
        or a.get('attempt_ids')!=ids or a.get('maximum_advances')!=3456
        or not a.get('user_authorization_text') or not a.get('authorized_utc')):
        raise ContractError('Explicit frozen-campaign user authorization missing/mismatched')
    if (p.get('status')!='RUNTIME_QUALIFIED' or p.get('proposal_sha256')!=digest
            or p.get('evidence_classification')!='DEVELOPMENT_PREFLIGHT'):
        raise ContractError('Separately authorized runtime preflight is not qualified')
    expected={r['scenario']:(r['start'],r['warmup_seconds']) for r in config['runs']}
    qualified={r['scenario']:(r['start'],r['warmup_seconds']) for r in p.get('windows',[])}
    if qualified!=expected or len(p.get('windows',[]))!=len(expected):raise ContractError('Preflight windows do not match frozen campaign')
    checks=['step_300_verified','native_history_verified','forecast_order_verified',
            'pulse_schedule_forecasts_verified','fresh_native_initialization_verified',
            'localhost_api_version_verified','units_and_limits_verified']
    if not all(p.get(k) is True for k in checks) or not p.get('proof_files'):
        raise ContractError('Preflight evidence incomplete')
    proof_root=Path(preflight).resolve().parent
    for path,d in p['proof_files'].items():
        proof=(proof_root/path).resolve()
        if not proof.is_relative_to(proof_root):raise ContractError('Preflight proof leaves its development evidence directory')
        if sha(proof)!=d:raise ContractError('Preflight proof hash mismatch')
    reference=json.loads((HERE/'RUNTIME_REFERENCE_IDENTITIES.json').read_text())
    if p.get('building_fmu_sha256')!=reference['building_fmu_sha256'] or p.get('container_image_ids')!=reference['container_image_ids']:
        raise ContractError('Preflight runtime identities differ from the preserved pinned reference')
    return {'approval_sha256':sha(approval),'preflight_sha256':sha(preflight),'proposal_sha256':digest}


def metadata_gate(meta,reference):
    if meta.get('version')!={'version':'0.9.0'} or meta.get('name')!={'name':'bestest_air'}:
        raise ContractError('Wrong runtime version/building')
    for group in ('measurements','inputs'):
        if set(meta[group])!=set(reference[group]):raise ContractError('Runtime signal catalog mismatch')
        for name,entry in reference[group].items():
            if meta[group][name].get('Unit')!=entry.get('Unit'):raise ContractError('Runtime unit mismatch: '+name)
    for name in POINTS:
        if meta['forecast_points'].get(name,{}).get('Unit')!=reference['forecast_points'][name]['Unit']:
            raise ContractError('Forecast unit/name mismatch')
    for name in reference['inputs']:
        for bound in ('Minimum','Maximum'):
            if meta['inputs'][name].get(bound)!=reference['inputs'][name].get(bound):
                raise ContractError('Actuator limits changed')


def files_manifest(directory):
    return {f.relative_to(directory).as_posix():sha(f) for f in directory.rglob('*')
            if f.is_file() and f.name!='ARTIFACT_MANIFEST.json'}


def collect_one(run,config,directory,reference,binding,client_factory=OrderedClient):
    """One consumed attempt, one deployment, no retry/resume. Test with fake factory."""
    directory=Path(directory)
    directory.mkdir() # Existing evidence/attempt is NEVER overwritten or resumed.
    save_new(directory/'ATTEMPT_STARTED.json',dict(run=run,started_utc=utc(),binding=binding))
    save_new(directory/'QUARANTINE.json',{'training_release':False,'default':'quarantined until complete campaign audit and separate release decision'})
    journal=Journal(directory/'receipt_order.jsonl')
    client=client_factory(config['base'],directory,journal)
    status={'attempt_id':run['attempt_id'],'classification':'FAILED','cleanup':'NOT_CONFIRMED'}
    endpoints=[];records=[];combined={};stop_ok=False;advance_attempts=0;advance_responses=0
    try:
        client.deploy()
        meta=client.discover();metadata_gate(meta,reference)
        result=client.request('PUT','scenario',{'time_period':run['scenario'],'electricity_price':'constant'})
        current_receipt=client.last_receipt_order
        current=result.get('time_period')
        validate_observation(current,run['start'],meta)
        current=dict(current,time=run['start'])
        if any(current[f] for f in FLAGS):raise ContractError('Warmup did not end in native override state')
        observed_at=time.monotonic()
        client.request('PUT','step',{'step':STEP})
        if float(client.request('GET','step'))!=STEP:raise ContractError('Step readback failed')
        scenario=client.request('GET','scenario')
        if scenario.get('time_period')!=run['scenario'] or scenario.get('electricity_price')!='constant':
            raise ContractError('Scenario readback mismatch')
        if any(scenario.get(k) is not None for k in ('temperature_uncertainty','solar_uncertainty','seed')):
            raise ContractError('Unexpected uncertainty/seed configuration')
        save_new(directory/'initialization.json',dict(run=run,actual_scenario=scenario,
            initial_endpoint=current,initial_receipt_order=current_receipt,
            interpretation='source/native seven-day warmup; actual initial vector recorded, not prescribed'))
        endpoints.append(current)
        safety=Safety(config)
        journal.emit('nominal_plan_known',sim_time=run['start'],plan_hash=binding['proposal_sha256'])
        for i in range(run['maximum_advances']):
            t=run['start']+i*STEP
            if current['time']!=t:raise ContractError('Endpoint clock mismatch')
            forecast=client.request('PUT','forecast',{'point_names':list(POINTS),'horizon':1800,'interval':STEP})
            forecast_receipt=client.last_receipt_order
            boundary=validate_forecast(forecast,t)
            save_new(directory/f'forecast_{i:04d}.json',{'issued_at_sim':t,'received_order':forecast_receipt,
                'boundary_kind':'perfect benchmark weather / known schedule, not future indoor truth','data':forecast})
            proposal=nominal(run,t,config)
            command,reason=safety.decide(proposal,current,boundary,time.monotonic()-observed_at)
            proposed_path=action_path(run,t,config)
            known_path=[dict(p) for p in proposed_path]
            known_path[0]=dict(known_path[0],command=dict(command),source='issued_current_command')
            cutoff=journal.emit('origin_cutoff',sim_time=t,forecast_received_order=forecast_receipt,
                observation_received_order=current_receipt,
                proposed=proposal,issued_command=command,known_path=known_path,reason=reason)
            before=current
            # No retries, no catch-up, no additional advance to fix a rejection.
            advance_attempts+=1
            current=client.request('POST','advance',command)
            advance_responses+=1
            observed_at=time.monotonic();receipt=client.last_receipt_order
            save_new(directory/f'endpoint_{i+1:04d}.json',current)
            validate_observation(current,t+STEP,meta)
            current=dict(current,time=t+STEP)
            validate_readback(command,current,forecast[UP][1])
            chunk=client.request('PUT','results',{'point_names':[COOL,FAN,HEAT],
                'start_time':t,'final_time':t+STEP})
            save_new(directory/f'native_chunk_{i:04d}.json',chunk)
            append_native(combined,chunk,t,t+STEP)
            record={'start':t,'end':t+STEP,'origin_cutoff_order':cutoff,
                'forecast_received_order':forecast_receipt,'endpoint_received_order':receipt,
                'observation_received_order':current_receipt,
                'current_observation':before,'current_boundary':boundary,'proposed_command':proposal['command'],
                'applied_command':command,'reason':reason,'proposed_path':proposed_path,
                'known_path':known_path,'future_safety_veto_unknown_at_origin':True,
                'effective_setpoint_k':current['con_oveTSetCoo_u'],
                'readback_verified':True,'response_temperature_k':current[TEMP]-before[TEMP]}
            journal.emit('step_accepted',start=t,end=t+STEP,origin_cutoff_order=cutoff)
            records.append(record);endpoints.append(current)
            current_receipt=receipt
            with (directory/'steps.jsonl').open('a',encoding='utf-8') as f:
                f.write(json.dumps(record,allow_nan=False)+'\n');f.flush()
        if current['time']!=run['end'] or any(current[f] for f in FLAGS):
            raise ContractError('Final budget/native release failed')
        if len(endpoints)!=865 or len(records)!=864:
            # Test-only shortened fixtures may exercise failures, but cannot
            # qualify as a complete production run.
            raise ContractError('Frozen 865-endpoint / 864-advance coverage failed')
        for record in records:
            cutoff=record['origin_cutoff_order']
            if not (record['observation_received_order']<cutoff and
                    record['forecast_received_order']<cutoff<record['endpoint_received_order']):
                raise ContractError('Knowledge receipt cutoff invalid')
        # Whole-history query is independent of chunk stitching; includes reported
        # gas channel solely to reconcile the official combined-carrier energy KPI.
        whole=client.request('PUT','results',{'point_names':[COOL,FAN,HEAT],
            'start_time':run['start'],'final_time':run['end']})
        save_new(directory/'whole_native_results.json',whole)
        if combined!=whole:raise ContractError('Chunk stitching differs from whole native history')
        kpi=client.request('GET','kpi');save_new(directory/'official_kpis.json',kpi)
        audit=energy_audit(combined,run['start'],run['end'],kpi,config)
        save_new(directory/'energy_audit.json',audit)
        save_new(directory/'endpoints.json',endpoints)
        save_new(directory/'native_results.json',combined)
        status.update(classification='PASS_VALID_RAW',coverage=coverage(records,combined,config),
                      advances=len(records),endpoints=len(endpoints),native_samples=len(combined['time']))
    except Exception as exc:
        status.update(classification='FAILED',error=f'{type(exc).__name__}: {exc}',advances_accepted=len(records))
        journal.emit('run_failed',error=status['error'],release='stop without any extra advance; release-by-stop not an applied native command')
    finally:
        try:
            client.stop();stop_ok=True
            status['cleanup']='STOP_ACK_VERIFIED'
        except Exception as exc:
            status.update(cleanup='STOP_UNCONFIRMED',cleanup_error=str(exc),classification='FAILED')
        journal.emit('attempt_closed',classification=status['classification'],stop_ack=stop_ok)
        status.update(advance_requests_attempted=advance_attempts,advance_responses_received=advance_responses)
        save_new(directory/'RUN_COMPLETED.json',status)
        save_new(directory/'ARTIFACT_MANIFEST.json',{'files':files_manifest(directory)})
    return status


def pair_gate(native_dir,variation_dir,run):
    a=json.loads((native_dir/'endpoints.json').read_text())
    b=json.loads((variation_dir/'endpoints.json').read_text())
    first_pulse=run['start']+32400
    for x,y in zip(a,b):
        if x['time']>first_pulse:break
        if x.keys()!=y.keys() or any(abs(x[k]-y[k])>1e-7 for k in x):
            raise ContractError('Paired initialization/pretreatment differs')
    return True


def execute(approval,preflight,client_factory=OrderedClient):
    digest=verify_frozen()
    config=json.loads((HERE/'campaign.json').read_text())
    binding=authorize(approval,preflight,digest,config)
    # All future evidence paths are fixed by the frozen plan; no --output retry loophole.
    campaign=HERE/'campaign_evidence'
    campaign.mkdir()
    save_new(campaign/'CAMPAIGN_STARTED.json',dict(binding=binding,started_utc=utc(),attempt_ids=[r['attempt_id'] for r in config['runs']]))
    reference=json.loads((ROOT/'evidence/local_matched_AB/A/runtime_metadata.json').read_text())
    summaries=[];error=None
    for r in config['runs']:
        summary=collect_one(r,config,campaign/r['attempt_id'],reference,binding,client_factory)
        summaries.append(summary)
        if summary['classification']!='PASS_VALID_RAW':break
        if r['mode']=='scheduled_variation':
            try:
                n=config['runs'][len(summaries)-2]
                pair_gate(campaign/n['attempt_id'],campaign/r['attempt_id'],r)
            except Exception as exc:
                error=str(exc);break
    classification='FAILED' if error else campaign_gate(summaries,config)
    result={'classification':classification,'runs':summaries,'pair_error':error,
        'binding':binding,'training_release':False,'no_retries':True,
        'unused_attempt_ids':[r['attempt_id'] for r in config['runs'][len(summaries):]]}
    save_new(campaign/'CAMPAIGN_COMPLETED.json',result)
    save_new(campaign/'ARTIFACT_MANIFEST.json',{'files':files_manifest(campaign)})
    return result


def main():
    parser=argparse.ArgumentParser(description='D0 offline verification by default; future execution is gated')
    parser.add_argument('--execute',action='store_true')
    parser.add_argument('--authorization',type=Path)
    parser.add_argument('--preflight',type=Path)
    args=parser.parse_args()
    if not args.execute:
        print(json.dumps({'status':'OFFLINE_FROZEN_VERIFY_ONLY','proposal_sha256':verify_frozen(),
                          'runtime_execution':False}));return
    if not args.authorization or not args.preflight:
        parser.error('--execute requires explicit authorization AND qualified separate preflight proof')
    print(json.dumps(execute(args.authorization,args.preflight),indent=2))


if __name__=='__main__':main()
