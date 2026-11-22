"""Pure schedule, veto, native-history and validity functions for D0 v1."""
from __future__ import annotations
import hashlib
import json
import math
from pathlib import Path
from stage4e.dataset import TEMP, COOL, FAN, SET, FLAG, NativeElectric, ContractError
from core import integrate

FLAGS=(FLAG,'con_oveTSetHea_activate','fcu_oveFan_activate','fcu_oveTSup_activate')
HEAT='fcu_reaPHea_y'
LOW='LowerSetp[1]';UP='UpperSetp[1]';OCC='Occupancy[1]'
POINTS=(LOW,UP,OCC,'TDryBul','HGloHor')
ROOT=Path(__file__).resolve().parents[1]
HERE=Path(__file__).resolve().parent
STEP=300
SECONDS=259200
WARMUP=604800


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save_new(path,data):
    with Path(path).open('x',encoding='utf-8') as f:
        json.dump(data,f,indent=2,allow_nan=False);f.write('\n')


def finite(x):
    if isinstance(x,bool) or not isinstance(x,(int,float)) or not math.isfinite(x):
        raise ContractError('Missing/nonfinite required data')
    return x


def native_command():return dict.fromkeys(FLAGS,0)


def configuration():
    runs=[]
    for index,(scenario,day,group) in enumerate([
        ('typical_cool_day',146,'qualification_cool_146'),
        ('typical_heat_day',44,'qualification_heat_44')]):
        for arm,mode in [('N','native'),('X','scheduled_variation')]:
            run_id=f'Q{index*2+(1 if arm=="N" else 2):02d}_{arm}'
            start=day*86400
            runs.append({'attempt_id':run_id,'scenario':scenario,'start':start,
                'end':start+SECONDS,'warmup_start':start-WARMUP,'warmup_seconds':WARMUP,
                'mode':mode,'group_id':group,'partition':'development_qualification',
                'initialization':'fresh bestest_air; scenario native 7-day warmup; no copied state',
                'maximum_advances':864,'evidence_directory':f'stage4e_d0/campaign_evidence/{run_id}'})
    return {'protocol':'SDP_STAGE4E_D0_1.0.0','boptest_version':'0.9.0','testcase':'bestest_air',
        'base':'http://127.0.0.1:80','step':STEP,'maximum_attempts':4,'maximum_advances':3456,
        'electricity_price':'constant','temperature_uncertainty':None,'solar_uncertainty':None,
        'runs':runs,'pulse_blocks_local_seconds':[
            {'start':32400,'end':34200,'setpoint_k':296.90},
            {'start':39600,'end':41400,'setpoint_k':296.65},
            {'start':50400,'end':52200,'setpoint_k':296.90}],
        'occupied_expected_lower_k':294.15,'occupied_expected_upper_k':297.15,
        'minimum_heat_cool_deadband_k':.5,'activation_above_lower_k':.75,
        'release_above_lower_k':.5,'upper_excursion_veto_k':.5,
        'maximum_wall_age_s':30,'native_max_gap_s':30,'time_tolerance_s':1e-6,
        'readback_tolerance_k':1e-5,'energy_internal_abs_j':.036,
        'energy_internal_relative':1e-8,'official_audit_abs_j':36.,
        'official_audit_relative':1e-5,'official_kwh_per_j':2.77778e-7,'area_m2':48.,
        'activity_threshold_kw':.01,'minimum_occupied_intervals':100,
        'minimum_unoccupied_intervals':100,'minimum_hvac_active_intervals':50,
        'minimum_hvac_inactive_intervals':50,'minimum_verified_episodes':6,
        'minimum_distinct_active_levels':2,'minimum_native_recovery_intervals_per_episode':12,
        'minimum_cooling_active_intervals':50,'minimum_cooling_inactive_intervals':50,
        'minimum_external_cooling_active_intervals':12,'minimum_full_pulses':6,
        'minimum_applied_intervals_per_level':6}


def nominal(run,t,config):
    if t<run['start'] or t>=run['end'] or (t-run['start'])%STEP:
        raise ContractError('Command timestamp outside frozen grid')
    command=native_command();block=None
    if run['mode']=='scheduled_variation' and t<run['end']-STEP:
        for i,b in enumerate(config['pulse_blocks_local_seconds']):
            if b['start']<=t%86400<b['end']:
                command.update({FLAG:1,SET:b['setpoint_k']})
                block=f"day{(t-run['start'])//86400}_block{i}"
    return {'start':t,'end':t+STEP,'command':command,'block_id':block}


def action_path(run,t,config):
    return [dict(nominal(run,s,config),known_at_sim=run['start'],source='frozen_nominal_plan')
            for s in range(t,min(t+1800,run['end']),STEP)]


def schedule_rows(config):
    result=[]
    for run in config['runs']:
        events=[]
        if run['mode']=='scheduled_variation':
            for d in range(3):
                for b in config['pulse_blocks_local_seconds']:
                    base=run['start']+d*86400
                    events.append({'activate':base+b['start'],'release':base+b['end'],
                                   'requested_setpoint_k':b['setpoint_k']})
        result.append(dict(run,activation_release_events=json.dumps(events,separators=(',',':')),
            control_step_s=300,scored_hours=72,
            requested_action='all activation flags zero' if run['mode']=='native' else 'cooling only: 296.90 / 296.65 K per listed events, subject to veto',
            final_release_interval_start=run['end']-STEP,
            endpoint_count=865,nominal_native_power_samples=8641))
    return result


class Safety:
    """Veto latches for the rest of a fixed pulse; no adaptive make-up pulses."""
    def __init__(self,config):self.c=config;self.block=None;self.vetoed=False;self.active=False

    def decide(self,planned,obs,boundary,age):
        c=self.c;t=planned['start']
        for x in (obs.get('time'),obs.get(TEMP),obs.get('con_oveTSetHea_u'),
                  boundary.get('time'),boundary.get(LOW),boundary.get(UP),boundary.get(OCC),age):finite(x)
        if abs(obs['time']-t)>1e-6 or abs(boundary['time']-t)>1e-6 or not 0<=age<=c['maximum_wall_age_s']:
            raise ContractError('Stale/future observation or boundary')
        if not (200<obs[TEMP]<350 and 250<boundary[LOW]<=boundary[UP]<330
                and boundary[OCC]>=0 and 250<obs['con_oveTSetHea_u']<330):
            raise ContractError('Invalid physical/context range')
        if planned['block_id']!=self.block:
            self.block=planned['block_id'];self.vetoed=False;self.active=False
        if not planned['command'][FLAG]:
            self.active=False
            return native_command(),'scheduled_native_or_final_release'
        if self.vetoed:return native_command(),'latched_veto_rest_of_pulse'
        target=planned['command'][SET];temp=obs[TEMP];lo=boundary[LOW];up=boundary[UP]
        reason=None
        if boundary[OCC]<=0:reason='unoccupied_veto'
        elif abs(lo-c['occupied_expected_lower_k'])>1e-5 or abs(up-c['occupied_expected_upper_k'])>1e-5:
            raise ContractError('Pulse-time comfort schedule conflicts with frozen source contract')
        elif not max(278.15,lo+.5,obs['con_oveTSetHea_u']+.5)<=target<=min(308.15,up):reason='infeasible_command_veto'
        elif temp>up+c['upper_excursion_veto_k']:reason='upper_excursion_native_fallback'
        elif temp<lo+(c['release_above_lower_k'] if self.active else c['activation_above_lower_k']):reason='cold_margin_veto'
        if reason:
            self.vetoed=True;self.active=False
            return native_command(),reason
        self.active=True
        return dict(planned['command']),'scheduled_pulse_applied'


def validate_observation(obs,t,metadata):
    if abs(finite(obs.get('time'))-t)>1e-6:raise ContractError('Endpoint time mismatch')
    for name in list(metadata['measurements'])+list(metadata['inputs']):finite(obs.get(name))
    for flag in FLAGS:
        if obs[flag] not in (0,1):raise ContractError('Nonbinary activation readback')
    if any(obs[name]<-1e-6 for name in (COOL,FAN)):
        raise ContractError('Materially negative electrical demand')


def validate_readback(command,obs,native_upper=None):
    if any(obs[f]!=command[f] for f in FLAGS):raise ContractError('Activation readback mismatch')
    if command[FLAG] and abs(obs[SET]-command[SET])>1e-5:raise ContractError('Setpoint readback mismatch')
    if not command[FLAG] and native_upper is not None and abs(obs[SET]-native_upper)>1e-5:
        raise ContractError('Native cooling setpoint did not resume')
    return True


def validate_forecast(data,t):
    if data.get('time')!=list(range(t,t+1801,STEP)):raise ContractError('Forecast valid-time grid mismatch')
    for name in POINTS:
        if len(data.get(name,[]))!=7:raise ContractError('Forecast point absent/misaligned')
        for x in data[name]:finite(x)
    return dict(time=t,**{name:data[name][0] for name in POINTS})


def append_native(combined,chunk,start,end):
    names=[COOL,FAN,HEAT]
    ts=chunk.get('time',[])
    if not ts:raise ContractError('Empty native history')
    canonical=[round(finite(t)) if abs(t-round(t))<=1e-6 else t for t in ts]
    if canonical[0]!=start or canonical[-1]!=end:raise ContractError('Native coverage boundary mismatch')
    if any(b<a or b-a>30 for a,b in zip(canonical,canonical[1:])):raise ContractError('Native gap/order')
    for name in names:
        if len(chunk.get(name,[]))!=len(ts):raise ContractError('Native channel missing/misaligned')
        for x in chunk[name]:finite(x)
    if any(x<-1e-6 for name in (COOL,FAN) for x in chunk[name]):
        raise ContractError('Materially negative native electrical power')
    if combined:
        if combined['time'][-1]!=start:raise ContractError('Chunk overlap/gap')
        if any(combined[n][-1]!=chunk[n][0] for n in names):raise ContractError('Chunk overlap value mismatch')
        offset=1 # Drop only the repeated first boundary sample, retain event duplicates.
    else:
        combined.update({k:[] for k in ['time']+names});offset=0
    combined['time'].extend(canonical[offset:])
    for n in names:combined[n].extend(chunk[n][offset:])


def energy_audit(native,start,end,kpi,config):
    e=NativeElectric(native)
    interval_j=math.fsum(e.interval(t,t+STEP)['joules'] for t in range(start,end,STEP))
    channel_j={k:integrate(native['time'],native[k],start,end) for k in (COOL,FAN,HEAT)}
    independent_j=channel_j[COOL]+channel_j[FAN]
    internal_limit=max(config['energy_internal_abs_j'],abs(independent_j)*config['energy_internal_relative'])
    if abs(interval_j-independent_j)>internal_limit:raise ContractError('Interval/full-history integration disagreement')
    official=finite(kpi.get('ener_tot'))
    official_electric_j=official*config['area_m2']/config['official_kwh_per_j']-channel_j[HEAT]
    external_limit=max(config['official_audit_abs_j'],abs(independent_j)*config['official_audit_relative'])
    if abs(official_electric_j-independent_j)>external_limit:raise ContractError('Official combined-carrier reconciliation failed')
    return {'electrical_j':independent_j,'electrical_kwh':independent_j/3600000,
        'interval_sum_j':interval_j,'official_electric_reconstructed_j':official_electric_j,
        'internal_tolerance_j':internal_limit,'official_tolerance_j':external_limit,
        'gas_reported_channel_j_separate':channel_j[HEAT],
        'limitation':'independent code/API consistency, not an independent physical meter or sampling-error bound'}


def coverage(records,native,config):
    e=NativeElectric(native);occupied=active=episodes=0;levels=set();recoveries=0
    cooling_integral=NativeElectric({'time':native['time'],COOL:native[COOL],FAN:[0.]*len(native['time'])})
    cooling_active=external_cooling=full_pulses=0;level_counts={}
    was=False
    for i,r in enumerate(records):
        occupied+=r['current_boundary'][OCC]>0
        active+=e.interval(r['start'],r['end'])['average_kw']>config['activity_threshold_kw']
        cooling_kw=cooling_integral.interval(r['start'],r['end'])['average_kw']
        cooling_active+=cooling_kw>config['activity_threshold_kw']
        now=bool(r['applied_command'][FLAG])
        if now:
            level=r['applied_command'][SET];levels.add(level)
            level_counts[str(level)]=level_counts.get(str(level),0)+1
            external_cooling+=cooling_kw>config['activity_threshold_kw']
        if was and not now:
            episodes+=1
            following=records[i:i+config['minimum_native_recovery_intervals_per_episode']]
            recoveries+=len(following)==12 and all(not x['applied_command'][FLAG] for x in following)
            preceding=records[max(0,i-6):i]
            full_pulses+=len(preceding)==6 and all(x['applied_command'][FLAG] for x in preceding) and (
                i==6 or not records[i-7]['applied_command'][FLAG])
        was=now
    return {'intervals':len(records),'occupied':occupied,'unoccupied':len(records)-occupied,
        'hvac_active':active,'hvac_inactive':len(records)-active,
        'verified_episodes':episodes,'verified_recoveries':recoveries,
        'verified_full_pulses':full_pulses,'cooling_active':cooling_active,
        'cooling_inactive':len(records)-cooling_active,'external_cooling_active':external_cooling,
        'level_interval_counts':level_counts,
        'active_levels_k':sorted(levels),'veto_intervals':sum('veto' in x['reason'] or 'fallback' in x['reason'] for x in records),
        'occupied_outside_band_endpoints':sum(r['current_boundary'][OCC]>0 and not
            r['current_boundary'][LOW]<=r['current_observation'][TEMP]<=r['current_boundary'][UP] for r in records)}


def campaign_gate(summaries,config):
    if len(summaries)!=4 or any(s['classification']!='PASS_VALID_RAW' for s in summaries):return 'FAILED'
    totals={k:sum(s['coverage'][k] for s in summaries) for k in ('occupied','unoccupied','hvac_active','hvac_inactive','verified_episodes','verified_recoveries','cooling_active','cooling_inactive','external_cooling_active','verified_full_pulses')}
    levels={v for s in summaries for v in s['coverage']['active_levels_k']}
    limits={'occupied':config['minimum_occupied_intervals'],'unoccupied':config['minimum_unoccupied_intervals'],
        'hvac_active':config['minimum_hvac_active_intervals'],'hvac_inactive':config['minimum_hvac_inactive_intervals'],
        'verified_episodes':config['minimum_verified_episodes'],'verified_recoveries':config['minimum_verified_episodes'],
        'cooling_active':config['minimum_cooling_active_intervals'],'cooling_inactive':config['minimum_cooling_inactive_intervals'],
        'external_cooling_active':config['minimum_external_cooling_active_intervals'],'verified_full_pulses':config['minimum_full_pulses']}
    level_counts={level:sum(s['coverage']['level_interval_counts'].get(str(level),0) for s in summaries) for level in levels}
    useful_levels=sum(v>=config['minimum_applied_intervals_per_level'] for v in level_counts.values())
    return 'PASS_QUALIFICATION' if all(totals[k]>=v for k,v in limits.items()) and useful_levels>=config['minimum_distinct_active_levels'] else 'INCONCLUSIVE_EXCITATION'
