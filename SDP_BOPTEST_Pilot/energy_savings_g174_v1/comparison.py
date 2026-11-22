"""Read-only native equivalence and paired energy, comfort and recovery calculations."""
import json

from core import integrate
from hvac_control_expansion_b2f_v1.packaging import chain, read, require, sha
from hvac_control_expansion_v1.comparison import compare_endpoints
from stage4e_d0.plan import FLAGS, TEMP, COOL, HEAT, FAN, energy_audit, native_command
from stage4e_d1_v2.validation import HISTORY_POINTS
from .policy import (ARCHIVE, ARCHIVED_D2, ON, DURATION, RECOVERY, PROJECT_LO, PROJECT_HI,
                     MIN_SAVINGS_KWH, definitions)

REFERENCE_D2_MANIFEST = "e1ab52385410c413a646102aa208ed670e1dffb2a82064e747cf552a19249c4a"
REFERENCE_B1_MANIFEST = "d88055986016c8a99d567d0e3cc9f6f2577d58cca07c86abf0819ca90826e044"

def lines(path):
    return [json.loads(line) for line in path.read_text().splitlines()]

def source_verify(path,pin):
    file=path/"ARTIFACT_MANIFEST.json"
    require(sha(file)==pin,"Historical manifest hash drift")
    files=read(file)["files"]
    for name,pinned in files.items():
        object_path=(path/name).resolve()
        require(object_path.is_relative_to(path.resolve()) and sha(object_path)==pinned,
                f"Historical source artifact drift: {name}")
    state=read(path/"RUN_COMPLETED.json")
    require(state["classification"]=="PASS_VALID_RAW" and not state.get("data_is_fabricated",False)
            and state["unresolved_events"]==0 and state["cleanup"]=="STOP_ACK_AND_REMOVAL_VERIFIED",
            "Historical raw validity or cleanup is unverified")
    return dict(manifest_sha256=pin,files_verified=len(files),receipt_chain=chain(path/"receipt_order.jsonl"))

def check_equivalence(a,b,run,through,*,whole=False):
    result=compare_endpoints(read(a/"endpoints.json"),read(b/"endpoints.json"),through,common_only=True)
    a_w,b_w=[read(p/"NATIVE_WARMUP_HISTORY.json") for p in (a,b)]
    require(a_w["time"]==b_w["time"] and a_w["time"][0]==run["warmup_start"]
            and a_w["time"][-1]==run["start"],"Warmup clocks differ")
    for field in (COOL,FAN,HEAT,*FLAGS):
        require(all(abs(v-w)<=1e-7 for v,w in zip(a_w[field],b_w[field],strict=True)),"Warmup channels differ")
    a_n,b_n=[read(p/"whole_native_results.json") for p in (a,b)]
    require(a_n["time"]==b_n["time"],"Native time grid changed")
    end=a_n["time"].index(through)+1
    for k in HISTORY_POINTS:
        require(all(abs(v-w)<=1e-7 for v,w in zip(a_n[k][:end],b_n[k][:end],strict=True)),
                f"Native history mismatch in {k} before first action")
    for i in range(864):
        forecast_a,forecast_b=[read(p/f"forecast_{i:04d}.json") for p in (a,b)]
        require(forecast_a["issued_at_sim"]==forecast_b["issued_at_sim"]==run["start"]+300*i,
                "As-issued forecast clock changed")
        x,y=forecast_a["data"],forecast_b["data"]
        require({"time","LowerSetp[1]","UpperSetp[1]","Occupancy[1]","TDryBul","HGloHor"}<=x.keys() & y.keys(),
                "Missing core policies/weather forecast")
        require(all(len(x[k])==len(y[k]) and all(abs(v-w)<=1e-7 for v,w in zip(x[k],y[k]))
                    for k in x.keys() & y.keys()),f"As-issued forecast drift at origin {i}")
    return dict(**result,warmup_samples=len(a_w["time"]),native_samples_shared=end,
                matching_forecast_origins=864,full_native_reproduction=whole)

def energy(n,start,end):
    return [integrate(n["time"],n[key],start,end)/3600000 for key in (COOL,FAN)]

def comfort(n,steps,start,end,limits=None):
    rows={r["start"]:r["current_boundary"] for r in steps}
    temps=n[TEMP];times=n["time"]
    count=occupied=0;area=peak=0.
    for a,b,ta,tb in zip(times,times[1:],temps,temps[1:]):
        if a<start or b>end:
            continue
        bound=rows[a-(a%300)]
        if bound["Occupancy[1]"]<=0:
            continue
        lo,hi=limits if limits else (bound["LowerSetp[1]"],bound["UpperSetp[1]"])
        va,vb=[max(0.,lo-x,x-hi) for x in (ta,tb)]
        occupied+=b-a
        count+=(b-a)*int(va>1e-7)
        area+=(b-a)*(va+vb)/7200.
        peak=max(peak,va,vb)
    return dict(occupied_minutes=occupied/60.,violation_minutes=count/60.,degree_hours=area,peak_excursion_k=peak)

def metrics(n,steps,start,end):
    i=n["time"].index(start);j=n["time"].index(end)+1
    cool,fan=energy(n,start,end)
    return dict(cooling_kwh=cool,fan_kwh=fan,electrical_kwh=cool+fan,
                indoor_min_c=min(n[TEMP][i:j])-273.15,indoor_max_c=max(n[TEMP][i:j])-273.15,
                official_bounds_occupied_air=comfort(n,steps,start,end),
                project_bounds_occupied_air=comfort(n,steps,start,end,(PROJECT_LO,PROJECT_HI)))

def verify_native():
    m,r,nref=definitions()
    pins=[source_verify(ARCHIVE,REFERENCE_B1_MANIFEST),source_verify(ARCHIVED_D2,REFERENCE_D2_MANIFEST)]
    for d,rid in ((ARCHIVE,nref["run_id"]),(ARCHIVED_D2,"D2_G174_N")):
        started=read(d/"ATTEMPT_STARTED.json")["run"]
        require(started["run_id"]==rid and all(started[k]==nref[k] for k in (
            "group_id","partition","dataset_partition","mode","start","end","warmup_start","step","native_step",
            "initialization","maximum_advances","seed","solar_uncertainty","temperature_uncertainty")),
            "Archived native scenario or initialization drift")
        require(read(d/"DEPLOYED_FMU_IDENTITY.json")["sha256"]==m["model"]["FMU_sha256"],"Reference FMU mismatch")
        require(all(row["applied_command"]==native_command() for row in lines(d/"steps.jsonl")),"Native source has intervention")
    matched=check_equivalence(ARCHIVE,ARCHIVED_D2,nref,nref["end"],whole=True)
    native=read(ARCHIVE/"whole_native_results.json");steps=lines(ARCHIVE/"steps.jsonl")
    require(energy_audit(native,nref["start"],nref["end"],read(ARCHIVE/"official_kpis.json"),m["policy"])
            ==read(ARCHIVE/"energy_audit.json"),"Archived official energy reconciliation changed")
    windows=[]
    for d in range(3):
        t=nref["start"]+d*86400+ON
        sample=metrics(native,steps,t,t+DURATION)
        require(sample["cooling_kwh"]>.1,"Chosen daily window lacks cooling exposure")
        windows.append(dict(day=d+1,start_s=t,release_s=t+DURATION,**sample))
    arch_measures=metrics(native,steps,nref["start"],nref["end"])
    return dict(status="PASS_ARCHIVED_NATIVE_EQUIVALENCE",reference_id=nref["run_id"],native_path=str(ARCHIVE),
                source_pins=pins,equivalence=matched,baseline_72h=arch_measures,official_kpis=read(ARCHIVE/"official_kpis.json"),
                baseline_hold_windows=windows)

def summarize(run_path,run,raw_validation):
    n0,n1=[read(p/"whole_native_results.json") for p in (ARCHIVE,run_path)]
    st0,st1=[lines(p/"steps.jsonl") for p in (ARCHIVE,run_path)]
    step_table={r["start"]:r for r in st1}
    episodes=raw_validation["coverage"]["episodes"]

    def paired(a,b):
        ref=metrics(n0,st0,a,b);exp=metrics(n1,st1,a,b)
        dv=exp["electrical_kwh"]-ref["electrical_kwh"]
        return dict(start_s=a,end_s=b,native=ref,warm=exp,delta_kwh=dv,
                    percent=100*dv/ref["electrical_kwh"] if ref["electrical_kwh"] else None)

    windows=[]
    for e in episodes:
        a=e["scheduled_start_s"];b=e["scheduled_release_s"]
        proof=dict(e)
        release=e["actual_release_s"]
        if release is not None:
            n_time=n0["time"]
            recovery=[]
            for t in range(release,release+RECOVERY+1,300):
                i=n_time.index(t)
                ref=energy(n0,t-300,t);w=energy(n1,t-300,t)
                ok=(abs(n0[TEMP][i]-n1[TEMP][i])<=.05
                    and abs(sum(ref)-sum(w))*12<=.01)
                recovery.append(ok)
            rejoined=next((5*i for i in range(len(recovery)-2) if all(recovery[i:i+3])),None)
            proof.update(native_release_command=step_table[release]["applied_command"]==native_command(),
                         rejoined_three_intervals_minutes=rejoined,
                         actual_release_recovery=paired(release,release+RECOVERY))
        windows.append(dict(day=e["day"],delivery=proof,hold=paired(a,b),recovery=paired(b,b+RECOVERY),
                            combined=paired(a,b+RECOVERY)))
    full=paired(run["start"],run["end"])
    warm_26=full["warm"]["project_bounds_occupied_air"];ref_26=full["native"]["project_bounds_occupied_air"]
    # Compare absolute compliance during the common evidence window and whole-run incremental comfort.
    warm_ok=all(w["combined"]["warm"]["project_bounds_occupied_air"]["violation_minutes"]==0
                and w["combined"]["warm"]["project_bounds_occupied_air"]["peak_excursion_k"]<=1e-7 for w in windows)
    no_added=warm_26["degree_hours"]<=ref_26["degree_hours"]+1e-7 and warm_26["violation_minutes"]<=ref_26["violation_minutes"]
    delivered=raw_validation["coverage"]["applied_intervals"]>0
    window_energy_delta=sum(w["combined"]["delta_kwh"] for w in windows)
    substantial=full["delta_kwh"]<=-MIN_SAVINGS_KWH and window_energy_delta<=-MIN_SAVINGS_KWH
    full_dose=raw_validation["coverage"]["applied_intervals"]==27
    meets=warm_ok and no_added and full_dose and substantial
    compared_to=check_equivalence(ARCHIVE,run_path,run,run["start"]+ON)
    return dict(run_id=run["run_id"],matched_before_first_action_and_weather=compared_to,full_72h=full,
                windows=windows,net_window_delta_kwh=window_energy_delta,minimum_net_savings_kwh=MIN_SAVINGS_KWH,
                official_kpis_native=read(ARCHIVE/"official_kpis.json"),official_kpis_warm=read(run_path/"official_kpis.json"),
                delivered=delivered,full_dose=full_dose,
                accepts_20_26_during_windows=warm_ok,no_added_project_comfort_burden=no_added,
                meets_feasibility_margin=meets)

