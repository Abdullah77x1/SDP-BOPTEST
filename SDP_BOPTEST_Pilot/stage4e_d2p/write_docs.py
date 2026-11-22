"""Generate planning tables/inventory from inspected source evidence only."""
from .audit import OUT,ROOT,read

def put(path,text):
    with path.open('x',encoding='utf-8') as f:f.write(text)
def main():
    plan=read(OUT/'COLLECTION_AND_PARTITION_PLAN.json');budget=read(OUT/'BUDGET_CALCULATIONS.json')
    rows=['| Start day | Calendar bin | Partition | Reuse/new | Outdoor min–max °C | Horizontal solar kWh/m² |',
          '|---:|---|---|---|---:|---:|']
    for g in plan['recommended']:
        w=g['public_weather_only'];rows.append(f"| {g['start_day_offset']} | {g['calendar_regime_bin']} | {g['partition']} | {'reuse pair' if g['new_instances']==0 else 'new pair'} | {w['outdoor_min_c']:.1f}–{w['outdoor_max_c']:.1f} | {w['global_solar_kwh_m2']:.2f} |")
    sizes=['| Plan | Total temporal groups | Total/new runs | New advances | Projected total/new joint origins |',
           '|---|---:|---:|---:|---:|']
    costs=['| Plan | Total endpoints / scored intervals | Native scored samples | Baseline new runtime min | Reserved new runtime min | Baseline new raw GB / 3× reserve GB | Cumulative baseline preview MB |',
           '|---|---:|---:|---:|---:|---:|---:|']
    for b in budget['plans']:
        sizes.append(f"| {b['plan']} | {b['temporal_dependency_groups_total']} | {b['runs_total']} / {b['new_simulation_instances']} | {b['new_scored_advances']:,} | {b['projected_joint_origins']:,} / {b['new_joint_origins']:,} |")
        lo,hi=b['planning_simulation_minutes_range']
        costs.append(f"| {b['plan']} | {b['cumulative_endpoint_rows']:,} / {b['cumulative_scored_intervals']:,} | {b['cumulative_native_scored_samples']:,} | {b['baseline_new_simulation_minutes']:.1f} | {lo:.0f}–{hi:.0f} | {b['baseline_new_raw_bytes']/1e9:.3f} / {b['raw_reserve_bytes_3x']/1e9:.3f} | {b['baseline_preview_bytes_total']/1e6:.1f} |")
    for filename,replacements in {'STAGE4E_D2_COLLECTION_PLAN.md':{'<!-- RECOMMENDED_WINDOW_TABLE -->':'\n'.join(rows),'<!-- PLAN_SIZE_TABLE -->':'\n'.join(sizes)},
        'STAGE4E_D2_QA_AND_BUDGET.md':{'<!-- BUDGET_TABLE -->':'\n'.join(costs),'Pair/casual integrity':'Pair/causal integrity'}}.items():
        p=ROOT/filename;text=p.read_text(encoding='utf-8')
        for old,new in replacements.items():assert old in text;text=text.replace(old,new)
        p.write_text(text,encoding='utf-8')
    inv=read(OUT/'VARIABLE_INVENTORY.json')
    text=r'''# Stage 4E-D2 variable inventory and feature audit

**PLANNING ONLY. No new simulator observations, fitted parameters, supervised dataset or feature-performance ranking is generated.** Machine-readable per-variable units, source, status, availability, purpose, ML/RC/optimization relevance, missing-data limits and leakage risks are in `stage4e_d2p/VARIABLE_INVENTORY.json`. Static specifications are separately in `BUILDING_SPECIFICATIONS.json`.

## Findings and classification

The actual runtime catalog has **31 measurements, eight effective input/activation fields and 36 forecast fields**. All endpoint fields have saved project runtime values; only five forecast channels have qualified as-issued values. The other 31 are metadata/source-supported, not runtime-value verified. A local XML/internal state or a source variable name does not make it a public API measurement.

The **168 D1P features are an expanded set of lags/encodings/boundaries, not 168 independent sensors**. Their audit found **30 constant columns**: actual and issued heating/fan/supply override flags at five lags, consistent with the cooling-only policy. Four exact duplicate-vector groups occur in D1P: one 30-column all-zero group and three pairs of cooling activation readback versus prior issued-command lags. This reflects timing/semantics, not independent information. Combined cooling+fan history is also mathematically redundant with its components.

Keep original preview/schema intact for comparison. For future ML, propose source-based removal of invariant noncooling flags from the learned matrix while retaining audit fields; any empirical variance filtering, scaling or feature choice must use development only. Do not rank feature usefulness from counts/variance, fit models here or inspect protected values to select inputs. Begin with temperature/history and add separately labeled causal groups; optional RH, CO2 and flow remain ablation candidates, not mandatory inputs.

### A. Dynamic observations and actions

Actual temperature, measured outdoor/solar/RH, gas/cooling/fan power, flow, CO2, lighting/plug power and effective control readings exist in saved endpoints. Occupancy is a known forecast schedule, not a people sensor. Actual issued current/past commands differ from endpoint effective readbacks: an origin command acts on the following interval; its future readback cannot enter current inputs. API `_u` in a request is an external command, but response/history `_u` exposes the effective FMU output. A supply-temperature setpoint is not an independent supply-air measurement.

Electrical energy/demand comes from ordered native power integration, not endpoint watts. Cooling thermal transfer is not electrical consumption. Model-specific thermal proxies are possible only because the selected XML/source fixes COP=3 and eff=0.9; the exact boundary/limitations are in the RC report. No thermal series is produced here.

### B. Temporal, historical and known information

Existing lags 0/5/10/15/30 min, trailing five-minute means, time-of-day and as-issued schedules/forecasts are causal only with complete support and receipt ordering. Benchmark day may identify the weather group; it should be separately ablated. Day-of-week is **not** currently qualified as a meaningful operating variable: the model repeats occupancy/loads every day, and an arbitrary Gregorian label must not manufacture a weekday regime. A documented TMY Sunday anchor would be an optional assumed benchmark calendar only.

Trailing means and backward temperature slopes are useful candidate derivatives if exact windows are preregistered; no centered smoothing, future differences, whole-run normalization or future realized control is allowed. Retain a measurement/history-only track and a distinct perfect-benchmark-forecast track. BOPTEST temperature/solar uncertainty options are source-supported but not qualified in this project and do not create a new independent physical weather trajectory.

### C. Constant specifications and unknown parameters

Geometry, heavy-wall/slab/roof materials, window dimensions/layers, source COP/eff, design flow/pressure, ground boundary and internal-load assumptions are recovered from selected-FMU XML and Modelica source. Keep these in metadata, not repeated 168-style predictors. Distinguish XML starts/local constants, source documentation and derived geometry/material properties. Material-only resistance/capacity is not a calibrated whole-zone R/C. Effective RC parameters, solar aperture and finite rated ideal-coil capacity remain unknown; no estimate or fictitious zero is supplied.

### D. Simulation metadata

Preserve actual case/scenario/custom-window annotation, start/end/warmup, run and dependency-component IDs, controller policy/proposal hash, simulator/FMU/image/executable/dependency identities, issue/valid/receipt clocks, seed (null/NOT_APPLICABLE for deterministic native runs), initialization identity and actual partition/custody. Run IDs, future target clocks, later resolutions and protected membership are not automatically inputs. The new handoff must retain the planned partition rather than hardcode development.

### E. Targets

Preserve eight targets: indoor °C at +300/+600/+900/+1800 s, and average cooling+fan kW over [t+h−300,t+h]. These are final five-minute intervals, not instantaneous watts or whole-horizon averages. Thermal/gas proxies do not replace these labels. Target values and future measured state never enter origin features.

## Proposed additions and exclusions

1. **Thermal RC sidecar:** source-derived cooling-removed, heating-added and signed net airside thermal proxies from native cooling/gas power, clearly labeled model-specific, not direct sensible meters. No additional physical output is needed, but units/source identity must be verified in the new data pipeline.
2. **Passive known-gain forecasts:** InternalGainsCon/Rad/Lat (W), plus wind speed/direction, pressure, direct/diffuse solar and RH. The proposed common new-arm request has 14 fields including the original five. Additional values require a separately authorized preflight; do not silently substitute forecasts for actual internal gains. Reused old pairs retain honest optional-field unavailability.
3. **Already exposed weather measurements:** wind, pressure, dew/wet-bulb and radiation/angles can be added to an optional versioned feature dictionary if justified. They are accessible, not absent, but not all are useful. Constant longitude/latitude and the 77777 m cloud-ceiling sentinel should not be learned as normal dynamic values; preserve original raw records and explicit quality/availability flags.
4. **Source internal-gain proxy:** actual lighting/plug sensible components plus 73 W × scheduled occupancy can provide approximate sensible forcing; event-time schedule/native mismatch and radiant/storage effects prevent a blanket exact-measurement claim.
5. **Not accessible as API observations:** indoor RH/humidity ratio, measured supply-air temperature, direct zone sensible/latent HVAC load and wall/soil state sensors. Do not invent them, infer true thermal power from rated airflow, or change the FMU to make this inventory appear complete. A future different-output model is a different qualified scope.

## Exact 168-feature audit

All rows below refer only to the exposed D1P development preview. “Constant” means constant in that preview, not proof of invariance in another policy/building. Full source/availability/purpose/relevance/risk fields are in the JSON inventory. Category A is current dynamic information; B is lags, historical derivatives, calendar or known boundary information.

| Existing column | Unit | Category | D1P unique values | Constant | Source |
|---|---|---|---:|---|---|
'''
    for row in inv['audited_D1P_features']:
        text+=f"| `{row['name']}` | {row['unit']} | {'A' if row['category']=='A_DYNAMIC' else 'B'} | {row['D1P_unique_values']} | {'yes' if row['constant_in_D1P_only'] else 'no'} | `{row['source']}` |\n"
    text+='''
## Complete actual API catalog

RUNTIME_VERIFIED means actual saved endpoint/forecast values exist; metadata-only channels are not promoted to that status. Input entries represent both actuator request schema and effective readback semantics. A missing metadata unit for a Boolean flag is retained; its semantic values are 0/1.

| API name | Kind | Source unit | Evidence status |
|---|---|---|---|
'''
    for row in inv['API_catalog']:text+=f"| `{row['name']}` | {row['kind']} | {row['unit'] if row['unit'] is not None else 'metadata undeclared; flag 0/1 where applicable'} | {row['status']} |\n"
    text+='''
## New proxies, constants, metadata and target definitions

The JSON inventory additionally contains 125 explicit entries for proposed derived/assumed quantities, all 66 inspected constant specifications, unknown/future RC parameters, 27 metadata columns, eight targets and additional provenance requirements. Each has unit, source, status, availability, purpose, relevance, missing-data and leakage fields. Null/unknown values are not numerical estimates. No static specification is appended to an ML matrix here, and no optional metadata-only channel is called runtime-verified.
'''
    put(ROOT/'STAGE4E_D2_VARIABLE_INVENTORY.md',text)
    print('Generated six planning documents and exact variable appendices.')

if __name__=='__main__':main()
