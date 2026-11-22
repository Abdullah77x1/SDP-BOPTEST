"""One-slot continuation using supported B1 collection and corrected B2-F finalization."""
from pathlib import Path
from . import HOME,ROOT,PILOT,RID,VERSION,STATE,BATCH_ID
from .integrity import require_only,manifest,run_definition,verify_frozen,historical_integrity,deny_existing_c45_claim
from hvac_control_expansion_v1.registry import Registry
from hvac_control_expansion_v1.collector import collect_run
from hvac_control_expansion_b2f_v1.packaging import read,sha,digest,require,write_new,inventory,finalize,verify_package,chain

class C45Registry(Registry):
    def check_selection(self,runs):
        require_only([r['run_id'] for r in runs]);super().check_selection(runs)
    def reserve(self,batch_id,run):
        require_only([run['run_id']]);return super().reserve(batch_id,run)

def authorize(approval_path,ids):
    require_only(ids);identity=verify_frozen();a=read(approval_path);m=manifest()
    expected=dict(version=VERSION,status='EXPLICITLY_AUTHORIZED_BY_B2G_USER_REQUEST',implementation_sha256=identity,
        run_manifest_sha256=sha(HOME/'RUN_MANIFEST.json'),campaign_sha256=digest(m),run_ids=[RID],maximum_instances=1,maximum_advances=864,
        request_sha256=sha(HOME/'REQUEST_SOURCE.json'))
    require(all(a.get(k)==v for k,v in expected.items()),'Exact C45 source/run/budget authorization mismatch')
    require(a.get('user_authorization_text')==read(HOME/'REQUEST_SOURCE.json')['text'],'Authorization text mismatch')
    require(read(HOME/'OFFLINE_QUALIFICATION.json')['status']=='PASS','Mandatory qualification not passed')
    return dict(**expected,authorization_sha256=sha(approval_path))

def real_factory(base,directory,journal,run,m):
    from stage4e_d0.runner import OrderedClient
    from stage4e_runtime_preflight.preflight import model_identity,verify_removed
    class RealTransport(OrderedClient):
        def fmu_identity(self):return model_identity(self.testid)
        def stop(self):
            ack=self.request('PUT','stop',{});require(ack=={'acknowledgement':'OK'},'Cleanup ACK mismatch')
            return dict(acknowledgement='OK',instance_removed=True,removal_checks=verify_removed(self.testid))
    return RealTransport(base,directory,journal)

def execute_one(m,run,registry,binding,factory,mode,verifier,package_output):
    """New orchestration shared by explicit live entry and labeled offline fabricated tests."""
    require_only([run['run_id']]);registry.check_selection([run])
    batch=registry.new_batch(BATCH_ID,[run],binding);path=registry.reserve(BATCH_ID,run)
    result=None;validation=None;error=None;state='CONSUMED_INTERRUPTED'
    try:
        result=collect_run(m,run,path,factory,mode)
        require(result['classification']=='PASS_VALID_RAW' and result['cleanup']=='STOP_ACK_AND_REMOVAL_VERIFIED','C45 raw/cleanup failure: '+str(result.get('error')))
        validation=verifier(path,run,m['policy']);write_new(batch/'C45_VALIDATION.json',validation)
        state='CONSUMED_COMPLETED'
    except BaseException as exc:
        error=f'{type(exc).__name__}: {exc}';state='CONSUMED_FAILED'
    finally:
        seal=batch/(RID+'_SEALED_MANIFEST.json')
        write_new(seal,dict(run_id=RID,files=inventory(path) if path.exists() else {},training_release=False))
        registry.finish(RID,state,dict(seal_sha256=sha(seal),result=result,error=error))
    outcome=dict(run_id=RID,state=state,raw_result=result,validation=validation,error=error,automatic_retry=False,remaining_runs_authorized=False)
    write_new(batch/'C45_ATTEMPT_CLOSED.json',outcome)
    # Applicable to partial/failed attempts too: preserve and exhaustively package their evidence.
    top=['BATCH_STARTED.json',RID+'_RESERVATION.json',RID+'_SEALED_MANIFEST.json','C45_ATTEMPT_CLOSED.json']
    if (batch/'C45_VALIDATION.json').exists():top.append('C45_VALIDATION.json')
    sealed=read(batch/(RID+'_SEALED_MANIFEST.json'))['files']
    required=['ARTIFACT_MANIFEST.json','ATTEMPT_STARTED.json','receipt_order.jsonl','RUN_COMPLETED.json']
    if not error:required+=['raw_api.jsonl','endpoints.json','whole_native_results.json','energy_audit.json','steps.jsonl']
    plan=dict(version=VERSION,scope='C45_EXACT_REGISTERED_ATTEMPT',batch_files={name:sha(batch/name) for name in top},
        runs=[dict(run_id=RID,seal_path=RID+'_SEALED_MANIFEST.json',required_files=required)])
    finalization=finalize(batch,plan,package_output)
    registry.verify_evidence();verify_package(batch,package_output)
    return dict(**outcome,corrected_finalization=finalization,source_batch=str(batch),run_path=str(path))

def validate_real(path,run,policy):
    from .validation import verify_run
    from hvac_control_expansion_v1.comparison import compare_runs
    raw=verify_run(path,run,policy);m=manifest();old=PILOT/'runtime_state/batches/B1_G174_INITIAL_PILOT'
    n,c=m['runs'][:2]
    return dict(raw=raw,matched_native=compare_runs(old/n['run_id'],path,n,run),
                common_C15_prefix=compare_runs(old/c['run_id'],path,c,run))

def execute():
    binding=authorize(HOME/'AUTHORIZATION.json',[RID]);deny_existing_c45_claim()
    history=historical_integrity();registry=C45Registry(STATE,read(HOME/'LEDGER_BASELINE.json'));registry.verify_evidence()
    registry.check_selection([run_definition()])
    from stage4e_d1_v2.runtime import verify_runtime
    runtime=verify_runtime();require(runtime['classification']=='PASS','Runtime identity failed')
    try:
        output=execute_one(manifest(),run_definition(),registry,dict(authorization=binding,runtime=runtime,historical_integrity=history),
            real_factory,'AUTHORIZED_B2G_C45_ONLY',validate_real,HOME/'corrected_c45_package')
    except BaseException as exc:
        # No second deployment, advance, cleanup attempt or finalization replacement.
        output=dict(run_id=RID,status='FAILED_OR_INTERRUPTED_NO_RETRY',error=f'{type(exc).__name__}: {exc}',automatic_retry=False)
    write_new(HOME/'LIVE_EXECUTION.json',output)
    write_new(HOME/'LEDGER_INVENTORY_AFTER.json',registry.inventory())
    write_new(HOME/'HISTORICAL_PRESERVATION_AFTER.json',historical_integrity())
    return output
