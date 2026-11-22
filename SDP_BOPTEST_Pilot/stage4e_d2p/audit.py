"""Static source, public weather, exposed development evidence and planning math."""
import csv,hashlib,io,json,math,re,socket,subprocess,zipfile
from collections import Counter,defaultdict
from datetime import datetime,timedelta
from pathlib import Path
from unittest.mock import patch
import xml.etree.ElementTree as ET
from stage4e_d1_v2.runner import ROOT,HERE,read,save_new,sha,verify_frozen,utc

OUT=Path(__file__).resolve().parent
REL=ROOT/'deployment/official_v0.9.0/project1-boptest-0.9.0'
BASE=REL/'testcases/bestest_air/models'
PREVIEW=ROOT/'stage4e_d1p/DEVELOPMENT_ONLY_SDP_STAGE4E_D1P_v1_0_0'
STATE={'scope':'PLANNING_ONLY_NOT_EXECUTION_AUTHORIZED','simulations':0,'model_fits':0,'dataset_release':False}
# Dates fixed by calendar/source coverage, not response inspection. Reuse only dev.
DESIGN=[(20,'winter','development'),(44,'winter','development'),(74,'spring','development'),
 (100,'spring','validation'),(126,'spring','protected_final_test'),(146,'spring','development'),
 (174,'summer','development'),(196,'summer','validation'),(218,'summer','development'),
 (240,'summer','protected_final_test'),(258,'autumn','development'),(270,'autumn','protected_final_test'),
 (288,'autumn','development'),(310,'autumn','validation'),(340,'winter','protected_final_test'),(354,'winter','validation')]
EXTRA=[(32,'winter','development'),(58,'winter_spring_transition','development'),(86,'spring','validation'),
 (112,'spring','protected_final_test'),(160,'summer','development'),(185,'summer','validation'),
 (207,'summer','protected_final_test'),(229,'summer','protected_final_test')]

def store(name,obj):save_new(OUT/name,{**STATE,**obj})
def conflict(a,b,embargo_s=3600):
    # Full closed warmup+scored support, followed by a minimum cross-group buffer.
    return max(a['warmup_start_s'],b['warmup_start_s'])<=min(a['scored_end_s'],b['scored_end_s'])+embargo_s
def group(day,season,partition):
    return {'group_id':f'D2_G{day:03d}','start_day_offset':day,'calendar_regime_bin':season,
        'partition':partition,'warmup_start_s':(day-7)*86400,'scored_start_s':day*86400,
        'scored_end_s':(day+3)*86400,'scored_hours':72,'warmup_seconds':604800,'step_seconds':300,
        'arms':['native','frozen_safe_cooling_variation'],
        'source':'REUSE_QUALIFIED_D1_V2' if day in (44,146) else 'PROPOSED_CUSTOM_INITIALIZATION',
        'new_instances':0 if day in (44,146) else 2,'new_scored_advances':0 if day in (44,146) else 1728,
        'runtime_status':'VERIFIED_EXISTING_72H_PAIR' if day in (44,146) else 'NOT_TESTED',
        'collector_compatibility':'D2_NEW_VERSION_REQUIRED; existing frozen v2 rejects custom initialize'}

def main():
    assert verify_frozen()=='ec9c64f9abffcda7095d537e375eda7bb8f6b6d367aa1aa2238bcc606bcbeb5c'
    prior=ROOT/'stage4e_d1p/PREVIEW_DELIVERY_MANIFEST.json'
    assert sha(prior)=='5da0d933b18ea68f719e52a18d5846a15e2cb28c57c3bbfc8f69322ec415b014'
    for p,h in read(prior)['files'].items():assert sha(ROOT/p)==h,p
    source_names=['STAGE4E_D1_V2_RESULTS.md','STAGE4E_D1P_DATASET_PREVIEW_RESULTS.md','STAGE4E_PREPARATION_READINESS.md',
      'BOPTEST_FUTURE_DATA_COLLECTION_PROPOSAL.md','stage4e_d0/campaign.json','stage4e_d1_v2/campaign.json',
      'stage4e_d1_v2/runner.py','stage4e_d1_v2/validation.py','stage4e/dataset.py','stage4e_d0/plan.py',
      'stage4e_d1_v2_execution/POSTFLIGHT_AUDIT.json','stage4e_d1_v2_execution/ADDITIONAL_RESULT_AUDIT.json',
      'stage4e_d1p/PREVIEW_DELIVERY_MANIFEST.json']
    for rel in ['testcase.py','data/find_days.py','data/data_manager.py',
       'testcases/bestest_air/models/days.json','testcases/bestest_air/models/config.json',
       'testcases/bestest_air/models/BESTESTAir/TestCases/TestCase_Ideal.mo',
       'testcases/bestest_air/models/BESTESTAir/BaseClasses/Case600FF.mo',
       'testcases/bestest_air/models/BESTESTAir/BaseClasses/Case900FF.mo',
       'testcases/bestest_air/models/BESTESTAir/BaseClasses/FanCoilUnit_T.mo',
       'testcases/bestest_air/models/BESTESTAir/BaseClasses/InternalLoad.mo',
       'testcases/bestest_air/models/BESTESTAir/BaseClasses/OccupancyLoad.mo',
       'testcases/bestest_air/models/BESTESTAir/BaseClasses/Thermostat_T.mo',
       'testcases/bestest_air/models/wrapped.mo','testcases/bestest_air/models/library_versions.json']:
        source_names.append((REL/rel).relative_to(ROOT).as_posix())
    sources={p:sha(ROOT/p) for p in source_names}
    fmu=BASE/'wrapped.fmu';assert sha(fmu)=='158008fa3b635280a67dfed8bab5804d1f9a96d218b467dfebab77e5cbf8b86a'
    sources[fmu.relative_to(ROOT).as_posix()]=sha(fmu)
    with zipfile.ZipFile(fmu) as z:
        days=json.loads(z.read('resources/days.json'));weather_bytes=z.read('resources/weather.csv')
        weather=list(csv.DictReader(io.StringIO(weather_bytes.decode())))
        mos_head=z.read('resources/0/DRYCOLD.mos').decode(errors='replace').splitlines()[:10]
        xmlbytes=z.read('modelDescription.xml');xml=ET.fromstring(xmlbytes)
        params={v.attrib['name']:{'value':v[0].get('start'),'unit':v[0].get('unit'),
            'causality':v.get('causality'),'description':v.get('description')} for v in xml.find('ModelVariables') if v[0].get('start') is not None}
        member_hashes={p:hashlib.sha256(z.read(p)).hexdigest() for p in ['resources/days.json','resources/weather.csv','resources/0/DRYCOLD.mos','modelDescription.xml']}
    assert len(weather)==35041 and float(weather[0]['time'])==0 and float(weather[-1]['time'])==31536000
    def weather_stats(start,end):
        block=[r for r in weather if start<=float(r['time'])<=end]
        times=[float(r['time']) for r in block];temps=[float(r['TDryBul'])-273.15 for r in block]
        solar=[float(r['HGloHor']) for r in block]
        assert times[0]==start and times[-1]==end
        return {'source_role':'EXOGENOUS_PUBLIC_WEATHER_ONLY_NOT_SIMULATED_BUILDING_OUTCOME',
            'samples':len(block),'outdoor_min_c':min(temps),'outdoor_max_c':max(temps),
            'outdoor_mean_c':sum(temps)/len(temps),'global_solar_peak_wm2':max(solar),
            'global_solar_kwh_m2':sum((solar[i]+solar[i-1])*.5*(times[i]-times[i-1]) for i in range(1,len(times)))/3600000,
            'low_solar_samples_below_20_wm2':sum(g<20 for g in solar),
            'heating_or_cooling_building_activity':'UNKNOWN_WITHOUT_NEW_RUNTIME'}
    scenarios=[]
    for name,day in days.items():
        start=day-7
        scenarios.append({'key':name,'source_selected_day':day,'API_start_day':start,'API_end_day':start+14,
            'API_warmup_start_day':start-7,'source_selected_day_in_first_72h':start<=day<start+3,
            'first_72h_runtime':'VERIFIED' if name in ('typical_heat_day','typical_cool_day') else 'VERIFIED_24H_ONLY' if name=='peak_cool_day' else 'NOT_TESTED',
            'weather_first_72h':weather_stats(start*86400,(start+3)*86400)})
    store('SCENARIO_AND_WEATHER_AUDIT.json',{'scenarios':scenarios,'annual_weather_samples':len(weather),
        'annual_weather_interval_s':900,'annual_weather_end_s':31536000,'weather_years':1,
        'weather_source_header':mos_head,'FMU_member_hashes':member_hashes,
        'named_scenario_duration_days':14,'all_named_first_72h_exclude_the_selected_day':True,
        'mix_is_not_a_calendar_shoulder_label':True})
    cases=[]
    for path in sorted((REL/'testcases').glob('*/models/wrapped.fmu')):
        cases.append({'case':path.parents[1].name,'local_FMU_present':True,'FMU_bytes':path.stat().st_size,
            'runtime_qualified_in_this_project':path.parents[1].name=='bestest_air',
            'same_physics_as_selected_model':path.parents[1].name=='bestest_air'})
    store('CASE_CATALOG.json',{'local_official_release_cases':cases,'changing_case_requires_new_reference_qualification':True})
    specs=[]
    patterns=[r'^mod\.fcu\.(COP|eff|mAir_flow_nominal|dpAir_nominal)$',r'^mod\.fcu\.fan\.addPowerToMedium$',
        r'^mod\.zon\.roo\.(AFlo|hRoo)$',r'^mod\.zon\.roo\.datConExtWin\[1\]\.(wWin|hWin|fFra)$',
        r'^mod\.zon\.(extWalCase900|floorCase900|roof)\.material\[\d+\]\.(x|k|c|d)$',
        r'^mod\.zon\.window600\.(UFra|haveExteriorShade|haveInteriorShade)$',
        r'^mod\.zon\.window600\.(glass|gas)\[\d+\]\.(x|k)$',
        r'^mod\.zon\.(soil)\.(x|k|c|d)$',r'^mod\.zon\.TSoi\[1\]\.T$',
        r'^mod\.zon\.InfiltrationRate\.k$',r'^mod\.zon\.(occ|lig|equ)\.(senPower|latPower|occ_density|senPower_nominal|latPower_nominal|radFraction)$']
    for name,info in params.items():
        if any(re.search(pattern,name) for pattern in patterns):specs.append({'name':name,**info,
            'status':'VERIFIED_STATIC_SELECTED_FMU_XML_START_OR_CONSTANT_NOT_RUNTIME_METER',
            'include_as_repeated_ML_feature':False})
    assert params['mod.fcu.COP']['value']=='3.0' and params['mod.fcu.eff']['value']=='0.9'
    layers={}
    for construction in ('extWalCase900','floorCase900','roof'):
        vals=[]
        for layer in range(1,5):
            prefix=f'mod.zon.{construction}.material[{layer}]'
            if prefix+'.x' not in params:continue
            vals.append({key:float(params[prefix+'.'+key]['value']) for key in ('x','k','c','d')})
        layers[construction]={'layers':vals,'material_only_R_m2K_W':sum(p['x']/p['k'] for p in vals),
            'material_areal_capacity_J_m2K':sum(p['x']*p['d']*p['c'] for p in vals),
            'not_an_identified_whole_zone_RC_parameter':True}
    store('BUILDING_SPECIFICATIONS.json',{'model':'bestest_air / BESTEST Case900FF via TestCase_Ideal',
        'FMU_sha256':sha(fmu),'XML_sha256':hashlib.sha256(xmlbytes).hexdigest(),'verified_static_parameters':specs,
        'source_documented_geometry':{'floor_dimensions_m':[6,8],'floor_area_m2':48,'height_m':2.7,
            'rough_window_openings_m2':12,'south_gross_wall_m2':21.6},
        'derived_geometry':{'volume_m3':48*2.7,'total_gross_wall_m2':2*(6+8)*2.7,
            'rough_south_window_to_wall_fraction':12/(8*2.7),'rough_all_wall_window_fraction':12/(2*(6+8)*2.7)},
        'derived_material_properties':layers,
        'source_thermal_proxy_formulas':{'cooling_removed_W':'3 * fcu_reaPCoo_y',
            'heating_added_W':'0.9 * fcu_reaPHea_y','signed_airside_HVAC_W':'0.9*PHea_gas - 3*PCoo_electric'},
        'thermal_proxy_status':'SOURCE_AND_XML_SUPPORTED_DERIVATION; NOT_DIRECT_ZONE_SENSIBLE_METER; NO_DATA_SERIES_GENERATED',
        'unknowns':['identified effective zone R/C','exact effective lumped solar aperture','rated finite coil capacity (ideal temperature source)',
            'runtime actual supply temperature (effective setpoint is not independent measurement)','unmeasured wall/soil state history']})
    groups=[group(*g) for g in DESIGN]
    for g in groups:g['public_weather_only']=weather_stats(g['scored_start_s'],g['scored_end_s'])
    previous_exposed=[{'group_id':'EXPOSED_D1_HEAT','warmup_start_s':37*86400,'scored_end_s':47*86400},
        {'group_id':'EXPOSED_D1_COOL_BM01','warmup_start_s':139*86400,'scored_end_s':149*86400},
        {'group_id':'EXPOSED_C4_D4_PEAK_COOL','warmup_start_s':275*86400,'scored_end_s':283*86400}]
    for i,a in enumerate(groups):
        assert 0<=a['warmup_start_s']<a['scored_start_s']<a['scored_end_s']<=31536000
        for b in groups[i+1:]:assert not conflict(a,b),(a,b)
        conflicts=[p['group_id'] for p in previous_exposed if conflict(a,p)]
        a['prior_exposed_connections']=conflicts
        if conflicts:assert a['partition']=='development',(a,conflicts)
    expanded=sorted(groups+[group(*g) for g in EXTRA],key=lambda g:g['scored_start_s'])
    for i,a in enumerate(expanded):
        for b in expanded[i+1:]:assert not conflict(a,b),(a,b)
        if any(conflict(a,p) for p in previous_exposed):assert a['partition']=='development'
    minimum=[g for g in groups if g['start_day_offset'] in (20,44,74,100,146,174,288,354)]
    # Minimum is development/validation feasibility, not a defensible protected test.
    min_groups=[dict(g,partition='validation' if g['start_day_offset'] in (100,354) else 'development') for g in minimum]
    store('COLLECTION_AND_PARTITION_PLAN.json',{'recommended':groups,'minimum':min_groups,'expanded':expanded,
        'new_runtime_authorization':False,'step_s':300,'scored_days_per_run':3,'warmup_days':7,
        'cross_group_embargo_s':3600,'existing_exposed_footprints':previous_exposed,
        'footprints_include_warmup_and_all_scored_feature_target_support':True,
        'all_partitions_planned_not_datasets':True,'statistically_independent_weather_years':1,
        'legacy_2_groups_reused_only_in_development':True})
    # Development-only feature usefulness audit, not a fit or a protected evaluation.
    dictionary=read(PREVIEW/'DATA_DICTIONARY.json')['columns']
    with (PREVIEW/'DEVELOPMENT_ONLY_OBSERVATIONAL.csv').open(encoding='utf-8',newline='') as f:rows=list(csv.DictReader(f))
    features=[name for name,entry in dictionary.items() if entry['role']=='feature'];assert len(features)==168
    audited=[];signatures=defaultdict(list)
    for name in features:
        entry=dictionary[name];values=[float(r[name]) for r in rows]
        signature=hashlib.sha256(json.dumps(values,separators=(',',':')).encode()).hexdigest();signatures[signature].append(name)
        category='A_DYNAMIC' if entry.get('lag_s')==0 and 'interval_kw' not in name else 'B_TEMPORAL_HISTORICAL_KNOWN_BOUNDARY'
        audited.append({'name':name,'unit':entry['unit'],'source':entry['source'],'category':category,
            'status':'DERIVED' if 'issued_cooling_delta' in name or 'interval_kw' in name or entry['group']=='calendar' else 'RUNTIME_OBSERVED_OR_AS_ISSUED',
            'available_at_prediction':entry.get('availability'),'purpose':entry['group'],
            'relevance':{'ML':'candidate ablation group, no usefulness ranking','RC':'depends on thermal boundary; observations not fitted parameters','optimization':'future causal state/proposal input only, not validated controller'},
            'missing_data_limitations':'complete in four D1P development arms only; future availability must be checked',
            'leakage_risk':'perfect benchmark forecast track' if 'boundary::' in name else 'known source time/group confounding' if 'benchmark_day' in name else 'must respect lag/receipt cutoff',
            'D1P_unique_values':len(set(values)),'D1P_min':min(values),'D1P_max':max(values),
            'constant_in_D1P_only':len(set(values))==1,'exclude_if_constant_in_future_train_partition_only':True})
    meta=read(HERE/'campaign_evidence/V2_Q01_N/runtime_metadata.json');api=[]
    for kind in ('measurements','inputs','forecast_points'):
        for name,info in meta[kind].items():api.append({'name':name,'kind':kind,'unit':info.get('Unit'),
            'source':'stage4e_d1_v2/campaign_evidence/V2_Q01_N/runtime_metadata.json#'+kind+'/'+name,
            'description':info.get('Description'),'status':'RUNTIME_VERIFIED' if kind!='forecast_points' or name in ('LowerSetp[1]','UpperSetp[1]','Occupancy[1]','TDryBul','HGloHor') else 'METADATA_SOURCE_SUPPORTED_NOT_RUNTIME_VALUE_VERIFIED',
            'available_at_prediction':'only after receipt at/before origin; forecasts use issued vintage',
            'purpose':'state/history' if kind=='measurements' else 'control/effective readback' if kind=='inputs' else 'known boundary',
            'relevance':'ML optional; RC source/thermal semantics must be checked; not optimization evidence',
            'missing_data_limitations':'additional forecast channels require separately authorized passive runtime preflight',
            'leakage_risk':'future measurement prohibited; forecasts not actual future observations'})
    store('VARIABLE_INVENTORY.json',{'audited_D1P_features':audited,'feature_count':168,
        'constant_D1P_feature_count':sum(v['constant_in_D1P_only'] for v in audited),
        'exact_duplicate_D1P_columns':[v for v in signatures.values() if len(v)>1],
        'API_catalog':api,'API_counts':{k:len(meta[k]) for k in ('measurements','inputs','forecast_points')},
        'all_168_not_mandatory':True,'no_feature_selection_fit_or_protected_data_used':True})
    execution=read(ROOT/'stage4e_d1_v2_execution/POSTFLIGHT_AUDIT.json')
    raw_bytes=sum(p.stat().st_size for p in (HERE/'campaign_evidence').rglob('*') if p.is_file())
    preview_bytes=sum(p.stat().st_size for p in PREVIEW.rglob('*') if p.is_file())
    storage_per_run=raw_bytes/4
    start=read(ROOT/'stage4e_d1_v2_execution/CAMPAIGN_DISPATCH_STARTED.json')['utc']
    end=read(ROOT/'stage4e_d1_v2_execution/CAMPAIGN_DISPATCH_COMPLETED.json')['utc']
    observed_s=(datetime.fromisoformat(end)-datetime.fromisoformat(start)).total_seconds()
    budgets=[]
    for name,gg in [('minimum',min_groups),('recommended',groups),('expanded',expanded)]:
        n=len(gg);new=n-2;total_runs=n*2;new_runs=new*2
        budgets.append({'plan':name,'temporal_dependency_groups_total':n,'new_groups':new,'existing_dev_groups':2,
            'runs_total':total_runs,'new_simulation_instances':new_runs,'new_scored_advances':new_runs*864,
            'cumulative_scored_intervals':total_runs*864,'cumulative_endpoint_rows':total_runs*865,
            'cumulative_native_scored_samples':total_runs*8641,'projected_joint_origins':total_runs*852,
            'new_joint_origins':new_runs*852,'projected_numeric_targets':total_runs*852*8,
            'partitions_by_group':dict(Counter(g['partition'] for g in gg)),
            'baseline_new_simulation_minutes':new_runs*observed_s/4/60,
            'planning_simulation_minutes_range':[new_runs*observed_s/4/60*2,new_runs*observed_s/4/60*4],
            'baseline_new_raw_bytes':round(new_runs*storage_per_run),'raw_reserve_bytes_3x':round(new_runs*storage_per_run*3),
            'baseline_preview_bytes_total':round(preview_bytes*total_runs/4),
            'forecast_collection_and_audit_cost_not_yet_benchmarked':True})
    store('BUDGET_CALCULATIONS.json',{'observed_D1_four_run_wall_seconds':observed_s,'observed_D1_seconds_per_run':observed_s/4,
        'observed_qualified_raw_bytes_total':raw_bytes,'observed_preview_uncompressed_bytes':preview_bytes,
        'observed_preview_zip_bytes':(ROOT/'stage4e_d1p/DEVELOPMENT_ONLY_SDP_STAGE4E_D1P_v1_0_0.zip').stat().st_size,
        'observed_runtime_basis':'same local machine, sequential four arms, seven-day warmup and online audits included; stack startup/offline preview excluded',
        'plans':budgets,'size_and_runtime_projections_are_assumptions_not_results':True,
        'preflight_budget_separate_proposal':{'fresh_instances_max':4,'native_advances_max':12,'purpose':'four seasonal development-only custom-start/reporting probes; separate explicit authorization required'}})
    store('INSPECTION_AND_SOURCE_MANIFEST.json',{'created_utc':utc(),'files':sources,
        'protected_simulator_outputs_or_reference_results_opened':False,'only_public_weather_and_exposed_development_features_analyzed':True,
        'previous_D1P_delivery_verified':True,'no_frozen_artifacts_modified':True})
    print(json.dumps({'scenarios':days,'groups':len(groups),'new_runs':28,'projected_rows':32*852,
        'constant_D1P_columns':sum(v['constant_in_D1P_only'] for v in audited),'raw_bytes_D1':raw_bytes,
        'FMU_static_parameters_recovered':len(specs),'planning_checks':'PASS'},indent=2))

if __name__=='__main__':
    with patch.object(socket.socket,'connect',side_effect=RuntimeError('D2P offline only')),patch.object(subprocess,'Popen',side_effect=RuntimeError('No Docker/process execution in planning')):main()
