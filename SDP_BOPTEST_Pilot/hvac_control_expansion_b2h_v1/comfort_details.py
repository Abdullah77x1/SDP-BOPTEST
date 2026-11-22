"""Supplementary new/worse comfort samples, grouped by each policy's actual schedule."""
import csv,json,math
from . import HOME,PILOT,V2,RID
from hvac_control_expansion_b2f_v1.packaging import read,require
from hvac_control_expansion_b2f_v1.review import excess,quantiles

def derive(record=False,verify=False):
    dirs=[PILOT/'runtime_state/batches/B1_G174_INITIAL_PILOT/B1V01_G174_NREF',PILOT/'runtime_state/batches/B1_G174_INITIAL_PILOT/B1V01_G174_C15',V2/'runtime_state/batches/B2G_G174_C45_ONLY'/RID]
    steps=[[json.loads(x) for x in (d/'steps.jsonl').read_text().splitlines()] for d in dirs];rows=[]
    for k,ref in [(1,0),(2,0),(2,1)]:
        release=40500 if k==1 else 42300
        for a,b in zip(steps[ref],steps[k]):
            n=sum(excess(a));c=sum(excess(b));delta=c-n;clock=a['start']%86400
            phase='pre_intervention' if clock<39600 else 'hold' if clock<release else 'actual_postrelease_recovery' if clock<release+7200 else 'later'
            if delta>1e-7 or (n==0 and c>0):rows.append(dict(policy=['NREF','C15','C45'][k],reference=['NREF','C15','C45'][ref],time_s=a['start'],
                day=(a['start']-15033600)//86400+1,clock_s=clock,phase=phase,native_excess_k=n,alternative_excess_k=c,additional_excess_k=delta,new_violation=n==0 and c>0))
    c45=[x for x in rows if x['policy']=='C45' and x['reference']=='NREF']
    report=dict(phase_basis='Each alternative policy own fixed activation/release + two hours; C15 11:15, C45 11:45',
        C45_new_timestamp_details=[x for x in c45 if x['new_violation']],C45_additional_distribution=quantiles([x['additional_excess_k'] for x in c45]),
        C45_minutes_additional_below_0_001k=5*sum(x['additional_excess_k']<.001 for x in c45),
        C45_by_clock_phase={p:dict(minutes=5*sum(x['phase']==p for x in c45),additional_k_hours=math.fsum(x['additional_excess_k'] for x in c45 if x['phase']==p)/12) for p in sorted({x['phase'] for x in c45})})
    if record:
        # Derived, unpublished B2-H analysis only. Never touches a simulator file or historical artifact.
        (HOME/'COMFORT_DETAIL.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
        with (HOME/'B2H_COMFORT_NEW_WORSE_SAMPLES.csv').open('w',newline='',encoding='utf-8') as f:
            w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
    if verify:
        require(read(HOME/'COMFORT_DETAIL.json')==report,'Comfort detail reconstruction mismatch')
        with (HOME/'B2H_COMFORT_NEW_WORSE_SAMPLES.csv').open() as f:stored=list(csv.DictReader(f))
        require(stored==[{k:str(v) for k,v in row.items()} for row in rows],'Comfort sample reconstruction mismatch')
    return report

if __name__=='__main__':
    import argparse
    from hvac_control_expansion_b2f_v1.tests import offline_guard
    p=argparse.ArgumentParser();p.add_argument('--record',action='store_true');p.add_argument('--verify',action='store_true');a=p.parse_args()
    require(not a.record or not (HOME/'DELIVERY_MANIFEST.json').exists(),'Final analysis delivery cannot be overwritten')
    with offline_guard():print(json.dumps(derive(a.record,a.verify),indent=2))
