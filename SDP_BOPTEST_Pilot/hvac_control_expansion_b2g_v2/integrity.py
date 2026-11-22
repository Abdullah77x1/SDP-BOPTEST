"""Offline preservation, saved identity requirements and readiness freeze only."""
import csv,json
from . import HOME,ROOT,V1,PILOT,B2F,RID,VERSION,STATE
from hvac_control_expansion_b2f_v1.packaging import read,sha,digest,require,write_new
from hvac_control_expansion_b2g_v1.integrity import (manifest,run_definition,require_only,parent_inventory,
    deny_existing_c45_claim,historical_integrity,baseline as parent_baseline)

def verify_v1():
    path=V1/'B2G_PARTIAL_DELIVERY_MANIFEST.json';data=read(path)
    for name,h in data['files'].items():
        p=(V1/name).resolve();require(p.is_relative_to(V1.resolve()),'V1 manifest path escape')
        require(sha(p)==h,'V1 failed evidence changed: '+name)
    actual={p.relative_to(V1).as_posix() for p in V1.rglob('*') if p.is_file() and '__pycache__' not in p.parts and p!=path}
    require(actual==set(data['files']),'V1 failed evidence file set changed')
    q=read(V1/'OFFLINE_QUALIFICATION.json')
    require(q['tests']==38 and q['errors']==1 and q['status']=='FAIL_STOP_NO_LIVE_AUTHORITY','V1 failure history changed')
    require("UPDATE slots SET status='UNUSED_NOT_AUTHORIZED'" in (V1/'tests.py').read_text(),'V1 failing source replaced')
    return dict(status='PASS_UNCHANGED',files=len(actual)+1,manifest_sha256=sha(path),original_qualification=q)

def runtime_requirements():
    reference=read(ROOT/'stage4e_d0/RUNTIME_REFERENCE_IDENTITIES.json')
    saved=read(PILOT/'runtime_state/batches/B1_G174_INITIAL_PILOT/BATCH_STARTED.json')['binding']['runtime']
    worker=read(ROOT/'stage4e_runtime_preflight/evidence/WORKER_EXECUTABLE_AND_DEPENDENCIES.json')
    require(saved['classification']=='PASS' and saved['container_image_ids']==reference['container_image_ids'],'Saved image identity mismatch')
    require(saved['worker_identity']==worker,'Saved worker identity mismatch')
    require(reference['building_fmu_sha256']=='158008fa3b635280a67dfed8bab5804d1f9a96d218b467dfebab77e5cbf8b86a','FMU pin mismatch')
    require(worker['boptest_version']=='0.9.0','BOPTEST identity mismatch')
    return dict(status='PASS_OFFLINE_PINNED_AND_RECORDED_IDENTITIES',testcase='bestest_air',BOPTEST_version='0.9.0',
        FMU_sha256=reference['building_fmu_sha256'],container_image_ids=reference['container_image_ids'],
        worker_identity=worker,current_runtime_contacted=False,
        current_runtime_verification='MANDATORY_BEFORE_FUTURE_AUTHORIZED_LIVE_REQUEST',
        deployed_FMU_verification='MANDATORY_AFTER_SINGLE_DEPLOYMENT_BEFORE_INITIALIZATION')

def preservation():
    require(not STATE.exists(),'Unexpected v2 live state: offline preparation must not consume slots')
    require(not (HOME/'AUTHORIZATION.json').exists(),'Active authorization prohibited in offline task')
    deny_existing_c45_claim()
    return dict(status='PASS',failed_v1=verify_v1(),earlier_evidence=historical_integrity(),
        C45_unused=True,G146_unused=True,new_ledger_initialized=False,live_operations=0,models_run=0)

def baseline():
    result=parent_baseline();result['version']=VERSION
    result['continuation_state_path']=str(STATE)
    result['creation_deferred_until']='SEPARATELY_AUTHORIZED_EXECUTION_AFTER_CURRENT_RUNTIME_CHECK'
    return result

def verify_frozen():
    p=HOME/'IMPLEMENTATION_MANIFEST.json';frozen=read(p)
    require(frozen['version']==VERSION and frozen['execution_authorized'] is False,'Invalid v2 readiness freeze')
    for name,h in frozen['files'].items():require(sha(name)==h,'Frozen v2 source/input changed: '+name)
    require(read(HOME/'RUN_MANIFEST.json')['run']==run_definition(),'Frozen C45 definition drift')
    return sha(p)

def freeze(request_path):
    require(read(HOME/'TARGETED_LEDGER_RESULT.json')['status']=='PASS','Targeted ledger check not passed')
    require(read(HOME/'OFFLINE_QUALIFICATION.json')['status']=='PASS','Mandatory full qualification not passed')
    before=preservation();runtime=runtime_requirements();r=run_definition();m=manifest()
    text=__import__('pathlib').Path(request_path).read_text(encoding='utf-8-sig')
    require('Do not execute BOPTEST simulations' in text and RID in text,'Wrong offline-only request')
    write_new(HOME/'REQUEST_SOURCE.json',dict(text=text,source_sha256=sha(request_path),execution_permission=False))
    write_new(HOME/'HISTORICAL_PRESERVATION.json',before);write_new(HOME/'RUNTIME_IDENTITY_REQUIREMENTS.json',runtime)
    write_new(HOME/'LEDGER_BASELINE.json',baseline())
    from hvac_control_expansion_v1.campaign import nominal
    write_new(HOME/'RUN_MANIFEST.json',dict(version=VERSION,status='QUALIFIED_INTENT_NOT_LIVE_AUTHORIZATION',run=r,
        campaign_sha256=digest(m),maximum_instances=1,maximum_advances=864,run_ids=[RID],
        schedule=[nominal(r,t) for t in range(r['start'],r['end'],300)],
        finalizer='hvac_control_expansion_b2f_v1.packaging.finalize',other_runs_authorized=False))
    files={str(p.resolve()):sha(p) for p in HOME.glob('*.py')}
    for p in V1.glob('*.py'):files[str(p.resolve())]=sha(p)
    for name,h in read(PILOT/'IMPLEMENTATION_MANIFEST.json')['files'].items():files[name]=h
    for name,h in read(B2F/'B2F_IMPLEMENTATION_MANIFEST.json')['files'].items():
        if name.endswith('.py'):files[str((B2F/name).resolve())]=h
    for p in [V1/'B2G_PARTIAL_DELIVERY_MANIFEST.json',B2F/'B2F_IMPLEMENTATION_MANIFEST.json',PILOT/'DELIVERY_MANIFEST.json',
              PILOT/'runtime_state/attempts.sqlite3',ROOT/'stage4e_d0/RUNTIME_REFERENCE_IDENTITIES.json',
              ROOT/'stage4e_runtime_preflight/evidence/WORKER_EXECUTABLE_AND_DEPENDENCIES.json']:
        files[str(p.resolve())]=sha(p)
    for p in HOME.glob('*'):
        if p.is_file() and p.suffix in ('.json','.txt','.patch','.csv'):files[str(p.resolve())]=sha(p)
    write_new(HOME/'IMPLEMENTATION_MANIFEST.json',dict(version=VERSION,files=files,execution_authorized=False,
        status='QUALIFIED_FROZEN_OFFLINE_ONLY',corrected_finalizer_bound=True))
    identity=verify_frozen()
    write_new(HOME/'EXECUTION_READINESS.json',dict(version=VERSION,status='PASS',
        permission='NOT AUTHORIZED FOR EXECUTION',implementation_sha256=identity,
        run_manifest_sha256=sha(HOME/'RUN_MANIFEST.json'),run_ids=[RID],maximum_instances=1,maximum_advances=864,
        ledger_baseline_sha256=sha(HOME/'LEDGER_BASELINE.json'),runtime_requirements_sha256=sha(HOME/'RUNTIME_IDENTITY_REQUIREMENTS.json'),
        current_runtime_verified=False,live_authorization_artifact_created=False,ledger_initialized=False,
        future_command='.venv/Scripts/python.exe -B -m hvac_control_expansion_b2g_v2 execute --approval <NEW_EXPLICIT_LIVE_C45_APPROVAL.json>',
        next_required='Separate explicit live authorization bound to this freeze; current runtime/slot checks before any BOPTEST request'))
    return dict(status='PASS_QUALIFIED_FROZEN_NOT_AUTHORIZED',implementation_sha256=identity)
