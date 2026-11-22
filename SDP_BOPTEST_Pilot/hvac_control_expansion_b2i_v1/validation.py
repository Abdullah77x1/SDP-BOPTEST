"""G146 recorded-run validator, versioned from B2G; named initialization and origin-plan checks."""
import json,base64
from pathlib import Path
from dataclasses import asdict
from hvac_control_expansion_b2f_v1.packaging import read,sha,digest,require,chain

def verify_run(directory,run,policy,*,fabricated=False):
    rid=run['run_id']
    from stage4e_d0.plan import Safety,FLAGS,POINTS,LOW,UP,OCC,COOL,FAN,HEAT,append_native,energy_audit
    from stage4e_d1_v2.validation import EventTracker,endpoint,initial_native,history,command_guard
    from stage4e_d2i_1.schema import observation_gate,forecast_gate,canonical_schema,catalog_gate
    from stage4e_d2i_1_v1_0_1.metadata import validate_metadata_receipt
    from stage4e_runtime_preflight.preflight import warmup_gate
    from hvac_control_expansion_v1.campaign import nominal,coverage
    from stage4e_d2_public.export import decode_truth
    d=Path(directory);status=read(d/'RUN_COMPLETED.json');ends=read(d/'endpoints.json');meta=read(d/'runtime_metadata.json')
    require(status['run_id']==rid and status['data_is_fabricated'] is fabricated and status['classification']=='PASS_VALID_RAW','Recorded raw status failure')
    require(status['cleanup']=='STOP_ACK_AND_REMOVAL_VERIFIED' and status['unresolved_events']==0,'Recorded cleanup/events failure')
    require(read(d/'ATTEMPT_STARTED.json')['run']==run and read(d/'INITIALIZATION_METADATA.json')['run']==run,'Run identity changed')
    schema=canonical_schema();catalog_gate(meta,schema,list(schema['optional_collected_variables']));validate_metadata_receipt(d,meta)
    require(read(d/'DEPLOYED_FMU_IDENTITY.json')['sha256']=='158008fa3b635280a67dfed8bab5804d1f9a96d218b467dfebab77e5cbf8b86a','FMU identity failure')
    init=run['initialization'];require(init==dict(method='scenario',start_time=12614400,warmup_period=604800,scenario_key='typical_cool_day'),'Initialization drift')
    warm=read(d/'NATIVE_WARMUP_HISTORY.json');warmup_gate(warm,run['start'])
    require(set(range(run['warmup_start'],run['start']+1,30))<=set(warm['time']),'Warmup sample support failure')
    require(len(ends)==865 and [e['time'] for e in ends]==list(range(run['start'],run['end']+1,300)),'Endpoint count/grid failure')
    initial_native(ends[0]);require(read(d/'INITIAL_ENDPOINT.json')==ends[0],'Initial endpoint mismatch')
    steps=[json.loads(line) for line in (d/'steps.jsonl').read_text().splitlines()]
    require(len(steps)==864,'Step count failure')
    events=[json.loads(line) for line in (d/'receipt_order.jsonl').read_text().splitlines()];orders={e['order']:e for e in events}
    tracker=EventTracker();safety=Safety(policy);combined={}
    for i,r in enumerate(steps):
        t=run['start']+i*300;require((r['start'],r['end'])==(t,t+300),'Command timestamp failure')
        require(r['current_observation']==ends[i],'Origin observation mismatch')
        fc=read(d/f'forecast_{i:04d}.json')['data'];forecast_gate(fc,t,schema,list(schema['optional_collected_variables']))
        boundary=dict(time=t,**{p:fc[p][0] for p in POINTS});require(boundary==r['current_boundary'],'Boundary vintage mismatch')
        cutoff=orders[r['origin_cutoff_order']];age=cutoff['observation_age_s']
        planned=nominal(run,t);command,reason=safety.decide(planned,ends[i],boundary,age)
        require(command==r['applied_command'] and reason==r['reason'] and planned['command']==r['proposed_command'],'Safety/command replay mismatch')
        command_guard(command,ends[i],boundary,t,age);tracker.guard(t,command,ends[i],age,864-i)
        observation_gate(ends[i+1],t+300,meta)
        checked=endpoint(t,command,ends[i+1],dict(time=t+300,issued_at=t,lower_k=fc[LOW][1],upper_k=fc[UP][1],occupancy=fc[OCC][1]),
            dict(observation=r['observation_received_order'],forecast=r['forecast_received_order'],cutoff=r['origin_cutoff_order'],response=r['endpoint_received_order']),age)
        require(digest(asdict(checked))==digest(r['validation_at_receipt']),'Recorded endpoint validity mismatch')
        chunk=read(d/f'native_chunk_{i:04d}.json');history(chunk,t,t+300);append_native(combined,chunk,t,t+300)
        for j,stamp in enumerate(chunk['time']):
            if stamp<=t:continue
            require(all(chunk[f][j]==command[f] for f in FLAGS),'Native delivered flag mismatch')
            if command[FLAGS[0]]:require(abs(chunk['con_oveTSetCoo_u'][j]-296.90)<=1e-5,'Native delivered target mismatch')
        if tracker.pending:
            ev=tracker.pending['event_time'];saved=read(d/f'event_resolution_{int(ev)}.json')
            resolved=tracker.resolve(read(d/f'pending_history_{int(ev)}.json'),ends[i+1],checked,r['endpoint_received_order'],saved['history_receipt_order'])
            require(digest(resolved)==digest(saved),'Event-resolution mismatch')
        tracker.register(ends[i+1],checked,r['endpoint_received_order'])
    require(tracker.pending is None and digest(tracker.resolutions)==digest(read(d/'event_resolutions.json')),'Unresolved/altered event')
    require(combined==read(d/'native_results.json'),'Native chunk assembly mismatch')
    whole=read(d/'whole_native_results.json');history(whole,run['start'],run['end'])
    require(combined=={k:whole[k] for k in combined},'Whole/chunk mismatch')
    audit=energy_audit(combined,run['start'],run['end'],read(d/'official_kpis.json'),policy)
    require(audit==read(d/'energy_audit.json'),'Energy reconciliation changed')
    from .metadata import verify_origin_metadata
    metadata=verify_origin_metadata(d,run)
    raw_ends,raw_fc,raw_whole,count=decode_truth(d,run)
    require(list(raw_ends.values())==ends and raw_whole==whole,'Raw/materialized reconstruction mismatch')
    require(all(raw_fc[r['start']]==read(d/f'forecast_{i:04d}.json')['data'] for i,r in enumerate(steps)),'Raw forecast mismatch')
    mutations=[];raw_advance=[];raw_kpi=None;raw_warm=None
    for line in (d/'raw_api.jsonl').read_text().splitlines():
        row=json.loads(line);require(row.get('attempt',1)==1 and row['http_status']==200,'Failed/retried raw request')
        route=row['url'].split('://',1)[-1].split('/',1)[-1].split('/')[0]
        if route=='advance':raw_advance.append(row['request'])
        if row['method']=='POST' or (row['method']=='PUT' and route in ('initialize','scenario','stop')):mutations.append((row['method'],route))
        if route in ('scenario','kpi','results'):
            value=json.loads(base64.b64decode(row['raw_body_base64']))['payload']
            if route=='scenario' and row['method']=='PUT':require(row['request']==dict(time_period='typical_cool_day',electricity_price='constant') and value['time_period']==ends[0],'Raw named initialization mismatch')
            if route=='kpi':raw_kpi=value
            if route=='results' and row['request']['start_time']==run['warmup_start']:raw_warm=value
    require(raw_advance==[r['applied_command'] for r in steps],'Raw issued command disagreement')
    require(mutations.count(('POST','testcases'))==1 and mutations.count(('PUT','scenario'))==1 and mutations.count(('PUT','initialize'))==0 and mutations.count(('POST','advance'))==864 and mutations.count(('PUT','stop'))==1,'Mutation budget mismatch')
    require(raw_kpi==read(d/'official_kpis.json') and raw_warm==warm,'Raw KPI/warmup mismatch')
    return dict(run_id=rid,status='PASS_REPRODUCED_RAW_VALIDITY',advances=864,endpoints=865,native_samples=len(combined['time']),
        warmup_samples=len(warm['time']),resolved_events=len(tracker.resolutions),raw_requests=count,
        receipt_chain=chain(d/'receipt_order.jsonl'),coverage=coverage(steps,combined,policy,run),energy=audit,
        initialization='NAMED_TYPICAL_COOL_DAY_WARMUP_604800',cleanup=status['cleanup'],safety_replayed=True,origin_metadata=metadata)
