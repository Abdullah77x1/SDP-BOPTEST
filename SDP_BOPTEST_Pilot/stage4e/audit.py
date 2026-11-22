"""Read saved evidence/source; emit metadata audit and matrix intermediary only.

Run: python -B -m stage4e.audit from the pilot workspace. No HTTP/Docker/ML.
No feature/label rows from preserved pilot evidence are written to disk.
"""
import base64
import collections
import csv
import hashlib
import json
import math
from pathlib import Path
from .dataset import (SIGNALS,read_stage4c,read_stage4d,build_rows,ContractError)

ROOT=Path(__file__).resolve().parents[1]
HERE=ROOT/'stage4e'
RELEASE=ROOT/'deployment/official_v0.9.0/project1-boptest-0.9.0'


def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()


def preservation_snapshot():
    files={}
    for manifest in [ROOT/'stage4d/preserved/STAGE4C_AB_HASHES.json',
                     ROOT/'stage4d/FINAL_ARTIFACT_MANIFEST.json',
                     ROOT/'stage4d/FROZEN_MANIFEST.json']:
        data=json.loads(manifest.read_text()); files.update(data.get('files',data))
    mismatch=[name for name,value in files.items() if digest(ROOT/name)!=value]
    if mismatch:raise ContractError('Preserved artifact changed: '+str(mismatch))
    return files


def main():
    before=preservation_snapshot()
    metadata=json.loads((ROOT/'evidence/local_matched_AB/A/runtime_metadata.json').read_text())
    a,b=[read_stage4c(ROOT/f'evidence/local_matched_AB/{arm}',arm) for arm in ('A','B')]
    d=read_stage4d(ROOT/'stage4d/evidence/authorized_replacement_demo')
    # Metadata step=3600 is the default queried before setting the 300s step.
    # Actual endpoint and native timestamp differences are the evidence of cadence.
    summaries=[]
    for r in (a,b,d):
        try:
            preview_rows=build_rows(r)
            smoke={'classification':'DEVELOPMENT_ONLY_IN_MEMORY_NO_ROWS_EXPORTED',
                   'eligible_origins_default_spec':len(preview_rows)}
        except ContractError as e:
            smoke={'classification':'INELIGIBLE_FOR_DUAL_TARGET_ROWS','reason':str(e)}
        summaries.append({'run_id':r.run_id,'endpoints':len(r.endpoints),
            'start':r.endpoints[0]['time'],'end':r.endpoints[-1]['time'],
            'endpoint_deltas':dict(collections.Counter(y['time']-x['time'] for x,y in zip(r.endpoints,r.endpoints[1:]))),
            'native_samples':len(r.native['time']) if r.native else None,
            'native_deltas':dict(collections.Counter(y-x for x,y in zip(r.native['time'],r.native['time'][1:]))) if r.native else None,
            'controls':len(r.control_history),'smoke_check':smoke})
    requested_forecasts={q.name for q in a.boundaries}
    matrix=[]
    headers=['api_name','unit','kind','support_status','stage4c_endpoint','stage4c_native',
        'stage4d_endpoint','timing','available_at_prediction','ml_role','rc_role',
        'ablation_group','rationale','leakage_risk','evidence']
    def row(**kwargs):matrix.append({k:kwargs.get(k,'not applicable') for k in headers})
    for name,info in metadata['measurements'].items():
        endpoint=all(name in e and isinstance(e[name],(float,int)) and math.isfinite(e[name]) for e in a.endpoints+b.endpoints)
        native=all(name in r.native and len(r.native[name])==len(r.native['time']) and all(math.isfinite(x) for x in r.native[name]) for r in (a,b))
        d_ok=all(name in e and math.isfinite(e[name]) for e in d.endpoints)
        group='optional_weather';role='optional candidate, not enabled by default';rc='optional boundary'
        why=info['Description'];risk='Use current/past only; never realized future measurements'
        if name in SIGNALS:
            group='G1 weather and solar'
            if 'TRooAir' in name:group='G0 temperature history';role='primary state and temperature target';rc='state observation'
            elif name in ['fcu_reaPCoo_y','fcu_reaPFan_y']:
                group='G2 electrical history';role='current/past endpoint input; integrated sum is target';rc='electrical proxy only, not thermal cooling'
            elif name.startswith('zon_reaP'):group='G4 internal-load proxies';rc='load proxy, not sensible heat identity'
            elif 'CO2' in name or 'FloSup' in name:group='G5 optional sensors';rc='optional state/flow diagnostic'
            elif 'RelHum' in name:group='G5 optional outdoor humidity';rc='optional boundary'
        elif name=='fcu_reaPHea_y':
            role='separate heating diagnostic; not electrical target';rc='thermal report requires source boundary clarification';group='diagnostic'
        elif any(x in name for x in ('Lat_y','Lon_y','CeiHei','CloTim','SolHouAng')):
            role='exclude initially: constant, sentinel-prone, redundant or time identifier';rc='none initially';group='excluded'
        row(api_name=name,unit=info['Unit'],kind='measurement',support_status='VERIFIED_RUNTIME' if endpoint and native else 'INCOMPLETE',
            stage4c_endpoint=str(endpoint),stage4c_native=str(native),stage4d_endpoint=str(d_ok),
            timing=f'A/B: 300s endpoints and 30s history; D: 300s endpoints; {int(a.analysis_start)}..{int(a.analysis_end)} s (D ends {d.analysis_end})',
            available_at_prediction='yes after current observation received; past history only',ml_role=role,rc_role=rc,ablation_group=group,rationale=why,leakage_risk=risk,
            evidence='A/B runtime_metadata + observations_SI + native_results; D autonomous_steps + archived initialization')
    for name,info in metadata['inputs'].items():
        active='activate' in name
        row(api_name=name,unit=info['Unit'] if info['Unit'] is not None else 'null in API; binary activation flag',kind='effective control/readback',
            support_status='VERIFIED_RUNTIME',stage4c_endpoint='True',stage4c_native='True',stage4d_endpoint='True',
            timing='300s endpoint effective readback; A/B 30s native; interval commands have separate start/end timestamps',
            available_at_prediction='current/past readback yes; future only if independently committed/proposed at origin',
            ml_role='G3 current/past control context; future realized feedback actions prohibited',rc_role='candidate exogenous command; endogenous native readback is not randomized treatment',
            ablation_group='G3 control context',rationale=info['Description'],
            leakage_risk='Native effective input may depend on unknown future state; inactive flag does not imply zero effective setpoint',
            evidence='runtime_metadata inputs, actual endpoint/native readbacks, timestamped command logs')
    schedule={'Occupancy[1]','UpperSetp[1]','LowerSetp[1]','UpperCO2[1]'}
    for name,info in metadata['forecast_points'].items():
        verified=name in requested_forecasts
        known=name in schedule
        row(api_name=name,unit=info['Unit'],kind='known schedule' if known else 'future boundary forecast',
            support_status='VERIFIED_ARCHIVED_VALUES' if verified else 'METADATA_SUPPORTED_VALUES_NOT_COLLECTED',
            stage4c_endpoint='archived initial 24h forecast at 300s' if verified else 'not collected',stage4c_native='not requested through results',
            stage4d_endpoint='current horizon-zero at decisions' if name in {'Occupancy[1]','UpperSetp[1]','LowerSetp[1]'} else ('initial compatibility forecast' if verified else 'not collected'),
            timing='valid_time grid 300s; issue_time is initialized start for A/B snapshot; D current schedule snapshots',
            available_at_prediction='only archived vintage issued <= origin; this benchmark uses known/perfect boundaries, not a real forecasting service',
            ml_role=('G4 known scheduled occupancy (not predicted count)' if name=='Occupancy[1]' else 'G6 separate forecast/schedule ablation') if verified else 'defer until runtime collection verified',
            rc_role='optional known boundary/schedule; internal-gain reports are simulator-dependent' if verified else 'not yet verified',
            ablation_group='G4 schedules' if known else 'G6 issued boundaries',rationale=info['Description'],
            leakage_risk='Do not reconstruct a forecast from future results; label benchmark-perfect information; no future indoor truth',
            evidence='runtime_metadata forecast_points; raw API initial forecast request/response; D horizon-zero records')
    for name,unit,kind,why in [
        ('derived_hvac_interval_kw','kW','derived past interval input / future target','Native trapezoidal integral of cooling plus fan W over exact 300s, divided by 300000'),
        ('derived_time_day_sin_cos','1','calendar','Deterministic from benchmark seconds; no claimed real year/weekday'),
        ('Zone indoor relative humidity','unavailable','unavailable measurement','No zone RH output in actual measurement metadata; outdoor RH is available'),
        ('Zone indoor humidity ratio','unavailable','unavailable measurement','Not in actual bestest_air measurement metadata'),
        ('Measured supply-air temperature','unavailable','unavailable measurement','Supply temperature setpoint exists; not a measured supply-air temperature'),
        ('Coil surface/internal state','unavailable','simulator-internal unavailable','No operational API observation; do not extract hidden FMU state'),
        ('Official ener_tot / tdis_tot','kWh/m2 / K.h per zone','evaluation-only aggregate','Whole-run KPIs must never become causal input or HVAC electrical-demand labels')]:
        row(api_name=name,unit=unit,kind=kind,support_status='DERIVABLE_STAGE4C_ONLY' if name=='derived_hvac_interval_kw' else ('DERIVABLE' if name.startswith('derived_') else 'UNAVAILABLE' if 'unavailable' in kind or 'internal' in kind else 'VERIFIED_EVALUATION_ONLY'),
            timing='current/past support for inputs; future interval for target only',available_at_prediction='derived from past only' if name.startswith('derived_') else 'no operational feature',
            ml_role='candidate/target separated by timestamp' if name.startswith('derived_') else 'not a feature',rc_role='electrical proxy only' if 'hvac' in name else 'none initially',
            ablation_group='G2' if 'hvac' in name else 'G0 calendar' if 'time_day' in name else 'excluded',rationale=why,leakage_risk='Post-origin support forbidden for features',evidence='saved metadata and raw histories; no hidden state access')
    (HERE/'input_matrix_rows.json').write_text(json.dumps({'headers':headers,'rows':matrix},indent=2)+'\n')
    days=json.loads((RELEASE/'testcases/bestest_air/models/days.json').read_text())
    catalog={k:{'selected_day':v,'analysis_start_day':v-7,'analysis_end_day':v+7,'warmup_start_day':v-14} for k,v in days.items()}
    audit={'classification':'OFFLINE_PREPARATION_ONLY_NO_TRAINING_RELEASE',
        'runs':summaries,'measurements_listed':len(metadata['measurements']),
        'inputs_listed':len(metadata['inputs']),'forecast_points_listed':len(metadata['forecast_points']),
        'forecast_values_actually_archived_stage4c':sorted(requested_forecasts),
        'matrix_rows':len(matrix),'source_catalog_not_new_runtime_verification':catalog,
        'scenario_runtime_verified':'peak_cool_day only',
        'default_metadata_step_s':metadata['step'],'actual_advance_step_s':300,
        'existing_pilots_all_development_exposed_same_weather_window_family':True,
        'no_new_simulations':True,'no_models_fit':True,'no_supervised_rows_exported':True,
        'preserved_files_verified':len(before)}
    weather=RELEASE/'testcases/bestest_air/models/Resources/weather.csv'
    with weather.open() as f: time_axis=[float(row['time']) for row in csv.DictReader(f)]
    audit['source_weather_time_axis_only']={'samples':len(time_axis),'start':time_axis[0],'end':time_axis[-1]}
    source_files=['testcase.py','testcases/bestest_air/models/days.json',
                  'testcases/bestest_air/models/config.json',
                  'testcases/bestest_air/models/Resources/weather.csv']
    audit['pinned_source_hashes']={name:digest(RELEASE/name) for name in source_files}
    fmu=RELEASE/'testcases/bestest_air/models/wrapped.fmu'
    audit['building_fmu_sha256']=digest(fmu)
    if audit['building_fmu_sha256']!='158008fa3b635280a67dfed8bab5804d1f9a96d218b467dfebab77e5cbf8b86a':
        raise ContractError('Original building hash mismatch')
    interrupted=ROOT/'stage4d/evidence/authorized_demo/autonomous_steps.jsonl'
    audit['interrupted_record']={'steps':len(interrupted.read_text().splitlines()),
        'eligibility':'EXCLUDED_INTERRUPTED; not concatenated or used for feature/target rows'}
    after=preservation_snapshot()
    if before!=after:raise ContractError('Preservation failed')
    (HERE/'PRESERVATION_HASHES.json').write_text(json.dumps(before,indent=2)+'\n')
    (HERE/'DATA_AVAILABILITY_AUDIT.json').write_text(json.dumps(audit,indent=2)+'\n')
    print(json.dumps(audit,indent=2))


if __name__=='__main__':main()
