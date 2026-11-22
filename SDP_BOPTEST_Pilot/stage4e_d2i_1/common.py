import hashlib,json,math
from pathlib import Path
from stage4e_d0.plan import ROOT,sha,save_new
from stage4e.dataset import ContractError

HOME=Path(__file__).resolve().parent
VERSION='SDP_D2_COLLECTOR_1.0.0'
PLAN_SHA='89050ba873352adc0cd946043993b5ad30c90dbedc54054a0520e7fb9166d470'
PREVIEW_SHA='e6978fa08fa6a870823a9880755f9d8291d5e350e6ddce177c9a362766ea5af3'
FMU_SHA='158008fa3b635280a67dfed8bab5804d1f9a96d218b467dfebab77e5cbf8b86a'
def read(path):return json.loads(Path(path).read_text(encoding='utf-8-sig'))
def digest(value):return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()
def require(ok,message):
    if not ok:raise ContractError(message)
def finite(value):
    require(type(value) in (int,float) and math.isfinite(value),'Missing/nonfinite/non-numeric value')
    return value
def safe_source(name):
    path=(ROOT/name).resolve()
    require(path.is_relative_to(ROOT.resolve()),'Source path escapes workspace')
    return path

def verify_planning_sources():
    path=ROOT/'stage4e_d2p/PLANNING_SNAPSHOT_MANIFEST.json'
    require(sha(path)==PLAN_SHA,'Approved D2P snapshot digest mismatch')
    for name,h in read(path)['files'].items():require(sha(safe_source(name))==h,'D2P source changed: '+name)
    preview=ROOT/'stage4e_d1p/DEVELOPMENT_ONLY_SDP_STAGE4E_D1P_v1_0_0/DATASET_MANIFEST.json'
    require(sha(preview)==PREVIEW_SHA,'D1P schema/preview manifest changed')
    for name in ('DATA_DICTIONARY.json','FEATURE_GROUPS.json'):
        require(sha(preview.parent/name)==read(preview)['files'][name]['sha256'],'D1P compatibility source changed')
    return PLAN_SHA

def verify_preservation():
    verify_planning_sources()
    from stage4e_d1_v2.runner import verify_frozen
    require(verify_frozen()=='ec9c64f9abffcda7095d537e375eda7bb8f6b6d367aa1aa2238bcc606bcbeb5c','D1 v2 changed')
    p=ROOT/'stage4e_d1p/PREVIEW_DELIVERY_MANIFEST.json'
    require(sha(p)=='5da0d933b18ea68f719e52a18d5846a15e2cb28c57c3bbfc8f69322ec415b014','D1P delivery changed')
    for name,h in read(p)['files'].items():require(sha(safe_source(name))==h,'Preserved D1P dependency changed: '+name)
    results=ROOT/'stage4e_d1_v2_execution/RESULTS_DELIVERY_MANIFEST.json'
    require(sha(results)=='881c880b601f35b5132991935856b7e3b191e004448c5b4d0bde46ccd77dc596','D1 v2 delivery changed')
    counts={}
    for manifest in (results,ROOT/'stage4e_d1/FINAL_ARTIFACT_MANIFEST.json'):
        files=read(manifest)['files']
        for name,h in files.items():require(sha(safe_source(name))==h,'Preserved experiment artifact changed: '+name)
        counts[str(manifest.relative_to(ROOT))]=len(files)
    return {'D2P':PLAN_SHA,'D1P':PREVIEW_SHA,'status':'PRESERVED_HASHES_VERIFIED',
        'preserved_experiment_file_counts':counts,'original_failed_D1_unchanged':True,'qualified_v2_raw_unchanged':True}
