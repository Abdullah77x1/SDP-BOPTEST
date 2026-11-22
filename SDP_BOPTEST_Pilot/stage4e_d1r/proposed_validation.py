"""SDP_SETPOINT_VALIDATION_2.0.0_DRAFT: fabricated-test prototype ONLY.

Separates native thermostat reference from comfort CSV signals. An old native
pair at the exact model event remains UNRESOLVED and stops production; this is
not a grace period, release waiver, or authorization for a diagnostic advance.
"""
from dataclasses import dataclass
import math

VERSION='SDP_SETPOINT_VALIDATION_2.0.0_DRAFT'
COOL='con_oveTSetCoo_u';HEAT='con_oveTSetHea_u'
CA='con_oveTSetCoo_activate'
FLAGS=(CA,'con_oveTSetHea_activate','fcu_oveFan_activate','fcu_oveTSup_activate')
TEMP='zon_reaTRooAir_y'
EPS_K=1e-5
EPS_TIME=1e-6


class Violation(ValueError):pass


def finite(x):
    if isinstance(x,bool) or not isinstance(x,(float,int)) or not math.isfinite(x):
        raise Violation('missing_or_nonfinite_value')
    return x


def near(a,b):return abs(a-b)<=EPS_K


@dataclass(frozen=True)
class NativeReference:
    """Binding from pinned XML/defaults and Thermostat_T table; not CSV limits."""
    occupied_start_s:int=28800
    occupied_end_s:int=64800
    occupied_heat_k:float=294.15
    occupied_cool_k:float=297.15
    unoccupied_heat_k:float=288.15
    unoccupied_cool_k:float=303.15

    def pair(self,t):
        phase=t%86400
        if self.occupied_start_s<=phase<self.occupied_end_s:
            return self.occupied_heat_k,self.occupied_cool_k
        return self.unoccupied_heat_k,self.unoccupied_cool_k

    def event_pairs(self,t):
        phase=t%86400
        if abs(phase-self.occupied_start_s)<=EPS_TIME:
            return (self.unoccupied_heat_k,self.unoccupied_cool_k),(self.occupied_heat_k,self.occupied_cool_k)
        if abs(phase-self.occupied_end_s)<=EPS_TIME:
            return (self.occupied_heat_k,self.occupied_cool_k),(self.unoccupied_heat_k,self.unoccupied_cool_k)
        return None


@dataclass(frozen=True)
class Result:
    status:str
    reason:str
    native_reference_pair:tuple
    observed_pair:tuple
    comfort_pair:tuple
    stop_production:bool=False
    external_control_verified:bool=False
    event_annotation:str='none'
    training_release:bool=False


def command_schema(command):
    if not set(command)<=set(FLAGS)|{COOL}:raise Violation('unsupported_command_field')
    for flag in FLAGS:
        finite(command.get(flag))
        if command[flag] not in (0,1):raise Violation('nonbinary_or_missing_command_flag')
    if any(command[f] for f in FLAGS if f!=CA):raise Violation('unsupported_noncooling_override')
    if command[CA]:
        target=finite(command.get(COOL))
        if not 278.15<=target<=308.15:raise Violation('command_outside_actuator_limits')


def clocks(origin,obs,forecast,orders,age):
    finite(origin);finite(age)
    if origin<0 or abs(origin-round(origin/300)*300)>EPS_TIME:raise Violation('origin_off_frozen_grid')
    if not 0<=age<=30:raise Violation('stale_observation')
    if abs(finite(obs.get('time'))-(origin+300))>EPS_TIME:raise Violation('endpoint_time_mismatch')
    if abs(finite(forecast.get('time'))-(origin+300))>EPS_TIME:raise Violation('forecast_valid_time_mismatch')
    if abs(finite(forecast.get('issued_at'))-origin)>EPS_TIME:raise Violation('forecast_issue_time_mismatch')
    for key in ('observation','forecast','cutoff','response'):
        finite(orders.get(key))
        if not isinstance(orders[key],int) or orders[key]<1:raise Violation('invalid_receipt_order')
    if not orders['observation']<orders['cutoff']<orders['response'] or not orders['forecast']<orders['cutoff']:
        raise Violation('future_or_misordered_receipt')


def validate_endpoint(origin,command,obs,forecast,orders,age_s,reference=NativeReference()):
    """Post-response prototype: always strict flags/active command readbacks.

    Returns UNRESOLVED at an exact native transition if the coherent old pair is
    observed. No subsequent production advance is permitted by that result.
    """
    command_schema(command);clocks(origin,obs,forecast,orders,age_s)
    for name in (COOL,HEAT,TEMP,*FLAGS):finite(obs.get(name))
    for flag in FLAGS:
        if obs[flag]!=command[flag]:raise Violation('external_activation_readback_mismatch')
    lo,up,occ=[finite(forecast.get(k)) for k in ('lower_k','upper_k','occupancy')]
    if not 250<lo<=up<330 or occ<0:raise Violation('invalid_comfort_or_occupancy')
    if not 200<obs[TEMP]<350 or not 278.15<=obs[COOL]<=308.15 or not 278.15<=obs[HEAT]<=308.15:
        raise Violation('invalid_effective_measurement')
    # Boundary handling NEVER excuses external-control mismatch.
    if command[CA] and not near(obs[COOL],command[COOL]):raise Violation('external_setpoint_readback_mismatch')
    t=origin+300;event=reference.event_pairs(t)
    expected=reference.pair(t);actual=(obs[HEAT],obs[COOL]);comfort=(lo,up)
    if event:
        old,new=event
        # Cooling under active external control is verified above. Native heating
        # remains checked, with the same unresolved-event policy.
        match_new=near(actual[0],new[0]) and (command[CA] or near(actual[1],new[1]))
        match_old=near(actual[0],old[0]) and (command[CA] or near(actual[1],old[1]))
        if match_new:
            return Result('VERIFIED_EVENT_NEW_REFERENCE','new_reference_observed_not_a_general_event_side_guarantee',
                new,actual,comfort,external_control_verified=bool(command[CA]),event_annotation='exact_native_event_new_values')
        if match_old:
            return Result('UNRESOLVED_BOUNDARY','old_reference_at_exact_event_requires_separate_diagnostic',
                new,actual,comfort,stop_production=True,external_control_verified=bool(command[CA]),event_annotation='exact_native_event_old_values')
        raise Violation('incoherent_or_unknown_native_pair_at_event')
    if not near(actual[0],expected[0]) or (not command[CA] and not near(actual[1],expected[1])):
        raise Violation('persistent_or_nonevent_native_reference_mismatch')
    reason='external_cooling_command_verified;native_heating_reference_verified' if command[CA] else 'source_native_reference_verified'
    if not command[CA] and not (near(actual[0],lo) and near(actual[1],up)):
        reason+=';comfort_signal_difference_recorded_separately'
    return Result('VERIFIED_REFERENCE',reason,expected,actual,comfort,external_control_verified=bool(command[CA]))


def precommand_guard(origin,command,current,current_forecast,age_s,native_status,reference=NativeReference()):
    """Keep actuator, occupancy, comfort, actual-heating gap and freshness checks.

    An unresolved/native-event origin cannot start a new external action. The
    original controller's cold/hot veto/dwell policy must remain separately in
    force; this function does not replace it or guarantee room comfort.
    """
    command_schema(command)
    finite(origin);finite(age_s)
    if not 0<=age_s<=30:raise Violation('stale_current_observation')
    if abs(finite(current.get('time'))-origin)>EPS_TIME or abs(finite(current_forecast.get('time'))-origin)>EPS_TIME:
        raise Violation('current_timestamp_mismatch')
    temp=finite(current.get(TEMP));heating=finite(current.get(HEAT))
    cooling=finite(current.get(COOL))
    for flag in FLAGS:
        finite(current.get(flag))
        if current[flag] not in (0,1):raise Violation('invalid_current_activation_flag')
    if any(current[f] for f in FLAGS if f!=CA):raise Violation('unexpected_active_noncooling_override')
    lo,up,occ=[finite(current_forecast.get(k)) for k in ('lower_k','upper_k','occupancy')]
    if (not 200<temp<350 or not 250<lo<=up<330 or occ<0
            or not 278.15<=heating<=308.15 or not 278.15<=cooling<=308.15):raise Violation('invalid_current_context')
    if native_status not in {'VERIFIED_REFERENCE','VERIFIED_EVENT_NEW_REFERENCE'}:
        raise Violation('unresolved_native_state_requires_stop_no_new_action')
    if command[CA]:
        if reference.event_pairs(origin):raise Violation('no_new_override_at_unqualified_native_event_origin')
        if occ<=0:raise Violation('unoccupied_override_forbidden')
        if not max(lo+.5,heating+.5,278.15)<=command[COOL]<=min(up,308.15):
            raise Violation('comfort_or_heating_deadband_violation')
    return True


def validate_boundary_followup_history(event_time,history,reference=NativeReference()):
    """Diagnostic-only native history check; never authorizes an extra advance.

    Old/new coherent values are distinguishable at the exact event. Every
    strictly later sample must match the new native reference; no 5-min grace.
    Require the ordinary first 30s communication sample and full 300s coverage.
    """
    finite(event_time)
    event=reference.event_pairs(event_time)
    if event is None:raise Violation('not_a_registered_native_event')
    ts=history.get('time',[])
    if not ts:raise Violation('missing_native_followup_history')
    for t in ts:finite(t)
    if ts[0]!=event_time or ts[-1]!=event_time+300 or event_time+30 not in ts:
        raise Violation('missing_event_or_followup_coverage')
    if any(b<a or b-a>30 for a,b in zip(ts,ts[1:])):raise Violation('native_history_gap_or_order')
    for name in (HEAT,COOL,TEMP,*FLAGS):
        if len(history.get(name,[]))!=len(ts):raise Violation('missing_native_history_signal')
        for x in history[name]:finite(x)
    old,new=event;sides=[]
    for i,t in enumerate(ts):
        if any(history[f][i]!=0 for f in FLAGS):raise Violation('external_activation_in_native_diagnostic')
        if not 200<history[TEMP][i]<350:raise Violation('invalid_native_temperature')
        pair=(history[HEAT][i],history[COOL][i])
        if abs(t-event_time)<=EPS_TIME:
            if all(near(a,b) for a,b in zip(pair,old)):sides.append('old')
            elif all(near(a,b) for a,b in zip(pair,new)):sides.append('new')
            else:raise Violation('unknown_event_pair')
        elif not all(near(a,b) for a,b in zip(pair,new)):
            raise Violation('native_mismatch_after_exact_event')
    if any(a=='new' and b=='old' for a,b in zip(sides,sides[1:])):
        raise Violation('event_pair_reverts_in_saved_order')
    return {'status':'FOLLOWUP_REFERENCE_VERIFIED_IN_DIAGNOSTIC',
        'event_samples_sides':sides,'first_positive_sample_time':next(t for t in ts if t>event_time+EPS_TIME),
        'production_continuation_authorized':False,'training_release':False}
