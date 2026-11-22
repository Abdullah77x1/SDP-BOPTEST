"""B1 ledger versioned from PREP02 registry (original unchanged); no network or simulator imports.

Reservation is consumption, even if the process dies before deploy. No reset,
resume, replacement or delete API. This is local audit bookkeeping, not custody.
"""
import json,re,sqlite3
from contextlib import contextmanager
from pathlib import Path
from datetime import datetime,timezone
from stage4e_d2i_1.common import digest,read,require,sha,save_new

def utc():return datetime.now(timezone.utc).isoformat()
def safe_id(value):
    require(isinstance(value,str) and re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,79}',value),'Unsafe identifier')
    return value

class Registry:
    def __init__(self,root,baseline):
        self.root=Path(root).resolve();self.baseline=baseline;self.db=self.root/'attempts.sqlite3'
        require(self.db.is_file(),'Registry missing; offline reviewed initialization required')
        self.validate()

    @classmethod
    def create(cls,root,baseline):
        root=Path(root).resolve();root.mkdir() # exclusive; never rebuild on existing evidence
        (root/'batches').mkdir()
        db=sqlite3.connect(root/'attempts.sqlite3')
        try:
            db.executescript('''
            CREATE TABLE metadata(key TEXT PRIMARY KEY,value TEXT NOT NULL);
            CREATE TABLE slots(run_id TEXT PRIMARY KEY,definition TEXT NOT NULL);
            CREATE TABLE batches(batch_id TEXT PRIMARY KEY,record TEXT NOT NULL);
            CREATE TABLE reservations(run_id TEXT PRIMARY KEY REFERENCES slots(run_id),batch_id TEXT NOT NULL REFERENCES batches(batch_id),record TEXT NOT NULL);
            CREATE TABLE events(id INTEGER PRIMARY KEY,run_id TEXT UNIQUE NOT NULL REFERENCES reservations(run_id),state TEXT NOT NULL,record TEXT NOT NULL);
            ''')
            for table in ('metadata','slots','batches','reservations','events'):
                for op in ('UPDATE','DELETE'):
                    db.execute(f"CREATE TRIGGER no_{op}_{table} BEFORE {op} ON {table} BEGIN SELECT RAISE(ABORT,'APPEND_ONLY_NO_RESET'); END")
            db.execute('INSERT INTO metadata VALUES (?,?)',('baseline_sha256',digest(baseline)))
            for slot in baseline['slots']:
                db.execute('INSERT INTO slots VALUES (?,?)',(slot['run_id'],json.dumps(slot,sort_keys=True)))
            db.commit()
        finally:db.close()
        return cls(root,baseline)

    @contextmanager
    def connect(self):
        db=sqlite3.connect(self.db,timeout=10,isolation_level=None)
        try:
            db.execute('PRAGMA foreign_keys=ON');db.execute('PRAGMA synchronous=FULL')
            with db:yield db
        finally:db.close() # sqlite's transaction context alone does not close Windows handles

    def validate(self):
        with self.connect() as db:
            require(db.execute('PRAGMA integrity_check').fetchone()[0]=='ok','Registry corruption')
            require(db.execute('SELECT value FROM metadata WHERE key=?',('baseline_sha256',)).fetchone()==(digest(self.baseline),),'Registry baseline mismatch')
            actual={rid:json.loads(s) for rid,s in db.execute('SELECT run_id,definition FROM slots')}
            require(actual=={s['run_id']:s for s in self.baseline['slots']},'Slot inventory changed')
            for table in ('metadata','slots','batches','reservations','events'):
                for op in ('UPDATE','DELETE'):
                    require(db.execute('SELECT name FROM sqlite_master WHERE type=? AND name=?',('trigger',f'no_{op}_{table}')).fetchone() is not None,'Append-only trigger missing')

    def inventory(self):
        self.validate()
        with self.connect() as db:
            reserved={rid:json.loads(rec) for rid,rec in db.execute('SELECT run_id,record FROM reservations')}
            events={}
            for rid,state,rec in db.execute('SELECT run_id,state,record FROM events ORDER BY id'):events[rid]=(state,json.loads(rec))
        result=[]
        for s in self.baseline['slots']:
            row=dict(s)
            if s['run_id'] in reserved:
                row['status']=events.get(s['run_id'],('CONSUMED_RESERVED_OR_INTERRUPTED',None))[0]
                row['reservation']=reserved[s['run_id']]
            result.append(row)
        return result

    def check_selection(self,runs):
        require(runs and len({r['run_id'] for r in runs})==len(runs),'Duplicate/empty run selection')
        slots={s['run_id']:s for s in self.inventory()}
        for r in runs:
            s=slots.get(r['run_id']);require(s is not None,'Unknown run')
            require(s['status']=='UNUSED_NOT_AUTHORIZED','Consumed/reused/protected slot cannot proceed')
            require(s['category'] in ('development','validation'),'Protected or preflight slot blocked')
            require(s['run_sha256']==digest(r),'Run/group/partition configuration changed')
        require(all(r['partition']=='development' for r in runs),'B1 development only')

    def new_batch(self,batch_id,runs,binding):
        safe_id(batch_id);self.check_selection(runs)
        path=self.root/'batches'/batch_id
        record={'batch_id':batch_id,'run_ids':[r['run_id'] for r in runs],'binding':binding,'created_utc':utc()}
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            path.mkdir() # exclusive; failure leaves no runnable replacement path
            db.execute('INSERT INTO batches VALUES (?,?)',(batch_id,json.dumps(record,sort_keys=True)))
            save_new(path/'BATCH_STARTED.json',record)
            db.commit()
        return path

    def reserve(self,batch_id,run):
        safe_id(batch_id);safe_id(run['run_id']);self.validate()
        path=self.root/'batches'/batch_id/run['run_id']
        require(not path.exists() and not path.is_symlink(),'Existing run directory refused')
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            require(db.execute('SELECT r.run_id FROM reservations r LEFT JOIN events e ON e.run_id=r.run_id WHERE e.run_id IS NULL').fetchone() is None,
                'Unclosed reservation: no concurrent instance or automatic interruption recovery')
            s=db.execute('SELECT definition FROM slots WHERE run_id=?',(run['run_id'],)).fetchone()
            require(s is not None,'Unknown run');s=json.loads(s[0])
            require(s['status']=='UNUSED_NOT_AUTHORIZED' and s['category'] in ('development','validation'),'Consumed/reference/protected/preflight slot refused')
            require(s['run_sha256']==digest(run),'Frozen run identity changed')
            b=db.execute('SELECT record FROM batches WHERE batch_id=?',(batch_id,)).fetchone()
            require(b is not None and run['run_id'] in json.loads(b[0])['run_ids'],'Run not selected in batch')
            record={'run_id':run['run_id'],'group_id':run['group_id'],'partition':run['partition'],
                'run_sha256':digest(run),'reserved_utc':utc(),'evidence_relative_path':path.relative_to(self.root).as_posix()}
            db.execute('INSERT INTO reservations VALUES (?,?,?)',(run['run_id'],batch_id,json.dumps(record,sort_keys=True)))
            db.commit() # irreversible consumption BEFORE any output/deploy
        save_new(path.parent/(run['run_id']+'_RESERVATION.json'),record)
        return path

    def finish(self,run_id,state,record):
        require(state in ('CONSUMED_COMPLETED','CONSUMED_FAILED','CONSUMED_INTERRUPTED'),'Invalid terminal state')
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            require(db.execute('SELECT run_id FROM reservations WHERE run_id=?',(run_id,)).fetchone() is not None,'No reservation')
            require(db.execute('SELECT id FROM events WHERE run_id=?',(run_id,)).fetchone() is None,'Terminal state immutable')
            db.execute('INSERT INTO events(run_id,state,record) VALUES (?,?,?)',(run_id,state,json.dumps(record,sort_keys=True)))
            db.commit()

    def verify_evidence(self):
        self.validate()
        with self.connect() as db:
            batches=list(db.execute('SELECT batch_id,record FROM batches'))
            reservations=list(db.execute('SELECT run_id,batch_id,record FROM reservations'))
            events={rid:(s,json.loads(r)) for rid,s,r in db.execute('SELECT run_id,state,record FROM events')}
        known={b for b,_ in batches}
        require({p.name for p in (self.root/'batches').iterdir()}==known,'Unregistered batch directory; refuse recovery/reset')
        for bid,rec in batches:
            base=self.root/'batches'/bid
            require(read(base/'BATCH_STARTED.json')==json.loads(rec),'Batch binding changed')
            manifest=base/'BATCH_ARTIFACT_MANIFEST.json'
            if manifest.exists():
                entries=read(manifest)['files']
                require({p.relative_to(base).as_posix() for p in base.rglob('*') if p.is_file() and p!=manifest}==set(entries),'Batch file set changed')
                for name,h in entries.items():
                    p=(base/name).resolve();require(p.is_relative_to(base.resolve()),'Batch manifest traversal')
                    require(sha(p)==h,'Batch evidence changed')
        for rid,bid,rec in reservations:
            rec=json.loads(rec);base=self.root/'batches'/bid
            require(read(base/(rid+'_RESERVATION.json'))==rec,'Missing/changed reservation receipt; no retry')
            if rid in events:
                state,ev=events[rid]
                seal=base/(rid+'_SEALED_MANIFEST.json')
                require(sha(seal)==ev['seal_sha256'],'Seal changed')
                entries=read(seal)['files']
                require({p.relative_to(base/rid).as_posix() for p in (base/rid).rglob('*') if p.is_file()}==set(entries),'Run file set changed')
                for name,h in entries.items():
                    p=(base/rid/name).resolve();require(p.is_relative_to((base/rid).resolve()),'Seal traversal')
                    require(sha(p)==h,'Run evidence changed')
        return {'classification':'PASS_REGISTRY_AND_EVIDENCE','reserved_runs':len(reservations),'batches':len(batches)}
