"""Versioned raw collector. Public offline entry accepts fabricated adapters only.

No features/targets are built. Protected collection is unconditionally refused.
Live adapter construction is separate and requires authorization/prerequisites.
"""
import json,time
from copy import deepcopy
from dataclasses import asdict
from pathlib import Path
from .common import *
from .manifest import validate_manifest,select_run,require_public_collection
from .schema import canonical_schema,validate_schema,catalog_gate,forecast_gate,observation_gate
from .transport import BudgetedTransport,initialize_run
from stage4e_d0.plan import (POINTS,FLAGS,LOW,UP,OCC,TEMP,COOL,FAN,HEAT,Safety,nominal,action_path,
    append_native,energy_audit,coverage)
from stage4e_d0.runner import Journal,files_manifest,utc
from stage4e_d1_v2.validation import EventTracker,endpoint,initial_native,history,HISTORY_POINTS,command_guard
from stage4e_runtime_preflight.preflight import warmup_gate

def _collect(manifest,run,directory,factory,mode):
    require_public_collection(run)
    directory=Path(directory);directory.mkdir()
    save_new(directory/'ATTEMPT_STARTED.json',{'version':VERSION,'mode':mode,'run':run,
        'config_sha256':digest(manifest),'started_utc':utc(),'data_is_fabricated':mode=='FABRICATED_OFFLINE_TEST_ONLY'})
    save_new(directory/'QUARANTINE.json',{'partition':run['partition'],'training_release':False,'dataset_constructed':False})
    journal=Journal(directory/'receipt_order.jsonl')
    status={'run_id':run['run_id'],'partition':run['partition'],'dataset_partition':run['dataset_partition'],
        'classification':'FAILED','mode':mode,'data_is_fabricated':mode=='FABRICATED_OFFLINE_TEST_ONLY',
        'training_release':False,'dataset_constructed':False,'cleanup':'NOT_CONFIRMED'}
    client=None;testid=None;records=[];ends=[];combined={};tracker=EventTracker();responses=0;profile={};qualified=[]
    try:
        client=BudgetedTransport(factory(manifest['policy']['base'],directory,journal,run,manifest),run)
        testid=client.deploy();meta=client.discover();schema=canonical_schema();validate_schema(schema)
        save_new(directory/'runtime_metadata.json',meta)
        production=manifest['purpose']=='production'
        qualified=list(schema['optional_collected_variables']) if production else []
        catalog=catalog_gate(meta,schema,qualified)
        save_new(directory/'CATALOG_AVAILABILITY.json',catalog)
        identity=client.fmu_identity();save_new(directory/'DEPLOYED_FMU_IDENTITY.json',identity)
        require(identity['sha256']==FMU_SHA,'Selected FMU identity mismatch')
        current=initialize_run(client,run);observed_at=time.monotonic();prior=client.last_receipt_order
        save_new(directory/'INITIAL_ENDPOINT.json',current)
        observation_gate(current,run['start'],meta);initial_native(current)
        client.request('PUT','step',{'step':300});client.request('GET','step')
        scenario=client.request('GET','scenario')
        expected_period=run['initialization']['scenario_key']
        require(scenario.get('time_period')==expected_period and scenario.get('electricity_price')=='constant','Actual scenario/custom metadata mismatch')
        require(all(scenario.get(k) is None for k in ('temperature_uncertainty','solar_uncertainty','seed')),'Unapproved uncertainty/seed')
        save_new(directory/'INITIALIZATION_METADATA.json',{'run':run,'actual_API_scenario':scenario,
            'custom_window_annotation_is_not_named_API_scenario':run['initialization']['method']=='custom'})
        warm=client.request('PUT','results',{'point_names':[COOL,FAN,HEAT,*FLAGS],
            'start_time':run['warmup_start'],'final_time':run['start']})
        save_new(directory/'NATIVE_WARMUP_HISTORY.json',warm);warmup_gate(warm,run['start'])
        require(set(range(run['warmup_start'],run['start']+1,30)).issubset(set(warm['time'])),
            'Missing regular native warmup sample')
        requested=list(schema['core_forecasts'])+[p for p in schema['optional_collected_variables'] if catalog[p]['available']]
        optional_value_status={p:True for p in schema['optional_collected_variables']}
        if not production:
            long_fc=client.request('PUT','forecast',{'point_names':requested,'horizon':259200,'interval':300})
            profile=forecast_gate(long_fc,run['start'],schema,(),259200,True)
            save_new(directory/'PREFLIGHT_72H_PASSIVE_FORECAST.json',{'issued_at_sim':run['start'],'data':long_fc,'availability':profile})
            optional_value_status={p:profile[p]['status']=='VALUES_RECEIVED' for p in optional_value_status}
        ends.append(current);safety=Safety(manifest['policy']);origin_status='VERIFIED_REFERENCE'
        for i in range(run['maximum_advances']):
            t=run['start']+i*300;require(current['time']==t,'Origin timestamp mismatch')
            fc=client.request('PUT','forecast',{'point_names':requested,'horizon':1800,'interval':300})
            fr=client.last_receipt_order;available=forecast_gate(fc,t,schema,qualified)
            for p in optional_value_status:optional_value_status[p]&=available[p]['status']=='VALUES_RECEIVED'
            save_new(directory/f'forecast_{i:04d}.json',{'issued_at_sim':t,'received_order':fr,'data':fc,
                'optional_availability':{p:available[p] for p in schema['optional_collected_variables']},'auto_ML_feature_selection':False})
            boundary=dict(time=t,**{p:fc[p][0] for p in POINTS});age=time.monotonic()-observed_at
            proposal=nominal(run,t,manifest['policy']);command,reason=safety.decide(proposal,current,boundary,age)
            command_guard(command,current,boundary,t,age);tracker.guard(t,command,current,age,run['maximum_advances']-i)
            proposed_path=action_path(run,t,manifest['policy']);known=deepcopy(proposed_path)
            known[0].update(command=deepcopy(command),source='issued_current_command',known_at_sim=t,effective_available_at_sim=t)
            # Keep nominal annotation distinct; future safety decisions are unknown.
            for p in known[1:]:p['effective_available_at_sim']=run['start']
            cutoff=journal.emit('origin_cutoff',sim_time=t,observation_received_order=prior,forecast_received_order=fr,
                issued_command=command,proposed_command=proposal['command'],known_path=known,
                observation_age_s=age,validation_state_at_origin=origin_status)
            before=current;state_at_origin=origin_status
            current=client.request('POST','advance',command);responses+=1
            observed_at=time.monotonic();receipt=client.last_receipt_order
            save_new(directory/f'endpoint_{i+1:04d}.json',current);observation_gate(current,t+300,meta)
            checked=endpoint(t,command,current,{'time':t+300,'issued_at':t,'lower_k':fc[LOW][1],
                'upper_k':fc[UP][1],'occupancy':fc[OCC][1]},
                {'observation':prior,'forecast':fr,'cutoff':cutoff,'response':receipt},age)
            chunk=client.request('PUT','results',{'point_names':list(HISTORY_POINTS),'start_time':t,'final_time':t+300})
            save_new(directory/f'native_chunk_{i:04d}.json',chunk);history(chunk,t,t+300)
            append_native(combined,chunk,t,t+300)
            if tracker.pending:
                e=tracker.pending['event_time']
                data=client.request('PUT','results',{'point_names':list(HISTORY_POINTS),'start_time':e-300,'final_time':e+300})
                save_new(directory/f'pending_history_{int(e)}.json',data)
                resolved=tracker.resolve(data,current,checked,receipt,client.last_receipt_order)
                save_new(directory/f'event_resolution_{int(e)}.json',resolved)
            tracker.register(current,checked,receipt);origin_status=checked.status
            record={'start':t,'end':t+300,'partition':run['partition'],'group_id':run['group_id'],
                'origin_cutoff_order':cutoff,'observation_received_order':prior,'forecast_received_order':fr,
                'endpoint_received_order':receipt,'current_observation':before,'current_boundary':boundary,
                'proposed_command':proposal['command'],'applied_command':command,'proposed_path':proposed_path,'known_path':known,
                'reason':reason,'validation_state_at_origin':state_at_origin,'validation_at_receipt':asdict(checked),
                'posthoc_resolution_is_not_an_origin_feature':True,'future_safety_veto_unknown_at_origin':True}
            records.append(record);ends.append(current);prior=receipt
            with (directory/'steps.jsonl').open('a',encoding='utf-8') as stream:stream.write(json.dumps(record,allow_nan=False)+'\n')
        require(tracker.pending is None,'Unresolved event at final budget')
        require(len(records)==run['maximum_advances'] and len(ends)==run['maximum_advances']+1,'Incomplete run count')
        require(current['time']==run['end'] and not any(current[f] for f in FLAGS),'Final native release/time failure')
        whole=client.request('PUT','results',{'point_names':list(HISTORY_POINTS),'start_time':run['start'],'final_time':run['end']})
        save_new(directory/'whole_native_results.json',whole);history(whole,run['start'],run['end'])
        require(combined=={k:whole[k] for k in combined},'Power chunks/whole history differ')
        kpis=client.request('GET','kpi');save_new(directory/'official_kpis.json',kpis)
        save_new(directory/'energy_audit.json',energy_audit(combined,run['start'],run['end'],kpis,manifest['policy']))
        save_new(directory/'endpoints.json',ends);save_new(directory/'native_results.json',combined)
        save_new(directory/'event_resolutions.json',tracker.resolutions)
        save_new(directory/'OPTIONAL_VALUE_QUALIFICATION.json',optional_value_status)
        classification='PASS_VALID_RAW' if production else 'PASS_PREFLIGHT_RAW' if all(optional_value_status.values()) else 'INCONCLUSIVE_OPTIONAL_REPORTING'
        status.update(classification=classification,advances=len(records),endpoints=len(ends),
            native_samples=len(combined['time']),pending_events_resolved=len(tracker.resolutions),
            optional_channel_status=optional_value_status,coverage=coverage(records,combined,manifest['policy']) if production else None)
    except (Exception,KeyboardInterrupt) as exc:
        status.update(classification='FAILED',error=f'{type(exc).__name__}: {exc}',interval_records_collected=len(records))
        journal.emit('run_failed',error=status['error'],quarantine=True,no_retry=True)
    finally:
        if client is not None:
            try:
                cleanup=client.stop()
                require(isinstance(cleanup,dict) and cleanup.get('acknowledgement')=='OK'
                    and cleanup.get('instance_removed') is True,'Cleanup acknowledgement/removal proof missing')
                status['cleanup']='STOP_ACK_AND_REMOVAL_VERIFIED'
                status['cleanup_evidence']=cleanup
            except Exception as exc:status.update(classification='FAILED',cleanup='STOP_UNCONFIRMED',cleanup_error=str(exc))
        status.update(deploy_attempts=client.deploy_attempts if client else 0,
            initialization_attempts=client.initialization_attempts if client else 0,
            advance_requests_attempted=client.advance_attempts if client else 0,advance_responses_received=responses,
            unresolved_events=int(tracker.pending is not None))
        journal.emit('attempt_closed',classification=status['classification'])
        save_new(directory/'RUN_COMPLETED.json',status)
        save_new(directory/'ARTIFACT_MANIFEST.json',{'files':files_manifest(directory)})
    return status

def collect_mock(manifest,run_id,directory,fixture_class=None):
    from .fixtures import FakeTransport
    validate_manifest(manifest);run=select_run(manifest,run_id);require_public_collection(run)
    fixture_class=fixture_class or FakeTransport
    require(isinstance(fixture_class,type) and issubclass(fixture_class,FakeTransport),'Offline collection accepts fabricated fixture classes only')
    return _collect(manifest,run,directory,fixture_class,'FABRICATED_OFFLINE_TEST_ONLY')
