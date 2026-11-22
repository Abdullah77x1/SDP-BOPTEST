"""One authorization, eight separately sealed public pairs, no retries."""
import json,shutil
from datetime import datetime,timezone
from . import HOME
from .audit import audit_run
from stage4e_d2i_1.common import ROOT,read,sha,digest,require,save_new
from stage4e_d2i_1_v1_0_1.live import implementation_identity
from stage4e_d2_prep02.adapter import future_batch,identity,STATE,BASELINE
from stage4e_d2_prep02.registry import Registry

GROUPS=['D2_G074','D2_G218','D2_G258','D2_G288','D2_G100','D2_G196','D2_G310','D2_G354']
def utc():return datetime.now(timezone.utc).isoformat()
def main():
    initial=read(HOME/'INITIAL_INCOMPLETE_DEVELOPMENT_v1_0_1/DATASET_QA_AND_COUNTS.json')
    require(initial['classification']=='PASS_DATASET_QA' and initial['completed_runs_included']==8,'Initial usable dataset not verified')
    delivery=read(HOME/'INITIAL_INCOMPLETE_DEVELOPMENT_v1_0_1_DELIVERY.json')
    require(sha(delivery['archive'])==delivery['sha256'],'Initial fallback ZIP changed')
    require(read(HOME/'runtime_startup/RECOVERY_RESULTS.json')['classification']=='RECOVERY_PASS','Startup did not pass')
    adapter=identity();collector=implementation_identity()
    require(adapter=='44ed53dfb2a2316a9a529d5b7340932d35e4cc4929d52af0e720c82c0ebc2afb' and collector=='c8b25149091419b514e8a65dd1987b624ac296ade6c27e527d616d778a813e86','Frozen implementation changed')
    m=read(ROOT/'stage4e_d2i_1/campaign_manifest.json');baseline=read(BASELINE)
    registry=Registry(STATE,baseline);registry.verify_evidence()
    ids=[g+s for g in GROUPS for s in ('_N','_X')]
    selected=[next(r for r in m['runs'] if r['run_id']==rid) for rid in ids]
    require(len(selected)==16 and sum(r['maximum_advances'] for r in selected)==13824,'Additional budget changed')
    # Validate each pair in authorization order; never relabel immutable slots.
    for i in range(0,16,2):registry.check_selection(selected[i:i+2])
    save_new(HOME/'PUBLIC_EXECUTION_ENTRY.json',{'utc':utc(),'run_ids':ids,'maximum_instances':16,'maximum_advances':13824,
        'initial_dataset_sha256':delivery['sha256'],'no_retry':True,'one_authorization_covers_all_eight_pairs':True})
    authtext=(HOME/'USER_AUTHORIZATION.md').read_text(encoding='utf-8-sig');proof=ROOT/'stage4e_d2_pair01/v1_0_0/PRODUCTION_PREREQUISITE_RECEIPT.json'
    results=[];qualified=[];audits=[];failure=None
    try:
        for group in GROUPS:
            pair=[next(r for r in m['runs'] if r['run_id']==group+s) for s in ('_N','_X')]
            run_ids=[r['run_id'] for r in pair];batch='PUBLIC_D2_'+group+'_20261115_01'
            d=HOME/'batch_authorizations'/group;d.mkdir(parents=True)
            envelope={'status':'AUTHORIZED_PUBLIC_PAIR','group_id':group,'selected_runs':pair,
                'source_production_config_sha256':digest(m),'policy':m['policy'],'reporting':m['reporting'],'acceptance':m['acceptance'],
                'collector_sha256':collector,'adapter_sha256':adapter,'maximum_instances':2,'maximum_advances':1728}
            save_new(d/'PAIR_CONFIGURATION.json',envelope);pairsha=digest(envelope)
            legacy={'status':'EXPLICITLY_AUTHORIZED','version':'SDP_D2_COLLECTOR_1.0.1','purpose':'production',
                'implementation_manifest_sha256':collector,'config_sha256':digest(m),'run_ids':run_ids,
                'maximum_fresh_instances':2,'maximum_advances':1728,'user_authorization_text':authtext,'authorized_utc':utc(),
                'pair_configuration_sha256':pairsha}
            save_new(d/'COLLECTOR_AUTHORIZATION.json',legacy)
            new={'status':'EXPLICITLY_AUTHORIZED','version':'SDP_D2_EVIDENCE_ADAPTER_1.1.0','implementation_manifest_sha256':adapter,
                'baseline_sha256':sha(BASELINE),'config_sha256':digest(m),'run_ids':run_ids,'batch_id':batch,
                'collector_approval_sha256':sha(d/'COLLECTOR_AUTHORIZATION.json'),'maximum_fresh_instances':2,'maximum_advances':1728,
                'user_authorization_text':authtext,'authorized_utc':utc(),'pair_configuration_sha256':pairsha}
            save_new(d/'ADAPTER_AUTHORIZATION.json',new)
            print('BEGIN_AUTHORIZED_PAIR',group,'slots',run_ids,flush=True)
            result=future_batch(m,run_ids,batch,d/'ADAPTER_AUTHORIZATION.json',d/'COLLECTOR_AUTHORIZATION.json',proof)
            save_new(d/'EXECUTION_RESULT.json',result);results.append(result)
            for run,completed in zip(pair,result['runs']):
                if completed['classification']=='PASS_VALID_RAW':
                    audit=audit_run(STATE/'batches'/batch/run['run_id'],run,m)
                    audits.append(audit);save_new(d/(run['run_id']+'_INDEPENDENT_RAW_QA.json'),audit)
                    qualified.append(run['run_id'])
            registry.verify_evidence()
            require(result['classification']=='RAW_COMPLETE_ACCEPTANCE_REVIEW_REQUIRED' and not result['pair_error'],'Critical pair failure; stop subsequent pairs')
            print('PAIR_COMPLETE',group,'independent QA PASS; cooling qualification',result['excitation_audit'][group]['cooling_group_qualified'],flush=True)
    except BaseException as exc:
        failure=f'{type(exc).__name__}: {exc}'
        print('STOP_FURTHER_SIMULATIONS',failure,flush=True)
    finally:
        inventory=registry.inventory()
        save_new(HOME/'PUBLIC_EXECUTION_RESULT.json',{'classification':'ALL_16_PUBLIC_RUNS_COMPLETE' if len(qualified)==16 and failure is None else 'STOPPED_INCOMPLETE_PUBLIC_COLLECTION',
            'results':results,'independent_audits':audits,'qualified_additional_run_ids':qualified,'failure':failure,
            'fresh_attempts_reserved':sum(s.get('reservation',{}).get('run_id') in ids for s in inventory),
            'successful_scored_advances':sum(a['advances'] for a in audits),'inventory':inventory,
            'extra_simulations_authorized':False,'protected_collection':False,'completed_utc':utc()})
    if failure:raise SystemExit(1)

if __name__=='__main__':main()
