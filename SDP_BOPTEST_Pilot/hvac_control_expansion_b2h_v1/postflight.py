"""Read-only evidence verification and indexing after the one frozen CLI attempt."""
import sqlite3,json
from . import HOME,ROOT,V2,PILOT,RID
from hvac_control_expansion_b2f_v1.packaging import read,sha,require,write_new,inventory,chain,verify_package

def verify_historical():
    snapshot=read(HOME/'FROZEN_V2_INPUT_SNAPSHOT.json')
    for name,h in snapshot['files'].items():require(sha(V2/name)==h,'Frozen v2 input/qualification/history changed: '+name)
    from hvac_control_expansion_b2g_v2.integrity import verify_frozen,verify_v1,historical_integrity
    identity=verify_frozen();v1=verify_v1();earlier=historical_integrity()
    extras={p.relative_to(V2).as_posix() for p in V2.rglob('*') if p.is_file() and '__pycache__' not in p.parts}-set(snapshot['files'])
    require(all(name.startswith(('runtime_state/','corrected_c45_package/')) or name in
        {'LIVE_EXECUTION.json','LEDGER_INVENTORY_AFTER.json','HISTORICAL_PRESERVATION_AFTER.json'} for name in extras),'Unexpected addition to frozen v2 directory')
    return dict(status='PASS',frozen_v2_files_unchanged=len(snapshot['files']),frozen_implementation_sha256=identity,
        planned_append_only_v2_artifact_additions=len(extras),v1_failed_history=v1,earlier_pilot_B2F_D2=earlier)

def verify():
    execution=read(V2/'LIVE_EXECUTION.json');write_new(HOME/'EXECUTION_RESULT_REFERENCE.json',dict(path=str(V2/'LIVE_EXECUTION.json'),sha256=sha(V2/'LIVE_EXECUTION.json'),result=execution))
    require(execution.get('state')=='CONSUMED_COMPLETED','STOP: qualified attempt not completed: '+str(execution.get('error')))
    require(execution['corrected_finalization']['status']=='PASS_CORRECTED_OFFLINE_FINALIZATION','STOP: finalization not valid')
    status=execution['raw_result'];require(status['classification']=='PASS_VALID_RAW' and status['data_is_fabricated'] is False,'Real valid raw data required')
    require((status['deploy_attempts'],status['initialization_attempts'],status['advance_requests_attempted'],status['advance_responses_received'])==(1,1,864,864),'Mutation budget mismatch')
    require((status['advances'],status['endpoints'],status['native_samples'],status['unresolved_events'])==(864,865,8641,0),'Mandatory support/count mismatch')
    require(status['cleanup']=='STOP_ACK_AND_REMOVAL_VERIFIED','Cleanup not verified')
    batch=V2/'runtime_state/batches/B2G_G174_C45_ONLY';raw=batch/RID
    dbpath=V2/'runtime_state/attempts.sqlite3';db=sqlite3.connect(dbpath.as_uri()+'?mode=ro',uri=True)
    try:
        require(db.execute('PRAGMA integrity_check').fetchone()[0]=='ok','Continuation ledger integrity')
        claims=list(db.execute('SELECT run_id,batch_id,record FROM reservations'));require(len(claims)==1 and claims[0][0]==RID,'Unauthorized/duplicate reservation')
        events=list(db.execute('SELECT run_id,state,record FROM events'));require(len(events)==1 and events[0][:2]==(RID,'CONSUMED_COMPLETED'),'Invalid terminal ledger state')
        terminal=json.loads(events[0][2]);require(sha(batch/(RID+'_SEALED_MANIFEST.json'))==terminal['seal_sha256'],'Ledger seal binding changed')
        triggers=list(db.execute("SELECT name FROM sqlite_master WHERE type='trigger'"));require(len(triggers)==10,'Append-only triggers changed')
    finally:db.close()
    files=read(batch/(RID+'_SEALED_MANIFEST.json'))['files'];require(inventory(raw)==files,'Sealed run artifact set/hash mismatch')
    nested=read(raw/'ARTIFACT_MANIFEST.json')['files'];require(nested=={n:h for n,h in files.items() if n!='ARTIFACT_MANIFEST.json'},'Nested manifest mismatch')
    receipts=chain(raw/'receipt_order.jsonl');final=verify_package(batch,V2/'corrected_c45_package')
    outer=read(V2/'corrected_c45_package/BATCH_ARTIFACT_MANIFEST.json')['files'];require(RID+'/ARTIFACT_MANIFEST.json' in outer,'Nested manifest omitted from corrected outer scope')
    require(read(raw/'DEPLOYED_FMU_IDENTITY.json')['sha256']=='158008fa3b635280a67dfed8bab5804d1f9a96d218b467dfebab77e5cbf8b86a','Deployed FMU mismatch')
    validation=read(batch/'C45_VALIDATION.json');require(validation==execution['validation'],'Recorded independent verification changed')
    history=verify_historical()
    from hvac_control_expansion_b2g_v2.launcher import C45Registry
    inventory_after=C45Registry(V2/'runtime_state',read(V2/'LEDGER_BASELINE.json')).inventory()
    require([r['status'] for r in inventory_after[:3]]==['CONSUMED_COMPLETED']*3,'Effective G174 ledger chain incomplete')
    require(all(r['status']=='UNUSED_NOT_AUTHORIZED' for r in inventory_after[3:]),'G146 slot unexpectedly consumed/authorized')
    write_new(HOME/'CONTINUATION_LEDGER_INDEX.json',dict(parent_path=str(PILOT/'runtime_state/attempts.sqlite3'),parent_sha256=sha(PILOT/'runtime_state/attempts.sqlite3'),
        extension_path=str(dbpath),extension_sha256=sha(dbpath),inventory=inventory_after,history_rewritten=False))
    write_new(HOME/'RAW_C45_ARTIFACT_INDEX.json',dict(source_root=str(raw),files=files,source_seal_path=str(batch/(RID+'_SEALED_MANIFEST.json')),
        source_seal_sha256=sha(batch/(RID+'_SEALED_MANIFEST.json')),data_is_fabricated=False,
        storage_reason='Qualified launcher fixed paths retained; no raw evidence duplicated or redirected'))
    write_new(HOME/'CORRECTED_FINALIZATION_REFERENCE.json',dict(source_package=str(V2/'corrected_c45_package'),verification=final,files=inventory(V2/'corrected_c45_package')))
    write_new(HOME/'HISTORICAL_PRESERVATION_AFTER.json',history)
    report=dict(status='PASS',run_id=RID,actual_run=status,independent_validation=validation,receipt_chain=receipts,
        per_run_sealed_files=len(files),corrected_finalization=final,historical_preservation='PASS',
        parent_ledger_records_rewritten=False,continuation_reservations=1,G146_initiated=0,retries=0,models_executed=0)
    write_new(HOME/'POSTRUN_VERIFICATION.json',report)
    return report

if __name__=='__main__':
    from hvac_control_expansion_b2f_v1.tests import offline_guard
    with offline_guard():
        result=verify();print(json.dumps(dict(status=result['status'],raw_status=result['actual_run']['classification'],
            corrected_finalization=result['corrected_finalization'],sealed_files=result['per_run_sealed_files'],G146_initiated=0),indent=2))
