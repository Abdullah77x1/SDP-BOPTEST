"""Matched three-arm descriptive analysis; no models or training-data release."""
import csv,json,math
from . import HOME,PILOT,RID
from hvac_control_expansion_b2f_v1.packaging import read,require,write_new
from hvac_control_expansion_b2f_v1.review import excess,total,quantiles
from hvac_control_expansion_v1.campaign import coverage
from hvac_control_expansion_v1.analysis import recovery_time
from stage4e_d2_public.export import interval

TEMP='zon_reaTRooAir_y';COOL='fcu_reaPCoo_y';FAN='fcu_reaPFan_y';HEAT='fcu_reaPHea_y'
START=15033600;END=15292800;EPS=1e-7

def csv_new(name,rows):
    require(rows,'No fabricated empty physical results')
    with (HOME/name).open('x',newline='',encoding='utf-8') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)

def summarize_pair(a,b,na,nb,times):
    dt=[b[t][TEMP]-a[t][TEMP] for t in times]
    dp=[(interval(nb,t-300,t,[COOL,FAN])-interval(na,t-300,t,[COOL,FAN]))/1000 for t in times if t>START]
    return dict(reference_mean_temperature_c=math.fsum(a[t][TEMP]-273.15 for t in times)/len(times),
        reference_min_temperature_c=min(a[t][TEMP]-273.15 for t in times),reference_max_temperature_c=max(a[t][TEMP]-273.15 for t in times),
        alternative_mean_temperature_c=math.fsum(b[t][TEMP]-273.15 for t in times)/len(times),
        alternative_min_temperature_c=min(b[t][TEMP]-273.15 for t in times),alternative_max_temperature_c=max(b[t][TEMP]-273.15 for t in times),
        endpoints=len(dt),mean_signed_temperature_k=math.fsum(dt)/len(dt),mean_abs_temperature_k=math.fsum(map(abs,dt))/len(dt),
        max_abs_temperature_k=max(map(abs,dt)),min_signed_temperature_k=min(dt),max_signed_temperature_k=max(dt),
        endpoints_ge_0_025k=sum(abs(v)>=.025 for v in dt),endpoints_ge_0_05k=sum(abs(v)>=.05 for v in dt),endpoints_ge_0_1k=sum(abs(v)>=.1 for v in dt),
        absolute_temperature_area_k_hours=math.fsum((abs(x)+abs(y))/24 for x,y,t,u in zip(dt,dt[1:],times,times[1:]) if u-t==300),
        interval_power_comparisons=len(dp),intervals_ge_1w=sum(abs(v)>=.001 for v in dp),intervals_ge_10w=sum(abs(v)>=.01 for v in dp),
        intervals_ge_50w=sum(abs(v)>=.05 for v in dp),max_abs_interval_power_kw=max(map(abs,dp)))

def analyze(execution,record=False,verify_outputs=False):
    require(execution.get('state')=='CONSUMED_COMPLETED' and execution.get('corrected_finalization',{}).get('status')=='PASS_CORRECTED_OFFLINE_FINALIZATION','Complete real C45 and finalization required')
    old=PILOT/'runtime_state/batches/B1_G174_INITIAL_PILOT'
    dirs=[old/'B1V01_G174_NREF',old/'B1V01_G174_C15',__import__('pathlib').Path(execution['run_path'])]
    arms=['NREF','C15','C45'];m=read(PILOT/'campaign_manifest.json');cfgs=m['runs'][:3]
    endpoints=[];native=[];steps=[]
    for d in dirs:
        s=read(d/'RUN_COMPLETED.json');require(s['classification']=='PASS_VALID_RAW' and s['data_is_fabricated'] is False,'Real raw evidence required')
        endpoints.append({r['time']:r for r in read(d/'endpoints.json')});native.append(read(d/'whole_native_results.json'))
        steps.append([json.loads(line) for line in (d/'steps.jsonl').read_text().splitlines()])
    temps=[];populations=[('full_72h',list(range(START,END+1,300))),('common_11to14_all_days',[t for t in range(START,END+1,300) if 39600<=t%86400<=50400])]
    windows=[('full_72h',START,END)]
    for day in range(3):
        base=START+day*86400
        for label,lo,hi in [('common_11to14',39600,50400),('C15_hold_clock_11to1115',39600,40500),('C45_hold_clock_11to1145',39600,42300),
                           ('after_C15_release_clock_1115to1315',40500,47700),('after_C45_release_clock_1145to1345',42300,49500),
                           ('morning_0730to0900',27000,32400),('evening_1730to1900',63000,68400)]:
            name=f'day{day+1}_{label}';windows.append((name,base+lo,base+hi));populations.append((name,list(range(base+lo,base+hi+1,300))))
    for i,j in ((0,0),(0,1),(0,2),(1,2)):
        for name,times in populations:
            temps.append(dict(reference=arms[i],alternative=arms[j],population=name,**summarize_pair(endpoints[i],endpoints[j],native[i],native[j],times)))
    energy=[]
    for name,lo,hi in windows:
        ref={key:interval(native[0],lo,hi,channels)*(hi-lo)/3600000 for key,channels in [('cooling',[COOL]),('fan',[FAN]),('electric',[COOL,FAN]),('gas',[HEAT])]}
        for k,arm in enumerate(arms):
            row=dict(policy=arm,window=name,start_s=lo,end_s=hi,window_type='matched_clock_all_policies',
                note='Release-relative clocks differ; both release-clock windows are evaluated for every policy')
            for key,channels in [('cooling',[COOL]),('fan',[FAN]),('electric',[COOL,FAN]),('gas',[HEAT])]:
                value=interval(native[k],lo,hi,channels)*(hi-lo)/3600000;row[key+'_kwh']=value;row['delta_'+key+'_vs_NREF_kwh']=value-ref[key];row['percentage_'+key+'_vs_NREF']=100*(value-ref[key])/ref[key] if ref[key]!=0 else None
            energy.append(row)
    comfort=[];severities=[[sum(excess(r)) for r in ss] for ss in steps]
    for k,refk in ((0,0),(1,0),(2,0),(2,1)):
        arm=arms[k];vals=severities[k];nv=severities[refk];delta=[v-n for v,n in zip(vals,nv)]
        above=[excess(r)[1] for r in steps[k]];below=[excess(r)[0] for r in steps[k]]
        pos=[d for d in delta if d>EPS];q=quantiles(pos)
        comfort.append(dict(policy=arm,reference=arms[refk],**total(vals),above_degree_hours=math.fsum(above)/12,below_degree_hours=math.fsum(below)/12,above_violation_minutes=5*sum(v>0 for v in above),below_violation_minutes=5*sum(v>0 for v in below),
            new_violating_timestamps=sum(n==0 and v>0 for v,n in zip(vals,nv)),resolved_violating_timestamps=sum(n>0 and v==0 for v,n in zip(vals,nv)),
            worsened_existing_intervals=sum(n>0 and v>0 and d>EPS for n,v,d in zip(nv,vals,delta)),
            improved_existing_intervals=sum(n>0 and d<-EPS for n,d in zip(nv,delta)),
            unchanged_existing_intervals=sum(n>0 and v>0 and abs(d)<=EPS for n,v,d in zip(nv,vals,delta)),
            new_or_worse_minutes=5*len(pos),max_additional_violation_k=max([max(0,d) for d in delta]),
            additional_degree_hours=math.fsum(max(0,d) for d in delta)/12,reduced_degree_hours=-math.fsum(min(0,d) for d in delta)/12,
            median_additional_k=q.get('p50'),p95_additional_k=q.get('p95'),additional_intervals_ge_0_025k=sum(d>=.025 for d in pos),
            additional_intervals_ge_0_05k=sum(d>=.05 for d in pos),additional_intervals_ge_0_1k=sum(d>=.1 for d in pos)))
    controls=[];recoveries=[]
    for k in (1,2):
        cover=coverage(steps[k],native[k],m['policy'],cfgs[k])
        paired=[]
        for t in range(START+300,END+1,300):
            paired.append(dict(time_s=t,delta_temperature_k=endpoints[k][t][TEMP]-endpoints[0][t][TEMP],
                delta_electric_kw=(interval(native[k],t-300,t,[COOL,FAN])-interval(native[0],t-300,t,[COOL,FAN]))/1000))
        for e in cover['episodes']:
            act=e['activation_s'];rel=e['release_s'];desired=e['requested_activation_s']
            actual=[r for r in steps[k] if desired<=r['start']<e['requested_release_s'] and r['applied_command']['con_oveTSetCoo_activate']]
            values=sorted({endpoints[k][r['end']]['con_oveTSetCoo_u'] for r in actual})
            controls.append(dict(policy=arms[k],run_id=cfgs[k]['run_id'],day=e['day'],requested_intervals=e['requested_intervals'],applied_intervals=e['applied_intervals'],
                vetoed_intervals=e['requested_intervals']-e['applied_intervals'],actual_activation_s=act,actual_release_s=rel,
                requested_release_s=e['requested_release_s'],actual_minutes=e['applied_minutes'],readbacks_k=json.dumps(values),
                veto_reasons=json.dumps(e['veto_reasons']),native_recovery_intervals=e['recovery_native_intervals'],complete=e['complete']))
            row=dict(policy=arms[k],day=e['day'],actual_release_s=rel,requested_release_s=e['requested_release_s'],
                native_temperature_before_intervention_c=endpoints[0][desired][TEMP]-273.15,alternative_temperature_before_intervention_c=endpoints[k][desired][TEMP]-273.15,
                hold_max_abs_delta_temperature_k=max(abs(endpoints[k][t][TEMP]-endpoints[0][t][TEMP]) for t in range(desired,e['requested_release_s']+1,300)),
                pre_intervention_same_day_max_abs_delta_temperature_k=max(abs(endpoints[k][t][TEMP]-endpoints[0][t][TEMP]) for t in range(START+(e['day']-1)*86400,desired+1,300)),
                recovery_min_delta_power_kw=None,above_native_demand_intervals_gt_0w=None,
                return_marker_minutes=None,
                marker_censored=True,native_release_temperature_c=None,alternative_release_temperature_c=None,min_recovery_delta_temperature_k=None,
                max_recovery_delta_temperature_k=None,max_abs_recovery_delta_temperature_k=None,native_cooling_recovery_kwh=None,alternative_cooling_recovery_kwh=None,
                native_fan_recovery_kwh=None,alternative_fan_recovery_kwh=None,delta_recovery_electric_kwh=None,above_native_demand_intervals_gt_10w=None,
                max_recovery_delta_power_kw=None,later_max_abs_temperature_k=None,hold_active_cooling_intervals_gt10w=None,
                new_or_worse_recovery_minutes=None)
            if rel is not None:
                stop=rel+7200;rp=[p for p in paired if rel<=p['time_s']<=stop];dp=[(interval(native[k],t,t+300,[COOL,FAN])-interval(native[0],t,t+300,[COOL,FAN]))/1000 for t in range(rel,stop,300)]
                row.update(return_marker_minutes=recovery_time(paired,rel),marker_censored=recovery_time(paired,rel) is None,
                    native_release_temperature_c=endpoints[0][rel][TEMP]-273.15,alternative_release_temperature_c=endpoints[k][rel][TEMP]-273.15,
                    min_recovery_delta_temperature_k=min(p['delta_temperature_k'] for p in rp),max_recovery_delta_temperature_k=max(p['delta_temperature_k'] for p in rp),
                    max_abs_recovery_delta_temperature_k=max(abs(p['delta_temperature_k']) for p in rp),
                    native_cooling_recovery_kwh=interval(native[0],rel,stop,[COOL])*7200/3600000,alternative_cooling_recovery_kwh=interval(native[k],rel,stop,[COOL])*7200/3600000,
                    native_fan_recovery_kwh=interval(native[0],rel,stop,[FAN])*7200/3600000,alternative_fan_recovery_kwh=interval(native[k],rel,stop,[FAN])*7200/3600000,
                    delta_recovery_electric_kwh=(interval(native[k],rel,stop,[COOL,FAN])-interval(native[0],rel,stop,[COOL,FAN]))*7200/3600000,
                    above_native_demand_intervals_gt_10w=sum(d>.01 for d in dp),max_recovery_delta_power_kw=max(dp),
                    recovery_min_delta_power_kw=min(dp),above_native_demand_intervals_gt_0w=sum(d>0 for d in dp),
                    later_max_abs_temperature_k=max(abs(endpoints[k][t][TEMP]-endpoints[0][t][TEMP]) for t in range(stop,min(START+e['day']*86400,END)+1,300)),
                    hold_active_cooling_intervals_gt10w=sum(interval(native[k],r['start'],r['end'],[COOL])>10 for r in actual),
                    new_or_worse_recovery_minutes=5*sum(severities[k][i]-severities[0][i]>EPS for i,s in enumerate(steps[k]) if rel<=s['start']<stop))
            recoveries.append(row)
    tables={'B2H_CONTROL_DELIVERY.csv':controls,'B2H_THREE_ARM_TEMPERATURE.csv':temps,
        'B2H_THREE_ARM_ENERGY.csv':energy,'B2H_THREE_ARM_COMFORT.csv':comfort,'B2H_RECOVERY_BY_DAY.csv':recoveries}
    primary=[t for t in temps if t['population']=='common_11to14_all_days']
    comparison=next(t for t in primary if t['reference']=='C15' and t['alternative']=='C45')
    summary=dict(primary_temperature=primary,full_energy=[e for e in energy if e['window']=='full_72h'],comfort=comfort,control=controls,recovery=recoveries,
        C45_C15_response_separation=comparison['endpoints_ge_0_05k']>0 or comparison['intervals_ge_10w']>0,
        all_C45_holds_complete=all(c['complete'] for c in controls if c['policy']=='C45'),models_trained=0,new_weather_groups=0,
        added_independent_groups=0,training_dataset_released=False)
    if record:
        require(read(HOME/'POSTRUN_VERIFICATION.json')['status']=='PASS','Independent post-run checks must pass before publishing physical analysis')
        for name,rows in tables.items():csv_new(name,rows)
        write_new(HOME/'B2H_THREE_ARM_ANALYSIS.json',summary)
    if verify_outputs:
        require(summary==read(HOME/'B2H_THREE_ARM_ANALYSIS.json'),'Recomputed summary differs')
        for name,rows in tables.items():
            with (HOME/name).open(newline='',encoding='utf-8') as f:stored=list(csv.DictReader(f))
            expected=[{key:'' if value is None else str(value) for key,value in row.items()} for row in rows]
            require(stored==expected,'Recomputed CSV differs: '+name)
    return summary

if __name__=='__main__':
    import argparse
    from . import V2
    from hvac_control_expansion_b2f_v1.tests import offline_guard
    p=argparse.ArgumentParser();p.add_argument('--record',action='store_true');p.add_argument('--verify',action='store_true');args=p.parse_args()
    with offline_guard():
        result=analyze(read(V2/'LIVE_EXECUTION.json'),record=args.record,verify_outputs=args.verify)
        print(json.dumps(dict(status='PASS_RECOMPUTED_READ_ONLY' if args.verify else 'ANALYZED',
            primary_temperature=result['primary_temperature'],full_energy=result['full_energy'],comfort=result['comfort'],
            control=result['control'],recovery=result['recovery'],C45_C15_response_separation=result['C45_C15_response_separation']),indent=2))
