"""Offline forensic review: bytes/JSON/CSV/XML only, never imports an FMU runtime.

No Docker, network, deployment, advance, dataset builder or estimator calls.
"""
import base64
import bisect
import csv
import hashlib
import io
import json
import math
import xml.etree.ElementTree as ET
import zipfile
from collections import Counter
from pathlib import Path
from stage4e_d0.plan import ROOT,sha,save_new,validate_readback,FLAGS,COOL,FAN,HEAT
from stage4e.dataset import ContractError

HERE=Path(__file__).resolve().parent
REL=ROOT/'deployment/official_v0.9.0/project1-boptest-0.9.0'
BASE=REL/'testcases/bestest_air/models'


def check_manifest(manifest,base):
    data=json.loads(manifest.read_text())
    for name,digest in data['files'].items():assert sha(base/name)==digest,(manifest,name)
    return len(data['files'])


def csv_rows(raw):
    return list(csv.DictReader(line for line in raw.decode('utf-8-sig').splitlines() if not line.startswith('#')))


def main():
    n_d1=check_manifest(ROOT/'stage4e_d1/FINAL_ARTIFACT_MANIFEST.json',ROOT)
    n_frozen=check_manifest(ROOT/'stage4e_d0/FROZEN_MANIFEST.json',ROOT)
    n_pref=check_manifest(ROOT/'stage4e_runtime_preflight/FINAL_ARTIFACT_MANIFEST.json',ROOT)
    assert sha(ROOT/'stage4e_d0/FROZEN_MANIFEST.json')=='9c033ec022e38479f2f86467d92f3bbd13ee83a1b4b2e987490401ee185d87b8'
    arm=ROOT/'stage4e_d0/campaign_evidence/Q01_N'
    raw=[json.loads(s) for s in (arm/'raw_api.jsonl').read_text().splitlines()]
    decoded=[]
    for r in raw:
        b=base64.b64decode(r['raw_body_base64'])
        if b.strip()==b'OK':v='OK'
        else:
            parsed=json.loads(b);v=parsed.get('payload',parsed) if isinstance(parsed,dict) else parsed
        decoded.append((r,v))
    advances=[(r,v) for r,v in decoded if r['method']=='POST' and '/advance/' in r['url']]
    forecasts=[(r,v) for r,v in decoded if r['method']=='PUT' and '/forecast/' in r['url']]
    native=[(r,v) for r,v in decoded if r['method']=='PUT' and '/results/' in r['url']]
    assert len(raw)==300 and len(advances)==len(forecasts)==96 and len(native)==95
    for i,(r,v) in enumerate(advances,1):
        assert v==json.loads((arm/f'endpoint_{i:04d}.json').read_text())
        assert r['request']==dict.fromkeys(FLAGS,0)
    for i,(r,v) in enumerate(forecasts):assert v==json.loads((arm/f'forecast_{i:04d}.json').read_text())['data']
    for i,(r,v) in enumerate(native):assert v==json.loads((arm/f'native_chunk_{i:04d}.json').read_text())
    records=[json.loads(s) for s in (arm/'steps.jsonl').read_text().splitlines()]
    initial=json.loads((arm/'initialization.json').read_text())['initial_endpoint']
    for i,r in enumerate(records):
        prior=initial if i==0 else advances[i-1][1]
        assert r['current_observation']==prior
        validate_readback(r['applied_command'],advances[i][1],forecasts[i][1]['UpperSetp[1]'][1])
    try:validate_readback(advances[-1][0]['request'],advances[-1][1],forecasts[-1][1]['UpperSetp[1]'][1])
    except ContractError as exc:original_failure=str(exc)
    else:raise AssertionError('Original frozen mismatch did not reproduce offline')
    events=[json.loads(s) for s in (arm/'receipt_order.jsonl').read_text().splitlines()]
    previous='0'*64;monotonic=0
    for i,e in enumerate(events,1):
        digest=e.pop('sha256');assert e['order']==i and e['previous_sha256']==previous and e['monotonic_ns']>=monotonic
        assert hashlib.sha256(json.dumps(e,sort_keys=True,separators=(',',':')).encode()).hexdigest()==digest
        previous=digest;monotonic=e['monotonic_ns']
    failure=next(e for e in events if e['kind']=='run_failed')
    assert failure['error']=='ContractError: Native cooling setpoint did not resume'
    assert not (arm/'native_chunk_0095.json').exists()
    with zipfile.ZipFile(BASE/'wrapped.fmu') as z:
        names=z.namelist();xml=z.read('modelDescription.xml');tree=ET.fromstring(xml)
        scalar=list(tree.findall('./ModelVariables/ScalarVariable'))
        wanted={'con_oveTSetCoo_u','con_oveTSetCoo_y','con_oveTSetHea_u','con_oveTSetHea_y',
            'con_oveTSetCoo_activate','con_oveTSetHea_activate',
            'mod.con.occSta','mod.con.occEnd','mod.con.TSetCooOcc','mod.con.TSetCooUno',
            'mod.con.TSetHeaOcc','mod.con.TSetHeaUno'}
        selected=[{'attributes':v.attrib,'type':[{'tag':x.tag,'attributes':x.attrib} for x in v]} for v in scalar if v.get('name') in wanted]
        resource=z.read('resources/internal_setpoints_occupancy.csv');embedded=csv_rows(resource)
        fmu={'container_sha256':sha(BASE/'wrapped.fmu'),'root_attributes':tree.attrib,
            'co_simulation':tree.find('CoSimulation').attrib,'model_exchange_present':tree.find('ModelExchange') is not None,
            'archive_entries':names,'generated_source_entries':[n for n in names if n.startswith('sources/')],
            'xml_sha256':hashlib.sha256(xml).hexdigest(),
            'linux_binary_sha256':hashlib.sha256(z.read('binaries/linux64/wrapped.so')).hexdigest(),
            'embedded_schedule_sha256':hashlib.sha256(resource).hexdigest(),'selected_static_variables':selected}
    loose=csv_rows((BASE/'Resources/internal_setpoints_occupancy.csv').read_bytes())
    assert len(loose)==len(embedded)
    mismatches=[]
    for i,(a,b) in enumerate(zip(embedded,loose)):
        assert a.keys()==b.keys()
        if any(float(a[k])!=float(b[k]) for k in a):
            mismatches.append(i)
    times=[float(r['time']) for r in embedded]
    assert all(0<b-a<=600 for a,b in zip(times,times[1:]))
    periods=Counter(round(b-a,8) for a,b in zip(times,times[1:]))
    def point(t):return embedded[bisect.bisect_right(times,t)-1]
    boundary=[]
    pref=json.loads((ROOT/'stage4e_runtime_preflight/evidence/PF01_COOL/AS_ISSUED_72H_BOUNDARY_FORECAST.json').read_text())['data']
    for offset in (28200,28500,28800,28830,29100,64200,64500,64800,64830,65100,65400):
        t=146*86400+offset;r=point(t)
        row={'time':t,'seconds_in_day':offset,'csv_selected_knot':float(r['time']),
            'lower_k':float(r['LowerSetp[1]']),'upper_k':float(r['UpperSetp[1]']),
            'scheduled_occupants':float(r['Occupancy[1]'])}
        if t in pref['time']:
            j=pref['time'].index(t)
            assert row['lower_k']==pref['LowerSetp[1]'][j] and row['upper_k']==pref['UpperSetp[1]'][j] and row['scheduled_occupants']==pref['Occupancy[1]'][j]
            row['archived_D1_preflight_forecast_match']=True
        boundary.append(row)
    # Additional already exposed DEVELOPMENT evidence only. No protected outcomes.
    cdir=ROOT/'evidence/local_matched_AB/A'
    old=json.loads((cdir/'native_results.json').read_text());start=old['time'][0]
    assert all(v==0 for f in FLAGS for v in old[f])
    c_forecast=json.loads((cdir/'boundary_forecast_NOT_ML.json').read_text())
    c_meta=json.loads((cdir/'runtime_metadata.json').read_text())
    assert c_meta['version']=={'version':'0.9.0'} and c_meta['name']=={'name':'bestest_air'}
    archive_points=[]
    for offset in (28500,28800,28830,29100,64500,64800,64830,65100,65400):
        t=start+offset;i=old['time'].index(t)
        row={'time':t,'seconds_in_day':offset,'heating_k':old['con_oveTSetHea_u'][i],
            'cooling_k':old['con_oveTSetCoo_u'][i],'all_override_flags_zero':all(old[f][i]==0 for f in FLAGS)}
        if t in c_forecast['time']:
            j=c_forecast['time'].index(t)
            row.update(forecast_lower_k=c_forecast['LowerSetp[1]'][j],forecast_upper_k=c_forecast['UpperSetp[1]'][j],forecast_occupancy=c_forecast['Occupancy[1]'][j])
        archive_points.append(row)
    old_posts=[]
    for line in (cdir/'raw_api.jsonl').read_text().splitlines():
        r=json.loads(line)
        if r['method']=='POST' and '/advance/' in r['url']:
            response=json.loads(base64.b64decode(r['raw_body_base64']));v=response.get('payload',response)
            if v.get('time') in (start+28800,start+29100,start+64800,start+65100):
                old_posts.append({'time':v['time'],'seconds_in_day':v['time']-start,
                    'heating_k':v['con_oveTSetHea_u'],'cooling_k':v['con_oveTSetCoo_u'],'command':r['request']})
    save_new(HERE/'FMU_STATIC_METADATA.json',fmu)
    save_new(HERE/'FORECAST_SCHEDULE_BOUNDARY_AUDIT.json',{'embedded_rows':len(embedded),
        'first_interval_s':times[1]-times[0],'most_common_interval_s':periods.most_common(1)[0][0],
        'not_strictly_uniform':len(periods)>1,'additional_irregular_knots':True,
        'loose_numeric_mismatch_rows':mismatches,
        'loose_bytes_differ_from_embedded':sha(BASE/'Resources/internal_setpoints_occupancy.csv')!=fmu['embedded_schedule_sha256'],
        'points':boundary,'all_compared_preserved_pref_values_match':True})
    save_new(HERE/'ARCHIVED_DEVELOPMENT_CORROBORATION.json',{'source_role':'Previously exposed Stage4C A native run, not protected evaluation',
        'scenario':'peak_cool_day','different_weather_start_from_D1':True,
        'native_points':archive_points,'raw_advance_endpoints':old_posts,
        'limitation':'Shows prior behavior; does not observe the stopped D1 instance after 08:00.'})
    source_names=['testcase.py','data/data_manager.py','forecast/forecaster.py','data/data_generator.py',
        'service/worker/jobs/boptest_run_test/job.py','service/web/server/src/routes/boptestRoutes.js',
        'testcases/bestest_air/models/wrapped.mo','testcases/bestest_air/models/generate_data.py',
        'testcases/bestest_air/models/library_versions.json',
        'testcases/bestest_air/models/BESTESTAir/BaseClasses/Thermostat_T.mo',
        'testcases/bestest_air/models/BESTESTAir/TestCases/TestCase_Ideal.mo']
    source={name:sha(REL/name) for name in source_names}
    source['frozen_guard_plan.py']=sha(ROOT/'stage4e_d0/plan.py')
    source['frozen_collector_runner.py']=sha(ROOT/'stage4e_d0/runner.py')
    audit={'classification':'OFFLINE_SOURCE_AND_PRESERVED_EVIDENCE_REVIEW',
        'D1_delivery_files_verified':n_d1,'frozen_D0_files_verified':n_frozen,'preflight_delivery_files_verified':n_pref,
        'raw_API_responses_decoded':len(raw),'raw_advances_matched_to_saved_endpoints':len(advances),
        'issued_forecasts_matched_to_raw':len(forecasts),'native_chunks_matched_to_raw':len(native),
        'accepted_prior_observations_reviewed':len(records),'initial_endpoint_reviewed':True,
        'receipt_events_reviewed_and_hash_verified':len(events),
        'original_guard_passes_accepted_prefix':95,'original_guard_last_response_error':original_failure,
        'failure_journal_order':failure['order'],'source_hashes':source,
        'D1_root_event_mechanism':'UNRESOLVED','unconditional_native_forecast_identity':'DISPROVEN_BY_SEPARATE_SOURCE_PATHS_AND_ARCHIVED_NATIVE_EVENING_DATA',
        'simulator_fault_proven':False,'D1_failed_status_changed':False,
        'Q01_consumed_failed':True,'Q02_Q03_Q04_remain_unused':True,
        'new_simulations':0,'Docker_commands':0,'datasets_generated':False,'model_training':False}
    save_new(HERE/'READ_ONLY_REVIEW_AUDIT.json',audit)
    print(json.dumps(audit,indent=2))


if __name__=='__main__':main()
