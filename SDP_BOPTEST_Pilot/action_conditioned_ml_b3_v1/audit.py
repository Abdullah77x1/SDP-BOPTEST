"""Audit existing development evidence; emit counts/provenance only, never feature rows.

No calls to build_rows, labels, model code, preprocessors, BOPTEST or runtime.
Reads only allowlisted development raw directories and development CSV values.
"""
import csv,json,math,ast,sqlite3
from pathlib import Path
from collections import Counter,defaultdict
from . import HOME,PILOT,WORKSPACE
from hvac_control_expansion_b2f_v1.packaging import sha,digest,read,write_new,require,chain,verify_package
from hvac_control_expansion_v1.campaign import canonical_manifest,action_path as b1_path
from hvac_control_expansion_v1.contracts import matched_size_plan
from stage4e_d0.plan import action_path as d2_path,configuration,FLAGS,SET,FLAG,Safety
from stage4e_d2i_1.manifest import origin_times

PUBLIC=PILOT/'stage4e_d2_public/PUBLIC_DEVELOPMENT_VALIDATION_v1_0_0'
MODEL=WORKSPACE/'experiments/five_model_hvac16_v1_0_0'
V2=WORKSPACE/'experiments/hvac_16_outputs_v2_0_0'
INPUT_HASHES={}

def source(path):
    path=Path(path).resolve();s=path.as_posix().lower()
    require(not any(x in s for x in ('/sealed_validation/','ml_validation','/protected','validation_predictions','validation_metrics')),'Forbidden validation/protected source')
    h=sha(path);old=INPUT_HASHES.setdefault(str(path),h);require(old==h,'Source changed during audit');return path

def load(path):return read(source(path))
def lines(path):
    return [json.loads(s) for s in source(path).read_text(encoding='utf-8-sig').splitlines()]

def common_features():
    tree=ast.parse(source(MODEL/'config.py').read_text());scope={}
    for n in tree.body:
        if isinstance(n,ast.Assign) and isinstance(n.targets[0],ast.Name):
            name=n.targets[0].id
            if name=='QUANTITIES':scope[name]=ast.literal_eval(n.value)
            if name=='FEATURES':return eval(compile(ast.Expression(n.value),'<frozen feature names>','eval'),{'__builtins__':{},**scope})
    raise ValueError('FEATURES missing')

def original_sources():
    # Read partition/source metadata; never follow validation source paths.
    metadata=load(PUBLIC/'PARTITION_AND_SOURCE_MANIFEST.json');configs=load(PUBLIC/'RUN_CONFIGURATION_MANIFEST.json')['runs']
    return [(r,next(c for c in configs if c['run_id']==r['run_id']),PILOT/r['source']) for r in metadata['runs'] if r['partition']=='development']

def b1_sources():
    m=canonical_manifest();old=PILOT/'hvac_control_expansion_v1/runtime_state/batches/B1_G174_INITIAL_PILOT'
    c45=load(PILOT/'hvac_control_expansion_b2g_v2/LIVE_EXECUTION.json')
    g146=load(PILOT/'hvac_control_expansion_b2i_v1/LIVE_EXECUTION.json')
    paths=[old/m['runs'][0]['run_id'],old/m['runs'][1]['run_id'],Path(c45['run_path'])]+[Path(o['run_path']) for o in g146['runs']]
    require(g146['status']=='PASS_ALL_THREE_G146' and c45['state']=='CONSUMED_COMPLETED','B1 not complete')
    for o in [c45]+g146['runs']:require(verify_package(o['source_batch'],o.get('package_path',PILOT/'hvac_control_expansion_b2g_v2/corrected_c45_package'))==o['corrected_finalization'],'Finalizer changed')
    return [(dict(run_id=r['run_id'],group_id=r['group_id'],partition='development',policy=r['arm']),r,p) for r,p in zip(m['runs'],paths)]

def verify_used(d,p,manifest):
    name=p.relative_to(d).as_posix();require(name in manifest and sha(p)==manifest[name],'Missing/changed raw source: '+str(p));source(p)

def scan_run(meta,cfg,d,folds,is_b1):
    require(meta['partition']=='development' and cfg['partition']=='development','Only development sources allowed')
    d=d.resolve();status=load(d/'RUN_COMPLETED.json');require(status['classification']=='PASS_VALID_RAW','Invalid source')
    require(status.get('unresolved_events')==0 and status.get('data_is_fabricated',False) is False,'Incomplete/fabricated evidence')
    require(status['cleanup'] in ('STOP_ACK_VERIFIED','STOP_ACK_AND_REMOVAL_VERIFIED'),'Cleanup failure')
    artifact=load(d/'ARTIFACT_MANIFEST.json')['files']
    required=['RUN_COMPLETED.json','endpoints.json','whole_native_results.json','native_results.json','runtime_metadata.json','steps.jsonl','receipt_order.jsonl','DEPLOYED_FMU_IDENTITY.json','energy_audit.json','raw_api.jsonl']
    for name in required:verify_used(d,d/name,artifact)
    ends=load(d/'endpoints.json');native=load(d/'whole_native_results.json');steps=lines(d/'steps.jsonl');runtime=load(d/'runtime_metadata.json')
    start,end=cfg['start'],cfg['end'];origins=origin_times(start,end)
    require(len(ends)==865 and [e['time'] for e in ends]==list(range(start,end+1,300)),'Endpoint grid/duplicates')
    require(len(steps)==864 and [r['start'] for r in steps]==list(range(start,end,300)),'Step grid/duplicates')
    ts=native['time'];require(len(ts)==8641 and ts==list(range(start,end+1,30)),'Native grid/duplicates')
    require(load(d/'native_results.json')=={k:native[k] for k in load(d/'native_results.json')},'Native chunk/whole disagreement')
    for e in ends:require(all(type(v) in (int,float) and math.isfinite(v) for v in e.values()),'Missing/nonfinite endpoint')
    for k,v in native.items():require(len(v)==len(ts) and all(type(x) in (int,float) and math.isfinite(x) for x in v),'Missing/nonfinite native')
    for k,u in [('zon_reaTRooAir_y','K'),('fcu_reaPCoo_y','W'),('fcu_reaPFan_y','W'),('fcu_reaPHea_y','W')]:
        require(runtime['measurements'][k]['Unit']==u and k in native,'Unit/channel mismatch')
    endpoint_required=['zon_reaTRooAir_y','zon_weaSta_reaWeaTDryBul_y','zon_weaSta_reaWeaHGloHor_y','con_oveTSetCoo_u','con_oveTSetHea_u',*FLAGS]
    require(all(all(k in e for k in endpoint_required) for e in ends),'Missing common25 endpoint source')
    receipts=lines(d/'receipt_order.jsonl');orders={r['order']:r for r in receipts};receipt_integrity=chain(d/'receipt_order.jsonl')
    # A completed-history response must precede each origin. Request-response pairs are adjacent in the qualified client.
    result_receipts=[]
    for r in receipts:
        if r.get('kind')=='api_request' and r.get('endpoint')=='results':
            req=r['request'];resp=orders.get(r['order']+1,{})
            if {'fcu_reaPCoo_y','fcu_reaPFan_y','fcu_reaPHea_y'}<=set(req.get('point_names',[])):
                require(resp.get('kind')=='api_received' and resp.get('endpoint')=='results','History receipt pair mismatch')
                result_receipts.append((req['start_time'],req['final_time'],resp['order']))
    require(load(d/'DEPLOYED_FMU_IDENTITY.json')['sha256']=='158008fa3b635280a67dfed8bab5804d1f9a96d218b467dfebab77e5cbf8b86a','Actual FMU pin mismatch')
    stepmap={r['start']:r for r in steps};forecast_width=set();nominal_origins=known_origins=0;path_match=Counter();vetoed=0;latched_origins=0
    safety=Safety(configuration())
    for i,r in enumerate(steps):
        t=start+i*300;verify_used(d,d/f'forecast_{i:04d}.json',artifact);f=load(d/f'forecast_{i:04d}.json');fc=f['data'];forecast_width.add(len(fc)-1)
        require(f['issued_at_sim']==t and f['received_order']==r['forecast_received_order'],'Forecast vintage mismatch')
        require(r['observation_received_order']<r['forecast_received_order']<r['origin_cutoff_order']<r['endpoint_received_order'],'Receipt order failure')
        require(fc['time']==list(range(t,t+1801,300)),'Forecast grid')
        for k in ('LowerSetp[1]','UpperSetp[1]','Occupancy[1]','TDryBul','HGloHor'):
            require(k in fc and len(fc[k])==7 and all(math.isfinite(v) for v in fc[k]),'Missing common forecast')
        expected=b1_path(cfg,t) if is_b1 else d2_path(cfg,t,configuration())
        require(r['proposed_path']==expected and r['proposed_command']==expected[0]['command'],'Immutable nominal plan mismatch')
        require(all(p['known_at_sim']<=t and p['source']=='frozen_nominal_plan' for p in expected),'Unavailable nominal plan')
        require(r['known_path'][0]['command']==r['applied_command'],'Current issued command mismatch')
        require(all(p['command']==q['command'] for p,q in zip(r['known_path'][1:],expected[1:])),'Future realized action in nominal path')
        require(orders[r['origin_cutoff_order']]['known_path']==r['known_path'],'Plan not cutoff-bound')
        pre_latched=safety.vetoed and safety.block==expected[0]['block_id'] and expected[0]['block_id'] is not None
        command,reason=safety.decide(expected[0],r['current_observation'],r['current_boundary'],orders[r['origin_cutoff_order']]['observation_age_s'])
        reason_parts=r['reason'].split(';')
        require(all(note=='pending_event_scheduled_native_verification' for note in reason_parts[1:]),'Unknown legacy reason annotation')
        if len(reason_parts)>1:require(not any(command[f] for f in FLAGS),'Event annotation on external command')
        require(command==r['applied_command'] and reason==reason_parts[0],'Frozen safety replay mismatch')
        if t in origins:
            for a in range(t-2100,t,300):require(any(s<=a and e>=a+300 and order<r['origin_cutoff_order'] for s,e,order in result_receipts),'Historical interval not available at origin')
            require(r['current_observation']==ends[i],'Current source mismatch')
            nominal_origins+=1;known_origins+=1
            latched_origins+=int(pre_latched)
            for horizon in (300,600,900,1800):
                path=r['known_path'][:horizon//300]
                if len(path)==horizon//300 and all(p['command']==stepmap[p['start']]['applied_command'] for p in path):path_match[str(horizon)]+=1
        vetoed+=bool(r['proposed_command'][FLAG] and not r['applied_command'][FLAG])
    require(nominal_origins==852 and len(origins)==len(set(origins)),'Eligibility count')
    held=next(f['fold'] for f in folds if meta['group_id'] in f['held_groups'])
    return dict(run_id=meta['run_id'],source=str(d),group_id=meta['group_id'],policy=meta['policy'],kind='B1' if is_b1 else 'ORIGINAL_D2',
        outer_held_fold=held,partition='development',scored_start=start,scored_end=end,endpoints=865,five_minute_scored_origins=864,
        history_support_s=2100,max_horizon_s=1800,eligible_origins=852,first_eligible=start+2100,last_eligible=end-1800,
        edge_exclusions=12,missing_required_channels=0,endpoint_duplicate_timestamps=0,native_duplicate_timestamps=0,duplicate_origin_ids=0,
        native_samples=8641,forecast_channel_counts=sorted(forecast_width),nominal_plan_eligible=nominal_origins,
        as_issued_hybrid_plan_origins=known_origins,posthoc_hybrid_equals_realized_by_horizon=dict(path_match),vetoed_scored_intervals=vetoed,
        safety_state_known_origins=nominal_origins,latched_before_origin_count=latched_origins,
        training_default=not is_b1 or cfg['arm']!='NREF',source_manifest_sha256=sha(d/'ARTIFACT_MANIFEST.json'),receipt_chain=receipt_integrity,
        source_identity=load(d/'DEPLOYED_FMU_IDENTITY.json'),legacy_fabrication_flag_absent='data_is_fabricated' not in status,
        status='PASS_STRUCTURAL_AND_PROVENANCE_ELIGIBILITY')

def audit(record=True):
    require(not record or not (HOME/'AUDIT_RESULTS.json').exists(),'Audit output exclusive')
    folds=load(MODEL/'run_01/outer_folds.json');features=common_features();schema=load(V2/'SCHEMA_FREEZE.json')
    require(features==schema['configs']['revised_components'] and len(features)==25,'common25 mismatch')
    devpath=source(V2/'dataset/ml_development_16_outputs.csv');expected=load(V2/'DATASET_CHECKSUMS.json')['dataset/ml_development_16_outputs.csv'];require(sha(devpath)==expected,'Original development checksum changed')
    counts=Counter();ids=set();times=defaultdict(set);missing=0
    with devpath.open(newline='',encoding='utf-8-sig') as f:
        for r in csv.DictReader(f):
            require(r['partition']=='development','Validation contamination');require(r['row_id'] not in ids,'Duplicate original identity');ids.add(r['row_id'])
            require(all(math.isfinite(float(r[k])) for k in features+schema['targets']),'Nonfinite original features/targets')
            counts[r['run_id']]+=1;times[r['run_id']].add(int(r['sim_time_s']))
    require(sum(counts.values())==13632 and len(counts)==16 and all(n==852 for n in counts.values()),'Original development counts')
    entries=original_sources();require(len(entries)==16 and set(counts)=={m['run_id'] for m,c,d in entries},'Run source identities differ')
    results=[]
    for m,c,d in entries+b1_sources():
        is_b1=m['run_id'].startswith('B1V01_');result=scan_run(m,c,d,folds,is_b1);results.append(result)
        if not is_b1:require(times[m['run_id']]==set(origin_times(c['start'],c['end'])),'Original table origin grid changed')
        print(json.dumps(dict(run_id=result['run_id'],eligible=result['eligible_origins'],plan_eligible=result['nominal_plan_eligible'],status='PASS')),flush=True)
    require(len(results)==22 and len({r['run_id'] for r in results})==22,'Global source identity collision')
    saved=load(PILOT/'hvac_control_expansion_v1/MATCHED_SIZE_TIMESTAMP_PLAN.json');recomputed=[x for r in canonical_manifest()['runs'][::3] for x in matched_size_plan(r)]
    require(saved==recomputed,'Frozen Mdiv timestamp assignment differs from implementation')
    mdiv={g:Counter(r['policy_pair'] for r in saved if r['group_id']==g) for g in ('D2_G146','D2_G174')}
    require(all(dict(v)=={'C15_C45':426,'original_N_X':426} for v in mdiv.values()),'Mdiv quotas changed')
    from hvac_control_expansion_v1.integrity import reservation_check
    reservations=reservation_check(canonical_manifest())
    foldcounts=[]
    for f in folds:
        alts=[r for r in results if r['kind']=='B1' and r['policy']!='NREF'];trainextra=sum(r['eligible_origins'] for r in alts if r['group_id'] in f['train_groups']);heldextra=sum(r['eligible_origins'] for r in alts if r['group_id'] in f['held_groups'])
        foldcounts.append(dict(fold=f['fold'],train_groups=f['train_groups'],held_groups=f['held_groups'],M0_training=10224,Mdiv_training=10224,Mfull_training=10224+trainextra,original_held=3408,B1_held_transfer=heldextra))
    b2i=load(PILOT/'hvac_control_expansion_b2i_v1/FINAL_VERIFICATION.json');require(b2i['status']=='PASS_READ_ONLY' and b2i['all_B1_slots_completed']==6,'B1 verification incomplete')
    ledger=PILOT/'hvac_control_expansion_b2i_v1/runtime_state/attempts.sqlite3';source(ledger)
    db=sqlite3.connect(ledger.as_uri()+'?mode=ro',uri=True)
    try:
        require(db.execute('PRAGMA integrity_check').fetchone()[0]=='ok','Ledger corrupt')
        terminal=list(db.execute('SELECT run_id,state FROM events'));require({rid for rid,state in terminal}=={r['run_id'] for r in canonical_manifest()['runs'][3:]} and all(state=='CONSUMED_COMPLETED' for rid,state in terminal),'G146 terminal ledger mismatch')
        require(len(list(db.execute("SELECT name FROM sqlite_master WHERE type='trigger'")))==10,'Append-only triggers changed')
    finally:db.close()
    for p,h in INPUT_HASHES.items():require(sha(p)==h,'Source changed during audit')
    result=dict(status='PASS_READ_ONLY_ELIGIBILITY_AUDIT',runs=results,original_development=13632,B1_alternative_eligible=3408,B1_native_QA_eligible=1704,
        total_candidate_development_excluding_NREF=17040,folds=foldcounts,Mdiv_quotas={g:dict(v) for g,v in mdiv.items()},
        Mdiv_timestamp_plan_sha256=sha(PILOT/'hvac_control_expansion_v1/MATCHED_SIZE_TIMESTAMP_PLAN.json'),reservations=reservations,
        common25=features,target_columns=schema['targets'],validation_outcomes_opened=0,protected_outcomes_opened=0,new_feature_rows_created=0,models_executed=0,simulation_calls=0)
    if record:
        write_new(HOME/'AUDIT_RESULTS.json',result);write_new(HOME/'AUDIT_SOURCE_HASHES.json',INPUT_HASHES)
    return result

if __name__=='__main__':
    import argparse
    from hvac_control_expansion_b2f_v1.tests import offline_guard
    p=argparse.ArgumentParser();p.add_argument('--verify',action='store_true');args=p.parse_args()
    with offline_guard():
        r=audit(record=not args.verify)
        if args.verify:require(r==read(HOME/'AUDIT_RESULTS.json'),'Recomputed audit differs')
    print(json.dumps({k:v for k,v in r.items() if k!='runs'},indent=2))
