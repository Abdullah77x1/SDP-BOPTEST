"""Three ordered one-attempt runs; next gate requires validated, finalized prior evidence."""
import json
from pathlib import Path
from . import HOME,ROOT,IDS,VERSION,STATE
from .integrity import manifest,runs,no_claim,authorize,historical,verify_frozen
from hvac_control_expansion_v1.registry import Registry
from hvac_control_expansion_v1.collector import collect_run
from hvac_control_expansion_b2g_v1.launcher import real_factory
from hvac_control_expansion_b2f_v1.packaging import read,sha,digest,require,write_new,inventory,finalize,verify_package,chain

class G146Registry(Registry):
    def check_selection(self,selected):
        require(len(selected)==1 and selected[0] in runs(),'Only one exact G146 arm permitted')
        rid=selected[0]['run_id'];index=IDS.index(rid)
        super().check_selection(selected)
        with self.connect() as db:
            prior={rid:(state,json.loads(rec)) for rid,state,rec in db.execute('SELECT run_id,state,record FROM events')}
            require(set(prior)==set(IDS[:index]),'Run order or prior failure/interruption blocks campaign')
            claims={rid for rid, in db.execute('SELECT run_id FROM reservations')}
            require(claims==set(IDS[:index]),'Unclosed or unexpected consumption blocks campaign')
        self.verify_evidence()
        for previous in IDS[:index]:
            state,rec=prior[previous];require(state=='CONSUMED_COMPLETED' and rec['validation_passed'],'Prior mandatory validity failed')
            p=verify_package(rec['batch'],rec['package']);require(p==rec['finalization'],'Prior corrected finalization changed')
    def reserve(self,bid,run):
        self.check_selection([run]);return super().reserve(bid,run)

def execute_one(m,run,registry,binding,factory,mode,verifier,package,finalizer=finalize):
    registry.check_selection([run]);rid=run['run_id'];bid='B2I_'+rid
    batch=registry.new_batch(bid,[run],binding);path=registry.reserve(bid,run)
    result=validation=finalization=None;error=None
    try:
        result=collect_run(m,run,path,factory,mode)
        require(result['classification']=='PASS_VALID_RAW' and result['cleanup']=='STOP_ACK_AND_REMOVAL_VERIFIED','Mandatory collection/cleanup failure: '+str(result.get('error')))
        require((result['deploy_attempts'],result['initialization_attempts'],result['advance_requests_attempted'],result['advance_responses_received'])==(1,1,864,864),'Mutation budget mismatch')
        require((result['advances'],result['endpoints'],result['native_samples'],result['unresolved_events'])==(864,865,8641,0),'Raw support mismatch')
        validation=verifier(path,run,m['policy']);write_new(batch/'VALIDATION.json',validation)
    except BaseException as exc:error=f'{type(exc).__name__}: {exc}'
    seal=batch/(rid+'_SEALED_MANIFEST.json')
    write_new(seal,dict(run_id=rid,files=inventory(path),training_release=False))
    write_new(batch/'ATTEMPT_VALIDATION_STATUS.json',dict(run_id=rid,result=result,validation=validation,error=error,automatic_retry=False))
    top=['BATCH_STARTED.json',rid+'_RESERVATION.json',rid+'_SEALED_MANIFEST.json','ATTEMPT_VALIDATION_STATUS.json']
    if validation is not None:top.append('VALIDATION.json')
    plan=dict(version=VERSION,batch_files={p:sha(batch/p) for p in top},runs=[dict(run_id=rid,seal_path=seal.name,
        required_files=['ARTIFACT_MANIFEST.json','ATTEMPT_STARTED.json','receipt_order.jsonl','RUN_COMPLETED.json'])])
    try:finalization=finalizer(batch,plan,package)
    except BaseException as exc:error=(error+'; ' if error else '')+f'FINALIZATION: {type(exc).__name__}: {exc}'
    state='CONSUMED_FAILED' if error else 'CONSUMED_COMPLETED'
    registry.finish(rid,state,dict(seal_sha256=sha(seal),validation_passed=validation is not None and error is None,
        batch=str(batch),package=str(package),finalization=finalization,error=error))
    registry.verify_evidence()
    return dict(run_id=rid,state=state,raw_result=result,validation=validation,error=error,
        corrected_finalization=finalization,source_batch=str(batch),run_path=str(path),package_path=str(package),automatic_retry=False)

def validate_real(path,run,policy):
    from .validation import verify_run
    from hvac_control_expansion_v1.comparison import compare_runs
    raw=verify_run(path,run,policy);rr=runs()
    comparisons={}
    if run['arm']=='NREF':
        archived=ROOT/'stage4e_d1_v2/campaign_evidence/V2_Q01_N'
        comparisons['archived_native_common_channels']=compare_runs(archived,path,run,run,archived=True)
    else:
        native=STATE/'batches'/('B2I_'+IDS[0])/IDS[0]
        comparisons['fresh_native_prefix']=compare_runs(native,path,rr[0],run)
        if run['arm']=='C45':
            short=STATE/'batches'/('B2I_'+IDS[1])/IDS[1]
            comparisons['C15_common_prefix']=compare_runs(short,path,rr[1],run)
    return dict(raw=raw,comparisons=comparisons)

def execute():
    binding=authorize(HOME/'AUTHORIZATION.json')
    require(not (HOME/'LIVE_EXECUTION.json').exists() and not STATE.exists(),'Existing campaign: no restart/resume/retry')
    for rid in IDS:no_claim(rid)
    history=historical();base=read(HOME/'LEDGER_BASELINE.json')
    G146Registry.create(STATE,base);registry=G146Registry(STATE,base);outputs=[]
    (HOME/'finalized').mkdir()
    try:
        for run in runs():
            verify_frozen();no_claim(run['run_id']);registry.check_selection([run])
            from stage4e_d1_v2.runtime import verify_runtime
            runtime=verify_runtime();require(runtime['classification']=='PASS','Current runtime identity failure')
            fmu=ROOT/'deployment/official_v0.9.0/project1-boptest-0.9.0/testcases/bestest_air/models/wrapped.fmu'
            require(sha(fmu)==manifest()['model']['FMU_sha256'],'Source FMU identity failure before deployment')
            out=execute_one(manifest(),run,registry,dict(authorization=binding,runtime=runtime,source_fmu_sha256=sha(fmu),historical_integrity=history),
                real_factory,'AUTHORIZED_B2I_G146_ONLY',validate_real,HOME/'finalized'/run['run_id'])
            outputs.append(out);write_new(HOME/(run['run_id']+'_EXECUTION.json'),out)
            print(json.dumps(dict(run_id=run['run_id'],state=out['state'],error=out['error'])),flush=True)
            require(out['state']=='CONSUMED_COMPLETED','STOP entire campaign after mandatory failure')
        result=dict(status='PASS_ALL_THREE_G146',runs=outputs)
    except BaseException as exc:result=dict(status='STOP_NO_RETRY',runs=outputs,error=f'{type(exc).__name__}: {exc}')
    write_new(HOME/'LIVE_EXECUTION.json',result);write_new(HOME/'LEDGER_INVENTORY_AFTER.json',registry.inventory())
    write_new(HOME/'HISTORICAL_PRESERVATION_AFTER.json',historical())
    return result
