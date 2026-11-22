"""Approved-plan-bound metadata validation; never opens protected results."""
from collections import Counter
from copy import deepcopy
from .common import *
from .schema import canonical_schema,validate_schema
from stage4e.dataset import FeatureSpec,HORIZONS
from .acceptance import LIMITS

PARTITIONS={'development','validation','protected_final_test'}

def origin_times(start,end,spec=None,horizons=HORIZONS):
    spec=spec or FeatureSpec()
    lookback=max(spec.lags)+(300 if spec.interval_power else 0)
    return [t for t in range(start,end+1,300) if t-lookback>=start and t+max(horizons)<=end]

def policy_config():
    original=read(ROOT/'stage4e_d1_v2/campaign.json')
    return {k:deepcopy(v) for k,v in original.items() if k not in ('runs','protocol','campaign_id','validation_contract','maximum_attempts','maximum_advances')}

def validate_initialization(init,start,end):
    require(type(start) is int and type(end) is int and start%300==0,'Initialization time/grid must be integer 300s aligned')
    require(set(init)=={'method','start_time','warmup_period','scenario_key'},'Initialization schema changed')
    require(init['warmup_period']==604800 and type(init['warmup_period']) is int,'Seven-day native warmup required')
    require(init['start_time']==start and start>=604800,'Wrong/clipped initialization start or warmup')
    require(start<end<=31536000 and end+1500<=31536000,'Scored/forecast window outside source year')
    if init['method']=='custom':require(init['scenario_key'] is None,'Custom initialization cannot masquerade as named scenario')
    elif init['method']=='scenario':
        days=read(ROOT/'deployment/official_v0.9.0/project1-boptest-0.9.0/testcases/bestest_air/models/days.json')
        key=init['scenario_key'];require(key in days,'Invalid scenario key')
        require(start==(days[key]-7)*86400,'Named scenario starts seven days before selected day')
        require(end<=start+14*86400,'Named scenario envelope exceeded')
    else:raise ContractError('Unknown initialization method')
    return True

def canonical_manifest(purpose='production'):
    require(purpose in ('production','preflight'),'Unsupported manifest purpose')
    source=read(ROOT/'stage4e_d2p/COLLECTION_AND_PARTITION_PLAN.json')
    groups=[];runs=[]
    for g in source['recommended']:
        if purpose=='preflight' and g['start_day_offset'] not in (20,74,174,258):continue
        group={'group_id':g['group_id'],'partition':g['partition'],'calendar_bin':g['calendar_regime_bin'],
            'warmup_start':g['warmup_start_s'],'start':g['scored_start_s'],
            'end':g['scored_start_s']+900 if purpose=='preflight' else g['scored_end_s']}
        groups.append(group)
        for i,mode in enumerate(('native',) if purpose=='preflight' else ('native','scheduled_variation')):
            reused=purpose=='production' and g['new_instances']==0
            rid=g['reused_run_ids'][i] if reused else f"D2PF_G{g['start_day_offset']:03d}" if purpose=='preflight' else g['group_id']+('_N' if i==0 else '_X')
            key=('typical_heat_day' if g['start_day_offset']==44 else 'typical_cool_day') if reused else None
            runs.append({'run_id':rid,'group_id':g['group_id'],'partition':g['partition'],
                'dataset_partition':'protected_test' if g['partition']=='protected_final_test' else g['partition'],
                'mode':mode,'reused':reused,'start':group['start'],'end':group['end'],
                'warmup_start':group['warmup_start'],'step':300,'native_step':30,
                'maximum_advances':(group['end']-group['start'])//300,
                'initialization':{'method':'scenario' if reused else 'custom','start_time':group['start'],
                    'warmup_period':604800,'scenario_key':key},
                'source_run':f'stage4e_d1_v2/campaign_evidence/{rid}' if reused else None,
                'source_group_id':g.get('legacy_source_group_id') if reused else None,
                'seed':None,'temperature_uncertainty':None,'solar_uncertainty':None})
    schema=canonical_schema()
    bindings={p:sha(ROOT/p) for p in ['stage4e_d2p/PLANNING_SNAPSHOT_MANIFEST.json','stage4e_d2p/COLLECTION_AND_PARTITION_PLAN.json',
        'stage4e_d2p/PROPOSED_RUN_SLOTS.json','stage4e_d2p/BUILDING_SPECIFICATIONS.json',
        'stage4e_d1p/DEVELOPMENT_ONLY_SDP_STAGE4E_D1P_v1_0_0/DATA_DICTIONARY.json',
        'stage4e_d1p/DEVELOPMENT_ONLY_SDP_STAGE4E_D1P_v1_0_0/FEATURE_GROUPS.json',
        'stage4e_d1_v2/campaign.json','stage4e_d1_v2/validation.py','stage4e_d0/plan.py','stage4e/dataset.py',
        'stage4e_d1_v2/campaign_evidence/V2_Q01_N/runtime_metadata.json',
        'stage4e_d0/RUNTIME_REFERENCE_IDENTITIES.json',
        'deployment/official_v0.9.0/project1-boptest-0.9.0/testcases/bestest_air/models/days.json']}
    return {'version':VERSION,'campaign_id':'SDP_D2_'+purpose.upper()+'_1.0.0','purpose':purpose,
        'planning_snapshot_sha256':PLAN_SHA,'source_bindings':bindings,'schema_sha256':digest(schema),
        'groups':groups,'runs':runs,'policy':policy_config(),'reporting':{
            'core_forecasts':list(schema['core_forecasts']),'optional_forecasts':list(schema['optional_collected_variables']),
            'common_new_arm_profile':'ALL_14_PENDING_SEPARATE_PREFLIGHT_QUALIFICATION',
            'forecast_horizon_s':1800,'forecast_interval_s':300,'native_history_keys':schema['native_history_keys'],
            'missing_optional_policy':'PREFLIGHT_RECORD_UNAVAILABLE;PRODUCTION_REQUIRES_FROZEN_QUALIFIED_PROFILE;NEVER_ZERO'},
        'acceptance':deepcopy(LIMITS),
        'origin_support':{'lags_s':list(FeatureSpec().lags),'historical_interval_power':True,'horizons_s':list(HORIZONS)},
        'cross_group_embargo_s':3600,'model':{'version':'0.9.0','name':'bestest_air','FMU_sha256':FMU_SHA},
        'protected_custody_status':'D2I2_NOT_IMPLEMENTED_COLLECTION_ALWAYS_REFUSED',
        'dataset_construction_enabled':False,'authorization_status':'NOT_AUTHORIZED'}

def validate_manifest(manifest,check_sources=True):
    require(isinstance(manifest,dict),'Manifest must be an object')
    require(manifest.get('purpose') in ('production','preflight'),'Invalid manifest purpose')
    purpose=manifest['purpose'];groups=manifest.get('groups',[]);runs=manifest.get('runs',[])
    require(isinstance(groups,list) and isinstance(runs,list) and groups and runs,'Missing groups/runs')
    ids=[g.get('group_id') for g in groups];rids=[r.get('run_id') for r in runs]
    require(all(isinstance(x,str) and x for x in ids+rids),'Invalid identifier')
    require(len(ids)==len(set(ids)) and len(rids)==len(set(rids)),'Duplicate run/group identifiers')
    by_group={g['group_id']:g for g in groups}
    for i,g in enumerate(groups):
        require(g.get('partition') in PARTITIONS,'Explicit valid partition required')
        require(g.get('warmup_start')==g.get('start',0)-604800,'Warmup footprint mismatch')
        require(g.get('end',0)-g.get('start',0)==(259200 if purpose=='production' else 900),'Wrong scored duration')
        for h in groups[i+1:]:
            require(max(g['warmup_start'],h['warmup_start'])>min(g['end'],h['end'])+3600,'Overlapping dependency footprints/embargo')
    for r in runs:
        require(r.get('group_id') in by_group,'Unresolved group reference')
        g=by_group[r['group_id']]
        require(r.get('partition')==g['partition'],'Run/group partition relabeling forbidden')
        require(r.get('dataset_partition')==('protected_test' if g['partition']=='protected_final_test' else g['partition']),'Dataset partition bypass')
        require(r.get('step')==300 and type(r.get('step')) is int and r.get('native_step')==30,'Wrong sampling periods')
        require((r.get('start'),r.get('end'),r.get('warmup_start'))==(g['start'],g['end'],g['warmup_start']),'Run/group boundaries differ')
        validate_initialization(r.get('initialization',{}),r['start'],r['end'])
        require(r.get('maximum_advances')==(r['end']-r['start'])//300,'Advance budget inconsistent')
        require(r.get('mode') in ('native','scheduled_variation'),'Unapproved policy')
        if r.get('reused'):
            require(r['partition']=='development' and r.get('source_run') is not None,'Reuse is development-only')
            require(r['initialization']['method']=='scenario','Reused provenance changed')
        else:require(r.get('source_run') is None,'New slot cannot substitute an old run')
        if r['partition']!='development':
            source=read(ROOT/'stage4e_d2p/COLLECTION_AND_PARTITION_PLAN.json')
            for exposed in source['existing_exposed_footprints']:
                require(max(r['warmup_start'],exposed['warmup_start_s'])>min(r['end'],exposed['scored_end_s'])+3600,
                    'Exposed dependency footprint cannot enter validation/protected partition')
    for g in groups:
        pair=[r for r in runs if r['group_id']==g['group_id']]
        require(len(pair)==(2 if purpose=='production' else 1),'Native/control pairing broken')
        require({r['mode'] for r in pair}==({'native','scheduled_variation'} if purpose=='production' else {'native'}),'Native/control consistency')
    if check_sources:
        verify_planning_sources()
        for name,h in manifest.get('source_bindings',{}).items():require(sha(safe_source(name))==h,'Source/config provenance mismatch')
        if purpose=='production':
            slots=read(ROOT/'stage4e_d2p/PROPOSED_RUN_SLOTS.json')['new_slots']
            require({r['run_id'] for r in runs if not r['reused']}=={s['proposed_attempt_id'] for s in slots},'Run slots differ from approved slot inventory')
    require(digest(manifest)==digest(canonical_manifest(purpose)),'Manifest differs from approved immutable plan/schema/policy; versioned review required')
    return arithmetic(manifest)

def arithmetic(manifest):
    runs=manifest['runs'];new=[r for r in runs if not r['reused']]
    spec=FeatureSpec(lags=tuple(manifest['origin_support']['lags_s']),interval_power=manifest['origin_support']['historical_interval_power'])
    count=lambda rr:sum(len(origin_times(r['start'],r['end'],spec,tuple(manifest['origin_support']['horizons_s']))) for r in rr)
    return {'status':'MANIFEST_VALID_METADATA_ONLY','dependency_groups':len(manifest['groups']),'runs_total':len(runs),
        'reused_development_runs':len(runs)-len(new),'new_runs':len(new),'new_scored_advances':sum(r['maximum_advances'] for r in new),
        'projected_new_joint_origins':count(new),'projected_cumulative_joint_origins':count(runs),
        'partition_group_counts':dict(Counter(g['partition'] for g in manifest['groups'])),
        'origin_formula':{'lookback_s':max(spec.lags)+(300 if spec.interval_power else 0),'max_horizon_s':max(HORIZONS),
            'method':'endpoint-grid origins whose entire input and target support fits scored run; matches existing builder'},
        'dataset_constructed':False}

def select_run(manifest,run_id):
    validate_manifest(manifest)
    selected=[r for r in manifest['runs'] if r['run_id']==run_id]
    require(len(selected)==1,'Unauthorized run slot substitution')
    return deepcopy(selected[0])

def require_public_collection(run):
    # Deliberately no bool/string/attestation escape hatch in D2I-1.
    require(run['partition']!='protected_final_test' and run['dataset_partition']!='protected_test',
        'PROTECTED_COLLECTION_REFUSED_D2I2_CUSTODY_NOT_IMPLEMENTED')
    require(not run['reused'],'REUSED_RUN_MUST_NOT_BE_REEXECUTED')
