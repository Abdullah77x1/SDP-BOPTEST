"""Render planning documents and metadata CSVs from audit counts, not training data."""
import csv,json
from . import HOME,PILOT,WORKSPACE
from hvac_control_expansion_b2f_v1.packaging import read,write_new,require,sha

def text(name,value):
    with (HOME/name).open('x',encoding='utf-8',newline='\n') as f:f.write(value.strip()+'\n')

def table(headers,rows):return '| '+' | '.join(headers)+' |\n|'+'|'.join(['---']*len(headers))+'|\n'+'\n'.join('| '+' | '.join(str(v) for v in row)+' |' for row in rows)+'\n'

def csv_new(name,rows):
    with (HOME/name).open('x',newline='',encoding='utf-8') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)

def reports():
    a=read(HOME/'AUDIT_RESULTS.json');require(a['status']=='PASS_READ_ONLY_ELIGIBILITY_AUDIT','No unverifiable counts')
    alias=read(HOME/'B3_PLAN_ALIASING_AUDIT.json');require(alias['status']=='PASS_RAW_SOURCE_EQUIVALENCE','Aliasing not verified')
    analysis=read(PILOT/'hvac_control_expansion_b2i_v1/ANALYSIS.json');tests=read(HOME/'FABRICATED_SEMANTICS_RESULT.json')
    b1=[r for r in a['runs'] if r['kind']=='B1'];original=[r for r in a['runs'] if r['kind']=='ORIGINAL_D2'];allrows=a['runs']
    perrun=[[r['run_id'],r['group_id'],r['outer_held_fold'],r['endpoints'],r['five_minute_scored_origins'],r['native_samples'],r['eligible_origins'],'candidate' if r['training_default'] else 'QA only'] for r in allrows]
    effects=[]
    for group in ('G174','G146'):
        g=analysis[group]
        for policy in ('C15','C45'):
            p=next(r for r in g['primary_temperature'] if r['reference']=='NREF' and r['alternative']==policy)
            e=next(r for r in g['full_energy'] if r['policy']==policy);c=next(r for r in g['comfort'] if r['policy']==policy and r['reference']=='NREF')
            effects.append([group,policy,f"{p['mean_abs_temperature_k']:.9f}",f"{p['max_abs_temperature_k']:.9f}",f"{p['absolute_temperature_area_k_hours']:.9f}",f"{e['delta_electric_vs_NREF_kwh']:+.9f}",f"{c['degree_hours']:.9f}"])
    closure=f'''# B3 formal B1 closure

Decision: **B1 is complete under its original six-run duration-expansion objectives.** No new simulation is required to close it or to begin a separately approved initial ML implementation. Small response amplitudes do not invalidate completed, correctly delivered evidence.

All six NREF/C15/C45 recordings under G174/G146 have valid raw evidence and corrected finalization. G174 original NREF/C15 are covered by the B2-F corrected pilot package; G174 C45 by its frozen B2-G v2 continuation package; G146 by three B2-I packages. The original failed packaging history remains preserved, not relabeled as a successful old attempt. The later corrected packages establish the current finalization result. Each run has 864 scored advances, 865 endpoints and 8,641 native samples. Both C15 runs delivered 9/9 requested intervals and both C45 runs 27/27, without vetoes. All six slots are consumed; no retry, replacement or extra condition is part of closure.

## Verified physical contribution

{table(['Group','Policy','11–14 MAE vs native K','Peak abs K','Abs area K·h','72h electricity Δ kWh','Discomfort K·h'],effects)}
C45 sustains a difference longer in every matched day, with C45/C15 common-window area ratios 2.904 (G174) and 2.728 (G146). Peak excursion hardly changes between durations within a group. All G146 release markers are 15 minutes; G174 C15 is 15/10/15 and C45 15/15/15. Localized comfort worsening and cross-day carryover remain recorded. Recovery demand can temporarily differ from native: G146 C15 has small positive intervals up to 2.22 W, below the existing 10 W reporting marker. Full-period electricity increases despite net recovery-window reductions. Aggregate discomfort improves, but this is not uniform comfort compliance or validated operational policy quality.

The new contribution is two different cooling histories at an existing 296.90 K target, different source-known release plans and distinct observed thermal/electrical/recovery histories in two existing development weather groups. There is no new numerical target extreme: 296.90 K was already tested. There are no new independent weather groups, occupancy regimes, heating controls, model physics or final-test population. C15 external control occupies only 45 minutes per 72-hour run; C45 135 minutes (1.0417% and 3.125%). Most operation remains native.

B3 verifies 852 structurally eligible origins per alternative, 3,408 total. The 1,704 fresh-NREF origins are QA duplicates of existing conditions by default. More origins are not proof of generalization. No B1 model has been fit or scored; there is no demonstrated action-conditioned or predecision counterfactual capability, ML improvement, real-building saving or energy-saving intervention.

## Evidence and preservation

Source evidence includes the frozen B1 design/evaluation plan, completed B2-H and B2-I reports/analysis, per-run artifact manifests, raw commands/forecasts/native histories, receipt chains and append-only ledger chain. B3 checks original development source hashes, B1 metadata and corrected continuation packages, not validation outcome payloads. Exact hashes are in B3_SOURCE_HASHES.json; AUDIT_RESULTS.json contains each run's source path, seal-source hash, FMU identity and terminal receipt hash.

The inherited B2-I implementation identity is `b7524fd479d7b2f7bfa1fc06d7780025fd8c04f63f29456308d7aa1b2f83f275`; it is historical execution provenance, not a new B3 execution approval. No B1/D2/controller/model source or result is edited. B3 is a planning continuation and grants no simulator or ML execution authority.
'''
    text('B3_B1_CLOSURE_REPORT.md',closure)
    posthoc=[[r['run_id'],r['vetoed_scored_intervals'],r['latched_before_origin_count'],*[r['posthoc_hybrid_equals_realized_by_horizon'].get(str(h),0) for h in (300,600,900,1800)]] for r in allrows if r['vetoed_scored_intervals']]
    eligibility=f'''# B3 development eligibility and dependency audit

PASS for existing structural/target support and nominal-plan provenance: original development 13,632 origins; four B1 alternatives 3,408; two B1 NREF QA recordings 1,704. The candidate expanded development population excluding fresh-native duplicates is 17,040, still eight parent groups. This is an eligibility audit, not a released dataset or model-ready feature table.

## Exact per-run counts

{table(['Run ID','Parent group','Held fold','Endpoints','Scored origins','Native samples','Eligible origins','Default use'],perrun)}
Every 72-hour run has 864 right-open five-minute command origins, plus the final endpoint. The historical rule excludes the first seven origins for 2100-second lookback and the last five for 1800-second future support, leaving exactly 852. Eligible range is `[start+2100,end−1800]` inclusive on the 300-second grid. Endpoint temperature lags reach 1800 seconds; the oldest completed demand interval reaches 2100 seconds. Warmup is not used to enlarge the frozen scored-origin population.

The audit follows only the 16 original development entries in partition/source metadata, plus the six B1 development runs. It verifies the original development CSV checksum, 13,632 unique row IDs, all common25/16-target values finite, original run IDs and exact eligible timestamp sets. For every raw run it checks 865 unique endpoints, 864 unique command origins, 8,641 ordered native timestamps, zero duplicate native times in these actual recordings, finite required endpoints/native values, 864 issued forecasts with correct core channels/vintages, origin cutoff order, completed-history receipt support, command/plan agreement and unchanged Safety replay. No B1 feature or target rows are computed/exported; source support proves reconstructibility, while a later implementation must prove exact transformed-value equivalence.

Required units remain K for raw temperature/effective setpoints, W for raw cooling/fan/gas and W/m² for solar. Celsius/kW conversions, modeled heating factor and final-interval targets remain frozen. All required common25 and component-target sources are present; required missing counts are zero. Legacy G044/G146 sources collect five forecast channels; later sources collect fourteen. All five common core channels needed here exist. Nine absent legacy optional forecasts are not imputed or introduced into the new contract.

## Nominal availability is not realized-action compliance

All 852 origins per source run have reconstructible nominal plans and prior guard state. Every B1 alternative's saved hybrid path also happens to match its delivered future commands at every horizon; that observed agreement is not the eligibility definition and must not be used to claim future vetoes are known.

Some original X runs have correctly vetoed actions:

{table(['Original run','Vetoed scored intervals','Eligible prior-latch=1','Hybrid matches +5','+10','+15','+30'],posthoc)}
These retrospective counts describe the saved hybrid path (current issued action plus future nominal requests), not a forced nominal-action target population. Retain all 852 structural origins under the safety-filtered-policy estimand. Never filter training or the primary test population by these future-compliance counts. Original N/X and B1 therefore share nominal-plan semantics, even though future application sometimes differs in the original cold groups. Prior latch state is reconstructible at every origin and materially necessary in the original data; all B1 latch counts are zero.

Legacy V2 sources omit the later `data_is_fabricated` flag and append an event note to some reason strings. Their live raw API/receipt provenance, pinned selected FMU, qualification status and hashes establish source identity. AUDIT_SCHEMA_CORRECTION.md records the audit adapter correction; the missing flag is explicitly reported per run. No source values, guards, bounds or validation tolerances were changed.

## Duplicate and dependency accounting

All original row IDs are unique, and the 22 audited raw run IDs are unique. Use `(run_id,sim_time_s)` as origin identity. Matching timestamps across N/X/C15/C45 are intentional dependent observations, not duplicate identity errors. Fresh NREF deliberately repeats native conditions and is excluded from default learning denominators even with a different raw ID. Actual B1 NREF reproducibility/prefix QA is retained rather than copied into training.

G146 and all its policies remain D2_G146 held in fold1; G174 remains D2_G174 held in fold4. Saved four-fold manifests are identical. The metadata-only protected/reservation audit passes 98 footprint comparisons, allowing intentional parent-group overlap and forbidding collisions with other reservations. No validation/protected raw or outcome CSVs were followed or used. Partition metadata is read solely to select allowed development source paths and verify dependencies.

## Mdiv support and exact counts

The saved map hash is `{a['Mdiv_timestamp_plan_sha256']}`. Its 426 alternative-pair / 426 original-pair assignments per B1 parent group exactly equal the original frozen function. All four source arms share all 852 eligible timestamps, so there is no failed-origin blocker or quota correction. The map remains metadata-only; B3 does not generate selected training rows. See the grouped plan for precise phase boundaries, pair labels and fold counts.

## Audit boundaries

The original D2 package has 24 public qualified runs / 12 groups by partition metadata. Only its 16 development runs / eight groups were audited as outcomes here. The other 6,816 validation origins remain a metadata count, not an inspected or scored population. B3 hashes only the development evidence it uses; it does not indiscriminately traverse all public manifests into forbidden payloads. Existing model binaries are neither loaded nor executed. Eligibility is mechanical readiness for a separately approved implementation, not training/release approval.

Reproducible read-only commands, absolute source locations and hashes are in README.md, B3_SOURCE_INDEX.csv and B3_SOURCE_HASHES.json.
'''
    text('B3_DATA_ELIGIBILITY_AUDIT.md',eligibility)
    split=[]
    for f in a['folds']:
        for r in allrows:
            train=r['group_id'] in f['train_groups'];b=r['kind']=='B1';qa=b and r['policy']=='NREF';alt=b and not qa;newgroup=r['group_id'] in ('D2_G146','D2_G174')
            split.append(dict(fold=f['fold'],run_id=r['run_id'],group_id=r['group_id'],policy=r['policy'],kind=r['kind'],eligible_origins=852,
                group_role='TRAIN_GROUP' if train else 'HELD_GROUP',M0_train=852 if train and not b else 0,
                Mdiv_train=(426 if newgroup else 852) if train and not qa else 0,
                Mfull_train=852 if train and not qa else 0,original_held=852 if not train and not b else 0,
                B1_transfer_held=852 if not train and alt else 0,QA_only=qa,default_training_excluded=qa,
                source_manifest_sha256=r['source_manifest_sha256'],source_path=r['source'],selection='FROZEN_METADATA_NOT_OUTCOMES'))
    for f in a['folds']:
        ss=[r for r in split if r['fold']==f['fold']]
        for key,col in [('M0_training','M0_train'),('Mdiv_training','Mdiv_train'),('Mfull_training','Mfull_train'),('original_held','original_held'),('B1_held_transfer','B1_transfer_held')]:require(sum(r[col] for r in ss)==f[key],'Split plan arithmetic mismatch')
    csv_new('B3_SPLIT_AND_SAMPLE_PLAN.csv',split)
    fields=[]
    committed={'cooling_override_committed','cooling_setpoint_change_committed_k'}
    for name in a['common25']:
        unit='degC' if name.endswith('_c') else 'K' if name.endswith('_k') else 'kW' if name.endswith('_kw') else 'W/m2' if 'w_m2' in name else 'people' if name.startswith('occupancy') else '0/1' if 'override' in name else '1'
        src='Actual issued command at t, after Safety' if name in committed else 'Endpoint/readback at or before t, completed native interval, simulation clock, or as-issued boundary forecast; exact mapping in COLUMN_MAPPING and v2 build_dataset'
        fields.append(dict(field=name,encoding='EXISTING_COMMON25',dtype='int8' if 'override' in name else 'float64',unit=unit,description='Unchanged existing field',source=src,
            knowledge_time='AFTER_CURRENT_COMMIT_BEFORE_ADVANCE' if name in committed else 'OBSERVED_OR_ISSUED_BEFORE_ORIGIN_DECISION',
            allowed_values='finite source-valid values',missing='BLOCK_NO_IMPUTATION',transform='Frozen common25 mapping; native W to kW and K to Celsius as applicable',
            leakage_risk='Critical if used for predecision' if name in committed else 'Do not use later response/vintage or whole-run statistics',predecision_available=name not in committed))
    compact=[
        ('a__cooling_block_present','int8','0/1','Any nominal active cooling slot in next 1800 s','0 or 1','Any active slot in frozen proposed_path'),
        ('a__cooling_delta_from_native_k','float64','K difference','One fixed requested target relative to pinned native reference','0 inactive; -0.25 or -0.50 active','Target minus REFERENCE.pair at clipped activation; inactive perturbation zero'),
        ('a__activation_offset_s','int32','s','Clipped nominal activation offset','0 inactive; 0,300,...,1500 active','max(0,nominal activation - origin)'),
        ('a__release_offset_s','int32','s','Clipped nominal release offset','0 inactive; 300,...,1800 active and release>activation','min(1800,nominal release - origin)'),
        ('c__cooling_veto_latched_before_t','int8','0/1','Already known prior veto for same ongoing source block','0 or 1','Replay strictly past Safety state with block resets; never current/future reason')]
    for name,dtype,unit,desc,allowed,transform in compact:
        latch=name.startswith('c__')
        fields.append(dict(field=name,encoding='RECOMMENDED_COMPACT',dtype=dtype,unit=unit,description=desc,source='Past saved decisions and pinned Safety' if latch else 'Saved proposed_path plus pinned policy/native schedule',
            knowledge_time='STRICTLY_BEFORE_CURRENT_DECISION' if latch else 'FROZEN_NOMINAL_PLAN_KNOWN_AT_OR_BEFORE_ORIGIN',allowed_values=allowed,missing='BLOCK_UNAVAILABLE_NOT_NATIVE_ZERO',transform=transform,
            leakage_risk='Never current/future veto' if latch else 'Never future realized command/readback; preserve proposal vs issued role',predecision_available=True))
    for j in range(6):
        for suffix,dtype,unit,allowed in [('on','int8','0/1','0 or 1'),('delta_k','float64','K difference','0 inactive; source-supported perturbation active')]:
            name=f'a__cooling_{suffix}_{j}'
            fields.append(dict(field=name,encoding='ALTERNATIVE_SIX_SLOT',dtype=dtype,unit=unit,description=f'Nominal slot [{j*300},{(j+1)*300}) seconds after origin',source='Saved proposed_path / pinned nominal resolver',knowledge_time='AT_OR_BEFORE_ORIGIN',allowed_values=allowed,
                missing='BLOCK_MISSING_SLOT_NOT_NATIVE_ZERO',transform='Activation bit' if suffix=='on' else 'Requested target minus native at slot; zero only inactive',leakage_risk='Never future realized actions or vetoes',predecision_available=True))
    availability=[];policytypes=[('ORIGINAL_N',[r for r in original if r['policy']=='native']),('ORIGINAL_X',[r for r in original if r['policy']=='scheduled_variation']),('B1_NREF',[r for r in b1 if r['policy']=='NREF']),('B1_C15',[r for r in b1 if r['policy']=='C15']),('B1_C45',[r for r in b1 if r['policy']=='C45'])]
    for field in fields:
        for policy,rr in policytypes:
            availability.append(dict(**field,model_input=field['field']!='a__cooling_block_present',source_policy_type=policy,available_origin_count=sum(r['eligible_origins'] for r in rr),availability='SUPPORTED_FROM_EXISTING_EVIDENCE',compatibility='Explicit legacy receipt/reason adapter; core-only weather sufficient' if policy.startswith('ORIGINAL') else 'B1 schedule and raw reporting profile supported'))
    csv_new('B3_FEATURE_AVAILABILITY_MATRIX.csv',availability)
    for field in fields:field['model_input']=field['field']!='a__cooling_block_present'
    write_new(HOME/'B3_FEATURE_SCHEMA.json',dict(version='B3_ACTION_CONTRACT_1.0.0_DESIGN_ONLY',fields=fields,observational_features=25,postdecision_action_features=29,predecision_action_features=27,wide_postdecision_features=38,wide_predecision_features=36,scope='ONE_FIXED_TARGET_BLOCK_PER_30MIN_HORIZON',training_release=False))
    readiness='''# B3 implementation readiness

Decision: **PASS — source/design ready for separately approved implementation.** This is not execution or dataset-release approval. No additional simulation is necessary for the first implementation or grouped ML comparison.

| Question | Audited answer |
|---|---|
| Are source artifacts available? | Yes: 16 original development and six B1 raw sources, original development table, schemas, plans, receipts and completed evidence. Validation payloads were not audited. |
| Are contracts documented? | Yes: common25, 168 candidate definitions/ablation groups, sixteen component labels and eight primary reported quantities are distinguished explicitly. |
| Are B1 nominal actions reconstructible? | Yes, all 852 origins in each run, from saved proposed_path and pinned schedules. |
| Are original N/X actions reconstructible? | Yes, all 13,632 original origins under the same nominal-policy semantics. Original X is three 30-minute pulses at two targets, not B1's one 15/45-minute pulse. |
| Are targets compatible? | Yes: endpoint temperature, final-five-minute native demand means, fixed units and gas-to-thermal conversion. No B1 label matrix was generated here. |
| Are enough origins available? | Mechanically yes: 3,408 alternative origins; 17,040 total candidate development origins excluding fresh NREF. Statistical power remains limited to two B1 transfer contexts. |
| Are splits suitable? | Yes: existing eight development groups/four folds preserved, G146 fold1/G174 fold4; no random row split. |
| Can existing evidence remain immutable? | Yes: use new adapters/artifacts and explicit source hashes; never edit original datasets, controller, models or predictions. |
| Is new simulation required? | No source/support gap was found. Wider action or weather validity remains untested, but it is not required for the bounded first ML question. |

Smallest next engineering task, after explicit approval: implement read-only legacy/new source adapters and strict origin availability checks; implement the compact nominal-plan/latch encoding in a separate namespace; verify all common25 and unchanged target semantics against existing originals and fabricated boundary tests; materialize only an explicitly authorized quarantined development view; save immutable group/sample memberships and preprocessing schemas. A subsequent explicit authorization can permit fitting/scoring under the frozen grouped plan. This B3 task does not authorize any of those matrix/fit steps.

The initial evaluation scope should preserve Track O's M0/Mdiv/Mfull and add A1-post compact under M0/Mdiv using reused A0 comparisons. Keep the state-only23 versus proposed-plan27 predecision diagnostic separately labeled and approved. Do not automatically implement every 168-feature candidate, wide schedule encoding, optimizer, new horizons or extra simulations.

Implementation acceptance gates: exact target/value reproduction at existing arithmetic tolerances; no required missing/imputed fields; explicit old event-note handling; proposed versus current-issued distinction; correct native release/forecast interval edges; prior-latch replay limited to past decisions; no future-compliance filtering; group/fold and exact saved Mdiv-map equivalence; identical held IDs/targets; source hashes unchanged; network/simulator and validation outcome paths denied in offline preparation.

Decisions to acknowledge before fitting: approve the compact one-block support restriction; confirm A1-post versus A-pre estimands and 16-component/8-primary reporting choice; approve the stated practical review margins and uncertainty limitations; choose whether the deferred Mfull A1 extension or predecision diagnostic is in the next authorized budget. None is a missing-source blocker. Do not choose these based on future held scores.

No forced-open-loop target population is claimed: original safety vetoes mean nominal proposed and realized paths differ in some X runs. The intended model predicts safety-filtered-policy outcomes conditional on a known request and prior guard context. Arbitrary continuous setpoints, unseen times/durations, altered guards, different buildings, real weather or real-building counterfactuals remain outside support.
'''
    text('B3_IMPLEMENTATION_READINESS.md',readiness)
    summary='''# B3 executive summary

B1 is complete. We verified six duration-experiment runs in two existing development weather groups. Longer cooling holds sustained a measurable temperature/demand difference, while adding little peak-temperature range. Both durations used more electricity than native control. Aggregate sampled discomfort improved, but small local worsening remained. This establishes useful localized operating diversity, not ML improvement or broad weather generalization.

The read-only audit confirmed 852 eligible origins in each alternative run: 3,408 additional candidates. Original development remains 13,632 origins. Fresh native repeats contribute 1,704 QA origins and are excluded from default training. The candidate expanded total is 17,040, with the same eight dependent weather groups and four outer folds. No new dataset was produced.

The action problem is now explicit: at first-day 11:00, C15/C45 share the current state and current command, but their planned releases differ. Common25 cannot see that future plan. It also contains two already committed command fields, so it is a postdecision forecasting contract. Preserve it unchanged as the baseline.

Recommend four added predictors: target perturbation from native, clipped activation offset, clipped release offset, and the veto latch already known before the decision. Planned block presence is derived from release offset for validation. This gives 29 inputs for the postdecision information comparison or 27 for a separate predecision interface after removing the two factual committed-command fields. A twelve-field, six-slot schedule is documented but unnecessary for the existing single-block 30-minute plans. Original N/X and B1 plans are reconstructible without future-action backfill; some original X requests are safety-vetoed, which the estimand must preserve.

Compare original training (M0), same-size outcome-blind policy replacement (Mdiv), and full augmentation (Mfull). Retain the exact saved Mdiv map and four group-held folds. Evaluate original-policy retention and B1-policy transfer separately on identical held origins. Action-feature comparisons must hold data composition, targets, splits and tuning budgets fixed. Only two B1 weather contexts support transfer, so report both rather than treating thousands of rows as independent evidence.

The design is ready for a separately approved implementation using existing evidence. First build/test the adapters and action contract, then authorize any dataset construction and model fitting explicitly. No extra simulation is needed now. B3 ran no simulation, ML training/prediction/evaluation, preprocessing fit or dataset release and did not open sealed validation/protected outcomes. Stop at this planning package.
'''
    text('B3_EXECUTIVE_SUMMARY.md',summary)
    return dict(status='PASS_PLANNING_REPORTS',required_documents=10,metadata_split_rows=len(split),availability_rows=len(availability),new_model_ready_rows=0)

if __name__=='__main__':print(json.dumps(reports(),indent=2))
