"""Frozen G174 warmer-setpoint study. Native controller and official bounds stay intact."""
from copy import deepcopy
from pathlib import Path

from hvac_control_expansion_v1.campaign import canonical_manifest, validate_manifest as check_b1
from stage4e_d0.plan import FLAGS, FLAG, LOW, OCC, SET, TEMP, UP, native_command
from stage4e_d1r.proposed_validation import command_schema
from stage4e_d1_v2.validation import REFERENCE, command_guard as check_standard_command
from stage4e_d2i_1.common import ROOT, digest, read, require

HOME = Path(__file__).resolve().parent
VERSION = "SDP_ENERGY_G174_1.0.0"
RID = "ESV01_G174_WARM45"
REFERENCE_ID = "B1V01_G174_NREF"
ARCHIVE = ROOT / "hvac_control_expansion_v1/runtime_state/batches/B1_G174_INITIAL_PILOT" / REFERENCE_ID
ARCHIVED_D2 = ROOT / "stage4e_d2_prep02/runtime_state/batches/D2_PAIR02_G174_20261115_01/D2_G174_N"
TARGET = 297.65
ON = 39600
DURATION = 2700
PROJECT_LO = 293.15
PROJECT_HI = 299.15
PROJECT_HOT_FALLBACK = 298.65
RECOVERY = 7200
MIN_SAVINGS_KWH = .0225  # 10 W, the B1 meaningful response marker, over 3 x 45 min

def definitions():
    b1 = read(ROOT / "hvac_control_expansion_v1/campaign_manifest.json")
    check_b1(b1)
    require(b1 == canonical_manifest(), "Canonical B1 source drift")
    native = deepcopy(next(x for x in b1["runs"] if x["run_id"] == REFERENCE_ID))
    require(native["group_id"] == "D2_G174" and native["outer_held_fold"] == 4
            and native["partition"] == native["dataset_partition"] == "development"
            and native["initialization"] == dict(method="custom",start_time=15033600,
                                                  warmup_period=604800,scenario_key=None)
            and (native["start"],native["end"],native["warmup_start"],native["maximum_advances"])
                 == (15033600,15292800,14428800,864), "G174 reference mismatch")
    run = dict(native,run_id=RID,arm="WARM45",mode="scheduled_variation",training_default=False)
    m = dict(version=VERSION, purpose="production", campaign_id="ESV01", runs=[run],
             reference=native, model=b1["model"], policy=b1["policy"], official_occupied_bounds_k=[294.15,297.15],
             project_occupied_bounds_k=[PROJECT_LO,PROJECT_HI], hot_fallback_k=PROJECT_HOT_FALLBACK,
             daily_start_s=ON, duration_s=DURATION, recovery_s=RECOVERY, cooling_target_k=TARGET,
             minimum_net_savings_kwh=MIN_SAVINGS_KWH, maximum_instances=1,
             maximum_initializations=1, maximum_advances=864, dataset_construction_enabled=False,
             model_training_enabled=False, automatic_retries=False)
    return m,run,native

def validate_manifest(m):
    require(m == definitions()[0], "Exact frozen G174 campaign required")

def nominal(run,t,config=None):
    require(type(t) is int and run["start"] <= t < run["end"] and t%300==0, "Off-grid command")
    cmd = native_command()
    block = None
    if ON <= t%86400 < ON + DURATION:
        cmd.update({FLAG:1,SET:TARGET})
        block = f"day{(t-run['start'])//86400}_WARM45"
    return dict(start=t,end=t+300,command=cmd,block_id=block)

def action_path(run,t,config=None):
    return [dict(nominal(run,s),known_at_sim=run["start"],source="frozen_nominal_plan")
            for s in range(t,min(t+1800,run["end"]),300)]

def verify_vintage(boundary,t):
    require(boundary["time"]==t and abs(boundary[LOW]-294.15)<=1e-5 and abs(boundary[UP]-297.15)<=1e-5,
            "Official occupied benchmark bounds drifted")

def command_guard(command,current,boundary,t,age):
    if not command.get(FLAG):
        return check_standard_command(command,current,boundary,t,age)
    # Check the qualified context, age, readback and status rules for every request.
    check_standard_command(native_command(),current,boundary,t,age)
    command_schema(command)
    require(command=={**native_command(),FLAG:1,SET:TARGET}, "One exact authorized cooling target")
    require(ON <= t%86400 < ON+DURATION and current["time"]==t and t%300==0
            and REFERENCE.event_pairs(t) is None, "Unexpected intervention time")
    verify_vintage(boundary,t)
    require(boundary[OCC]>0 and abs(current["con_oveTSetHea_u"]-294.15)<=1e-5, "Occupied heating schedule mismatch")
    require(TARGET-current["con_oveTSetHea_u"]>=.5 and PROJECT_LO+.5<=TARGET<=PROJECT_HI,
            "Heating/cooling deadband or project bounds failed")
    require(294.65<=current[TEMP]<PROJECT_HOT_FALLBACK, "Measured-temperature margin exhausted")
    return True

class Safety:
    """Restore native at release or at the first veto, latched to the end of that pulse."""
    def __init__(self,config):
        self.block=None
        self.vetoed=False
        self.active=False

    def decide(self,proposal,current,boundary,age):
        t=proposal["start"]
        check_standard_command(native_command(),current,boundary,t,age)
        if self.block!=proposal["block_id"]:
            self.block=proposal["block_id"]
            self.vetoed=False
            self.active=False
        request=proposal["command"]
        if not request[FLAG]:
            require(request==native_command() and self.block is None,"Invalid native plan")
            return native_command(),"scheduled_native_or_final_release"
        require(request=={**native_command(),FLAG:1,SET:TARGET} and self.block is not None
                and ON<=t%86400<ON+DURATION and t%300==0,"Unexpected proposed action")
        verify_vintage(boundary,t)
        if self.vetoed:
            return native_command(),"latched_veto_rest_of_pulse"
        reason=None
        if boundary[OCC]<=0:
            reason="unoccupied_veto"
        elif abs(current["con_oveTSetHea_u"]-294.15)>1e-5:
            reason="native_heating_readback_veto"
        elif current[TEMP]>=PROJECT_HOT_FALLBACK:
            reason="project_upper_margin_native_fallback"
        elif current[TEMP] < (294.65 if self.active else 294.90):
            reason="cold_margin_veto"
        if reason:
            self.vetoed=True
            self.active=False
            return native_command(),reason
        command_guard(request,current,boundary,t,age)
        self.active=True
        return dict(request),"scheduled_warmer_pulse_applied"

def coverage(records,native,config,run):
    by_time={r["start"]:r for r in records}
    episodes=[]
    for day in range(3):
        t=run["start"]+day*86400+ON
        requested=[by_time[s] for s in range(t,t+DURATION,300)]
        active=[r for r in requested if r["applied_command"][FLAG]]
        released=active[-1]["end"] if active else None
        recovery=[by_time[s] for s in range(released,released+RECOVERY,300)] if released else []
        require(all(r["applied_command"]==native_command() for r in recovery),"Non-native recovery")
        episodes.append(dict(day=day+1,scheduled_start_s=t,scheduled_release_s=t+DURATION,
                             requested_intervals=len(requested),applied_intervals=len(active),
                             actual_activation_s=active[0]["start"] if active else None,actual_release_s=released,
                             readback_target_k=sorted({r["applied_command"][SET] for r in active}),
                             vetoes=[r["reason"] for r in requested if not r["applied_command"][FLAG]],
                             native_recovery_intervals=len(recovery)))
    require(sum(x["requested_intervals"] for x in episodes)==27,"Requested pulse count drift")
    require(sum(x["applied_intervals"] for x in episodes)==sum(r["applied_command"][FLAG] for r in records),
            "Override outside scheduled intervals")
    return dict(episodes=episodes,requested_intervals=27,
                applied_intervals=sum(x["applied_intervals"] for x in episodes))


