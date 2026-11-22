"""Offline prepare/freeze stages; exclusive writes, no network or Docker calls."""
import json,sys
from copy import deepcopy
from .runner import HERE,ROOT,CAMPAIGN_ID,VERSION,read,save_new,sha,utc

def prepare():
    old=read(ROOT/'stage4e_d0/campaign.json');new=deepcopy(old)
    new.update(protocol=CAMPAIGN_ID,campaign_id=CAMPAIGN_ID,validation_contract=VERSION)
    for r in new['runs']:
        r['attempt_id']='V2_'+r['attempt_id']
        r['evidence_directory']='stage4e_d1_v2/campaign_evidence/'+r['attempt_id']
    save_new(HERE/'campaign.json',new)
    save_new(HERE/'attempt_ledger.json',{'campaign_id':CAMPAIGN_ID,'authorization_status':'NOT_AUTHORIZED',
        'attempts':[{'attempt_id':r['attempt_id'],'state':'UNUSED','maximum_instances':1,'maximum_advances':864,
            'evidence_directory':r['evidence_directory']} for r in new['runs']],
        'maximum_total_advances':3456,'retry_authorized':False,
        'consumption_rule':'exclusive attempt directory + ATTEMPT_STARTED before deployment; never overwrite or resume',
        'original_Q01_N':'CONSUMED_FAILED','original_Q02_X_Q03_N_Q04_X':'UNUSED; not part of this campaign'})
    save_new(HERE/'execution_authorization.template.json',{'status':'NOT_AUTHORIZED','campaign_id':CAMPAIGN_ID,
        'proposal_sha256':'REQUIRES_FINAL_FROZEN_MANIFEST_SHA256','attempt_ids':[r['attempt_id'] for r in new['runs']],
        'maximum_advances':3456,'authorized_utc':None,'user_authorization_text':None})
    differences=[]
    for key in sorted(set(old)|set(new)):
        if key=='runs':continue
        if old.get(key)!=new.get(key):differences.append({'field':key,'old':old.get(key),'new':new.get(key)})
    for a,b in zip(old['runs'],new['runs']):
        for key in a:
            if a[key]!=b[key]:differences.append({'field':a['attempt_id']+'.'+key,'old':a[key],'new':b[key]})
    save_new(HERE/'CONFIGURATION_DIFF.json',{'differences':differences,'physics_calendar_weather_sizing_controls_changed':False})

def freeze():
    names=[p.relative_to(ROOT).as_posix() for p in HERE.rglob('*') if p.is_file() and '__pycache__' not in p.parts]
    names += ['STAGE4E_SETPOINT_VALIDATION_V2_1.md','STAGE4E_REVISED_CAMPAIGN_PROTOCOL.md',
        'STAGE4E_V2_CONTRACT_CHANGELOG.md','STAGE4E_V2_AUTHORIZATION_REVIEW.md',
        'stage4e_d0/FROZEN_MANIFEST.json','stage4e_d1/FINAL_ARTIFACT_MANIFEST.json',
        'stage4e_d1r/FINAL_ARTIFACT_MANIFEST.json','stage4e_d1r_bm01/FINAL_ARTIFACT_MANIFEST.json',
        'stage4e_runtime_preflight/FINAL_ARTIFACT_MANIFEST.json',
        'stage4e_runtime_preflight/evidence/QUALIFIED_RECORD.json',
        'stage4e_runtime_preflight/evidence/WORKER_EXECUTABLE_AND_DEPENDENCIES.json',
        'stage4e_d1r/proposed_validation.py','stage4e_runtime_preflight/preflight.py']
    # Freeze transitive D0 software/data contracts and the statically bound native source.
    names+=list(read(ROOT/'stage4e_d0/FROZEN_MANIFEST.json')['files'])
    names+=['deployment/official_v0.9.0/project1-boptest-0.9.0/testcases/bestest_air/models/BESTESTAir/BaseClasses/Thermostat_T.mo']
    names+=['stage4e_d1r/REFERENCE_BINDING.json','stage4e_d1r/FMU_STATIC_METADATA.json']
    save_new(HERE/'FROZEN_MANIFEST.json',{'campaign_id':CAMPAIGN_ID,'frozen_utc':utc(),
        'status':'PREPARED_NOT_EXECUTION_AUTHORIZED','validation_contract':VERSION,'maximum_attempts':4,'maximum_advances':3456,
        'files':{n:sha(ROOT/n) for n in sorted(set(names))}})
    from .runner import verify_frozen
    digest=verify_frozen()
    with (HERE/'PROPOSAL_SHA256.txt').open('x',encoding='utf-8') as f:f.write(digest+'  FROZEN_MANIFEST.json\n')
    print(digest)

if __name__=='__main__':{'prepare':prepare,'freeze':freeze}[sys.argv[1]]()
