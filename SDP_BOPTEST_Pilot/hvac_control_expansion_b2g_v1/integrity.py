"""Frozen inputs and read-only ledger-chain checks; no simulator requests."""
import sqlite3,json
from . import HOME,ROOT,PILOT,B2F,RID,VERSION,STATE
from hvac_control_expansion_b2f_v1.packaging import read,sha,digest,require,write_new
from hvac_control_expansion_v1.campaign import canonical_manifest,validate_manifest,nominal

def manifest():
    m=read(PILOT/'campaign_manifest.json');validate_manifest(m)
    return m

def run_definition():return next(r for r in manifest()['runs'] if r['run_id']==RID)

def require_only(run_ids):
    require(run_ids==[RID],'Only the one G174 C45 slot is authorized; pilot reruns/G146 prohibited')

def parent_inventory():
    p=PILOT/'runtime_state/attempts.sqlite3';db=sqlite3.connect(p.as_uri()+'?mode=ro',uri=True)
    try:
        require(db.execute('PRAGMA integrity_check').fetchone()[0]=='ok','Parent ledger corrupt')
        slots={rid:json.loads(record) for rid,record in db.execute('SELECT run_id,definition FROM slots')}
        reservations={rid:json.loads(record) for rid,record in db.execute('SELECT run_id,record FROM reservations')}
        events={rid:state for rid,state in db.execute('SELECT run_id,state FROM events')}
        require(set(reservations)==set(events)=={'B1V01_G174_NREF','B1V01_G174_C15'},'Unexpected parent consumption')
        require(all(state=='CONSUMED_COMPLETED' for state in events.values()),'Pilot not complete')
        require(RID in slots and RID not in reservations,'C45 parent slot already consumed')
        return dict(parent_db_sha256=sha(p),slots=slots,consumed=events)
    finally:db.close()

def deny_existing_c45_claim():
    """Every continuation must consult this chain; changing output does not grant a new slot."""
    claims=[]
    for directory in ROOT.glob('hvac_control_expansion*'):
        dbpath=directory/'runtime_state/attempts.sqlite3'
        if not dbpath.is_file():continue
        db=sqlite3.connect(dbpath.as_uri()+'?mode=ro',uri=True)
        try:
            if db.execute('SELECT run_id FROM reservations WHERE run_id=?',(RID,)).fetchone():claims.append(str(dbpath))
        finally:db.close()
    require(not claims,'C45 already consumed in ledger chain; no retry: '+str(claims))
    # Detect orphan real attempt directories as well, without opening protected outcomes.
    for directory in ROOT.glob('hvac_control_expansion*'):
        state=directory/'runtime_state'
        if state.exists():
            require(not list(state.rglob(RID+'/ATTEMPT_STARTED.json')),'Existing C45 evidence; no replacement')

def baseline():
    parent=parent_inventory();m=manifest();slots=[]
    for r in m['runs']:
        slots.append(dict(run_id=r['run_id'],group_id=r['group_id'],partition=r['partition'],category='development',
            status=parent['consumed'].get(r['run_id'],'UNUSED_NOT_AUTHORIZED'),run_sha256=digest(r)))
    return dict(version=VERSION,parent_ledger_path=str(PILOT/'runtime_state/attempts.sqlite3'),
                parent_ledger_sha256=parent['parent_db_sha256'],parent_consumed_slots=parent['consumed'],slots=slots)

def historical_integrity():
    from hvac_control_expansion_b2f_v1.verification import verify_delivery
    from hvac_control_expansion_b2f_v1.packaging import verify_package
    old=verify_delivery()
    f=read(B2F/'B2F_IMPLEMENTATION_MANIFEST.json')
    for name,h in f['files'].items():require(sha(B2F/name)==h,'B2F evidence changed: '+name)
    require(sha(B2F/'B2F_IMPLEMENTATION_MANIFEST.json')=='917a80c01efde5d9615bafa4f5dc84914ae1851b85fa4f9058f12a69841a3992','B2F freeze changed')
    from hvac_control_expansion_v1.integrity import verify_frozen,source_evidence,reservation_check
    implementation=verify_frozen();source_evidence();reservation_check(manifest())
    from stage4e_d2i_1.common import verify_preservation
    d2=verify_preservation()
    return dict(original_delivery=old,B2F_frozen_files=len(f['files']),B1_implementation_sha256=implementation,
        corrected_pilot_finalization=verify_package(PILOT/'runtime_state/batches/B1_G174_INITIAL_PILOT',B2F/'corrected_pilot_package'),
        D2_preservation=d2,parent_inventory=parent_inventory())

def verify_frozen():
    frozen=read(HOME/'IMPLEMENTATION_MANIFEST.json')
    require(frozen['version']==VERSION,'Wrong launcher version')
    for name,h in frozen['files'].items():require(sha(name)==h,'B2G frozen source/config changed: '+name)
    require(read(HOME/'RUN_MANIFEST.json')['run']==run_definition(),'C45 manifest drift')
    return sha(HOME/'IMPLEMENTATION_MANIFEST.json')

def freeze(request_path):
    require(read(HOME/'OFFLINE_QUALIFICATION.json')['status']=='PASS','Mandatory offline qualification failed')
    deny_existing_c45_claim();history=historical_integrity();r=run_definition();m=manifest()
    # Read-only current runtime identity; never deploy a disposable preflight.
    from stage4e_d1_v2.runtime import verify_runtime
    runtime=verify_runtime();require(runtime['classification']=='PASS','Pinned runtime rejected')
    text=__import__('pathlib').Path(request_path).read_text(encoding='utf-8-sig')
    require(RID in text and 'explicitly authorizes this one run' in text,'Exact user authorization source required')
    write_new(HOME/'REQUEST_SOURCE.json',dict(text=text,source_sha256=sha(request_path)))
    write_new(HOME/'PREFLIGHT_INTEGRITY.json',history);write_new(HOME/'RUNTIME_IDENTITY_BEFORE_FREEZE.json',runtime)
    write_new(HOME/'LEDGER_BASELINE.json',baseline())
    write_new(HOME/'RUN_MANIFEST.json',dict(version=VERSION,run=r,campaign_sha256=digest(m),maximum_instances=1,
        maximum_advances=864,run_ids=[RID],schedule=[nominal(r,t) for t in range(r['start'],r['end'],300)],
        finalizer='hvac_control_expansion_b2f_v1.packaging.finalize',remaining_G146_authorized=False))
    files={str(p.resolve()):sha(p) for p in HOME.glob('*.py')}
    for name,h in read(PILOT/'IMPLEMENTATION_MANIFEST.json')['files'].items():files[name]=h
    for name,h in read(B2F/'B2F_IMPLEMENTATION_MANIFEST.json')['files'].items():
        if name.endswith('.py'):files[str((B2F/name).resolve())]=h
    for p in [B2F/'B2F_IMPLEMENTATION_MANIFEST.json',PILOT/'DELIVERY_MANIFEST.json',PILOT/'runtime_state/attempts.sqlite3',
              HOME/'RUN_MANIFEST.json',HOME/'LEDGER_BASELINE.json',HOME/'OFFLINE_QUALIFICATION.json',HOME/'OFFLINE_TEST_RESULTS.txt',
              HOME/'REQUEST_SOURCE.json',HOME/'PREFLIGHT_INTEGRITY.json',HOME/'RUNTIME_IDENTITY_BEFORE_FREEZE.json']:
        files[str(p.resolve())]=sha(p)
    write_new(HOME/'IMPLEMENTATION_MANIFEST.json',dict(version=VERSION,files=files))
    write_new(HOME/'AUTHORIZATION.json',dict(version=VERSION,status='EXPLICITLY_AUTHORIZED_BY_B2G_USER_REQUEST',
        implementation_sha256=sha(HOME/'IMPLEMENTATION_MANIFEST.json'),run_manifest_sha256=sha(HOME/'RUN_MANIFEST.json'),
        campaign_sha256=digest(m),run_ids=[RID],maximum_instances=1,maximum_advances=864,
        request_sha256=sha(HOME/'REQUEST_SOURCE.json'),user_authorization_text=text))
    from .launcher import C45Registry
    C45Registry.create(STATE,read(HOME/'LEDGER_BASELINE.json'))
    return dict(status='QUALIFIED_AND_FROZEN_C45_ONLY',implementation_sha256=verify_frozen(),run_manifest_sha256=sha(HOME/'RUN_MANIFEST.json'))
