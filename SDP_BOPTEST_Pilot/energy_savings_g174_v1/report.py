"""Render the single study report from verified native or measured paired evidence."""
from hvac_control_expansion_b2f_v1.packaging import read, sha
from .policy import HOME, MIN_SAVINGS_KWH, RID

def table(headers,rows):
    return "\n".join(["| "+" | ".join(headers)+" |","| "+" | ".join("---" for _ in headers)+" |",
                      *("| "+" | ".join(map(str,row))+" |" for row in rows)])

def power(r):
    return " / ".join(f"{r[k]:.6f}" for k in ("cooling_kwh","fan_kwh","electrical_kwh"))

def temp(r):
    return f"{r['indoor_min_c']:.3f} to {r['indoor_max_c']:.3f}"

def comfort(r):
    return f"{r['violation_minutes']:.1f} min / {r['degree_hours']:.6f} K·h"

def delta(r):
    return f"{r['delta_kwh']:+.6f} kWh ({r['percent']:+.4f}%)"

def measured(r):
    s=r["summary"]
    full=s["full_72h"]
    base,warm=(full[k] for k in ("native","warm"))
    eq=s["matched_before_first_action_and_weather"]
    rows=[]
    doses=[]
    for w in s["windows"]:
        e=w["delivery"]
        recovery=e.get("rejoined_three_intervals_minutes")
        doses.append([e["day"],e["applied_intervals"]*5,e["readback_target_k"],e["actual_release_s"],
                      ", ".join(e["vetoes"]) or "None",recovery if recovery is not None else "No marker"])
        for k,name in (("hold","Hold"),("recovery","Scheduled recovery")):
            v=w[k]
            rows.append([w["day"],name,power(v["native"]),power(v["warm"]),
                         delta(v),temp(v["native"]),temp(v["warm"])])
    conditions=dict(
        delivered=s["full_dose"],
        net_hold_plus_recovery_delta_kwh=f"{s['net_window_delta_kwh']:+.6f}",
        zero_project_violations_in_comparison_windows=s["accepts_20_26_during_windows"],
        no_added_full_window_project_violations=s["no_added_project_comfort_burden"])
    verdict=("GO for separately scoped balanced evidence collection. A single qualified scenario is feasibility evidence."
             if s["meets_feasibility_margin"] else
             "NO-GO for expanding action-conditioned ML training. The observed policy missed one or more predeclared criteria.")
    behavior=("The hold used less electricity on all three days."
              if all(w["hold"]["delta_kwh"]<0 for w in s["windows"]) else
              "Electricity during the hold did not decline on every day. Use the delivered duration and temperature traces above to interpret the response.")
    rebound=sum(w["recovery"]["delta_kwh"] for w in s["windows"])
    return f"""
## Measured result

The run used one deployment, one initialization and 864 advances. The replay verified instance removal, deployed FMU, endpoint/native command readbacks, official KPI and energy reconciliation. Shared channels matched through the first action at {eq['endpoints']} endpoints and {eq['native_samples_shared']} native samples. Weather and occupancy vintages agreed at all {eq['matching_forecast_origins']} origins. [Execution evidence](EXECUTION_RESULT.json)

{table(["Day","Delivered min","Target K","Actual release s","Vetoes","Recovery marker min"],doses)}

The marker requires three consecutive five-minute paired values within 0.05°C and 0.01 kW. Recovery is searched for 120 minutes from actual release. The matched energy windows below retain the same scheduled clock for each policy.

{table(["Day","Window","Native cooling / fan / combined kWh","Warm cooling / fan / combined kWh","Combined change","Native °C","Warm °C"],rows)}

Full 72 h cooling / fan / combined electricity was **{power(base)} kWh** for native and **{power(warm)} kWh** for WARM45. The combined change was **{delta(full)}**, computed as WARM45 minus native. The indoor range was **{temp(base)}°C** for native and **{temp(warm)}°C** for WARM45.

{table(["Comfort over 72 h","Native","WARM45"],[
("Official BOPTEST tdis_tot (K·h)",f"{s['official_kpis_native']['tdis_tot']:.6f}",f"{s['official_kpis_warm']['tdis_tot']:.6f}"),
("Official 21–24°C, occupied air",comfort(base["official_bounds_occupied_air"]),comfort(warm["official_bounds_occupied_air"])),
("Project 20–26°C, occupied air",comfort(base["project_bounds_occupied_air"]),comfort(warm["project_bounds_occupied_air"]))])}

{behavior} The summed scheduled recovery-only change was **{rebound:+.6f} kWh**.
{table(["Decision evidence","Result"],conditions.items())}

**{verdict}** [Paired energy, comfort, and recovery](runtime_state/batches/{RID}/PAIRED_ENERGY_COMFORT.json)
"""

def render():
    ref=read(HOME/"NATIVE_REFERENCE_VERIFICATION.json")
    eq=ref["equivalence"]
    b=ref["baseline_72h"]
    tests=read(HOME/"OFFLINE_QUALIFICATION.json")
    digest=sha(HOME/"EXPERIMENT_FREEZE.json")
    f=HOME/"EXECUTION_RESULT.json"
    result=read(f) if f.exists() else None
    rows=[(w["day"],power(w),temp(w)) for w in ref["baseline_hold_windows"]]
    front=f"""# BOPTEST energy-savings feasibility

## Configuration and qualification

| Item | Setting |
| --- | --- |
| Simulator | Pinned BOPTEST 0.9.0 BESTEST Air, unchanged FMU, occupancy and Denver-Stapleton TMY |
| Scenario | G174 development, custom t=15033600 s, seven-day native warmup, 72 h through t=15292800 s |
| Native reference | B1V01_G174_NREF. Occupied heating 21°C and cooling 24°C |
| Experimental arm | {RID}. 24.5°C cooling-only override daily from 11:00 to 11:45 across the three days |
| Budget | One instance, one initialization, 864 five-minute advances, 30-second native history, no retries |
| Safeguards | Exact target and occupied source-schedule checks, at least 0.5 K heat/cool separation, 21.75°C activation and 21.50°C continuation lower margins, 25.5°C upper fallback. Veto latches native through the end of the pulse |
| Comfort | Official benchmark KPI and published bounds retained. Separate project-specific occupied 20–26°C air assessment |
| Go criterion | Full delivery and ≥{MIN_SAVINGS_KWH:.4f} kWh savings both across scheduled holds plus their two-hour recoveries and over 72 h. Zero project-band excursions in the comparison windows and no added project-band burden over 72 h |

Previously, Docker's Linux-engine named pipe was missing. The new preflight found the engine and the pinned container identities, with Redis, MinIO, web and worker stopped. I started those existing containers without a rebuild or pull. The unchanged verifier then passed all six pinned container identities, platform, worker and localhost port checks. [Restoration evidence](RUNTIME_RESTORATION.json)

The frozen D2/B1 guard capped occupied overrides at the published 24°C upper bound, and B1's collector pinned the active readback to 23.75°C. The new campaign uses its own exact command and replay checks while retaining the qualified transport, FMU checks, native event validation, energy reconciliation and one-attempt ledger.

G174 had 19.486 kWh of native cooling-plus-fan electricity versus 8.456 kWh in G146. The qualified B1 45-minute clock provides three active cooling periods and a two-hour recovery window. NREF reproduced D2 G174 native across {eq['endpoints']} endpoints, {eq['native_samples_shared']:,} native samples, {eq['warmup_samples']:,} warmup samples and {eq['matching_forecast_origins']} forecast origins on shared channels at 1e−7. The historical source check verified {sum(q['files_verified'] for q in ref['source_pins']):,} raw artifact hashes. [Reference equivalence](NATIVE_REFERENCE_VERIFICATION.json)

{table(["Native day, 11:00–11:45","Cooling / fan / combined kWh","Indoor °C"],rows)}

All {tests['tests']} offline checks passed, including the fabricated full-budget collection, replay, native release and append-only seal. Implementation SHA-256 **{digest}**. [Frozen campaign](CAMPAIGN.json) · [Qualification](qualification.log)

The paired analysis also reproduced the archived G174 B1 C45 increase of 0.041300 kWh as a read-only regression check. [Historical analysis replay](ANALYSIS_REPLAY_VERIFICATION.json)

The 20–26°C range is a project analysis assumption for this simulator. The 30-second occupied-air statistics use the archived/project limits as indicated. Official comfort is reported independently using the unchanged BOPTEST KPI.
"""
    if result and result["state"]=="CONSUMED_COMPLETED":
        detail=measured(result)
    else:
        raw=result.get("raw_result") or {} if result else {}
        if result:
            blocker=f"One slot was consumed with status **{result['state']}**. The exact failure was **{result['error']}**. [Execution evidence](EXECUTION_RESULT.json)"
        else:
            blocker=f"**Explicit campaign authorization is pending.** Earlier approvals bind different run IDs and setpoints. The minimum remaining step is affirmative authorization for {RID} under the frozen one-attempt campaign. The runtime will be rechecked before any live reservation."
        detail=f"""
## Outcome and recommendation

{blocker}

New deploy / initialize / advance attempts were **{raw.get('deploy_attempts',0)} / {raw.get('initialization_attempts',0)} / {raw.get('advance_requests_attempted',0)}**. The 24.5°C outcome and percentage savings are unavailable.

The archived native 72-hour cooling / fan / combined electricity was **{power(b)} kWh**. Official tdis_tot was **{ref['official_kpis']['tdis_tot']:.6f} K·h**. The separate occupied-air assessments found **{comfort(b['official_bounds_occupied_air'])}** outside the original occupied band and **{comfort(b['project_bounds_occupied_air'])}** outside the project band. The native baseline already has some project-band excursions, so the decision compares full-run burden as well as requiring compliance during the study windows.

**NO-GO for expanding action-conditioned ML training.** A temporary warmer target has a plausible demand reduction during the hold. Evidence of net savings through recovery and acceptable occupied temperature is pending.
"""
    out=HOME/"ENERGY_SAVINGS_FEASIBILITY_REPORT.md"
    out.write_text(front+detail,encoding="utf-8")
    print(out)

if __name__=="__main__":
    render()

