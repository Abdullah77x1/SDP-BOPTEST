"""Read-only inherited evidence checks and new implementation freeze."""
import csv,sqlite3
from . import HOME,VERSION
from .campaign import canonical_manifest,validate_manifest
from stage4e_d2i_1.common import ROOT,read,sha,digest,require,save_new,verify_preservation

DESIGN=ROOT.parent/'hvac_expansion_design_B1_2026-11-18'

def source_evidence():
    rows=list(csv.DictReader((DESIGN/'SOURCE_EVIDENCE.csv').open(encoding='utf-8-sig')))
    for r in rows:require(sha(r['absolute_path'])==r['sha256'],'B1 source changed: '+r['relative_path'])
    return rows

def reservation_check(m):
    """Metadata only: no validation/protected outcomes opened."""
    plan=read(ROOT/'stage4e_d2p/COLLECTION_AND_PARTITION_PLAN.json');groups=[]
    def walk(obj):
        if isinstance(obj,dict):
            if {'warmup_start_s','scored_start_s','scored_end_s'}<=obj.keys():groups.append(obj)
            for v in obj.values():walk(v)
        elif isinstance(obj,list):
            for v in obj:walk(v)
    walk(plan);checked=0
    historical=[('validation_mix_14',7*86400,17*86400),('protected_heat_334',327*86400,337*86400),
                ('protected_custom_210',203*86400,213*86400),('exposed_peak_cool_family',275*86400,296*86400)]
    for run in m['runs'][::3]:
        for g in groups:
            # Exact original parent repeat is intentional, never an independent group.
            if (g['warmup_start_s'],g['scored_start_s'],g['scored_end_s'])==(run['warmup_start'],run['start'],run['end']):continue
            require(run['end']+5400<g['warmup_start_s']-5700 or g['scored_end_s']+5400<run['warmup_start']-5700,
                    'Reserved/dependency footprint collision: '+str(g.get('group_id')))
            checked+=1
        for name,start,end in historical:
            require(run['end']+5400<start-5700 or end+5400<run['warmup_start']-5700,'Historical reservation collision: '+name)
            checked+=1
    return dict(metadata_comparisons=checked,protected_outcomes_opened=0)

def old_inventory():
    p=ROOT/'stage4e_d2_prep02/runtime_state/attempts.sqlite3'
    db=sqlite3.connect(p.as_uri()+'?mode=ro',uri=True)
    try:
        require(db.execute('PRAGMA integrity_check').fetchone()[0]=='ok','Original registry integrity')
        rows=list(db.execute('SELECT run_id FROM reservations'))
        require(not any(r[0].startswith('B1V01_') for r in rows),'B1 slot already present in old registry')
        require(db.execute('SELECT r.run_id FROM reservations r LEFT JOIN events e ON e.run_id=r.run_id WHERE e.run_id IS NULL').fetchone() is None,'Unclosed original reservation')
        import json
        stored=db.execute('SELECT r.batch_id,r.record,e.record FROM reservations r JOIN events e ON r.run_id=e.run_id WHERE r.run_id=?',('D2_G174_N',)).fetchone()
        require(stored is not None,'Archived G174 native reservation absent')
        bid,reservation,event=stored;reservation=json.loads(reservation);event=json.loads(event)
        base=p.parent/'batches'/bid;seal=base/'D2_G174_N_SEALED_MANIFEST.json'
        require(sha(seal)==event['seal_sha256'],'Archived native seal changed')
        directory=base/'D2_G174_N';entries=read(seal)['files']
        require({f.relative_to(directory).as_posix() for f in directory.rglob('*') if f.is_file()}==set(entries),'Archived native file set changed')
        for name,h in entries.items():
            f=(directory/name).resolve();require(f.is_relative_to(directory.resolve()),'Archive path traversal')
            require(sha(f)==h,'Archived native raw integrity: '+name)
        return dict(original_consumed_reservations=len(rows),original_db_sha256=sha(p),old_registry_modified=False,
                    archived_G174_native_sealed_files_verified=len(entries))
    finally:db.close()

def verify_sources():
    rows=source_evidence();m=canonical_manifest();validate_manifest(m)
    return dict(status='PASS',b1_source_hashes_verified=len(rows),inherited_preservation=verify_preservation(),
                reservations=reservation_check(m),original_slots=old_inventory())

def freeze():
    report=verify_sources();save_new(HOME/'campaign_manifest.json',canonical_manifest())
    from .contracts import matched_size_plan
    save_new(HOME/'MATCHED_SIZE_TIMESTAMP_PLAN.json',[row for run in canonical_manifest()['runs'][::3] for row in matched_size_plan(run)])
    sources={str(p.resolve()):sha(p) for p in HOME.glob('*.py')}
    for p in DESIGN.iterdir():
        if p.is_file():sources[str(p.resolve())]=sha(p)
    for r in source_evidence():sources[r['absolute_path']]=r['sha256']
    # Bind all imported Python implementations, transport/runtime code included.
    for p in ROOT.rglob('*.py'):
        if '.venv' in p.parts or '__pycache__' in p.parts or HOME in p.parents:continue
        sources[str(p.resolve())]=sha(p)
    for p in [HOME/'campaign_manifest.json',HOME/'MATCHED_SIZE_TIMESTAMP_PLAN.json',HOME/'AUTHORIZATION_SOURCE.json',HOME/'OFFLINE_QA.json',HOME/'OFFLINE_TEST_RESULTS.txt',
              HOME/'REGRESSION_TEST_RESULTS.txt',ROOT/'stage4e_d2_prep02/runtime_state/attempts.sqlite3']:
        sources[str(p.resolve())]=sha(p)
    save_new(HOME/'SOURCE_INTEGRITY_REPORT.json',report)
    save_new(HOME/'IMPLEMENTATION_MANIFEST.json',dict(version=VERSION,files=sources))
    return sha(HOME/'IMPLEMENTATION_MANIFEST.json')

def verify_frozen():
    p=HOME/'IMPLEMENTATION_MANIFEST.json';data=read(p)
    require(data['version']==VERSION,'Wrong implementation version')
    for name,h in data['files'].items():require(sha(name)==h,'Frozen dependency changed: '+name)
    require(read(HOME/'campaign_manifest.json')==canonical_manifest(),'Campaign changed')
    return sha(p)
