"""Read-only B3 preservation and planning arithmetic checks; no model imports."""
import csv,json
from . import HOME,PILOT,WORKSPACE
from hvac_control_expansion_b2f_v1.packaging import read,sha,require,inventory,write_new

REQUIRED=['B3_B1_CLOSURE_REPORT.md','B3_DATA_ELIGIBILITY_AUDIT.md','B3_ACTION_FEATURE_CONTRACT.md',
    'B3_FEATURE_AVAILABILITY_MATRIX.csv','B3_TARGET_CONTRACT.md','B3_GROUPED_EVALUATION_PLAN.md',
    'B3_SPLIT_AND_SAMPLE_PLAN.csv','B3_LEAKAGE_AND_DEPENDENCY_AUDIT.md','B3_IMPLEMENTATION_READINESS.md','B3_EXECUTIVE_SUMMARY.md']

def csv_rows(name):
    with (HOME/name).open(newline='',encoding='utf-8-sig') as f:return list(csv.DictReader(f))

def verify():
    for name in REQUIRED:require((HOME/name).is_file() and (HOME/name).stat().st_size>0,'Required planning deliverable absent')
    hashes=read(HOME/'B3_SOURCE_HASHES.json')
    for p,h in hashes.items():require(sha(p)==h,'Historical source changed: '+p)
    before=read(HOME/'AUDIT_SOURCE_HASHES.json');require(all(hashes[p]==h for p,h in before.items()),'Initial audit source binding changed')
    a=read(HOME/'AUDIT_RESULTS.json');require(a['status']=='PASS_READ_ONLY_ELIGIBILITY_AUDIT','Audit failed')
    require(len(a['runs'])==22 and a['original_development']==13632 and a['B1_alternative_eligible']==3408 and a['B1_native_QA_eligible']==1704,'Eligibility count drift')
    require(a['validation_outcomes_opened']==a['protected_outcomes_opened']==a['new_feature_rows_created']==a['models_executed']==a['simulation_calls']==0,'Scope violation')
    split=csv_rows('B3_SPLIT_AND_SAMPLE_PLAN.csv');require(len(split)==88 and len({(r['fold'],r['run_id']) for r in split})==88,'Duplicate/missing split metadata')
    for f in a['folds']:
        rows=[r for r in split if int(r['fold'])==f['fold']]
        for key,col in [('M0_training','M0_train'),('Mdiv_training','Mdiv_train'),('Mfull_training','Mfull_train'),('original_held','original_held'),('B1_held_transfer','B1_transfer_held')]:
            require(sum(int(r[col]) for r in rows)==f[key],'Fold/sample-plan count mismatch')
        for r in rows:
            require((r['group_role']=='TRAIN_GROUP')==(r['group_id'] in f['train_groups']),'Split group mismatch')
            if r['QA_only']=='True':require(all(int(r[c])==0 for c in ('M0_train','Mdiv_train','Mfull_train','original_held','B1_transfer_held')),'NREF duplicate included')
    schema=read(HOME/'B3_FEATURE_SCHEMA.json');fields=schema['fields'];compact=[f for f in fields if f['encoding']=='RECOMMENDED_COMPACT' and f['model_input']]
    require(len(compact)==4 and len({f['field'] for f in compact})==4,'Compact redundant/missing predictors')
    require(schema['postdecision_action_features']==29 and schema['predecision_action_features']==27,'Feature count drift')
    require(next(f for f in fields if f['field']=='a__cooling_block_present')['model_input'] is False,'Redundant mask became predictor')
    availability=csv_rows('B3_FEATURE_AVAILABILITY_MATRIX.csv');require(len(availability)==210,'Missing availability matrix entries')
    require(len({(r['field'],r['source_policy_type']) for r in availability})==210,'Duplicate field-policy entry')
    for r in availability:
        require(int(r['available_origin_count'])==(6816 if r['source_policy_type'].startswith('ORIGINAL') else 1704),'Availability count mismatch')
        require(r['model_input']==str(r['field']!='a__cooling_block_present'),'Presence-mask role mismatch')
    # Fabricated proof that dropping presence loses no supported schedule information.
    from .semantics_tests import fabricated_compact,fabricated_expand
    cases=0
    for start in range(6):
        for stop in range(start+1,7):
            for delta in (-.25,-.5):
                for latch in (0,1):
                    slots=[delta if start<=i<stop else None for i in range(6)];present,d,on,off,c=fabricated_compact(slots,latch)
                    require(present==int(off>0) and fabricated_expand((int(off>0),d,on,off,c))==slots,'Minimal compact representation failed');cases+=1
    require(fabricated_expand((int(0>0),0,0,0,0))==[None]*6,'Native mask reconstruction failed')
    test=read(HOME/'FABRICATED_SEMANTICS_RESULT.json');require(test['status']=='PASS' and test['tests']==14 and test['errors']==test['failures']==0,'Fabricated design tests failed')
    alias=read(HOME/'B3_PLAN_ALIASING_AUDIT.json');require(alias['fold_manifests_identical'] and all(r['common25_source_equivalent_within_1e_7'] for r in alias['comparisons']),'Aliasing/fold proof changed')
    for row in csv_rows('B3_SOURCE_INDEX.csv'):
        p=row['absolute_path'];require(hashes[p]==row['sha256'] and row['symbol'] in __import__('pathlib').Path(p).read_text(encoding='utf-8-sig').splitlines()[int(row['line'])-1],'Code reference changed')
    model=WORKSPACE/'experiments/five_model_hvac16_v1_0_0';frozen=read(model/'FROZEN_TRAINING_MANIFEST.json')
    for name,h in frozen['core_code_hashes'].items():require(sha(model/name)==h,'Frozen historical model source changed')
    if (HOME/'B3_DESIGN_FREEZE.json').exists():
        for p,h in read(HOME/'B3_DESIGN_FREEZE.json')['files'].items():require(sha(HOME/p)==h,'Frozen B3 planning artifact changed: '+p)
    if (HOME/'B3_DELIVERY_MANIFEST.json').exists():
        files=inventory(HOME);files.pop('B3_DELIVERY_MANIFEST.json');require(files==read(HOME/'B3_DELIVERY_MANIFEST.json')['files'],'B3 delivery scope/hash changed')
    return dict(status='PASS_READ_ONLY_B3_VERIFICATION',source_files_verified=len(hashes),audited_development_runs=22,
        original_development_origins=13632,B1_alternative_eligible_origins=3408,NREF_QA_origins=1704,matched_outer_folds=4,
        split_metadata_rows=88,availability_metadata_rows=210,fabricated_tests_passed=14,minimal_encoding_cases=cases+1,
        new_feature_matrix_rows=0,models_executed=0,simulations_executed=0,validation_outcome_files_opened=0,protected_outcome_files_opened=0)

def seal():
    result=verify()
    write_new(HOME/'B3_DESIGN_FREEZE.json',dict(version='B3_DESIGN_1.0.0',status='PLANNING_ONLY_READY_FOR_SEPARATE_IMPLEMENTATION_APPROVAL',
        simulation_authority=False,model_execution_authority=False,dataset_release_authority=False,files=inventory(HOME)))
    write_new(HOME/'B3_FINAL_VERIFICATION.json',dict(**result,design_freeze_sha256=sha(HOME/'B3_DESIGN_FREEZE.json')))
    write_new(HOME/'B3_DELIVERY_MANIFEST.json',dict(version='B3_DELIVERY_1.0.0',files=inventory(HOME)))
    return verify()

if __name__=='__main__':
    import argparse
    from hvac_control_expansion_b2f_v1.tests import offline_guard
    p=argparse.ArgumentParser();p.add_argument('--seal',action='store_true');args=p.parse_args()
    with offline_guard():print(json.dumps(seal() if args.seal else verify(),indent=2))
