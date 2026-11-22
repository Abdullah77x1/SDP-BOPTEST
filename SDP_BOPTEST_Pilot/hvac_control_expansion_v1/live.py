"""Bounded B1 pilot entry. No continuation, retry, disposable preflight or training."""
from pathlib import Path
from . import HOME,VERSION
from .campaign import PILOT,select_run,validate_manifest
from .integrity import verify_frozen,verify_sources
from .registry import Registry
from .collector import collect_run
from .comparison import compare_runs
from .analysis import analyze
from stage4e_d2i_1.common import ROOT,read,sha,digest,require,save_new
from stage4e_d0.runner import OrderedClient,utc,files_manifest

STATE=HOME/'runtime_state'

def baseline(m):
    return dict(version=VERSION,slots=[dict(run_id=r['run_id'],group_id=r['group_id'],partition='development',
        category='development',status='UNUSED_NOT_AUTHORIZED',run_sha256=digest(r)) for r in m['runs']])

def authorize(m,approval):
    validate_manifest(m);identity=verify_frozen();a=read(approval)
    expected=dict(version=VERSION,status='EXPLICITLY_AUTHORIZED',implementation_manifest_sha256=identity,
        campaign_sha256=digest(m),run_ids=PILOT,maximum_fresh_instances=2,maximum_advances=1728)
    require(all(a.get(k)==v for k,v in expected.items()),'B1 exact pilot authorization mismatch')
    require(a.get('user_authorization_text') and a.get('authorized_utc'),'Authorization provenance missing')
    require(read(HOME/'OFFLINE_QA.json')['status']=='PASS','Mandatory offline tests not passed')
    return dict(approval_sha256=sha(approval),**expected)

def real_factory(base,directory,journal,run,manifest):
    # Supported qualified client interface; never invoke a frozen collector's private methods.
    from stage4e_runtime_preflight.preflight import model_identity,verify_removed
    class RealTransport(OrderedClient):
        def fmu_identity(self):return model_identity(self.testid)
        def stop(self):
            ack=self.request('PUT','stop',{})
            require(ack=={'acknowledgement':'OK'},'Cleanup acknowledgement')
            return dict(acknowledgement='OK',instance_removed=True,removal_checks=verify_removed(self.testid))
    return RealTransport(base,directory,journal)

def execute(approval):
    m=read(HOME/'campaign_manifest.json');binding=authorize(m,approval);integrity=verify_sources()
    reg=Registry(STATE,baseline(m));reg.verify_evidence()
    runs=[select_run(m,rid) for rid in PILOT];reg.check_selection(runs)
    from stage4e_d1_v2.runtime import verify_runtime
    runtime=verify_runtime();require(runtime['classification']=='PASS','Pinned runtime failed')
    # No HTTP/deployment until every launch prerequisite is established.
    batch=reg.new_batch('B1_G174_INITIAL_PILOT',runs,dict(binding=binding,runtime=runtime,integrity=integrity))
    results=[];error=None
    for run in runs:
        path=reg.reserve('B1_G174_INITIAL_PILOT',run);result=None;state='CONSUMED_INTERRUPTED'
        try:
            result=collect_run(m,run,path,real_factory,'AUTHORIZED_B1_PILOT_RAW')
            require(result['classification']=='PASS_VALID_RAW','Raw collection failed: '+str(result.get('error')))
            require(result['cleanup']=='STOP_ACK_AND_REMOVAL_VERIFIED','Cleanup failed')
            if run['arm']=='NREF':
                from stage4e_d2_public.export import locate
                public=read(ROOT/'stage4e_d2_public/PUBLIC_DEVELOPMENT_VALIDATION_v1_0_0/RUN_CONFIGURATION_MANIFEST.json')['runs']
                old=next(r for r in public if r['run_id']==run['archived_native_run_id'])
                check=compare_runs(locate(old),path,old,run,archived=True)
                save_new(batch/'NATIVE_REPRODUCIBILITY.json',check)
            else:
                check=compare_runs(batch/PILOT[0],path,runs[0],run)
                save_new(batch/'PRETREATMENT_COMPARISON.json',check)
            state='CONSUMED_COMPLETED'
        except (Exception,KeyboardInterrupt) as exc:
            error=f'{type(exc).__name__}: {exc}'
            state='CONSUMED_FAILED'
        finally:
            seal=batch/(run['run_id']+'_SEALED_MANIFEST.json')
            save_new(seal,dict(files={p.relative_to(path).as_posix():sha(p) for p in path.rglob('*') if p.is_file()},training_release=False))
            reg.finish(run['run_id'],state,dict(seal_sha256=sha(seal),result=result,error=error))
        results.append(dict(run_id=run['run_id'],state=state,result=result))
        if error:break
    summary=None
    if not error and len(results)==2:
        try:summary=analyze(batch/PILOT[0],batch/PILOT[1],runs[1],HOME)
        except Exception as exc:error=f'Analysis failed: {type(exc).__name__}: {exc}'
    output=dict(status='INVALID_OR_INCOMPLETE' if error else summary['outcome'],runs=results,error=error,analysis=summary,
                remaining_runs_authorized=False,automatic_continuation=False,ml_models_trained=0)
    save_new(batch/'PILOT_COMPLETED.json',output)
    save_new(batch/'BATCH_ARTIFACT_MANIFEST.json',dict(files=files_manifest(batch)))
    reg.verify_evidence()
    save_new(HOME/'PILOT_EXECUTION.json',output)
    return output
