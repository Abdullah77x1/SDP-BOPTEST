"""Compatibility sidecars and labels only; no feature matrix, model or release."""
from .campaign import action_path
from stage4e_d2i_1.common import require, ROOT, read
from stage4e_d2i_1.manifest import origin_times
from stage4e_d2_public.export import interval
from stage4e_d0.plan import TEMP, COOL, FAN, HEAT

def planned_at_origin(run,t):
    path=action_path(run,t)
    require(all(p['known_at_sim']<=t and p['source']=='frozen_nominal_plan' for p in path),'Future information')
    return path

def validate_origin_path(path,origin):
    for p in path:
        require(set(p)=={'start','end','command','block_id','known_at_sim','source'},'Unexpected future outcome field')
        require(p['known_at_sim']<=origin and p['source']=='frozen_nominal_plan','Realized/future decision cannot be a plan')
    return True

def labels(endpoints,native,t):
    """Original 16 labels: endpoint temperature and LAST interval means."""
    result={}; e={x['time']:x for x in endpoints}
    for mins in (5,10,15,30):
        end=t+mins*60
        result[f'target_indoor_temp_{mins}min_c']=e[end][TEMP]-273.15
        for name,channel,mult in [('cooling_electric',COOL,1),('fan_electric',FAN,1),('heating_thermal',HEAT,.9)]:
            result[f'target_{name}_power_{mins}min_kw']=mult*interval(native,end-300,end,[channel])/1000
    require(set(result)==set(read(ROOT.parent/'experiments/hvac_16_outputs_v2_0_0/SCHEMA_FREEZE.json')['targets']),'Target definitions changed')
    return result

def overlay_metadata(run):
    return dict(run_id=run['run_id'],group_id=run['group_id'],partition='development',
                outer_held_fold=run['outer_held_fold'],policy=run['arm'],training_default=run['training_default'],
                origins=origin_times(run['start'],run['end']),release_status='QUARANTINED_REVIEW_REQUIRED')

def matched_size_plan(run):
    """Metadata-only 426/426 clock map, <=60-minute blocks, stratified day/phase."""
    import random
    rng=random.Random(20261118);strata={}
    for t in origin_times(run['start'],run['end']):
        clock=t%86400
        # chronological phases; night split at midnight remains within the day stratum
        phase=next(i for i,end in enumerate((28800,39600,42300,50400,64800,86400)) if clock<end)
        strata.setdefault(((t-run['start'])//86400,phase),[]).append(t)
    chosen=set();odd=[]
    for key,times in sorted(strata.items()):
        blocks=[times[i:i+12] for i in range(0,len(times),12)];rng.shuffle(blocks)
        quota=len(times)//2
        remaining=quota
        for block in blocks:
            take=min(len(block),remaining);chosen.update(block[:take]);remaining-=take
        if len(times)%2:odd.append([t for t in times if t not in chosen])
    rng.shuffle(odd)
    for candidates in odd:
        if len(chosen)>=426:break
        chosen.add(candidates[0])
    origins=origin_times(run['start'],run['end'])
    require(len(chosen)==426 and len(origins)==852,'Matched-size quota mismatch')
    return [dict(group_id=run['group_id'],time_s=t,policy_pair='C15_C45' if t in chosen else 'original_N_X',
                 seed=20261118,selection_inputs='METADATA_ONLY_NOT_OUTCOMES') for t in origins]
