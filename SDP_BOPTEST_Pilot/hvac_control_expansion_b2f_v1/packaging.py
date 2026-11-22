"""Small offline finalizer. Explicit registered scope, exhaustive hashes, external output.

No simulator/collector/transport imports. Never writes into the evidence root.
"""
import hashlib,json,os,re,stat
from pathlib import Path,PurePosixPath

class PackagingError(ValueError):pass

def require(ok,message):
    if not ok:raise PackagingError(message)

def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()

def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for chunk in iter(lambda:f.read(1024*1024),b''):h.update(chunk)
    return h.hexdigest()

def _unique(pairs):
    result={}
    for k,v in pairs:
        require(k not in result,'Duplicate JSON registration: '+k);result[k]=v
    return result

def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'),object_pairs_hook=_unique,
                      parse_constant=lambda x:(_ for _ in ()).throw(PackagingError('Nonfinite JSON')))

def write_new(path,value):
    with Path(path).open('x',encoding='utf-8',newline='\n') as f:
        json.dump(value,f,sort_keys=True,indent=2,allow_nan=False);f.write('\n');f.flush();os.fsync(f.fileno())

def relative(name):
    require(isinstance(name,str) and name and '\\' not in name and ':' not in name,'Noncanonical relative path')
    p=PurePosixPath(name)
    require(bool(p.parts) and not p.is_absolute() and str(p)==name and all(x not in ('.','..') for x in p.parts),'Unsafe relative path')
    require(all(not x.endswith(('.', ' ')) and not any(c in x for c in '<>"|?*') for x in p.parts),'Unstable Windows path')
    return name

def inventory(root):
    root=Path(root);require(root.is_dir() and not root.is_symlink(),'Invalid evidence root')
    result={};folded=set()
    for p in sorted(root.rglob('*')):
        require(not p.is_symlink(),'Symlink artifact prohibited')
        require(p.resolve().is_relative_to(root.resolve()),'Artifact escapes evidence root')
        if p.is_dir():continue
        require(stat.S_ISREG(p.stat().st_mode),'Nonregular artifact')
        name=relative(p.relative_to(root).as_posix())
        require(name.casefold() not in folded,'Case-colliding artifact');folded.add(name.casefold())
        result[name]=sha(p)
    return result

def entries(value):
    require(isinstance(value,dict) and value,'Empty/malformed artifact map')
    seen=set()
    for name,h in value.items():
        relative(name);require(name.casefold() not in seen,'Duplicate/case-colliding registration');seen.add(name.casefold())
        require(isinstance(h,str) and re.fullmatch('[0-9a-f]{64}',h),'Invalid SHA-256 registration')
    return value

def chain(path):
    previous='0'*64;count=0;last_ns=None
    for line in Path(path).read_text(encoding='utf-8').splitlines():
        event=json.loads(line,object_pairs_hook=_unique);h=event.pop('sha256')
        require(event['previous_sha256']==previous and event['order']==count+1 and digest(event)==h,'Receipt chain failure')
        if 'monotonic_ns' in event:
            require(last_ns is None or event['monotonic_ns']>=last_ns,'Receipt clock reversal');last_ns=event['monotonic_ns']
        previous=h;count+=1
    require(count>0,'Empty receipt chain')
    return dict(events=count,terminal_sha256=previous)

def verify_source(root,plan):
    """Registration is supplied by a frozen plan/ledger, never inferred to accept extras."""
    root=Path(root);whole_inventory=inventory(root)
    registered=dict(entries(plan['batch_files']));seen={k.casefold() for k in registered}
    require(plan['runs'] and len({r['run_id'].casefold() for r in plan['runs']})==len(plan['runs']),'Duplicate run registration')
    results=[]
    for run in plan['runs']:
        rid=relative(run['run_id']);require('/' not in rid,'Run must be a direct child')
        seal_path=relative(run['seal_path']);require(seal_path in registered,'Unregistered run seal')
        require(sha(root/seal_path)==registered[seal_path],'Seal hash mismatch')
        sealed=entries(read(root/seal_path)['files'])
        require(set(run['required_files'])<=sealed.keys(),'Required run artifact missing from registration')
        require('ARTIFACT_MANIFEST.json' in sealed and 'receipt_order.jsonl' in sealed,'Required nested manifest/chain absent')
        for name,h in sealed.items():
            path=relative(rid+'/'+name)
            require(path.casefold() not in seen,'Duplicate artifact registration');seen.add(path.casefold());registered[path]=h
        actual=inventory(root/rid)
        require(actual==sealed,'Missing, unexpected or tampered run artifact')
        nested=entries(read(root/rid/'ARTIFACT_MANIFEST.json')['files'])
        require(nested=={name:h for name,h in sealed.items() if name!='ARTIFACT_MANIFEST.json'},'Nested run manifest scope/hash mismatch')
        results.append(dict(run_id=rid,sealed_files=len(sealed),receipt_chain=chain(root/rid/'receipt_order.jsonl')))
    require(whole_inventory==registered,'Batch artifact scope/hash mismatch')
    return dict(files=dict(sorted(registered.items())),runs=results,plan_sha256=digest(plan))

def finalize(root,plan,output,checkpoint=None):
    """Publish a NEW external package. Completion is explicit; interrupted output fails closed."""
    root=Path(root).resolve();output=Path(output).resolve()
    require(not output.is_relative_to(root) and not root.is_relative_to(output),'Output overlaps historical evidence')
    output.mkdir() # exclusive; never replace/recover an existing finalization attempt
    write_new(output/'FINALIZATION_STARTED.json',dict(version='B2F_PACKAGING_1.0.0',plan_sha256=digest(plan),source_root=str(root)))
    try:
        write_new(output/'SOURCE_PLAN.json',plan);verified=verify_source(root,plan)
        write_new(output/'manifest.pending',verified)
        if checkpoint:checkpoint()
        (output/'manifest.pending').rename(output/'BATCH_ARTIFACT_MANIFEST.json')
        # Read back and revalidate against the source before marking complete.
        require(read(output/'BATCH_ARTIFACT_MANIFEST.json')==verify_source(root,plan),'Final readback mismatch')
        write_new(output/'FINALIZATION_COMPLETED.json',dict(status='PASS_CORRECTED_OFFLINE_FINALIZATION',
            manifest_sha256=sha(output/'BATCH_ARTIFACT_MANIFEST.json'),plan_sha256=sha(output/'SOURCE_PLAN.json')))
        return verify_package(root,output)
    except BaseException as exc:
        write_new(output/'FINALIZATION_FAILED.json',dict(status='FAILED_OR_INTERRUPTED',error=f'{type(exc).__name__}: {exc}'))
        raise

def verify_package(root,output):
    output=Path(output)
    expected={'FINALIZATION_STARTED.json','SOURCE_PLAN.json','BATCH_ARTIFACT_MANIFEST.json','FINALIZATION_COMPLETED.json'}
    require(set(inventory(output))==expected,'Incomplete, interrupted or unexpected finalization package')
    done=read(output/'FINALIZATION_COMPLETED.json');start=read(output/'FINALIZATION_STARTED.json')
    require(done['status']=='PASS_CORRECTED_OFFLINE_FINALIZATION','Finalization not complete')
    require(done['manifest_sha256']==sha(output/'BATCH_ARTIFACT_MANIFEST.json') and done['plan_sha256']==sha(output/'SOURCE_PLAN.json'),'Final package hash mismatch')
    plan=read(output/'SOURCE_PLAN.json');require(start['plan_sha256']==digest(plan),'Start/plan binding mismatch')
    require(Path(start['source_root']).resolve()==Path(root).resolve(),'Source-root identity mismatch')
    require(read(output/'BATCH_ARTIFACT_MANIFEST.json')==verify_source(root,plan),'Final source verification failed')
    return dict(status='PASS_CORRECTED_OFFLINE_FINALIZATION',source_files=len(read(output/'BATCH_ARTIFACT_MANIFEST.json')['files']),
                manifest_sha256=done['manifest_sha256'])
