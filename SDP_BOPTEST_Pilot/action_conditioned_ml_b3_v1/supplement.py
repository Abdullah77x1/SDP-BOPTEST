"""Planning metadata/alias checks and source index; emits no feature vectors."""
import csv,json,re
from pathlib import Path
from bisect import bisect_left,bisect_right
from . import HOME,PILOT,WORKSPACE
from .audit import load,source,INPUT_HASHES,MODEL,V2
from hvac_control_expansion_b2f_v1.packaging import read,write_new,require,sha,digest

REFERENCES={
    'experiments/five_model_hvac16_v1_0_0/config.py':['FEATURES=','TARGETS=','RIDGE_ALPHAS=','RF_PARAMS=','XGB_PARAMS='],
    'experiments/five_model_hvac16_v1_0_0/train.py':['def outer_splits','def choose_ridge'],
    'experiments/five_model_hvac16_v1_0_0/estimators.py':['def persistence','def linear_model','class IndependentTrees'],
    'experiments/hvac_16_outputs_v2_0_0/build_dataset.py':['def build','for col,lag in zip','for h in HORIZONS'],
    'experiments/hvac_16_outputs_v2_0_0/common.py':['COMMITTED=','CONFIGS='],
    'SDP_BOPTEST_Pilot/stage4e/dataset.py':['class NativeElectric','def known_actions','def build_rows','def validate_partitions'],
    'SDP_BOPTEST_Pilot/stage4e_d1p/build.py':['LAGS=','def schema'],
    'SDP_BOPTEST_Pilot/stage4e_d0/plan.py':['def nominal','def action_path','class Safety'],
    'SDP_BOPTEST_Pilot/stage4e_d0/handoff.py':['def known_path_annotations'],
    'SDP_BOPTEST_Pilot/stage4e_d1_v2/runner.py':["if tracker.pending:reason+=","known_path="],
    'SDP_BOPTEST_Pilot/stage4e_d2_public/export.py':['def interval','def decode_truth'],
    'SDP_BOPTEST_Pilot/hvac_control_expansion_v1/campaign.py':['def canonical_manifest','def nominal','def action_path'],
    'SDP_BOPTEST_Pilot/hvac_control_expansion_v1/contracts.py':['def labels','def matched_size_plan'],
    'SDP_BOPTEST_Pilot/hvac_control_expansion_v1/collector.py':['proposed_path=','known[0].update'],
    'SDP_BOPTEST_Pilot/stage4e_d2i_1_v1_0_1/collector.py':['proposed_path=','known[0].update'],
    'SDP_BOPTEST_Pilot/hvac_control_expansion_v1/integrity.py':['def reservation_check'],
}

def supplement():
    a=read(HOME/'AUDIT_RESULTS.json');old=read(HOME/'AUDIT_SOURCE_HASHES.json')
    f1=load(MODEL/'run_01/outer_folds.json');f2=load(V2/'evaluation_01/folds.json');require(f1==f2,'Historical folds differ')
    schema=load(V2/'SCHEMA_FREEZE.json');require(len(schema['configs']['revised_components'])==25,'Baseline contract changed')
    groupdefs=load(PILOT/'stage4e_d1p/DEVELOPMENT_ONLY_SDP_STAGE4E_D1P_v1_0_0/FEATURE_GROUPS.json');require(sum(map(len,groupdefs['feature_groups'].values()))==168,'Candidate groups count changed')
    alias=[]
    for group in ('D2_G146','D2_G174'):
        rr=[next(r for r in a['runs'] if r['kind']=='B1' and r['group_id']==group and r['policy']==p) for p in ('C15','C45')]
        dirs=[Path(r['source']) for r in rr];ends=[load(d/'endpoints.json') for d in dirs];native=[load(d/'whole_native_results.json') for d in dirs]
        ss=[[json.loads(s) for s in source(d/'steps.jsonl').read_text().splitlines()] for d in dirs]
        start=rr[0]['scored_start'];t=start+39600;i=(t-start)//300
        for j in range(i+1):
            require(ends[0][j].keys()==ends[1][j].keys() and all(abs(ends[0][j][k]-ends[1][j][k])<=1e-7 for k in ends[0][j]),'First-day pretreatment differs')
        for n in native:
            require(n['time']==native[0]['time'],'Native history clocks differ')
        lo=bisect_left(native[0]['time'],t-2100);hi=bisect_right(native[0]['time'],t)
        for k in ('fcu_reaPCoo_y','fcu_reaPFan_y','fcu_reaPHea_y'):
            require(all(abs(x-y)<=1e-7 for x,y in zip(native[0][k][lo:hi],native[1][k][lo:hi])),'Common25 historical source differs')
        fc=[load(d/f'forecast_{i:04d}.json')['data'] for d in dirs];require(fc[0]==fc[1],'Origin boundary forecasts differ')
        require(ss[0][i]['applied_command']==ss[1][i]['applied_command'],'Current committed controls differ at first11')
        plan_first=next(x['start'] for x,y in zip(ss[0],ss[1]) if [p['command'] for p in x['proposed_path']]!=[p['command'] for p in y['proposed_path']])
        commit_first=next(x['start'] for x,y in zip(ss[0],ss[1]) if x['applied_command']!=y['applied_command'])
        require(plan_first==start+39000 and commit_first==start+40500,'Unexpected aliasing clock')
        alias.append(dict(group_id=group,first_day_1100_origin=t,common25_source_equivalent_within_1e_7=True,
            current_command_equal=True,nominal_path_differs=True,first_bounded_30min_plan_distinction_s=plan_first,
            first_current_committed_distinction_s=commit_first,new_feature_rows_exported=0))
    write_new(HOME/'B3_PLAN_ALIASING_AUDIT.json',dict(status='PASS_RAW_SOURCE_EQUIVALENCE',comparisons=alias,fold_manifests_identical=True,candidate_feature_definitions=168))
    more=['experiments/hvac_16_outputs_v2_0_0/candidate_168_review.csv','experiments/hvac_16_outputs_v2_0_0/HVAC_V2_INPUT_SELECTION.md',
        'experiments/persistence_linear_regression/input_reference/COLUMN_MAPPING.csv','experiments/five_model_hvac16_v1_0_0/REPORT_FACTS.json',
        'experiments/five_model_hvac16_v1_0_0/FROZEN_TRAINING_MANIFEST.json','experiments/five_model_hvac16_v1_0_0/OUTPUT_CHECKSUMS_SHA256.json',
        'hvac_expansion_design_B1_2026-11-18/HVAC_EXPANSION_DESIGN.md','hvac_expansion_design_B1_2026-11-18/EVALUATION_PLAN.md',
        'SDP_BOPTEST_Pilot/hvac_control_expansion_b2h_v1/DELIVERY_MANIFEST.json','SDP_BOPTEST_Pilot/hvac_control_expansion_b2h_v1/B2H_EXECUTION_REPORT.md',
        'SDP_BOPTEST_Pilot/hvac_control_expansion_b2i_v1/DELIVERY_MANIFEST.json','SDP_BOPTEST_Pilot/hvac_control_expansion_b2i_v1/ANALYSIS.json',
        'SDP_BOPTEST_Pilot/hvac_control_expansion_b2i_v1/B2I_EXECUTION_REPORT.md','SDP_BOPTEST_Pilot/hvac_control_expansion_b2i_v1/B2I_G174_VS_G146_COMPARISON.md',
        'SDP_BOPTEST_Pilot/hvac_control_expansion_b2i_v1/B2I_ML_READINESS_REVIEW.md',
        'SDP_BOPTEST_Pilot/hvac_control_expansion_b2i_v1/LEDGER_BASELINE.json']
    for p in more:source(WORKSPACE/p)
    # Ledger anchors are metadata. Read/hash the three immutable SQLite databases, not any new simulator state.
    baseline=load(PILOT/'hvac_control_expansion_b2i_v1/LEDGER_BASELINE.json')
    for p,h in baseline['chain_anchors'].items():require(sha(source(p))==h,'Historical ledger chain changed')
    rows=[]
    for relative,symbols in REFERENCES.items():
        p=source(WORKSPACE/relative);text=p.read_text(encoding='utf-8-sig').splitlines()
        for symbol in symbols:
            found=[i+1 for i,line in enumerate(text) if symbol in line]
            require(found,'Missing reference symbol: '+relative+':'+symbol)
            rows.append(dict(relative_path=relative,absolute_path=str(p),symbol=symbol,line=found[0],sha256=sha(p)))
    with (HOME/'B3_SOURCE_INDEX.csv').open('x',newline='',encoding='utf-8') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
    old.update(INPUT_HASHES);write_new(HOME/'B3_SOURCE_HASHES.json',old)
    return dict(status='PASS_ALIASING_AND_SOURCE_INDEX',source_files=len(old),reference_symbols=len(rows),feature_matrices_created=0)

if __name__=='__main__':
    from hvac_control_expansion_b2f_v1.tests import offline_guard
    with offline_guard():print(json.dumps(supplement(),indent=2))
