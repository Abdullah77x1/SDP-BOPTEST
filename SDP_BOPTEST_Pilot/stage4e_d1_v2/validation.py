"""SDP_SETPOINT_VALIDATION_2.1.0. Native references are not comfort forecasts."""
from copy import deepcopy
from dataclasses import asdict,replace
from stage4e_d1r.proposed_validation import (NativeReference,Violation,finite,near,
    command_schema,validate_endpoint as draft_endpoint,validate_boundary_followup_history,
    COOL,HEAT,TEMP,FLAGS,CA,EPS_K,EPS_TIME)
from stage4e_d0.plan import COOL as POWER_COOL,FAN,HEAT as POWER_HEAT

VERSION='SDP_SETPOINT_VALIDATION_2.1.0'
NATIVE=dict.fromkeys(FLAGS,0)
HISTORY_POINTS=(HEAT,COOL,*FLAGS,TEMP,POWER_COOL,FAN,POWER_HEAT)
REFERENCE=NativeReference()

def command_guard(command,current,boundary,origin,age_s):
    command_schema(command)
    for key in (HEAT,COOL,TEMP,*FLAGS):finite(current.get(key))
    if any(current[f] not in (0,1) for f in FLAGS):raise Violation('invalid_current_flag')
    if any(current[f] for f in FLAGS if f!=CA):raise Violation('unexpected_current_noncooling_activation')
    finite(age_s)
    if not 0<=age_s<=30 or current.get('time')!=origin or boundary.get('time')!=origin:
        raise Violation('stale_or_wrong_current_timestamp')
    lo=finite(boundary.get('LowerSetp[1]'));up=finite(boundary.get('UpperSetp[1]'))
    occ=finite(boundary.get('Occupancy[1]'))
    if not 250<lo<=up<330 or occ<0 or not 200<current[TEMP]<350:
        raise Violation('invalid_current_context')
    if command[CA]:
        if REFERENCE.event_pairs(origin):raise Violation('no_new_external_command_at_exact_native_event')
        if occ<=0 or not max(lo+.5,current[HEAT]+.5,278.15)<=command[COOL]<=min(up,308.15):
            raise Violation('external_occupancy_comfort_or_deadband_violation')
    elif command!=NATIVE:raise Violation('noncanonical_native_command')
    return True

def endpoint(origin,command,obs,forecast,orders,age_s):
    # Reuse unchanged strict clocks, finite values, limits and active readbacks.
    if not command.get(CA) and set(command)!=set(FLAGS):
        raise Violation('inactive_command_must_contain_only_four_zero_flags')
    result=draft_endpoint(origin,command,obs,forecast,orders,age_s)
    if obs[COOL]-obs[HEAT]<.5-EPS_K:raise Violation('effective_heating_cooling_separation')
    if result.status=='UNRESOLVED_BOUNDARY':
        if any(command[f] for f in FLAGS):raise Violation('active_command_cannot_create_native_pending_event')
        return replace(result,status='PENDING_EVENT_VERIFICATION',
            reason='coherent_previous_pair_at_registered_event;one_scheduled_native_interval_only',stop_production=False)
    return result

def initial_native(obs):
    t=finite(obs.get('time'))
    for key in (HEAT,COOL,TEMP,*FLAGS):finite(obs.get(key))
    if any(obs[f]!=0 for f in FLAGS):raise Violation('initial_external_activation')
    if not all(near(obs[k],v) for k,v in zip((HEAT,COOL),REFERENCE.pair(t))):
        raise Violation('initial_native_reference_mismatch')
    return True

def history(data,start,end):
    ts=data.get('time',[])
    if not ts or ts[0]!=start or ts[-1]!=end:raise Violation('native_history_coverage')
    for t in ts:finite(t)
    if any(b<a or b-a>30+EPS_TIME for a,b in zip(ts,ts[1:])):raise Violation('native_history_gap_or_order')
    present=set(ts)
    if any(t not in present for t in range(int(start),int(end)+1,30)):
        raise Violation('missing_regular_native_sample')
    for name in HISTORY_POINTS:
        if len(data.get(name,[]))!=len(ts):raise Violation('missing_native_signal:'+name)
        for v in data[name]:finite(v)
    if any(v not in (0,1) for f in FLAGS for v in data[f]):raise Violation('nonbinary_history_flag')
    if any(v<-1e-6 for k in (POWER_COOL,FAN) for v in data[k]):raise Violation('negative_native_electricity')
    for i,t in enumerate(ts):
        if any(data[f][i] for f in FLAGS if f!=CA):raise Violation('unexpected_noncooling_history_activation')
        heat,cool=data[HEAT][i],data[COOL][i]
        if not 278.15<=heat<=308.15 or not 278.15<=cool<=308.15 or cool-heat<.5-EPS_K:
            raise Violation('invalid_history_setpoint_or_separation')
        event=REFERENCE.event_pairs(t)
        allowed=event if event else (REFERENCE.pair(t),)
        if data[CA][i]:
            if not any(near(heat,pair[0]) for pair in allowed):raise Violation('history_native_heating_mismatch')
        elif not any(near(heat,pair[0]) and near(cool,pair[1]) for pair in allowed):
            raise Violation('mixed_or_persistent_native_history_pair')
    return True

class EventTracker:
    """One pending observation; resolution is a separate later audit record.

    Neither the original endpoint nor its at-origin status is rewritten.
    This state is never a forecasting feature or a source of future truth.
    """
    def __init__(self):self.pending=None;self.resolutions=[]
    def register(self,obs,result,receipt):
        if result.status!='PENDING_EVENT_VERIFICATION':return
        if self.pending is not None:raise Violation('second_pending_event')
        self.pending={'event_time':obs['time'],'endpoint_at_event':deepcopy(obs),
            'event_receipt_order':receipt,'status_at_event':'PENDING_EVENT_VERIFICATION'}
    def guard(self,origin,command,current,age_s,remaining_advances):
        finite(age_s)
        if not 0<=age_s<=30:raise Violation('stale_pending_origin')
        if self.pending is None:return
        if (origin!=self.pending['event_time'] or current!=self.pending['endpoint_at_event']
            or remaining_advances<1 or command!=NATIVE or any(current.get(f)!=0 for f in FLAGS)):
            raise Violation('pending_requires_same_event_and_one_scheduled_native_interval')
    def resolve(self,data,obs,result,response_order,history_receipt_order):
        if self.pending is None:raise Violation('no_pending_event_to_resolve')
        p=self.pending;e=p['event_time']
        history(data,e-300,e+300)
        if (obs.get('time')!=e+300 or result.status!='VERIFIED_REFERENCE'
            or not p['event_receipt_order']<response_order<history_receipt_order):
            raise Violation('pending_followup_endpoint_or_receipt_mismatch')
        if any(obs.get(f)!=0 for f in FLAGS):raise Violation('pending_followup_endpoint_activation')
        if not all(near(obs[k],v) for k,v in zip((HEAT,COOL),REFERENCE.pair(e+300))):
            raise Violation('pending_followup_endpoint_not_new_pair')
        indices=[i for i,t in enumerate(data['time']) if t>=e]
        post={k:[v[i] for i in indices] for k,v in data.items()}
        checked=validate_boundary_followup_history(e,post)
        # The original event endpoint must still occur in preserved event history.
        if not any(t==e and all(near(data[k][i],p['endpoint_at_event'][k]) for k in (HEAT,COOL))
                   for i,t in enumerate(data['time'])):raise Violation('event_endpoint_missing_from_history')
        resolution={**deepcopy(p),'status':'RESOLVED_EVENT_VERIFICATION',
            'resolved_at_sim':e+300,'resolved_after_response_order':response_order,
            'history_receipt_order':history_receipt_order,'history_check':checked,
            'extra_advance_inserted':False,'training_release':False,
            'resolution_is_validation_metadata_not_origin_information':True}
        self.resolutions.append(resolution);self.pending=None
        return resolution
