"""Read-only historical checks, exact approval, and immutable source freeze."""
import sqlite3,json
from pathlib import Path
from . import HOME,ROOT,IDS,VERSION,STATE
from hvac_control_expansion_b2f_v1.packaging import read,sha,digest,require,write_new
from hvac_control_expansion_v1.campaign import canonical_manifest,validate_manifest,nominal

def manifest():
    m=read(ROOT/'hvac_control_expansion_v1/campaign_manifest.json');validate_manifest(m);return m

def runs():return manifest()['runs'][3:]

def historical():
    from hvac_control_expansion_b2h_v1.verify import verify
    return verify()

def baseline():
    p=ROOT/'hvac_control_expansion_b2h_v1/CONTINUATION_LEDGER_INDEX.json';idx=read(p)
    anchors={str(p):sha(p)}
    for kind in ('parent','extension'):
        path=Path(idx[kind+'_path']);require(sha(path)==idx[kind+'_sha256'],'Historical ledger changed');anchors[str(path)]=sha(path)
    slots=idx['inventory'];require([s['run_id'] for s in slots]==[r['run_id'] for r in manifest()['runs']],'Slot order drift')
    require([s['status'] for s in slots]==['CONSUMED_COMPLETED']*3+['UNUSED_NOT_AUTHORIZED']*3,'Original chain not complete/unused as required')
    return dict(version=VERSION,chain_anchors=anchors,slots=[{k:v for k,v in s.items() if k!='reservation'} for s in slots])

def no_claim(rid):
    require(rid in IDS,'G146 only')
    for directory in ROOT.glob('hvac_control_expansion*'):
        path=directory/'runtime_state/attempts.sqlite3'
        if path.is_file():
            db=sqlite3.connect(path.as_uri()+'?mode=ro',uri=True)
            try:require(db.execute('SELECT run_id FROM reservations WHERE run_id=?',(rid,)).fetchone() is None,'Consumed run; no retry: '+str(path))
            finally:db.close()
        state=directory/'runtime_state'
        if state.exists():require(not list(state.rglob(rid+'/ATTEMPT_STARTED.json')),'Orphan attempt; no replacement')

def verify_frozen(home=HOME):
    f=read(home/'IMPLEMENTATION_MANIFEST.json');require(f['version']==VERSION,'Version mismatch')
    for p,h in f['files'].items():require(sha(p)==h,'Frozen source/config changed: '+p)
    require(read(home/'RUN_MANIFEST.json')['runs']==runs(),'G146 manifest drift')
    return sha(home/'IMPLEMENTATION_MANIFEST.json')

def expected_approval(home,identity):
    return dict(version=VERSION,status='EXPLICITLY_AUTHORIZED_B2I_G146_THREE_ORDERED_ATTEMPTS',
        implementation_sha256=identity,run_manifest_sha256=sha(home/'RUN_MANIFEST.json'),campaign_sha256=digest(manifest()),
        run_ids=IDS,individual_budgets={rid:dict(maximum_instances=1,maximum_initializations=1,maximum_advances=864) for rid in IDS},
        maximum_instances=3,maximum_advances=2592,request_sha256=sha(home/'REQUEST_SOURCE.json'),
        user_authorization_text=read(home/'REQUEST_SOURCE.json')['text'])

def authorize(path,home=HOME):
    require(path is not None,'Explicit approval required before any runtime contact')
    identity=verify_frozen(home);a=read(path);expected=expected_approval(home,identity)
    require(a==expected,'Exact three-run approval/budget/source mismatch')
    require(read(home/'OFFLINE_QUALIFICATION.json')['status']=='PASS','Mandatory qualification failed')
    return dict(implementation_sha256=identity,approval_sha256=sha(path),run_ids=IDS)

def freeze(request):
    require(read(HOME/'OFFLINE_QUALIFICATION.json')['status']=='PASS','STOP: qualification failed')
    for rid in IDS:no_claim(rid)
    write_new(HOME/'HISTORICAL_PRESERVATION_BEFORE.json',historical());write_new(HOME/'LEDGER_BASELINE.json',baseline())
    from hvac_control_expansion_b2g_v2.integrity import runtime_requirements
    write_new(HOME/'RUNTIME_IDENTITY_REQUIREMENTS.json',runtime_requirements())
    text=Path(request).read_text(encoding='utf-8-sig')
    require('explicitly authorize exactly' in text and all(r in text for r in IDS),'Explicit three-run source missing')
    write_new(HOME/'REQUEST_SOURCE.json',dict(text=text,source_path=str(request),source_sha256=sha(request)))
    write_new(HOME/'RUN_MANIFEST.json',dict(version=VERSION,runs=runs(),run_ids=IDS,campaign_sha256=digest(manifest()),
        maximum_instances=3,maximum_advances=2592,one_attempt_each=True,ordered=True,
        schedules={r['run_id']:[nominal(r,t) for t in range(r['start'],r['end'],300)] for r in runs()}))
    files={str(p):sha(p) for p in HOME.iterdir() if p.is_file()}
    for ns,mf in [('hvac_control_expansion_v1','IMPLEMENTATION_MANIFEST.json'),('hvac_control_expansion_b2g_v2','IMPLEMENTATION_MANIFEST.json')]:
        for p,h in read(ROOT/ns/mf)['files'].items():files[p]=h
    for p in (ROOT/'hvac_control_expansion_b2f_v1').glob('*.py'):files[str(p)]=sha(p)
    for p in (ROOT/'hvac_control_expansion_b2h_v1').glob('*.py'):files[str(p)]=sha(p)
    files.update(read(HOME/'LEDGER_BASELINE.json')['chain_anchors'])
    for p in (ROOT.parent/'hvac_expansion_design_B1_2026-11-18').iterdir():
        if p.is_file():files[str(p)]=sha(p)
    write_new(HOME/'IMPLEMENTATION_MANIFEST.json',dict(version=VERSION,files=files))
    identity=verify_frozen();write_new(HOME/'AUTHORIZATION.json',expected_approval(HOME,identity))
    return dict(status='PASS_FROZEN',implementation_sha256=identity)
