"""Future opt-in boundary. NOT AUTHORIZED OR INVOKED by D2I-1.

No Docker start/stop lifecycle commands. The read-only identity checker is lazy.
Approval files are audit bindings, not an OS security boundary/private custodian.
Protected collection is refused before approval/prerequisite file access.
"""
from .common import *
from .manifest import validate_manifest,select_run,require_public_collection

def implementation_identity():
    p=HOME/'IMPLEMENTATION_MANIFEST.json'
    require(p.is_file(),'Implementation has not been frozen')
    data=read(p)
    require(data['version']==VERSION,'Wrong implementation version')
    for name,h in data['files'].items():
        require(sha(safe_source(name))==h,'Implementation/dependency integrity mismatch: '+name)
    return sha(p)

def authorize(manifest,run_ids,approval_path,prerequisite_path=None):
    validate_manifest(manifest)
    require(isinstance(run_ids,list) and run_ids and len(run_ids)==len(set(run_ids)),'Explicit unique run selection required')
    runs=[select_run(manifest,rid) for rid in run_ids]
    for run in runs:require_public_collection(run)
    # No protected access/adapter creation occurs above or in metadata validation.
    canonical=[r['run_id'] for r in manifest['runs'] if r['run_id'] in run_ids]
    require(run_ids==canonical,'Frozen run ordering required')
    if manifest['purpose']=='production':
        for gid in {r['group_id'] for r in runs}:
            require(sum(r['group_id']==gid for r in runs)==2,'Select complete native/variation pairs')
    else:
        require(run_ids==[r['run_id'] for r in manifest['runs']],'Bounded four-window preflight must be authorized as frozen')
    require(approval_path is not None,'Explicit authorization file required')
    frozen_sha=implementation_identity();approval=read(approval_path)
    ledger=read(HOME/'ATTEMPT_LEDGER_NOT_AUTHORIZED.json')
    slots=ledger['preflight_slots' if manifest['purpose']=='preflight' else 'new_production_slots']
    require(all(slots.get(rid)=='UNUSED_NOT_AUTHORIZED' for rid in run_ids),'Slot not unused in implementation ledger')
    require(approval.get('status')=='EXPLICITLY_AUTHORIZED' and approval.get('version')==VERSION,'Live execution not authorized')
    require(approval.get('implementation_manifest_sha256')==frozen_sha,'Authorization implementation digest mismatch')
    require(approval.get('config_sha256')==digest(manifest) and approval.get('purpose')==manifest['purpose'],'Authorization config mismatch')
    require(approval.get('run_ids')==run_ids and approval.get('maximum_fresh_instances')==len(runs)
        and approval.get('maximum_advances')==sum(r['maximum_advances'] for r in runs),'Authorization slots/budget mismatch')
    require(isinstance(approval.get('user_authorization_text'),str) and approval['user_authorization_text'].strip()
        and isinstance(approval.get('authorized_utc'),str) and approval['authorized_utc'].strip(),'User authorization record missing')
    proof_sha=None
    if manifest['purpose']=='production':
        require(prerequisite_path is not None,'Qualified separately authorized development preflight required')
        p=Path(prerequisite_path).resolve();proof=read(p)
        from .manifest import canonical_manifest
        require(proof.get('status')=='RUNTIME_QUALIFIED' and proof.get('data_is_fabricated') is False,'Real qualified preflight required')
        require(proof.get('preflight_config_sha256')==digest(canonical_manifest('preflight'))
            and proof.get('production_config_sha256')==digest(manifest),'Preflight/config binding mismatch')
        require(proof.get('development_start_days')==[20,74,174,258],'Preflight windows incomplete')
        require(proof.get('qualified_optional_channels')==manifest['reporting']['optional_forecasts'],'Common reporting profile not qualified')
        checks=('custom_initialization_verified','warmup_verified','native_history_verified','forecast_order_verified',
            'pulse_period_forecasts_verified','units_and_limits_verified','physical_tolerances_reviewed')
        require(all(proof.get(k) is True for k in checks),'Preflight prerequisite incomplete')
        reference=read(ROOT/'stage4e_d0/RUNTIME_REFERENCE_IDENTITIES.json')
        require(proof.get('container_image_ids')==reference['container_image_ids'] and proof.get('building_fmu_sha256')==FMU_SHA,'Preflight runtime identity mismatch')
        require(isinstance(proof.get('proof_files'),dict) and proof['proof_files'],'Missing preflight proof files')
        for name,h in proof['proof_files'].items():
            path=(p.parent/name).resolve()
            require(path.is_relative_to(p.parent),'Proof path traversal')
            require(sha(path)==h,'Preflight evidence hash mismatch')
        proof_sha=sha(p)
    return {'approval_sha256':sha(approval_path),'prerequisite_sha256':proof_sha,
        'implementation_sha256':frozen_sha,'config_sha256':digest(manifest),'run_ids':run_ids}

def _real_factory(base,directory,journal,run,manifest):
    # Imports/construction intentionally occur only after authorize + verify_runtime.
    from stage4e_d0.runner import OrderedClient
    from stage4e_runtime_preflight.preflight import model_identity,verify_removed
    class RealTransport(OrderedClient):
        def fmu_identity(self):return model_identity(self.testid)
        def stop(self):
            ack=self.request('PUT','stop',{})
            require(ack=={'acknowledgement':'OK'},'Unexpected cleanup acknowledgement')
            removed=verify_removed(self.testid)
            return {'acknowledgement':'OK','instance_removed':True,'removal_checks':removed}
    return RealTransport(base,directory,journal)

def future_live(manifest,run_ids,approval_path=None,prerequisite_path=None):
    binding=authorize(manifest,run_ids,approval_path,prerequisite_path)
    verify_preservation()
    from stage4e_d1_v2.runtime import verify_runtime
    identity=verify_runtime() # READ ONLY; deliberately never called by offline operations.
    from .collector import _collect
    from stage4e_d0.runner import utc,files_manifest
    from .pairing import public_pair_gate
    # Fixed exclusive directory. A changed --output cannot create replacement attempts.
    directory=HOME/('future_'+manifest['purpose']+'_evidence');directory.mkdir()
    save_new(directory/'CAMPAIGN_STARTED.json',{'binding':binding,'runtime_identity':identity,'started_utc':utc(),
        'run_ids':run_ids,'no_retry_or_resume':True,'training_release':False})
    summaries=[];error=None
    for rid in run_ids:
        run=select_run(manifest,rid)
        result=_collect(manifest,run,directory/rid,_real_factory,'FUTURE_AUTHORIZED_RAW_COLLECTION')
        summaries.append(result)
        expected='PASS_VALID_RAW' if manifest['purpose']=='production' else 'PASS_PREFLIGHT_RAW'
        if result['classification']!=expected:break
        if run['mode']=='scheduled_variation':
            try:
                pair_audit=public_pair_gate(directory/run_ids[len(summaries)-2],directory/rid,run)
                save_new(directory/(run['group_id']+'_PAIR_AUDIT.json'),pair_audit)
            except Exception as exc:error=str(exc);break
    passed=len(summaries)==len(run_ids) and not error and all(s['classification'] in ('PASS_VALID_RAW','PASS_PREFLIGHT_RAW') for s in summaries)
    classification='PASS_SELECTED_RAW_COLLECTION' if passed else 'FAILED_OR_INCOMPLETE_STOPPED'
    # Public pair audits do not claim D2-wide coverage or access protected outcomes.
    excitation={}
    if passed and manifest['purpose']=='production':
        for i in range(0,len(summaries),2):
            pair=summaries[i:i+2]
            from .acceptance import public_pair_audit
            run=select_run(manifest,run_ids[i])
            try:
                excitation[run['group_id']]=public_pair_audit(*pair,
                    read(directory/run_ids[i]/'native_results.json'),read(directory/run_ids[i+1]/'native_results.json'),run,manifest['policy'])
            except Exception as exc:
                error=str(exc);classification='FAILED_ACCEPTANCE_AUDIT';break
        classification='RAW_COMPLETE_ACCEPTANCE_REVIEW_REQUIRED'
    output={'classification':classification,'runs':summaries,'pair_error':error,'binding':binding,
        'unused_attempt_ids':run_ids[len(summaries):],'excitation_audit':excitation,
        'training_release':False,'dataset_constructed':False,'automatic_next_stage':False}
    save_new(directory/'CAMPAIGN_COMPLETED.json',output)
    save_new(directory/'ARTIFACT_MANIFEST.json',{'files':files_manifest(directory)})
    return output
