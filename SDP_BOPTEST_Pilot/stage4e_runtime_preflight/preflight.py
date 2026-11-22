"""Exactly two possible fresh instances, at most one {} advance per instance.

No qualification campaign entry point is imported or called. No thermostat
command, retry, training release or Docker lifecycle change is performed here.
"""
import argparse
import hashlib
import json
import math
import re
import subprocess
import time
from pathlib import Path
from stage4e_d0.plan import (ROOT,STEP,FLAGS,POINTS,LOW,UP,OCC,COOL,FAN,HEAT,TEMP,
    sha,save_new,validate_forecast,validate_observation,append_native)
from stage4e_d0.runner import OrderedClient,Journal,metadata_gate,verify_frozen,utc
from stage4e.dataset import ContractError,NativeElectric

HERE=Path(__file__).resolve().parent
EVIDENCE=HERE/'evidence'
PRIMARY='9c033ec022e38479f2f86467d92f3bbd13ee83a1b4b2e987490401ee185d87b8'
DOCKER='docker'
WORKER='sdp-boptest-v090-worker-1'
PYTHON='/miniconda/envs/pyfmi3/bin/python'


def read_json(path):return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def docker_read(*args):
    result=subprocess.run([DOCKER,*args],capture_output=True,text=True,timeout=30)
    if result.returncode:raise ContractError('Read-only Docker verification failed: '+result.stderr[-1000:])
    return result.stdout


def model_identity(testid):
    if not re.fullmatch(r'[0-9a-f-]{36}',testid):raise ContractError('Invalid test identifier')
    # Read only the just-created instance; never enumerate unrelated model states.
    code="import hashlib,json,pathlib; p=pathlib.Path('/simulate')/"+repr(testid)+"/'model.fmu'; print(json.dumps({'path':str(p),'sha256':hashlib.sha256(p.read_bytes()).hexdigest()}))"
    return json.loads(docker_read('exec',WORKER,PYTHON,'-c',code))


def verify_removed(testid):
    code="import pathlib; print(int((pathlib.Path('/simulate')/"+repr(testid)+").exists()))"
    observations=[]
    for _ in range(6):
        exists=docker_read('exec',WORKER,PYTHON,'-c',code).strip()=='1'
        observations.append({'utc':utc(),'instance_directory_exists':exists})
        if not exists:return observations
        time.sleep(1) # Read-only cleanup wait; never another advance or stop retry.
    raise ContractError('Instance directory remains after stop ACK')


class NativeOnlyClient(OrderedClient):
    def __init__(self,*args):
        super().__init__(*args);self.advance_attempts=0;self.deploy_attempts=0
    def deploy(self):
        if self.deploy_attempts:raise ContractError('Fresh deployment retry prohibited')
        self.deploy_attempts+=1
        return super().deploy()
    def request(self,method,endpoint,data=None,instance=True):
        if method=='POST' and endpoint=='advance':
            if data!={}:raise ContractError('No external thermostat/control inputs permitted')
            if self.advance_attempts:raise ContractError('Second preflight advance prohibited')
            self.advance_attempts+=1
        if endpoint=='initialize':raise ContractError('No extra/replacement initialization permitted')
        return super().request(method,endpoint,data,instance)


def long_forecast_gate(data,run,config):
    ts=list(range(run['start'],run['end']+1,STEP))
    if data.get('time')!=ts:raise ContractError('72-hour passive forecast coverage mismatch')
    for name in POINTS:
        if len(data.get(name,[]))!=len(ts) or any(not isinstance(v,(int,float)) or not math.isfinite(v) for v in data[name]):
            raise ContractError('Incomplete/nonfinite forecast channel '+name)
    bytime={t:i for i,t in enumerate(ts)};checks=[]
    for day in range(3):
        for block in config['pulse_blocks_local_seconds']:
            times=range(run['start']+day*86400+block['start'],run['start']+day*86400+block['end']+1,STEP)
            for t in times:
                i=bytime[t]
                if (abs(data[LOW][i]-294.15)>1e-5 or abs(data[UP][i]-297.15)>1e-5
                    or data[OCC][i]!=2):raise ContractError('Pulse-time schedule conflicts with frozen D0')
            checks.append({'day_offset':day,'activation_time':times.start,
                'release_time':times.stop-STEP,'lower_k':294.15,'upper_k':297.15,'scheduled_occupants':2})
    return checks


def warmup_gate(data,start):
    times=data.get('time',[])
    if not times or times[0]!=start-604800 or times[-1]!=start:
        raise ContractError('Native warmup history does not establish exact seven-day coverage')
    if any(b<a or b-a>30 for a,b in zip(times,times[1:])):raise ContractError('Warmup native-history gap/order')
    for name in [COOL,FAN,HEAT,*FLAGS]:
        if len(data.get(name,[]))!=len(times) or any(not math.isfinite(v) for v in data[name]):
            raise ContractError('Warmup missing/nonfinite signal '+name)
    if any(v!=0 for name in FLAGS for v in data[name]):raise ContractError('Warmup external override activation detected')
    return {'start':times[0],'end':times[-1],'duration_s':times[-1]-times[0],
        'samples':len(times),'all_external_flags_zero':True,
        'classification':'INITIALIZATION_DIAGNOSTIC_NOT_SUPERVISED_DATA'}


def one_window(run,attempt,config,identity_checker=model_identity,cleanup_checker=verify_removed,client_factory=NativeOnlyClient):
    d=EVIDENCE/attempt;d.mkdir()
    save_new(d/'ATTEMPT_STARTED.json',{'attempt_id':attempt,'scenario':run['scenario'],
        'started_utc':utc(),'maximum_fresh_instances':1,'maximum_native_advances':1,
        'qualification_attempt_consumed':False})
    j=Journal(d/'receipt_order.jsonl');c=client_factory(config['base'],d,j)
    outcome={'attempt_id':attempt,'scenario':run['scenario'],'classification':'FAILED',
        'advance_responses_received':0,'cleanup':'NOT_CONFIRMED'}
    testid=None
    try:
        testid=c.deploy();outcome['testid']=testid
        meta=c.discover()
        reference=read_json(ROOT/'evidence/local_matched_AB/A/runtime_metadata.json')
        metadata_gate(meta,reference)
        identity=identity_checker(testid);save_new(d/'DEPLOYED_FMU_IDENTITY.json',identity)
        reference_identity=read_json(ROOT/'stage4e_d0/RUNTIME_REFERENCE_IDENTITIES.json')
        if identity['sha256']!=reference_identity['building_fmu_sha256']:
            raise ContractError('Actual deployed FMU differs from frozen model')
        init=c.request('PUT','scenario',{'time_period':run['scenario'],'electricity_price':'constant'})
        initial=init.get('time_period');validate_observation(initial,run['start'],meta)
        if any(initial[f] for f in FLAGS):raise ContractError('Initial external overrides are active')
        init_order=c.last_receipt_order;save_new(d/'INITIAL_ENDPOINT.json',initial)
        scenario=c.request('GET','scenario')
        if scenario.get('time_period')!=run['scenario'] or scenario.get('electricity_price')!='constant':
            raise ContractError('Scenario readback mismatch')
        if any(scenario.get(k) is not None for k in ('temperature_uncertainty','solar_uncertainty','seed')):
            raise ContractError('Unexpected uncertainty configuration')
        save_new(d/'ACTUAL_SCENARIO.json',scenario)
        c.request('PUT','step',{'step':300})
        if float(c.request('GET','step'))!=300:raise ContractError('300-second timestep rejected')
        warm=c.request('PUT','results',{'point_names':[COOL,FAN,HEAT,*FLAGS],
            'start_time':run['start']-604800,'final_time':run['start']})
        save_new(d/'WARMUP_NATIVE_HISTORY.json',warm)
        warm_check=warmup_gate(warm,run['start'])
        long=c.request('PUT','forecast',{'point_names':list(POINTS),'horizon':259200,'interval':300})
        save_new(d/'AS_ISSUED_72H_BOUNDARY_FORECAST.json',{'issued_at_sim':run['start'],
            'receipt_order':c.last_receipt_order,'received_utc':utc(),'data':long,
            'kind':'perfect benchmark boundaries / known schedules; not future zone measurements'})
        pulses=long_forecast_gate(long,run,config)
        short=c.request('PUT','forecast',{'point_names':list(POINTS),'horizon':1800,'interval':300})
        boundary=validate_forecast(short,run['start']);forecast_order=c.last_receipt_order
        save_new(d/'AS_ISSUED_CURRENT_FORECAST.json',{'issued_at_sim':run['start'],
            'receipt_order':forecast_order,'data':short})
        if abs(initial['con_oveTSetCoo_u']-boundary[UP])>1e-5 or abs(initial['con_oveTSetHea_u']-boundary[LOW])>1e-5:
            raise ContractError('Initial native thermostat readbacks differ from current schedules')
        cutoff=j.emit('native_origin_cutoff',sim_time=run['start'],observation_receipt_order=init_order,
            forecast_receipt_order=forecast_order,command={},no_external_inputs=True)
        if not init_order<cutoff or not forecast_order<cutoff:raise ContractError('Receipt ordering invalid')
        endpoint=c.request('POST','advance',{}) # THE ONLY scored advance in this attempt.
        outcome['advance_responses_received']=1
        response_order=c.last_receipt_order
        save_new(d/'FIVE_MINUTE_ENDPOINT.json',endpoint)
        validate_observation(endpoint,run['start']+300,meta)
        if any(endpoint[f] for f in FLAGS):raise ContractError('External override active after native advance')
        native=c.request('PUT','results',{'point_names':[COOL,FAN,HEAT,*FLAGS],
            'start_time':run['start'],'final_time':run['start']+300})
        save_new(d/'SCORED_NATIVE_HISTORY.json',native)
        assembled={};append_native(assembled,native,run['start'],run['start']+300)
        for f in FLAGS:
            if len(native.get(f,[]))!=len(native['time']) or any(v!=0 for v in native[f]):
                raise ContractError('Scored native override history invalid')
        energy=NativeElectric(native).interval(run['start'],run['start']+300)
        after=c.request('PUT','forecast',{'point_names':list(POINTS),'horizon':1800,'interval':300})
        after_boundary=validate_forecast(after,run['start']+300)
        save_new(d/'AS_ISSUED_POST_ADVANCE_FORECAST.json',{'issued_at_sim':run['start']+300,
            'receipt_order':c.last_receipt_order,'data':after})
        if abs(endpoint['con_oveTSetCoo_u']-after_boundary[UP])>1e-5 or abs(endpoint['con_oveTSetHea_u']-after_boundary[LOW])>1e-5:
            raise ContractError('Native thermostat readbacks differ from endpoint schedules')
        if not response_order>cutoff:raise ContractError('Response did not follow origin cutoff')
        outcome.update(classification='PASS',initial_time=initial['time'],end_time=endpoint['time'],
            endpoint_observations=2,measurement_channels=len(meta['measurements']),input_channels=len(meta['inputs']),
            forecast_points_listed=len(meta['forecast_points']),forecast_points_value_verified=list(POINTS),
            warmup=warm_check,scored_native_samples=len(native['time']),scored_energy=energy,
            pulse_schedule_checks=pulses,forecast_72h_samples=len(long['time']),
            initial_indoor_c=initial[TEMP]-273.15,final_indoor_c=endpoint[TEMP]-273.15,
            current_boundary=boundary,end_boundary=after_boundary,receipt_order_verified=True,
            unit_and_limit_match=True,deployed_fmu_verified=True,external_commands_sent=False,
            thermostat_intervention_tested=False,full_72h_dataset_tested=False)
    except Exception as exc:
        outcome.update(classification='FAILED',error=f'{type(exc).__name__}: {exc}')
        j.emit('preflight_failed',error=outcome['error'],retry_permitted=False)
    finally:
        try:
            c.stop()
            if not testid:raise ContractError('No instance identity; no cleanup ACK can be asserted')
            outcome['cleanup']='STOP_ACK_VERIFIED'
            outcome['cleanup_path_observations']=cleanup_checker(testid)
            outcome['instance_directory_removed']=True
        except Exception as exc:
            outcome.update(classification='FAILED',cleanup='UNCONFIRMED',cleanup_error=str(exc))
        outcome['advance_requests_attempted']=c.advance_attempts
        j.emit('attempt_closed',classification=outcome['classification'],cleanup=outcome['cleanup'])
        save_new(d/'ATTEMPT_COMPLETED.json',outcome)
        save_new(d/'ARTIFACT_MANIFEST.json',{'files':{f.name:sha(f) for f in d.iterdir() if f.is_file() and f.name!='ARTIFACT_MANIFEST.json'}})
    return outcome


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--run-authorized-preflight',action='store_true')
    args=parser.parse_args()
    if verify_frozen()!=PRIMARY:raise ContractError('Frozen qualification proposal digest differs')
    if not args.run_authorized_preflight:
        print('Verification only. No API calls.');return
    manifest=read_json(HERE/'PREFLIGHT_MANIFEST.json')
    for name,digest in manifest['files'].items():
        if sha(ROOT/name)!=digest:raise ContractError('Preflight dependency changed: '+name)
    authority=read_json(HERE/'AUTHORIZATION.json')
    if authority.get('scope')!='TWO_NATIVE_PREFLIGHTS_ONLY' or authority.get('qualification_campaign_authorized') is not False:
        raise ContractError('Preflight-only authority missing')
    identity=read_json(EVIDENCE/'RUNTIME_IDENTITY.json')
    if identity.get('classification')!='PASS':raise ContractError('Runtime identity prerequisite not passed')
    save_new(EVIDENCE/'PREFLIGHT_STARTED.json',{'utc':utc(),'maximum_instances':2,'maximum_scored_advances':2,
        'proposal_sha256':PRIMARY,'preflight_manifest_sha256':sha(HERE/'PREFLIGHT_MANIFEST.json')})
    config=read_json(ROOT/'stage4e_d0/campaign.json');outcomes=[]
    for attempt,run in zip(('PF01_COOL','PF02_HEAT'),config['runs'][::2]):
        result=one_window(run,attempt,config);outcomes.append(result)
        print(json.dumps(result,allow_nan=False),flush=True)
        if result['classification']!='PASS':break
    summary={'classification':'PASS' if len(outcomes)==2 and all(r['classification']=='PASS' for r in outcomes) else 'FAILED',
        'runs':outcomes,'qualification_campaign_authorized':False,'maximum_instances':2,'maximum_scored_advances':2,
        'actual_instances':len(outcomes),'scored_advances_attempted':sum(r['advance_requests_attempted'] for r in outcomes),
        'thermostat_actuation_verified':False,'full_72h_dataset_verified':False}
    save_new(EVIDENCE/'PREFLIGHT_COMPLETED.json',summary)


if __name__=='__main__':main()
