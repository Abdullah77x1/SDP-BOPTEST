"""DEVELOPMENT_ONLY preview documentation; does not edit observations/targets."""
import csv,json
from .build import HOME,PACKAGE,STATUS
from stage4e_d1_v2.runner import ROOT,read,save_new

def write(name,text):
    with (PACKAGE/name).open('x',encoding='utf-8') as f:f.write(text)

def main():
    d=read(PACKAGE/'DATA_DICTIONARY.json')
    with (PACKAGE/'DEVELOPMENT_ONLY_OBSERVATIONAL.csv').open(newline='',encoding='utf-8') as f:cols=next(csv.reader(f))
    descriptions={
        'dataset_status':('string','status','Must remain DEVELOPMENT_ONLY_PREVIEW.'),
        'evaluation_status':('string','status','NON_FINAL_EVALUATION; no independent final test partition.'),
        'release_status':('string','status','Local review only; sharing/training approval has not been granted.'),
        'row_id':('string','identifier','Unique run_id:origin_sim_s. Never an input feature.'),
        'run_id':('string','identifier','One of four V2_Qxx qualified arms.'),
        'scenario':('string','provenance','typical_cool_day or typical_heat_day.'),
        'weather_id':('string','provenance','bestest_air_v090_weather; same source weather file, distinct windows.'),
        'group_id':('string','group','Matched weather/initialization group; keep both paired arms together.'),
        'control_policy':('string','provenance','native or scheduled_variation; metadata, not automatically a model feature.'),
        'partition':('string','scope','development for every row. No train/test split is supplied.'),
        'origin_sim_s':('int64','simulation seconds','Prediction origin; not UTC or a real calendar date.'),
        'support_start_sim_s':('int64','simulation seconds','origin-2100; earliest required past electrical support.'),
        'support_end_sim_s':('int64','simulation seconds','origin+1800; latest label endpoint.'),
        'initialization_id':('string','provenance','Unique fresh initialization per arm; warmup values are not examples.'),
        'origin_cutoff_order':('int64','per-run journal order','Known information cutoff; not an input feature.')}
    for col in cols:
        if col in d['columns']:continue
        if col in descriptions:typ,unit,meaning=descriptions[col]
        elif col.startswith('target_time_'):typ,unit,meaning='int64','simulation seconds','Actual target endpoint time origin+horizon; label provenance, not input.'
        elif col.startswith('electric_label_interval_start_'):typ,unit,meaning='int64','simulation seconds','Start of final five-minute label interval origin+horizon-300.'
        elif col.startswith('electric_label_interval_end_'):typ,unit,meaning='int64','simulation seconds','End of final five-minute label interval origin+horizon.'
        else:raise ValueError(col)
        d['columns'][col]={'role':'metadata_not_feature','dtype':typ,'unit':unit,'group':'metadata','definition':meaning,'source':'qualified run identity/clock/journal'}
    d['columns']={col:d['columns'][col] for col in cols}
    d['action_eligibility_columns']={**{k:{'role':'status','dtype':'string'} for k in STATUS},
        'row_id':{'role':'join_key','dtype':'string'},'run_id':{'role':'provenance','dtype':'string'},
        'origin_sim_s':{'role':'provenance','dtype':'int64','unit':'simulation seconds'},
        'role':{'role':'scope','definition':'POSTHOC_ELIGIBILITY_NOT_MODEL_INPUT'},
        **{f'eligible_plus{h}s':{'role':'posthoc_eligibility_not_feature','dtype':'int64','unit':'0/1',
            'definition':'1 iff origin-known path equals later realized issued path for this horizon; never use the mask as an input.'} for h in (300,600,900,1800)}}
    (PACKAGE/'DATA_DICTIONARY.json').write_text(json.dumps(d,indent=2)+'\n',encoding='utf-8')
    table=['# DEVELOPMENT_ONLY data dictionary','', 'NON_FINAL_EVALUATION. LOCAL_REVIEW_ONLY. No sharing or training release approved.', '',
        'The JSON dictionary is authoritative for machine loading. Only the 168 columns explicitly listed in FEATURE_GROUPS.json are candidate model inputs.','',
        '| Column | Role | Unit | Definition |','|---|---|---|---|']
    for col,spec in d['columns'].items():table.append(f"| `{col}` | {spec['role']} | {spec['unit']} | {spec['definition']} |")
    table+=['','Action masks are in a separate file and are posthoc eligibility metadata, never predictors. Original raw commands, proposed paths and effective readbacks retain separate meanings.']
    write('DATA_DICTIONARY.md','\n'.join(table)+'\n')
    write('INPUT_TARGET_DEFINITIONS.md',r'''# DEVELOPMENT_ONLY input and target definitions

NON_FINAL_EVALUATION. LOCAL_REVIEW_ONLY. Sharing and training release are not approved.

There is one row per run and prediction origin. Each row has 168 candidate inputs, eight target values and 27 metadata columns. Inputs are a candidate ablation pool, not a recommendation to use every variable together. No normalization, feature selection or other fitted transform was performed.

## Time and information availability

All `*_sim_s` values are BOPTEST simulation seconds on the benchmark clock. They are not UTC timestamps or an asserted real year. Clock phase uses modulo 86400; benchmark_day is floor(time/86400). API send/receipt UTC is retained in the referenced raw evidence and receipt orders are per-run, not comparable between runs.

Lags are 0, 300, 600, 900 and 1800 seconds. An endpoint feature at lag L is the measurement actually returned at t-L. Required history starts at t-2100 because the 1800-second power lag also needs its preceding 300-second interval. Warmup data are not borrowed to fill this lookback. All support remains inside one scored 72-hour run.

At origin t, the effective thermostat/fan/supply readbacks are from endpoint t, received before the cutoff. The command newly issued at t applies to [t,t+300]; its effective readback at t+300 is not an input at t. Issued-command lags come from commands committed by their own origin cutoffs, all at or before t.

## Included input families

- Indoor temperature: actual current and lagged air temperature, K converted to degC by subtracting 273.15.
- Weather measurements: actual outdoor dry-bulb (degC) and global/diffuse/direct-normal radiation (W/m2). Outdoor relative humidity is a separate optional fraction-valued group, not percent.
- Issued boundary forecasts: TDryBul, HGloHor, Occupancy[1], LowerSetp[1], UpperSetp[1] from the forecast actually received at t before its cutoff, at valid offsets 0/5/10/15/20/25/30 minutes. Forecast temperature/comfort columns retain K; measured temperature columns use degC. These are benchmark perfect-weather/known-schedule signals, not future indoor observations or evidence of real-world forecasting skill.
- Historical electricity: native interval-average cooling, fan and their sum, in kW, over [t-L-300,t-L]. Combined/components are intentionally redundant candidate groups for future ablation, not mandatory simultaneous inputs. Endpoint watts are excluded from the feature pool and labels.
- Effective control readbacks: cooling/heating setpoints (degC), activation flags (0/1), fan fraction and supply-temperature setpoint (degC), current and lagged.
- Issued control commands: all four flags plus a cooling perturbation encoding, current and lagged. The perturbation is requested target minus the source-native cooling reference when cooling override is active, and exactly zero perturbation when inactive. This is an action encoding, not an invented native requested target or a replacement for observed effective setpoints. Native raw command objects still omit an external setpoint field.
- Internal-load proxies: measured lighting and plug electrical power (kW). They are not complete internal thermal gains, occupant heat gains or future loads.
- Optional supply mass flow (kg/s) and CO2 (ppm): actual observed signals for future ablation. Scheduled occupancy remains a distinct known count, not measured occupancy.
- Calendar: time-of-day sine/cosine and benchmark day. Day may identify the two weather groups and must be treated cautiously in any future generalization study.

All feature names, exact units, signal keys, lags, transforms and availability are in DATA_DICTIONARY.json. Metadata, target times, IDs, posthoc masks and event resolutions are not automatically model inputs.

## Exact targets

For h in {300,600,900,1800} seconds:

`indoor_c(t+h) = raw_zone_temperature_K(t+h) - 273.15`

`hvac_interval_kw(t+h) = integral_[t+h-300,t+h](Pcool_W + Pfan_W) ds / 300000`

The integral uses ordered native 30-second samples and trapezoids. Duplicate-time jumps, if present, have zero duration and retain their saved order. Heating/gas, lighting and plug power are excluded from this HVAC electrical label. There is no endpoint-watts substitution, missing-value imputation, clipping or fitted scaling.

| Horizon | Electrical label interval |
|---|---|
| +5 min | [t,t+300] |
| +10 min | [t+300,t+600] |
| +15 min | [t+600,t+900] |
| +30 min | [t+1500,t+1800] |

Thus each demand target is the final five-minute interval at its horizon, not the average over the entire horizon and not instantaneous future power. This preserves the existing causal builder's target contract.

## Action-conditioned information and retrospective metadata

ACTION_PATHS.jsonl preserves each original proposed path and origin-known path. The first known-path entry is the issued current command; later entries are frozen proposals and contain no later veto outcomes. Use the first h/300 entries for horizon h.

The source `known_at_sim` annotation is inherited from the nominal plan. The separate `effective_available_at_sim_by_step` records the current issued command as available at the actual origin cutoff, and future frozen proposals as known at the run start. Original source annotations are not edited and are not used to claim current safety decisions were known earlier.

ACTION_ELIGIBILITY.csv contains horizon-specific equality masks determined after observing actual commands. They are eligibility/QA information only. REALIZED_ACTIONS_POSTHOC.jsonl contains actual commands, reasons and later readbacks in a separate audit file. Do not join its future fields or the masks into input features.

EVENT_VALIDATION_POSTHOC.jsonl contains later event-resolution information. At all 24 exact events, original old readbacks remain in the observational features; later verification is not used to replace them. ORIGIN_PROVENANCE.jsonl records the validation state known at each origin separately from later resolution.

## Unavailable or excluded inputs

No indoor relative humidity/humidity ratio, latent cooling or future indoor truth is inferred. Outdoor humidity is available as an optional measurement only. Wind, pressure, sky/dew/wet-bulb temperatures and other weather quantities exist in raw metadata but are outside the existing builder's approved input whitelist for this preview. Gas/heating power is preserved in source evidence but is not an electrical target or a new input here. No future internal-load measurement, realized future setpoint, future safety veto, later event-resolution outcome, failed D1 trajectory or earlier overlapping C/D trajectory is included as an observational input/example.
''')
    write('README.md',r'''# DEVELOPMENT_ONLY SDP Stage 4E-D1P preview v1.0.0

NON_FINAL_EVALUATION. LOCAL_REVIEW_ONLY. Not approved for automatic sharing, training or final evaluation.

## Contents and current result

The preview has 3408 origins, 852 from each qualified v2 arm, with 168 candidate features and eight targets. All 27264 label values and 572544 feature values passed independent raw-response QA. No model fitting, tuning, scoring or simulation was performed.

- DEVELOPMENT_ONLY_OBSERVATIONAL.csv: one flat row per origin; 203 columns = 27 metadata + 168 features + 8 targets.
- DEVELOPMENT_ONLY_ACTION_PATHS.jsonl: 3408 origin-known/proposed paths; no realized future control decisions.
- DEVELOPMENT_ONLY_ACTION_ELIGIBILITY.csv: 3408 rows with retrospective masks at +5/+10/+15/+30 minutes; counts 3408/3366/3359/3338.
- DEVELOPMENT_ONLY_REALIZED_ACTIONS_POSTHOC.jsonl: 3456 actual issued interval commands and later readbacks, audit only.
- DEVELOPMENT_ONLY_EVENT_VALIDATION_POSTHOC.jsonl: 24 later resolutions, audit only.
- DEVELOPMENT_ONLY_ORIGIN_PROVENANCE.jsonl: 3408 origin/receipt/source records; distinct from later validation metadata.
- FEATURE_GROUPS.json, DATA_DICTIONARY.json/.md and INPUT_TARGET_DEFINITIONS.md: authoritative feature/target whitelist, units, transformations, grouping and timing.
- QA_RESULTS.json, DATASET_QA_REPORT.md and OFFLINE_TEST_RESULTS.txt: whole-preview QA and seven fabricated adversarial label/unit/support tests.
- RAW_SOURCE_HASHES.json: exact qualified raw/source hashes and original relative paths. Large original raw logs are referenced, not copied into this package.
- DATASET_MANIFEST.json, MANIFEST_SHA256.txt and SHA256SUMS.txt: file integrity and provenance. A trusted manifest digest must be communicated independently for external integrity review.
- load_preview.py: standard-library integrity/load validation only, no fitting or sharing.

## Local loading example

After extracting, run `python load_preview.py` from this directory. It validates manifest/file hashes and row status, then loads only the explicit feature/target whitelists. It prints shape/status without fitting, evaluating or splitting data. It requires no Docker, network, pandas or ML library. Imported `load_preview()` returns X, Y, row IDs, feature/target names and group identities.

Use this locally for parser/schema development, checking units/timestamps, plotting inspections after review, or preparing feature-ablation configurations. The feature groups are a candidate pool; no ablation, model comparison or training has been executed or authorized by this package. Do not treat every numeric column as an input: future target timestamps, IDs and retrospective masks/resolutions are excluded.

## Dependency groups and evaluation limits

V2_Q01_N and V2_Q02_X share qualification_cool_146. V2_Q03_N and V2_Q04_X share qualification_heat_44. All rows have partition=development. There is no independent final test set. Never randomly split adjacent rows or paired arms into allegedly independent training/test sets. Preserve full temporal feature/label support, matched weather/initialization groups and any future preregistered embargo. The old builder's 3600-second partition embargo remains the existing default; no partitioning is done here.

Only two weather groups, correlated overlapping horizons, weak winter cooling response, safety-veto imbalance and perfect benchmark boundary forecasts limit generalization. This preview cannot establish reliable final ML rankings, real-world forecast skill or comfort compliance. Broader D2 collection requires a separately reviewed plan with additional nonoverlapping seasonal/weather/control coverage and separate execution permission. No D2 work is implied here.

## Reproducibility and status

Source is exclusively the four completed qualified v2 runs. Warmup records, failed original D1 and older overlapping C/D records are not examples or label support. The initial post-warmup endpoint is an actual scored-boundary observation, not a warmup trajectory. Source hashes, receipts and the frozen ec9c64f9abffcda7095d537e375eda7bb8f6b6d367aa1aa2238bcc606bcbeb5c proposal identify the exact inputs. The unchanged Stage 4E causal builder produced core lag/target/calendar values; documented deterministic adapters add separate native cooling/fan histories, issued command encodings and exact-origin forecast vintages. Rebuilding requires the original qualified workspace and source files; loading the preview is self-contained.

Dataset/source version is v1.0.0. Do not overwrite this snapshot or edit original evidence. Any later source/specification change needs a new version and fresh QA. Source quarantine and training_release=false markers remain intact. This local archive has not been sent to teammates or uploaded. Return for explicit review and release approval before sharing or training.
''')
    qa=read(PACKAGE/'QA_RESULTS.json')
    write('DATASET_QA_REPORT.md',f'''# DEVELOPMENT_ONLY dataset QA report

NON_FINAL_EVALUATION. LOCAL_REVIEW_ONLY. Sharing/training release not approved.

**PASS.** 3408 unique origins, 852 per arm; 168 inputs and 8 targets per row. All 27264 targets (13632 temperature + 13632 native-integrated electrical demand) and 572544 input values were checked against independently decoded preserved raw API responses.

Maximum temperature error: {qa['maximum_temperature_error_degC']} degC. Maximum electrical-label error: {qa['maximum_electrical_error_kW']:.17g} kW. Absolute floating-arithmetic QA tolerance: 1e-10 in the corresponding numeric unit; this does not change any simulator validation tolerance.

All required checks passed: exact/unique counts, causal lags, target endpoint/interval timestamps, native 30-second integration and units, forecast vintage/receipt cutoff, current-command availability, no future realization in features, no run-boundary crossing, proposed/applied path separation, correct veto masks, 24 unchanged event-time readbacks, separate later resolutions, finite/nonmissing values, source hashes before/after and exclusion of warmup/failed/earlier overlapping trajectories as examples.

Action masks exactly match qualification: +5=3408, +10=3366, +15=3359, +30=3338. Missing future path agreement is not fabricated/backfilled. The 70 fewer exact-path-eligible +30 origins remain valid observational rows.

10,456 original API requests and per-run receipt-journal chains were rechecked. Feature and label truth came from raw POST/forecast/results payloads, not just the builder's own saved endpoints or its prefix-integral output. Source file identities were checked before and after QA. Native-history event duplicates remain ordered in the algorithms; actual source scored histories have no duplicate timestamps. Seven fabricated tests independently exercise units, varying-power means, duplicate jumps, missing support/cadence, nonfinite/bool rejection and wrong-unit/shifted-value failure.

The inherited nominal-plan known_at_sim annotation on current issued entries is retained; actual current-command availability is explicitly tied to the origin cutoff. This is a documented provenance distinction, not altered source data or a changed eligibility count. No material data/count discrepancy was found.

The package contains observational labels solely as a development preview. It is not a released final supervised dataset, independent final evaluation or permission to fit models. No simulator, network, Docker dispatch or model-fitting/scoring path was invoked. Actual construction/QA and tests blocked socket connections and external-process dispatch.
''')

if __name__=='__main__':main()
