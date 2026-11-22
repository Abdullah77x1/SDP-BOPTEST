"""Exact six-arm manifest and origin-known duration plans."""
from copy import deepcopy
from . import HOME, VERSION
from stage4e_d2i_1.common import ROOT, read, require, digest, FMU_SHA, sha
from stage4e_d2i_1.manifest import policy_config, validate_initialization, origin_times
from stage4e_d0.plan import native_command, FLAG, SET

PILOT = ['B1V01_G174_NREF', 'B1V01_G174_C15']
DURATIONS = {'NREF': 0, 'C15': 900, 'C45': 2700}

def canonical_manifest():
    public = read(ROOT/'stage4e_d2_public/PUBLIC_DEVELOPMENT_VALIDATION_v1_0_0/RUN_CONFIGURATION_MANIFEST.json')['runs']
    runs = []
    for gid, archived, fold in [('D2_G174', 'D2_G174_N', 4), ('D2_G146', 'V2_Q01_N', 1)]:
        parent = next(r for r in public if r['run_id'] == archived)
        require(parent['partition'] == 'development', 'Parent is not development')
        for arm in DURATIONS:
            r = deepcopy(parent)
            r.update(run_id='B1V01_'+gid[3:]+'_'+arm, arm=arm, mode='native' if arm=='NREF' else 'scheduled_variation',
                     reused=False, source_run=None, source_group_id=gid, archived_native_run_id=archived,
                     outer_held_fold=fold, training_default=arm!='NREF')
            runs.append(r)
    policy = policy_config()
    # Retain raw/safety/energy values; old pulse/coverage floors are not B1 criteria.
    policy.pop('pulse_blocks_local_seconds', None)
    return dict(version=VERSION, purpose='production', campaign_id='B1V01', runs=runs, policy=policy,
                durations_s=DURATIONS, daily_start_s=39600, cooling_target_k=296.90,
                model=dict(version='0.9.0', name='bestest_air', FMU_sha256=FMU_SHA),
                response_temperature_k=.05, response_power_kw=.01, recovery_intervals=24,
                comparison_tolerance=1e-7, maximum_instances=6, maximum_advances=5184,
                pilot_run_ids=PILOT, pilot_maximum_advances=1728,
                dataset_construction_enabled=False, model_training_enabled=False)

def validate_manifest(m):
    require(m == canonical_manifest(), 'B1 manifest differs from frozen six-run design')
    for r in m['runs']:
        validate_initialization(r['initialization'], r['start'], r['end'])
        require(len(origin_times(r['start'], r['end']))==852, 'ML support changed')
    return True

def select_run(m, rid):
    validate_manifest(m)
    found = [r for r in m['runs'] if r['run_id']==rid]
    require(len(found)==1, 'Unknown B1 slot')
    return deepcopy(found[0])

def nominal(run, t, config=None):
    require(type(t) is int and run['start']<=t<run['end'] and (t-run['start'])%300==0,
            'Command outside fixed grid')
    duration = DURATIONS[run['arm']]
    command = native_command(); block = None
    if duration and 39600<=t%86400<39600+duration and t<run['end']-300:
        command.update({FLAG:1, SET:296.90})
        block = f"day{(t-run['start'])//86400}_B1_{run['arm']}"
    return dict(start=t, end=t+300, command=command, block_id=block)

def action_path(run, t, config=None):
    return [dict(nominal(run,s), known_at_sim=run['start'], source='frozen_nominal_plan')
            for s in range(t,min(t+1800,run['end']),300)]

def first_divergence(a,b):
    require((a['group_id'],a['start'],a['end'])==(b['group_id'],b['start'],b['end']), 'Unmatched dependencies')
    return next((t for t in range(a['start'],a['end'],300) if nominal(a,t)['command']!=nominal(b,t)['command']), a['end'])

def coverage(records, native, config, run):
    """Readbacks have already passed raw gates; explicit per-day delivered doses."""
    if run['arm']=='NREF':
        require(all(r['applied_command']==native_command() for r in records), 'Native override')
        return dict(requested_intervals=0, applied_intervals=0, episodes=[])
    bytime={r['start']:r for r in records}; episodes=[]; duration=DURATIONS[run['arm']]
    for day in range(3):
        start=run['start']+day*86400+39600; planned_release=start+duration
        window=[bytime[t] for t in range(start,planned_release,300) if t in bytime]
        applied=[r for r in window if r['applied_command'][FLAG]]
        activation=applied[0]['start'] if applied else None
        release=applied[-1]['end'] if applied else None
        recovery=[bytime[t] for t in range(release,release+7200,300) if t in bytime] if release else []
        released=release in bytime and bytime[release]['applied_command']==native_command() if release else False
        episodes.append(dict(day=day+1, requested_activation_s=start, requested_release_s=planned_release,
            requested_intervals=duration//300, applied_intervals=len(applied), activation_s=activation,
            release_s=release, applied_minutes=len(applied)*5, explicit_native_release=bool(released),
            effective_targets_k=sorted({r['applied_command'][SET] for r in applied}),
            veto_reasons=[r['reason'] for r in window if not r['applied_command'][FLAG]],
            recovery_native_intervals=sum(r['applied_command']==native_command() for r in recovery),
            complete=len(applied)==duration//300 and released and len(recovery)==24 and all(r['applied_command']==native_command() for r in recovery)))
    return dict(requested_intervals=3*duration//300, applied_intervals=sum(e['applied_intervals'] for e in episodes), episodes=episodes)
