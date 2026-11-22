"""Offline D2P acceptance definitions and public-group engineering audits.

This is not a protected evaluator. A full campaign decision requires future
custodian coverage attestations and dataset QA; no D2 PASS is returned here.
"""
import math
from .common import require
from stage4e_d0.plan import COOL,FAN,HEAT,integrate

LIMITS={
    'activity_threshold_kw':.01,'heating_transfer_threshold_W':100.,
    'aggregate_floor':{'occupied':100,'unoccupied':100,'hvac_active':50,'hvac_inactive':50,
        'cooling_active':50,'cooling_inactive':50,'verified_full_pulses':6,'verified_episodes':6,
        'verified_recoveries':6,'external_cooling_active':12},
    'minimum_distinct_levels':2,'minimum_level_intervals':6,
    'cooling_group_floor':{'cooling_active':50,'external_cooling_active':12,
        'verified_full_pulses':6,'verified_recoveries':6},
    'cooling_groups_required':4,'cooling_partition_groups':{'development':2,'validation':1,'protected_final_test':1},
    'heating_groups_required':4,'heating_active_intervals_per_group':50,
    'heating_partition_groups':{'development':1,'validation':1,'protected_final_test':1},
    'minimum_origins_per_intended_partition_stratum':50,
    'missing_coverage_decision':'INCONCLUSIVE_EXCITATION / CLAIM_LIMITED',
    'source':'STAGE4E_D2_QA_AND_BUDGET.md#Regime/excitation acceptance',
    'private_custodian_and_full_dataset_QA_required_for_campaign_decision':True}

def public_pair_audit(a,b,native_a,native_b,run,policy):
    require(run['partition']!='protected_final_test','Protected audit requires D2I-2 private custody')
    totals={k:a['coverage'][k]+b['coverage'][k] for k in LIMITS['aggregate_floor']}
    levels=set(a['coverage']['level_interval_counts'])|set(b['coverage']['level_interval_counts'])
    levels={k:a['coverage']['level_interval_counts'].get(k,0)+b['coverage']['level_interval_counts'].get(k,0) for k in levels}
    useful=sum(n>=6 for n in levels.values())>=2
    floor=all(totals[k]>=v for k,v in LIMITS['aggregate_floor'].items()) and useful
    cooling=all(totals[k]>=v for k,v in LIMITS['cooling_group_floor'].items()) and useful
    heating=0;heating_inactive=0
    for data in (native_a,native_b):
        # Integration uses source gas power times pinned efficiency, never endpoint W.
        for t in range(run['start'],run['end'],300):
            transfer=.9*integrate(data['time'],data[HEAT],t,t+300)/300
            heating+=transfer>100.;heating_inactive+=transfer<=100.
    return {'group_id':run['group_id'],'partition':run['partition'],'totals':totals,
        'level_interval_counts':levels,'aggregate_floor_met_within_pair':floor,
        'cooling_group_qualified':cooling,'heating_active_intervals':heating,
        'heating_inactive_intervals':heating_inactive,'heating_group_qualified':heating>=50,
        'heating_quantity':'0.9 * integrated source gas rate, model-specific thermal proxy',
        'campaign_decision':'NOT_ESTABLISHED_REQUIRES_ALL_FIXED_GROUPS_PRIVATE_CUSTODIAN_AND_DATASET_QA',
        'training_release':False}
