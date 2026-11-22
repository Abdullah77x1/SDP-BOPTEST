"""Frozen common-schema, seed, resource and model settings. No validation paths."""
from pathlib import Path
ROOT=Path(__file__).resolve().parent
WORKSPACE=ROOT.parents[1]
SOURCE=ROOT.parent/'hvac_16_outputs_v2_0_0'
AUDIT=ROOT.parent/'hvac_low_error_audit_2026_11_17_v1_0_0'
PILOT=WORKSPACE/'SDP_BOPTEST_Pilot'
MODEL=PILOT/'deployment/official_v0.9.0/project1-boptest-0.9.0/testcases/bestest_air/models'
HORIZONS=[5,10,15,30]
QUANTITIES=['indoor_temp','cooling_electric_power','fan_electric_power','heating_thermal_power']
TARGETS=[f'target_{kind}_{h}min_'+('c' if kind=='indoor_temp' else 'kw') for kind in QUANTITIES for h in HORIZONS]
FEATURES=['indoor_temp_c','indoor_temp_5min_ago_c','indoor_temp_30min_ago_c','outdoor_temp_c','solar_irradiance_w_m2','cooling_setpoint_current_c','heating_setpoint_current_c','cooling_override_current','cooling_override_committed','cooling_setpoint_change_committed_k','occupancy_now','occupancy_forecast_30min','outdoor_temp_forecast_30min_k','solar_forecast_30min_w_m2','time_of_day_sin','time_of_day_cos']+[f'{kind}_{suffix}_kw' for kind in QUANTITIES[1:] for suffix in ['last_5min','previous_5min','30min_ago']]
MODELS=['Persistence','OLS','Ridge','RandomForest','XGBoost']
PERSISTENCE_INPUTS=['indoor_temp_c']+[f'{kind}_last_5min_kw' for kind in QUANTITIES[1:]]
SEED=20261117
RIDGE_ALPHAS=[.1,1.,10.,100.]
WORKERS=4
RF_PARAMS={'n_estimators':128,'max_depth':12,'min_samples_leaf':8,'max_features':.8,'bootstrap':True,'n_jobs':1,'criterion':'squared_error'}
XGB_PARAMS={'n_estimators':240,'max_depth':3,'learning_rate':.05,'min_child_weight':5,'reg_lambda':1.,'reg_alpha':0.,'subsample':1.,'colsample_bytree':1.,'tree_method':'hist','objective':'reg:squarederror','n_jobs':1,'verbosity':0,'max_bin':256,'device':'cpu'}
ACTIVITY_THRESHOLDS=[.001,.01,.05]
ABRUPT_THRESHOLDS=[1.,2.,3.]
