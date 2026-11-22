"""Fixed descriptive pilot analysis. All output requires two real, valid raw runs."""
import csv,json,math
from pathlib import Path
from .campaign import coverage,DURATIONS
from stage4e_d2i_1.common import require,read,save_new
from stage4e_d0.plan import TEMP,COOL,FAN,HEAT,LOW,UP,OCC
from stage4e_d2_public.export import interval

def load_steps(d):
    return [json.loads(s) for s in (Path(d)/'steps.jsonl').read_text().splitlines()]

def write_csv(path,rows):
    require(bool(rows),'No fabricated/empty result table')
    with Path(path).open('x',newline='',encoding='utf-8') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)

def recovery_time(pairs,release):
    """First of three consecutive endpoint/preceding-interval pairs, censored 120m."""
    good=0
    for row in pairs:
        if not release<=row['time_s']<=release+7200:continue
        good=good+1 if abs(row['delta_temperature_k'])<=.05 and abs(row['delta_electric_kw'])<=.01 else 0
        if good==3:return (row['time_s']-600-release)/60
    return None

def comfort(records,start,end,occupied_only=False,nominal=False):
    dh=minutes=peak=events=below_dh=above_dh=below_minutes=above_minutes=0.;was=False
    for r in records:
        if not start<=r['start']<end:continue
        t=r['start']%86400; occ=r['current_boundary'][OCC]>0
        lo,up=r['current_boundary'][LOW],r['current_boundary'][UP]
        if nominal:
            occ=28800<=t<64800;lo,up=(294.15,297.15) if occ else (288.15,303.15)
        if occupied_only and not occ:was=False;continue
        temp=r['current_observation'][TEMP];below=max(lo-temp,0);above=max(temp-up,0);v=below+above
        below_dh+=below/12;above_dh+=above/12;below_minutes+=5*(below>0);above_minutes+=5*(above>0)
        dh+=v/12;minutes+=5*(v>0);peak=max(peak,v);events+=(v>0 and not was);was=v>0
    return dict(degree_hours=dh,violation_minutes=minutes,peak_k=peak,events=int(events),
                below_degree_hours=below_dh,above_degree_hours=above_dh,below_minutes=below_minutes,above_minutes=above_minutes)

def analyze(native_dir,alt_dir,run,out):
    out=Path(out);a,b=Path(native_dir),Path(alt_dir)
    for d in (a,b):
        s=read(d/'RUN_COMPLETED.json')
        require(s['classification']=='PASS_VALID_RAW' and s['data_is_fabricated'] is False and s['cleanup']=='STOP_ACK_AND_REMOVAL_VERIFIED','Real complete raw evidence required')
    ea=read(a/'endpoints.json');eb=read(b/'endpoints.json');na=read(a/'native_results.json');nb=read(b/'native_results.json')
    sa,sb=load_steps(a),load_steps(b);cover=coverage(sb,nb,{},run)
    pairs=[]
    for x,y in zip(ea,eb):
        t=x['time'];require(t==y['time'],'Unmatched analysis time')
        pa=interval(na,t-300,t,[COOL,FAN])/1000 if t>run['start'] else None
        pb=interval(nb,t-300,t,[COOL,FAN])/1000 if t>run['start'] else None
        pairs.append(dict(time_s=t,native_temperature_c=x[TEMP]-273.15,alternative_temperature_c=y[TEMP]-273.15,
            delta_temperature_k=y[TEMP]-x[TEMP],native_interval_electric_kw=pa,alternative_interval_electric_kw=pb,
            delta_electric_kw=pb-pa if pa is not None else None))
    delivery=[]
    for e in cover['episodes']:
        r=e['release_s'];rr=recovery_time(pairs,r) if r else None
        delivery.append(dict(run_id=run['run_id'],**{k:json.dumps(v) if isinstance(v,(list,dict)) else v for k,v in e.items()},
            return_near_native_minutes=rr,recovery_censored_at_120min=r is not None and rr is None))
    energy=[]
    windows=[('full_72h',run['start'],run['end'])]
    for day in range(3):
        start=run['start']+day*86400+39600;rel=start+DURATIONS[run['arm']]
        windows.extend([(f'day{day+1}_11to14',start,start+10800),(f'day{day+1}_intervention',start,rel),(f'day{day+1}_recovery',rel,rel+7200)])
    for name,start,end in windows:
        row=dict(window=name,start_s=start,end_s=end)
        for label,keys in [('cooling',[COOL]),('fan',[FAN]),('electric',[COOL,FAN]),('gas',[HEAT])]:
            va=interval(na,start,end,keys)*(end-start)/3600000;vb=interval(nb,start,end,keys)*(end-start)/3600000
            row.update({f'native_{label}_kwh':va,f'alternative_{label}_kwh':vb,f'delta_{label}_kwh':vb-va})
        for nominal in (False,True):
            for occupied in (False,True):
                ca=comfort(sa,start,end,occupied,nominal);cb=comfort(sb,start,end,occupied,nominal)
                tag=('nominal_' if nominal else 'published_')+('occupied_' if occupied else 'all_')
                for k in ca:row.update({tag+'native_'+k:ca[k],tag+'alternative_'+k:cb[k],tag+'delta_'+k:cb[k]-ca[k]})
        # Pairwise new/worse sampled violations; distinct from native pre-existing events.
        worsened=[]
        for x,y in zip(sa,sb):
            if not start<=x['start']<end:continue
            def violation(z):
                v=z['current_observation'][TEMP];c=z['current_boundary'];return max(c[LOW]-v,0)+max(v-c[UP],0)
            worsened.append(max(0,violation(y)-violation(x)))
        row.update(new_or_worse_minutes=5*sum(v>1e-7 for v in worsened),additional_degree_hours=sum(worsened)/12,
                   peak_additional_violation_k=max(worsened,default=0),new_or_worse_events=sum(v>1e-7 and (i==0 or worsened[i-1]<=1e-7) for i,v in enumerate(worsened)))
        energy.append(row)
    common=[p for p in pairs if 39600<=p['time_s']%86400<=50400]
    deltas=[p['delta_temperature_k'] for p in common];powers=[p['delta_electric_kw'] for p in common]
    summary=dict(control=cover,maximum_abs_temperature_difference_k=max(map(abs,deltas)),mean_temperature_difference_k=sum(deltas)/len(deltas),
        mean_absolute_temperature_difference_k=sum(map(abs,deltas))/len(deltas),
        temperature_difference_area_k_hours=sum((abs(x['delta_temperature_k'])+abs(y['delta_temperature_k']))/24 for x,y in zip(common,common[1:]) if y['time_s']-x['time_s']==300),
        temperature_threshold_counts={str(k):sum(abs(v)>=k for v in deltas) for k in (.025,.05,.1)},
        power_threshold_counts_w={str(k):sum(abs(v)*1000>=k for v in powers) for k in (1,10,50)},
        response_separation=any(abs(v)>=.05 for v in deltas) or any(abs(v)>=.01 for v in powers),
        full_period_energy=energy[0],cleanup_verified=True,ml_models_trained=0,remaining_runs_executed=0)
    complete=all(e['complete'] for e in cover['episodes'])
    summary['outcome']='VALID_AND_INFORMATIVE' if complete and summary['response_separation'] else 'VALID_BUT_INCONCLUSIVE'
    write_csv(out/'B1_CONTROL_DELIVERY.csv',delivery);write_csv(out/'B1_TEMPERATURE_RESPONSE.csv',pairs)
    write_csv(out/'B1_ENERGY_COMFORT_COMPARISON.csv',energy);save_new(out/'PILOT_ANALYSIS.json',summary)
    return summary
