"""Offline one-time preparation: source/metadata only, no simulator outcomes."""
import csv
import json
from .plan import HERE,ROOT,configuration,save_new,schedule_rows,nominal,sha


def main():
    c=configuration()
    release=ROOT/'deployment/official_v0.9.0/project1-boptest-0.9.0'
    days=json.loads((release/'testcases/bestest_air/models/days.json').read_text())
    source_schedule=release/'testcases/bestest_air/models/Resources/internal_setpoints_occupancy.csv'
    with source_schedule.open() as f:
        points={float(r['time']):r for r in csv.DictReader(l for l in f if not l.startswith('#'))}
    checks=[]
    for run in c['runs']:
        assert run['start']==(days[run['scenario']]-7)*86400
        assert run['warmup_start']==run['start']-604800
        assert run['end']<=run['start']+14*86400
        for day in range(3):
            for b in c['pulse_blocks_local_seconds']:
                for offset in range(b['start'],b['end']+1,600):
                    row=points[run['start']+day*86400+offset]
                    assert float(row['UpperSetp[1]'])==297.15 and float(row['LowerSetp[1]'])==294.15
                    assert float(row['Occupancy[1]'])==2
        checks.append({'attempt_id':run['attempt_id'],'source_window_supported':True,
            'source_pulse_schedule_21_24_c_occupancy_2':True,'runtime_window_qualified':False})
    save_new(HERE/'campaign.json',c)
    save_new(HERE/'four_run_schedule_rows.json',schedule_rows(c))
    save_new(HERE/'attempt_ledger.json',{'immutable_template':True,'attempts':[
        {'attempt_id':r['attempt_id'],'status':'UNUSED','maximum_advances':864,
         'evidence_directory':r['evidence_directory']} for r in c['runs']]})
    save_new(HERE/'execution_authorization.template.json',{
        'status':'NOT_AUTHORIZED','proposal_sha256':'COPY_FINAL_MANIFEST_DIGEST_ONLY_AFTER_USER_APPROVAL',
        'attempt_ids':[r['attempt_id'] for r in c['runs']],'maximum_advances':3456,
        'user_authorization_text':'','authorized_utc':''})
    save_new(HERE/'preflight_requirements.json',{'status':'NOT_RUNTIME_QUALIFIED',
        'proposal_sha256':'BIND_SEPARATE_PREFLIGHT_RECORD_TO_FINAL_MANIFEST',
        'windows':[{'scenario':r['scenario'],'start':r['start'],'warmup_seconds':604800}
                   for r in (c['runs'][0],c['runs'][2])],
        **dict.fromkeys(['step_300_verified','native_history_verified','forecast_order_verified',
            'pulse_schedule_forecasts_verified','fresh_native_initialization_verified',
            'localhost_api_version_verified','units_and_limits_verified'],False),'proof_files':{}})
    paths=['testcase.py','kpis/kpi_calculator.py','testcases/bestest_air/models/days.json',
        'testcases/bestest_air/models/config.json','testcases/bestest_air/models/kpis.json',
        'testcases/bestest_air/models/wrapped.fmu',
        'testcases/bestest_air/models/Resources/internal_setpoints_occupancy.csv',
        'testcases/bestest_air/models/Resources/weather.csv']
    save_new(HERE/'SOURCE_FEASIBILITY_REVIEW.json',{'checks':checks,
        'runtime_assumptions':'Only peak_cool_day, 300s endpoints, 30s histories and prior cooling actuation qualified in existing evidence. Neither new window nor 296.90 K has a new runtime qualification.',
        'source_hashes':{p:sha(release/p) for p in paths}})
    # This is a frozen command plan, NOT measured or simulated data.
    with (HERE/'nominal_commands.jsonl').open('x',encoding='utf-8') as f:
        for run in c['runs']:
            for t in range(run['start'],run['end'],300):
                f.write(json.dumps(dict(attempt_id=run['attempt_id'],**nominal(run,t,c)))+'\n')
    print(json.dumps({'prepared_advances':3456,'attempts':4,'runtime_executed':False,
        'runs':[{k:r[k] for k in ('attempt_id','scenario','start','end','warmup_start','mode')}
                for r in c['runs']]},indent=2))


if __name__=='__main__':main()
