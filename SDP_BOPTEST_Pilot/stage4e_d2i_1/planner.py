"""Metadata/command intentions only. No client construction or trajectory values."""
from .common import digest
from .manifest import validate_manifest
from stage4e_d0.plan import nominal

def dry_run(manifest):
    counts=validate_manifest(manifest);plans=[]
    for run in manifest['runs']:
        intentions=[]
        if not run['reused']:
            for t in range(run['start'],run['end'],300):
                intentions.append(nominal(run,t,manifest['policy']))
        plans.append({'run_id':run['run_id'],'group_id':run['group_id'],'partition':run['partition'],
            'disposition':'REFERENCE_EXISTING_ONLY' if run['reused'] else 'REFUSED_PENDING_D2I2' if run['partition']=='protected_final_test' else 'FUTURE_AUTHORIZATION_AND_PREREQUISITES_REQUIRED',
            'initialization_intention':run['initialization'],'scored_end_intention':run['end'],
            'planned_advances':len(intentions),'nominal_command_intentions_sha256':digest(intentions),
            'nominal_active_intervals':sum(p['command']['con_oveTSetCoo_activate'] for p in intentions),
            'applied_actions':'UNKNOWN; future observed safety veto has priority',
            'collection_requests_intended':manifest['reporting'],'real_API_calls':0,'datasets_constructed':False})
    return {'operation':'OFFLINE_DRY_RUN_INTENTIONS_ONLY','version':manifest['version'],'config_sha256':digest(manifest),
        'arithmetic':counts,'run_intentions':plans,'instances_initialized':0,'network_access':False,
        'FMU_execution':False,'protected_results_access':False,'supervised_dataset_constructed':False}
