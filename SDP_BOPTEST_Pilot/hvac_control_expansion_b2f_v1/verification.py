"""Read-only reconstruction of recorded B1 validity. No live identity query."""
import json,sqlite3,base64
from dataclasses import asdict
from . import HOME,PILOT,BATCH
from .packaging import read,sha,digest,require,write_new,inventory,chain

IDS=['B1V01_G174_NREF','B1V01_G174_C15']

def verify_delivery():
    m=read(PILOT/'DELIVERY_MANIFEST.json')
    for name,h in m['files'].items():
        p=(PILOT/name).resolve();require(p.is_relative_to(PILOT.resolve()),'Historical delivery path escape')
        require(sha(p)==h,'Historical delivery changed: '+name)
    actual={p.relative_to(PILOT).as_posix() for p in PILOT.rglob('*') if p.is_file() and '__pycache__' not in p.parts and p.name!='DELIVERY_MANIFEST.json'}
    require(actual==set(m['files']),'Historical delivery scope changed')
    return dict(files=len(actual),delivery_manifest_sha256=sha(PILOT/'DELIVERY_MANIFEST.json'))

def recorded_validity(rid,run,policy):
    from stage4e_d0.plan import Safety,FLAGS,POINTS,LOW,UP,OCC,COOL,FAN,HEAT,append_native,energy_audit
    from stage4e_d1_v2.validation import EventTracker,endpoint,initial_native,history,command_guard
    from stage4e_d2i_1.schema import observation_gate,forecast_gate,canonical_schema,catalog_gate
    from stage4e_d2i_1_v1_0_1.metadata import validate_metadata_receipt
    from stage4e_runtime_preflight.preflight import warmup_gate
    from hvac_control_expansion_v1.campaign import nominal,coverage
    from stage4e_d2_public.export import decode_truth
    d=BATCH/rid;status=read(d/'RUN_COMPLETED.json');ends=read(d/'endpoints.json');meta=read(d/'runtime_metadata.json')
    require(status['run_id']==rid and status['data_is_fabricated'] is False and status['classification']=='PASS_VALID_RAW','Recorded raw status failure')
    require(status['cleanup']=='STOP_ACK_AND_REMOVAL_VERIFIED' and status['unresolved_events']==0,'Recorded cleanup/events failure')
    require(read(d/'ATTEMPT_STARTED.json')['run']==run and read(d/'INITIALIZATION_METADATA.json')['run']==run,'Run identity changed')
    schema=canonical_schema();catalog_gate(meta,schema,list(schema['optional_collected_variables']));validate_metadata_receipt(d,meta)
    require(read(d/'DEPLOYED_FMU_IDENTITY.json')['sha256']=='158008fa3b635280a67dfed8bab5804d1f9a96d218b467dfebab77e5cbf8b86a','FMU identity failure')
    init=run['initialization'];require(init==dict(method='custom',start_time=15033600,warmup_period=604800,scenario_key=None),'Initialization drift')
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
    raw_ends,raw_fc,raw_whole,count=decode_truth(d,run)
    require(list(raw_ends.values())==ends and raw_whole==whole,'Raw/materialized reconstruction mismatch')
    require(all(raw_fc[r['start']]==read(d/f'forecast_{i:04d}.json')['data'] for i,r in enumerate(steps)),'Raw forecast mismatch')
    mutations=[];raw_advance=[];raw_kpi=None;raw_warm=None
    for line in (d/'raw_api.jsonl').read_text().splitlines():
        row=json.loads(line);require(row.get('attempt',1)==1 and row['http_status']==200,'Failed/retried raw request')
        route=row['url'].split('://',1)[-1].split('/',1)[-1].split('/')[0]
        if route=='advance':raw_advance.append(row['request'])
        if row['method']=='POST' or (row['method']=='PUT' and route in ('initialize','scenario','stop')):mutations.append((row['method'],route))
        if route in ('initialize','kpi','results'):
            value=json.loads(base64.b64decode(row['raw_body_base64']))['payload']
            if route=='initialize':require(row['request']==dict(start_time=run['start'],warmup_period=604800) and value==ends[0],'Raw initialization mismatch')
            if route=='kpi':raw_kpi=value
            if route=='results' and row['request']['start_time']==run['warmup_start']:raw_warm=value
    require(raw_advance==[r['applied_command'] for r in steps],'Raw issued command disagreement')
    require(mutations.count(('POST','testcases'))==1 and mutations.count(('PUT','initialize'))==1 and mutations.count(('POST','advance'))==864 and mutations.count(('PUT','stop'))==1,'Mutation budget mismatch')
    require(raw_kpi==read(d/'official_kpis.json') and raw_warm==warm,'Raw KPI/warmup mismatch')
    return dict(run_id=rid,status='PASS_REPRODUCED_RAW_VALIDITY',advances=864,endpoints=865,native_samples=len(combined['time']),
        warmup_samples=len(warm['time']),resolved_events=len(tracker.resolutions),raw_requests=count,
        receipt_chain=chain(d/'receipt_order.jsonl'),coverage=coverage(steps,combined,policy,run),energy=audit,
        initialization='CUSTOM_15033600_WARMUP_604800',cleanup=status['cleanup'],safety_replayed=True)

def verify():
    before=verify_delivery();manifest=read(PILOT/'IMPLEMENTATION_MANIFEST.json')
    for name,h in manifest['files'].items():require(sha(name)==h,'Executed source/dependency hash changed: '+name)
    supplement=read(PILOT/'SUPPLEMENTAL_BATCH_MANIFEST.json')['files'];require(inventory(BATCH)==supplement,'Supplemental manifest disagreement')
    outer=read(BATCH/'BATCH_ARTIFACT_MANIFEST.json')['files'];actual={k:v for k,v in supplement.items() if k!='BATCH_ARTIFACT_MANIFEST.json'}
    omitted=set(actual)-set(outer);require(omitted=={rid+'/ARTIFACT_MANIFEST.json' for rid in IDS} and not set(outer)-set(actual),'Broader historical manifest defect')
    require(all(actual[k]==v for k,v in outer.items()),'Original outer-manifest hash mismatch')
    db=sqlite3.connect((PILOT/'runtime_state/attempts.sqlite3').as_uri()+'?mode=ro',uri=True)
    try:
        require(db.execute('PRAGMA integrity_check').fetchone()[0]=='ok','Ledger integrity failure')
        events={rid:(state,json.loads(rec)) for rid,state,rec in db.execute('SELECT run_id,state,record FROM events')}
        reservations={rid:json.loads(rec) for rid,rec in db.execute('SELECT run_id,record FROM reservations')}
        slots={rid:json.loads(rec) for rid,rec in db.execute('SELECT run_id,definition FROM slots')}
        require(set(events)==set(reservations)==set(IDS) and len(slots)==6,'Consumed/unused slot identities changed')
    finally:db.close()
    batch_start=read(BATCH/'BATCH_STARTED.json');reference=read(HOME.parent/'stage4e_d0/RUNTIME_REFERENCE_IDENTITIES.json')
    runtime=batch_start['binding']['runtime']
    require(runtime['classification']=='PASS' and runtime['container_image_ids']==reference['container_image_ids'],'Recorded runtime image identity mismatch')
    require(runtime['worker_identity']==read(HOME.parent/'stage4e_runtime_preflight/evidence/WORKER_EXECUTABLE_AND_DEPENDENCIES.json'),'Recorded worker identity mismatch')
    campaign=read(PILOT/'campaign_manifest.json');require(digest(campaign)==batch_start['binding']['binding']['campaign_sha256'],'Campaign binding changed')
    top={'BATCH_STARTED.json','PILOT_COMPLETED.json','NATIVE_REPRODUCIBILITY.json','PRETREATMENT_COMPARISON.json','BATCH_ARTIFACT_MANIFEST.json'}
    runs=[];validated=[]
    required=['ATTEMPT_STARTED.json','runtime_metadata.json','receipt_order.jsonl','raw_api.jsonl','INITIAL_ENDPOINT.json','endpoints.json',
              'whole_native_results.json','NATIVE_WARMUP_HISTORY.json','RUN_COMPLETED.json','energy_audit.json','steps.jsonl','ARTIFACT_MANIFEST.json']
    for rid in IDS:
        seal=rid+'_SEALED_MANIFEST.json';res=rid+'_RESERVATION.json';top.update((seal,res))
        require(events[rid][0]=='CONSUMED_COMPLETED' and sha(BATCH/seal)==events[rid][1]['seal_sha256'],'Ledger-bound seal mismatch')
        require(read(BATCH/res)==reservations[rid],'Reservation binding changed')
        cfg=next(r for r in campaign['runs'] if r['run_id']==rid);require(digest(cfg)==reservations[rid]['run_sha256'],'Run config identity mismatch')
        validated.append(recorded_validity(rid,cfg,campaign['policy']))
        runs.append(dict(run_id=rid,seal_path=seal,required_files=required))
    from hvac_control_expansion_v1.comparison import compare_runs
    from stage4e_d2_public.export import locate
    public=read(HOME.parent/'stage4e_d2_public/PUBLIC_DEVELOPMENT_VALIDATION_v1_0_0/RUN_CONFIGURATION_MANIFEST.json')['runs']
    old=next(r for r in public if r['run_id']=='D2_G174_N');n,c=[next(r for r in campaign['runs'] if r['run_id']==rid) for rid in IDS]
    native=compare_runs(locate(old),BATCH/IDS[0],old,n,True);prefix=compare_runs(BATCH/IDS[0],BATCH/IDS[1],n,c)
    require(native==read(BATCH/'NATIVE_REPRODUCIBILITY.json') and prefix==read(BATCH/'PRETREATMENT_COMPARISON.json'),'Pair comparison changed')
    plan=dict(version='B2F_PACKAGING_1.0.0',scope='HISTORICAL_BATCH_READ_ONLY_ALL_REGISTERED_FILES',
              historical_outer_manifest_is_preserved_evidence=True,batch_files={name:supplement[name] for name in sorted(top)},runs=runs)
    after=verify_delivery();require(before==after,'Historical files changed during verification')
    report=dict(status='PASS',original_finalization='FAILED_PRESERVED',original_raw_validity='PASS',
        supplemental_audit_independently_reproduced='PASS',exact_omissions=sorted(omitted),broader_observed_evidence_defect=False,
        historical_delivery=before,executed_source_manifest_sha256=sha(PILOT/'IMPLEMENTATION_MANIFEST.json'),
        recorded_runtime_identity='PASS_FROM_SAVED_EVIDENCE_NOT_CURRENT_LIVE_QUERY',runs=validated,
        native_reproducibility=native,pretreatment=prefix,remaining_unused_slots=4,
        simulator_calls=0,deployments=0,initializations=0,advances=0,model_fits=0)
    write_new(HOME/'PILOT_VERIFICATION.json',report);write_new(HOME/'PACKAGING_SCOPE_PLAN.json',plan)
    return report,plan
