"""Read-only qualified-input checks and exact schema-bound user approval creation.

Never deploys, initializes or advances. Live execution is a separate documented
CLI invocation after this exclusive preflight passes.
"""
import json,sqlite3
from pathlib import Path
from datetime import datetime,timezone
from . import HOME,ROOT,V2,PILOT,RID
from hvac_control_expansion_b2f_v1.packaging import read,sha,digest,require,write_new

EXPECTED_IMPL='725408bd1fe98544a89b07d39b54da96f6854988f58a791f52d5fcba1db2f603'
EXPECTED_RUN='4842d660bc9de6161fd4a48d78c938dc58c5024a2bcf5e399756d9a3c8ec48f3'
FMU='158008fa3b635280a67dfed8bab5804d1f9a96d218b467dfebab77e5cbf8b86a'

def prepare(request_path):
    require(not (HOME/'PREEXECUTION_CHECKS.json').exists() and not (HOME/'PREFLIGHT_FAILURE.json').exists(),'Existing preflight must not be replaced')
    checks=[]
    try:
        require(sha(V2/'IMPLEMENTATION_MANIFEST.json')==EXPECTED_IMPL,'STOP: frozen implementation digest mismatch')
        require(sha(V2/'RUN_MANIFEST.json')==EXPECTED_RUN,'STOP: frozen run digest mismatch')
        from hvac_control_expansion_b2g_v2.integrity import verify_frozen,preservation,manifest,deny_existing_c45_claim
        require(verify_frozen()==EXPECTED_IMPL,'Frozen dependency mismatch');checks.append('Exact expected implementation/run and all bound source/configuration hashes PASS')
        for name,h in read(V2/'DELIVERY_MANIFEST.json')['files'].items():require(sha(V2/name)==h,'Frozen v2 qualification/delivery changed: '+name)
        snapshot=dict(read(V2/'DELIVERY_MANIFEST.json')['files']);snapshot['DELIVERY_MANIFEST.json']=sha(V2/'DELIVERY_MANIFEST.json')
        write_new(HOME/'FROZEN_V2_INPUT_SNAPSHOT.json',dict(root=str(V2),files=snapshot))
        require(read(V2/'OFFLINE_QUALIFICATION.json')['status']=='PASS' and read(V2/'OFFLINE_QUALIFICATION.json')['tests']==42,'Existing qualification not passed')
        require(read(V2/'TARGETED_LEDGER_RESULT.json')['status']=='PASS','Targeted trigger qualification missing')
        checks.append('Existing targeted + 42-case qualification verified; not rerun')
        history=preservation();deny_existing_c45_claim();write_new(HOME/'HISTORICAL_PRESERVATION_BEFORE.json',history)
        checks.append('NREF/C15 consumed; C45 never attempted; parent-plus-extension chain, G146 unused, prior histories and D2 preservation PASS')
        rm=read(V2/'RUN_MANIFEST.json');r=rm['run'];m=manifest()
        require(r==next(x for x in m['runs'] if x['run_id']==RID),'Run definition differs from frozen B1')
        require((r['start'],r['end'],r['warmup_start'],r['maximum_advances'],r['group_id'],r['outer_held_fold'])==(15033600,15292800,14428800,864,'D2_G174',4),'Exact G174 experiment mismatch')
        active=[p for p in rm['schedule'] if p['command']['con_oveTSetCoo_activate']]
        require(len(active)==27 and all(p['command']['con_oveTSetCoo_u']==296.90 and 39600<=p['start']%86400<42300 for p in active),'C45 schedule/target mismatch')
        require(r['initialization']==dict(method='custom',start_time=15033600,warmup_period=604800,scenario_key=None),'Initialization mismatch')
        require(rm['maximum_instances']==1 and rm['maximum_advances']==864 and rm['run_ids']==[RID],'Launch budget mismatch')
        checks.append('Exact 27-interval C45 schedule, 296.90 K, native releases/other flags, initialization, fold and one-instance/864-advance contract PASS')
        from hvac_control_expansion_b2g_v2 import launcher as qualified
        from hvac_control_expansion_b2g_v1 import launcher as core
        from hvac_control_expansion_b2f_v1 import packaging
        require(qualified.execute_one is core.execute_one and core.finalize is packaging.finalize,'Qualified corrected finalizer not bound')
        checks.append('Frozen v2 -> reused qualified core -> corrected B2-F finalizer binding PASS')
        fmu=ROOT/'deployment/official_v0.9.0/project1-boptest-0.9.0/testcases/bestest_air/models/wrapped.fmu'
        require(sha(fmu)==FMU,'Pinned local source FMU identity mismatch')
        write_new(HOME/'SOURCE_FMU_IDENTITY.json',dict(path=str(fmu),sha256=sha(fmu),bytes=fmu.stat().st_size,
            actual_selected_instance_check='Qualified launcher additionally verifies deployed instance FMU before initialization'))
        checks.append('Actual pinned source FMU SHA-256 PASS; selected-instance FMU verification is required after deployment, before initialization')
        from stage4e_d1_v2.runtime import verify_runtime
        runtime=verify_runtime();require(runtime['classification']=='PASS','Current pinned runtime rejected')
        write_new(HOME/'CURRENT_RUNTIME_IDENTITY.json',runtime);checks.append('Current runtime images, worker executable/dependencies, BOPTEST version and localhost ports PASS; no simulation deployed')
        text=Path(request_path).read_text(encoding='utf-8-sig')
        require('one live execution of this exact run' in text and RID in text and EXPECTED_IMPL in text and EXPECTED_RUN in text,'B2-H explicit user authorization missing')
        write_new(HOME/'USER_AUTHORIZATION_SOURCE.json',dict(text=text,source_path=str(request_path),source_sha256=sha(request_path)))
        approval=dict(version='SDP_B2G_2.0.0',status='EXPLICITLY_AUTHORIZED_FOR_LIVE_C45',implementation_sha256=EXPECTED_IMPL,
            run_manifest_sha256=EXPECTED_RUN,campaign_sha256=digest(m),run_ids=[RID],maximum_instances=1,maximum_advances=864,
            request_sha256=sha(V2/'REQUEST_SOURCE.json'),user_authorization_text=text,
            authorized_utc=datetime.now(timezone.utc).isoformat(),authorization_source_sha256=sha(HOME/'USER_AUTHORIZATION_SOURCE.json'),
            no_retries=True,G146_authorized=False,ML_execution_authorized=False)
        path=HOME/'EXPLICIT_LIVE_C45_APPROVAL.json';write_new(path,approval)
        binding=qualified.authorize(path,[RID]);checks.append('Exact existing approval schema and sole-run/budget bindings accepted by frozen launcher.authorize PASS')
        write_new(HOME/'PREEXECUTION_CHECKS.json',dict(status='PASS',checks=checks,binding=binding,
            runtime_sha256=sha(HOME/'CURRENT_RUNTIME_IDENTITY.json'),slot_consumed=False,deployments=0,
            actual_instance_FMU_gate='AFTER_SINGLE_DEPLOYMENT_BEFORE_INITIALIZATION_PER_FROZEN_PROTOCOL',
            raw_output_location=str(V2/'runtime_state/batches/B2G_G174_C45_ONLY'/RID),
            output_note='Qualified launcher fixed paths are preserved; B2-H will index evidence here without redirecting or modifying the launcher'))
        return dict(status='PASS_ALL_PREEXECUTION_CHECKS',approval_path=str(path),slot_consumed=False,deployments=0)
    except BaseException as exc:
        write_new(HOME/'PREFLIGHT_FAILURE.json',dict(status='STOP_NO_EXECUTION',error=f'{type(exc).__name__}: {exc}',completed_checks=checks,deployments=0,slot_consumed=False))
        raise

if __name__=='__main__':
    import sys
    print(json.dumps(prepare(sys.argv[1]),indent=2))
