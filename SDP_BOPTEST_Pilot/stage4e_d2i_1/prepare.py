"""One-time offline materialization of immutable configuration documents."""
from .common import HOME,save_new,digest
from .manifest import canonical_manifest
from .schema import canonical_schema

def prepare():
    for purpose,name in (('production','campaign_manifest.json'),('preflight','preflight_manifest.json')):
        config=canonical_manifest(purpose);save_new(HOME/name,config)
        save_new(HOME/(purpose+'_approval_NOT_AUTHORIZED.json'),{
            'version':config['version'],'status':'NOT_AUTHORIZED','purpose':purpose,
            'config_sha256':digest(config),'implementation_manifest_sha256':None,
            'run_ids':[],'maximum_fresh_instances':0,'maximum_advances':0,
            'user_authorization_text':None,'authorized_utc':None})
    save_new(HOME/'schema_manifest.json',canonical_schema())
    save_new(HOME/'ATTEMPT_LEDGER_NOT_AUTHORIZED.json',{
        'version':canonical_manifest()['version'],'authorization_status':'NOT_AUTHORIZED','real_attempts_consumed':0,
        'new_production_slots':{r['run_id']:'UNUSED_NOT_AUTHORIZED' for r in canonical_manifest()['runs'] if not r['reused']},
        'preflight_slots':{r['run_id']:'UNUSED_NOT_AUTHORIZED' for r in canonical_manifest('preflight')['runs']},
        'reused_runs':'REFERENCES_ONLY_NO_NEW_SLOT_NO_REEXECUTION',
        'future_execution_accounting':'Exclusive fixed campaign directory, ATTEMPT_STARTED before deployment, no resume or replacement'})

if __name__=='__main__':prepare()
