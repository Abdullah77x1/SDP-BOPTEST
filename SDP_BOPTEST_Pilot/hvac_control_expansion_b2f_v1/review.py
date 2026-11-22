"""Derived comfort/recovery statistics from saved pilot records only."""
import csv,json,math
from . import HOME,PILOT,BATCH
from .packaging import read,require,write_new
from .verification import IDS

TEMP='zon_reaTRooAir_y';COOL='fcu_reaPCoo_y';FAN='fcu_reaPFan_y';HEAT='fcu_reaPHea_y'
LOW='LowerSetp[1]';UP='UpperSetp[1]';OCC='Occupancy[1]';EPS=1e-7

def csv_new(path,rows):
    with path.open('x',newline='',encoding='utf-8') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)

def quantiles(values):
    values=sorted(values)
    if not values:return dict(n=0)
    def q(p):
        x=(len(values)-1)*p;i=int(x);j=min(i+1,len(values)-1)
        return values[i]+(values[j]-values[i])*(x-i)
    return dict(n=len(values),min=values[0],p50=q(.5),p90=q(.9),p95=q(.95),p99=q(.99),max=values[-1])

def phase(t):
    clock=t%86400
    return 'hold_11to1115' if 39600<=clock<40500 else 'recovery_1115to1315' if 40500<=clock<47700 else 'later_1315to2400' if clock>=47700 else 'pre_0000to1100'

def excess(r,nominal=False):
    c=r['current_boundary'];lo,up=c[LOW],c[UP]
    if nominal:lo,up=(294.15,297.15) if 28800<=r['start']%86400<64800 else (288.15,303.15)
    v=r['current_observation'][TEMP]
    return max(lo-v,0),max(v-up,0)

def total(rows):
    return dict(minutes=5*sum(x>0 for x in rows),degree_hours=math.fsum(rows)/12,peak_k=max(rows,default=0),
                episodes=sum(x>0 and (i==0 or rows[i-1]<=0) for i,x in enumerate(rows)))

def analyze():
    from stage4e_d2_public.export import interval
    from hvac_control_expansion_v1.analysis import recovery_time
    steps=[[json.loads(line) for line in (BATCH/rid/'steps.jsonl').read_text().splitlines()] for rid in IDS]
    endpoints=[read(BATCH/rid/'endpoints.json') for rid in IDS]
    native=[read(BATCH/rid/'whole_native_results.json') for rid in IDS]
    start=15033600;end=15292800
    paired=[];episode_rows=[];run_totals=[];severity=[[],[]];episode_labels=[{},{}]
    for k in (0,1):
        low=[excess(r)[0] for r in steps[k]];high=[excess(r)[1] for r in steps[k]];values=[a+b for a,b in zip(low,high)];severity[k]=values
        run_totals.append(dict(run_id=IDS[k],**total(values),below_degree_hours=math.fsum(low)/12,above_degree_hours=math.fsum(high)/12,
            nominal_schedule_sensitivity=total([sum(excess(r,True)) for r in steps[k]])))
        i=0;number=0
        while i<len(values):
            if values[i]<=0:i+=1;continue
            first=i
            while i<len(values) and values[i]>0:i+=1
            number+=1
            for j in range(first,i):episode_labels[k][j]=number
            episode_rows.append(dict(run_id=IDS[k],episode=number,start_s=steps[k][first]['start'],end_s=steps[k][i-1]['end'],
                day=(steps[k][first]['start']-start)//86400+1,clock_start_s=steps[k][first]['start']%86400,
                duration_minutes=(i-first)*5,discomfort_k_hours=math.fsum(values[first:i])/12,
                above_k_hours=math.fsum(high[first:i])/12,below_k_hours=math.fsum(low[first:i])/12,
                peak_excess_k=max(values[first:i]),paired_new_violation_minutes=0,paired_worsened_minutes=0,
                paired_improved_minutes=0,overlapping_other_episode_ids=''))
    for i,(a,b) in enumerate(zip(steps[0],steps[1])):
        require(a['start']==b['start'],'Paired comfort grid mismatch');n,c=severity[0][i],severity[1][i];delta=c-n
        state='new_violation' if n==0 and c>0 else 'resolved_violation' if c==0 and n>0 else 'both_violate' if n>0 else 'both_compliant'
        change='worsened' if delta>EPS else 'improved' if delta<-EPS else 'unchanged_within_1e-7'
        paired.append(dict(time_s=a['start'],day=(a['start']-start)//86400+1,phase=phase(a['start']),
            native_temperature_c=a['current_observation'][TEMP]-273.15,c15_temperature_c=b['current_observation'][TEMP]-273.15,
            published_lower_c=a['current_boundary'][LOW]-273.15,published_upper_c=a['current_boundary'][UP]-273.15,
            occupancy=a['current_boundary'][OCC],native_excess_k=n,c15_excess_k=c,delta_excess_k=delta,
            violation_state=state,paired_change=change,native_episode=episode_labels[0].get(i),c15_episode=episode_labels[1].get(i)))
    for row in episode_rows:
        k=0 if row['run_id']==IDS[0] else 1
        indices=[i for i,t in enumerate(steps[k]) if row['start_s']<=t['start']<row['end_s']]
        row['paired_new_violation_minutes']=5*sum(paired[i]['violation_state']=='new_violation' for i in indices)
        row['paired_worsened_minutes']=5*sum(paired[i]['paired_change']=='worsened' for i in indices)
        row['paired_improved_minutes']=5*sum(paired[i]['paired_change']=='improved' for i in indices)
        row['overlapping_other_episode_ids']=';'.join(map(str,sorted({episode_labels[1-k][i] for i in indices if i in episode_labels[1-k]})))
    changed=[r for r in paired if r['delta_excess_k']>EPS];extra=[r['delta_excess_k'] for r in changed]
    byphase={p:dict(samples=sum(r['phase']==p for r in changed),minutes=5*sum(r['phase']==p for r in changed),
        additional_degree_hours=math.fsum(max(0,r['delta_excess_k']) for r in paired if r['phase']==p)/12,
        peak_additional_k=max([r['delta_excess_k'] for r in changed if r['phase']==p],default=0)) for p in sorted({r['phase'] for r in paired})}
    categories={}
    for state in ('new_violation','resolved_violation','both_violate','both_compliant'):
        rows=[r for r in paired if r['violation_state']==state]
        categories[state]=dict(samples=len(rows),minutes=len(rows)*5,delta_degree_hours=math.fsum(r['delta_excess_k'] for r in rows)/12,
            native_severity=quantiles([r['native_excess_k'] for r in rows]),c15_severity=quantiles([r['c15_excess_k'] for r in rows]))
    changes={name:dict(samples=sum(r['paired_change']==name for r in paired),minutes=5*sum(r['paired_change']==name for r in paired),
        violation_samples=sum(r['paired_change']==name and max(r['native_excess_k'],r['c15_excess_k'])>0 for r in paired))
        for name in ('worsened','improved','unchanged_within_1e-7')}
    bins=[EPS,1e-6,1e-5,1e-4,.001,.01,.025,.05,.1,math.inf]
    histogram=[dict(lower_exclusive_k=lo,upper_inclusive_k=None if math.isinf(hi) else hi,
        samples=sum(lo<v<=hi for v in extra),minutes=5*sum(lo<v<=hi for v in extra)) for lo,hi in zip(bins,bins[1:])]
    pairs=[];endmaps=[{e['time']:e for e in es} for es in endpoints]
    for t in range(start+300,end+1,300):
        power=[interval(n,t-300,t,[COOL,FAN])/1000 for n in native]
        pairs.append(dict(time_s=t,delta_temperature_k=endmaps[1][t][TEMP]-endmaps[0][t][TEMP],delta_electric_kw=power[1]-power[0]))
    recovery=[]
    for day in range(3):
        act=start+day*86400+39600;rel=act+900;stop=rel+7200;row=dict(day=day+1,activation_s=act,release_s=rel,
            requested_minutes=15,applied_minutes=5*sum(r['applied_command']['con_oveTSetCoo_activate'] for r in steps[1] if act<=r['start']<rel))
        for k,label in enumerate(('native','c15')):
            row[label+'_temperature_at_activation_c']=endmaps[k][act][TEMP]-273.15
            row[label+'_temperature_last_endpoint_before_activation_c']=endmaps[k][act-300][TEMP]-273.15
            row[label+'_temperature_at_release_c']=endmaps[k][rel][TEMP]-273.15
        for window,lo,hi in [('hold',act,rel),('recovery',rel,stop),('later',stop,start+(day+1)*86400),('pre',start+day*86400,act)]:
            dt=[endmaps[1][t][TEMP]-endmaps[0][t][TEMP] for t in range(lo,hi+1,300)]
            row.update({window+'_min_delta_temperature_k':min(dt),window+'_max_delta_temperature_k':max(dt),window+'_max_abs_delta_temperature_k':max(map(abs,dt))})
            for k,label in enumerate(('native','c15')):
                for carrier,channels in [('cooling',[COOL]),('fan',[FAN]),('electric',[COOL,FAN])]:
                    row[label+'_'+window+'_'+carrier+'_kwh']=interval(native[k],lo,hi,channels)*(hi-lo)/3600000
                vals=[severity[k][i] for i,r in enumerate(steps[k]) if lo<=r['start']<hi]
                row[label+'_'+window+'_discomfort_k_hours']=math.fsum(vals)/12
                row[label+'_'+window+'_violation_minutes']=5*sum(v>0 for v in vals)
                for carrier,channel in [('cooling',COOL),('fan',FAN)]:
                    row[label+'_'+window+'_'+carrier+'_active_intervals_gt10w']=sum(interval(native[k],t,t+300,[channel])>10 for t in range(lo,hi,300))
            for carrier in ('cooling','fan','electric'):
                row['delta_'+window+'_'+carrier+'_kwh']=row['c15_'+window+'_'+carrier+'_kwh']-row['native_'+window+'_'+carrier+'_kwh']
            dp=[(interval(native[1],t,t+300,[COOL,FAN])-interval(native[0],t,t+300,[COOL,FAN]))/1000 for t in range(lo,hi,300)]
            row[window+'_min_delta_interval_power_kw']=min(dp);row[window+'_max_delta_interval_power_kw']=max(dp)
            row[window+'_power_difference_intervals_ge10w']=sum(abs(v)>=.01 for v in dp)
            row[window+'_new_or_worse_minutes']=5*sum(r['delta_excess_k']>EPS for r in paired if lo<=r['time_s']<hi)
        row['return_near_native_minutes']=recovery_time(pairs,rel)
        row['marker_confirmation_minutes']=row['return_near_native_minutes']+10 if row['return_near_native_minutes'] is not None else None
        row['recovery_temperature_overshoot_above_native_endpoints']=sum(p['delta_temperature_k']>EPS for p in pairs if rel<=p['time_s']<=stop)
        recovery.append(row)
    old=read(PILOT/'PILOT_ANALYSIS.json')['full_period_energy']
    for k,label in enumerate(('native','alternative')):
        require(abs(run_totals[k]['degree_hours']-old['published_all_'+label+'_degree_hours'])<1e-12,'Comfort reproduction mismatch')
        require(run_totals[k]['minutes']==old['published_all_'+label+'_violation_minutes'] and run_totals[k]['episodes']==old['published_all_'+label+'_events'],'Comfort count reproduction mismatch')
    require(len(changed)*5==820,'New/worse duration reproduction mismatch')
    summary=dict(primary_comparison_precision_k=EPS,comfort_violation_threshold='strict excess > 0 against unchanged published bounds',
        sampled_convention='five-minute origin observation times current issued bounds; right-open interval weight 300s',
        totals=run_totals,categories=categories,changes=changes,new_worse_minutes=len(changed)*5,
        additional_degree_hours=math.fsum(max(0,r['delta_excess_k']) for r in paired)/12,
        improved_degree_hours=-math.fsum(min(0,r['delta_excess_k']) for r in paired)/12,
        additional_excess_distribution_k=quantiles(extra),c15_absolute_excess_during_new_worse_k=quantiles([r['c15_excess_k'] for r in changed]),
        additional_excess_histogram=histogram,byphase=byphase,
        reporting_marker_sensitivity={str(v):dict(samples=sum(x>=v for x in extra),minutes=5*sum(x>=v for x in extra)) for v in (.025,.05,.1)},
        c15_episode_overlap=[dict(episode=r['episode'],overlaps=r['overlapping_other_episode_ids'],start_s=r['start_s'],end_s=r['end_s']) for r in episode_rows if r['run_id']==IDS[1]],
        recovery=recovery,simulator_observations_created=0)
    csv_new(HOME/'B2F_COMFORT_EPISODES.csv',episode_rows);csv_new(HOME/'B2F_COMFORT_PAIRED_INTERVALS.csv',paired)
    csv_new(HOME/'B2F_RECOVERY_BY_DAY.csv',recovery);write_new(HOME/'COMFORT_REVIEW.json',summary)
    return summary
