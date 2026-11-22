"""Planning-only inventory completion; no data series, fitting or simulation."""
import json,zipfile,xml.etree.ElementTree as E
from .audit import OUT,ROOT,BASE,read

def main():
    p=OUT/'VARIABLE_INVENTORY.json';inv=read(p)
    extra=[]
    def add(name,unit,category,status,source,availability,purpose,limits,risk):
        extra.append({'name':name,'unit':unit,'category':category,'status':status,'source':source,
            'available_at_prediction':availability,'purpose':purpose,
            'relevance':{'ML':'optional preregistered ablation; not all are model inputs','RC':purpose,'optimization':'future simulator-specific causal boundary, not a validated optimizer'},
            'missing_data_limitations':limits,'leakage_risk':risk})
    for name,formula in [('q_cooling_removed_proxy_W','3*PCoo_electric'),('q_heating_added_proxy_W','0.9*PHea_gas'),
                         ('q_hvac_signed_proxy_W','0.9*PHea_gas-3*PCoo_electric')]:
        add(name,'W','A_DERIVED_THERMAL','DERIVED_MODEL_ALGEBRA_NOT_DIRECT_SENSIBLE_METER',
            'selected FMU COP/eff XML + FanCoilUnit_T.mo powCooThe/powHeaThe/gain equations: '+formula,
            'only after underlying native power sample receipt; future values are never inputs',
            'model-specific airside heating/cooling influence for future RC identification',
            'fixed COP/eff only; includes enthalpy definition; not independently metered zone sensible load; no series constructed here',
            'do not use future power or promote proxy to physical real-building ground truth')
    add('internal_sensible_gain_proxy_W','W','A_DERIVED_PROXY','DERIVED_APPROXIMATION',
        'P_lighting+P_plug+73*scheduled_occupants; Case600FF + OccupancyLoad',
        'current/past measured load + issued schedule only','approximate sensible internal forcing',
        'scheduled people are not actual table output at discontinuities; radiant/convective splits and thermal storage remain',
        'published occupancy/gain forecasts are independent of instantaneous native internal gains')
    for field in ('InternalGainsCon[1]','InternalGainsRad[1]','InternalGainsLat[1]'):
        add(field,'W','B_KNOWN_BOUNDARY','METADATA_SOURCE_SUPPORTED_NOT_RUNTIME_VALUES_VERIFIED',
            'actual saved forecast_points metadata + embedded internal_setpoints_occupancy resource',
            'only after actual as-issued forecast receipt','collect sensible/radiant/latent schedule boundaries for RC context',
            'passive preflight required; not a direct zone heat-flux meter','never replace a native measured heat flux with a forecast')
    add('historical_temperature_slope_K_s','K/s','B_HISTORICAL','DERIVED_PROPOSAL_NOT_COMPUTED',
        '(T(t)-T(t-300))/300 from received endpoints','at origin after both endpoints','thermal-response state proxy',
        'no centered/future differences; measurement noise can dominate','centered derivative would leak future temperature')
    add('historical_rolling_mean_temperature_c','degC','B_HISTORICAL','DERIVED_PROPOSAL_NOT_COMPUTED',
        'trailing [t-1800,t] observations, fixed window definition','after all samples received','optional smoothing/ablation',
        'keep 35-minute support if no additional power window; any longer window requires revised purge','no centered rolling summaries or whole-run normalization')
    add('benchmark_weekday','0..6','B_CALENDAR','ASSUMED_OPTIONAL_NOT_PRIMARY_FEATURE',
        'TMY file Sunday anchor + simulation day offset','known only under explicitly declared anchor','possible calendar experiment',
        'native internal loads repeat daily; this is not a real Gregorian weekday nor verified weekday operating variation','weather/group identification and artificial weekend claims')
    specs=read(OUT/'BUILDING_SPECIFICATIONS.json')
    for spec in specs['verified_static_parameters']:
        add(spec['name'],spec['unit'] or 'XML unit undeclared; interpret with source equation','C_STATIC_SPEC',
            spec['status'],'selected FMU XML + Modelica source','known before run','constant specification/prior, kept outside ML matrix',
            'XML starts/constants are not live meters or independently calibrated properties','constant is not a dynamic predictor; never use a fitted value from protected outcomes')
    for name,unit in [('R_effective','K/W'),('C_effective','J/K'),('R_air_mass','K/W'),('C_mass','J/K'),
        ('effective_solar_aperture','m2'),('rated_coil_thermal_capacity','W')]:
        add(name,unit,'C_UNKNOWN_OR_FUTURE_ESTIMATE','UNKNOWN_NOT_ESTIMATED',
            'no approved RC fit or finite rated-capacity specification','not available as an observed input','future identifiable reduced-order model parameter, if supported',
            'no numerical value supplied; high-mass distributed model does not imply a unique lumped equivalent','fitting on validation/protected data would leak outcomes')
    dictionary=read(ROOT/'stage4e_d1p/DEVELOPMENT_ONLY_SDP_STAGE4E_D1P_v1_0_0/DATA_DICTIONARY.json')['columns']
    for name,spec in dictionary.items():
        if spec['role']=='feature':continue
        target=spec['role']=='target'
        add(name,spec['unit'],'E_TARGET' if target else 'D_METADATA','DERIVED_TARGET' if target else 'RECORDED_OR_DETERMINISTIC_METADATA',
            spec['source'],'future label only' if target else 'identity/clock at origin or journal provenance; not automatically a feature',
            spec['definition'],'preserve four horizons/last-five-minute electrical definition; no endpoint substitution' if target else 'metadata not final-test evidence',
            'must never enter prediction inputs' if target else 'IDs, partition and later validation metadata can identify trajectories or leak outcomes')
    for name,unit in [('seed','nullable integer'),('initialization_method','category'),('warmup_seconds','s'),
        ('FMU_sha256','SHA-256'),('simulator_version','version'),('dependency_component','identifier'),
        ('forecast_issue_and_receipt','sim s + UTC + journal order'),('controller_proposal_hash','SHA-256')]:
        add(name,unit,'D_METADATA','REQUIRED_PROVENANCE_PROPOSAL','D2 manifest/runtime receipts',
            'known when recorded, but not a primary model feature','reproducibility and audit',
            'native deterministic run has no stochastic seed; store null/NOT_APPLICABLE, not a fictitious independent replicate',
            'later resolutions, future veto outcomes and protected membership are not predictors')
    inv['proposed_derived_constants_metadata_targets']=extra
    inv['recommended_new_passive_forecasts']=['LowerSetp[1]','UpperSetp[1]','Occupancy[1]','TDryBul','HGloHor',
        'InternalGainsCon[1]','InternalGainsRad[1]','InternalGainsLat[1]','HDirNor','HDifHor','relHum','winSpe','winDir','pAtm']
    inv['new_reporting_policy']='same optional passive requests in every new arm; five existing channels mandatory; preflight new channels before campaign. Never pad old reused runs with zeros.'
    p.write_text(json.dumps(inv,indent=2)+'\n',encoding='utf-8')
    print('Inventory completed:',len(inv['audited_D1P_features']),'existing features,',len(inv['API_catalog']),'API entries,',len(extra),'spec/proxy/metadata/target entries.')

if __name__=='__main__':main()
