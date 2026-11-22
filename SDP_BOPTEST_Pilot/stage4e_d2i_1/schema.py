"""Schema/availability validation only. Never creates a supervised dataset."""
from copy import deepcopy
from .common import *
from stage4e_d0.plan import POINTS,FLAGS,COOL,FAN,HEAT,TEMP,validate_observation
from stage4e_d1_v2.validation import HISTORY_POINTS

META_PATH='stage4e_d1_v2/campaign_evidence/V2_Q01_N/runtime_metadata.json'
DICT_DIR=ROOT/'stage4e_d1p/DEVELOPMENT_ONLY_SDP_STAGE4E_D1P_v1_0_0'

def canonical_schema():
    meta=read(ROOT/META_PATH);dictionary=read(DICT_DIR/'DATA_DICTIONARY.json')['columns']
    optional=[p for p in read(ROOT/'stage4e_d2p/VARIABLE_INVENTORY.json')['recommended_new_passive_forecasts'] if p not in POINTS]
    raw={name:{'unit':v['Unit'],'minimum':v.get('Minimum'),'maximum':v.get('Maximum'),
        'role':'raw_observation' if kind=='measurements' else 'effective_readback_or_activation',
        'source':META_PATH+'#'+kind+'/'+name,'auto_ML_input':False}
        for kind in ('measurements','inputs') for name,v in meta[kind].items()}
    return {'version':VERSION,'raw_observations':raw,'native_history_keys':list(HISTORY_POINTS),
        'core_forecasts':{p:{'unit':meta['forecast_points'][p]['Unit'],'source':META_PATH+'#forecast_points/'+p,
            'evidence':'PRIOR_RUNTIME_VERIFIED','auto_ML_input':False} for p in POINTS},
        'optional_collected_variables':{p:{'unit':meta['forecast_points'][p]['Unit'],'source':META_PATH+'#forecast_points/'+p,
            'evidence':'METADATA_SUPPORTED_RUNTIME_QUALIFICATION_REQUIRED','auto_ML_input':False,'missing_policy':'UNAVAILABLE_WITH_REASON_NEVER_ZERO'} for p in optional},
        'static_specifications':{'role':'STATIC_METADATA_NOT_TIMESERIES','source':'stage4e_d2p/BUILDING_SPECIFICATIONS.json',
            'source_sha256':sha(ROOT/'stage4e_d2p/BUILDING_SPECIFICATIONS.json'),'auto_ML_input':False},
        'derived_engineering_quantities':{
            'cooling_removed_proxy_W':{'inputs':{COOL:3.},'unit':'W','role':'MODELSPECIFIC_AIRSIDE_THERMAL_PROXY_NOT_DIRECT_SENSIBLE_METER','auto_ML_input':False},
            'heating_added_proxy_W':{'inputs':{HEAT:.9},'unit':'W','role':'MODELSPECIFIC_AIRSIDE_THERMAL_PROXY_NOT_DIRECT_SENSIBLE_METER','auto_ML_input':False},
            'signed_HVAC_thermal_proxy_W':{'inputs':{HEAT:.9,COOL:-3.},'unit':'W','role':'MODELSPECIFIC_AIRSIDE_THERMAL_PROXY_NOT_ELECTRIC_LABEL','auto_ML_input':False}},
        'model_feature_candidates':{k:deepcopy(v) for k,v in dictionary.items() if v['role']=='feature'},
        'prediction_targets':{k:deepcopy(v) for k,v in dictionary.items() if v['role']=='target'},
        'provenance_metadata':{k:deepcopy(v) for k,v in dictionary.items() if v['role']=='metadata_not_feature'},
        'additional_provenance':{'partition':'EXPLICIT_IMMUTABLE_NOT_FEATURE','initialization':'CUSTOM_OR_NAMED_ACTUAL_METHOD',
            'seed':'NULL_DETERMINISTIC_NOT_FAKE_INDEPENDENT_REPLICATE','source_hashes':'REQUIRED','event_resolution':'POSTHOC_NOT_FEATURE',
            'future_realized_commands':'POSTHOC_NOT_FEATURE','current_command_availability':'ACTUAL_ORIGIN_CUTOFF_NOT_INHERITED_PLAN_ANNOTATION'},
        'electrical_target_boundary':{'channels':[COOL,FAN],'native_sample_s':30,'average_interval_s':300,
            'window':'[origin+horizon-300,origin+horizon]','gas_excluded':True,'endpoint_watt_substitution':False},
        'dataset_construction_enabled':False,'feature_selection_or_ranking_enabled':False}

def validate_schema(value):
    require(isinstance(value,dict),'Schema must be an object')
    require(digest(value)==digest(canonical_schema()),'Signal/schema/units/target/provenance definition mismatch')
    require(len(value['model_feature_candidates'])==168 and len(value['prediction_targets'])==8,'Compatibility schema cardinality')
    return {'status':'SCHEMA_VALID','raw_count':39,'core_forecasts':5,'optional_forecasts':9,'candidate_features':168,'targets':8}

def catalog_gate(actual,schema,qualified_optional=()):
    reference=read(ROOT/META_PATH)
    require(actual.get('version')=={'version':'0.9.0'} and actual.get('name')=={'name':'bestest_air'},'Runtime version/case mismatch')
    for kind in ('measurements','inputs'):
        require(set(actual.get(kind,{}))==set(reference[kind]),'Raw catalog changed: '+kind)
        for name,entry in reference[kind].items():
            for field in ('Unit','Minimum','Maximum'):
                require(actual[kind][name].get(field)==entry.get(field),'Raw unit/limit mismatch: '+name)
    available={}
    all_fields={**schema['core_forecasts'],**schema['optional_collected_variables']}
    for name,entry in all_fields.items():
        present=name in actual.get('forecast_points',{})
        if present:require(actual['forecast_points'][name].get('Unit')==entry['unit'],'Forecast unit mismatch: '+name)
        if name in schema['core_forecasts'] or name in qualified_optional:require(present,'Required forecast metadata unavailable: '+name)
        available[name]={'available':present,'status':'CATALOG_ONLY_NOT_VALUE_VERIFIED' if present else 'UNAVAILABLE_NOT_ZERO'}
    return available

def forecast_gate(data,origin,schema,qualified_optional=(),horizon=1800,preflight=False):
    require(data.get('time')==list(range(origin,origin+horizon+1,300)),'Forecast valid-time grid mismatch')
    n=horizon//300+1;availability={}
    for name in [*schema['core_forecasts'],*schema['optional_collected_variables']]:
        required=name in schema['core_forecasts'] or name in qualified_optional
        present=isinstance(data.get(name),list) and len(data[name])==n
        if present:
            for v in data[name]:finite(v)
        if required:require(present,'Missing required forecast: '+name)
        availability[name]={'status':'VALUES_RECEIVED' if present else 'UNAVAILABLE_NOT_ZERO',
            'values':deepcopy(data[name]) if present else None,'ML_feature_selection':'NOT_AUTOMATIC'}
    return availability

def observation_gate(obs,t,catalog):
    validate_observation(obs,t,catalog)
    require(obs['time']==t,'Exact endpoint clock required')
    require(200<obs[TEMP]<350,'Nonphysical indoor temperature')
    require(285.15<=obs['fcu_oveTSup_u']<=313.15,'Invalid effective supply setpoint')
    require(0<=obs['fcu_oveFan_u']<=1,'Invalid effective fan fraction')
    require(-1e-9<=obs['zon_weaSta_reaWeaRelHum_y']<=1+1e-9,'Invalid outdoor RH')
    return True
