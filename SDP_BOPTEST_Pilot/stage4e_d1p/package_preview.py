"""DEVELOPMENT_ONLY local packaging. No upload, sharing or training release."""
import csv,hashlib,importlib.util,json,socket,subprocess,zipfile
from pathlib import Path
from unittest.mock import patch
from .build import HOME,PACKAGE,STATUS
from stage4e_d1_v2.runner import ROOT,read,save_new,sha,utc,verify_frozen

def main():
    assert read(PACKAGE/'QA_RESULTS.json')['classification']=='PASS'
    assert read(PACKAGE/'OFFLINE_TEST_SUMMARY.json')['passed']
    assert verify_frozen()=='ec9c64f9abffcda7095d537e375eda7bb8f6b6d367aa1aa2238bcc606bcbeb5c'
    original=ROOT/'stage4e_d1_v2_execution/RESULTS_DELIVERY_MANIFEST.json'
    assert sha(original)=='881c880b601f35b5132991935856b7e3b191e004448c5b4d0bde46ccd77dc596'
    for name,digest in read(original)['files'].items():assert sha(ROOT/name)==digest,name
    entries={}
    for path in sorted(PACKAGE.iterdir()):
        if not path.is_file():continue
        entry={'sha256':sha(path),'bytes':path.stat().st_size}
        if path.suffix=='.csv':
            with path.open(encoding='utf-8',newline='') as f:
                reader=csv.reader(f);entry['columns']=len(next(reader));entry['data_rows']=sum(1 for _ in reader)
        if path.suffix=='.jsonl':entry['records']=sum(1 for _ in path.open(encoding='utf-8'))
        entries[path.name]=entry
    manifest=PACKAGE/'DATASET_MANIFEST.json'
    save_new(manifest,{**STATUS,'dataset_version':'SDP_STAGE4E_D1P_PREVIEW_1.0.0','created_utc':utc(),
        'source_campaign':'SDP_STAGE4E_D1_V2_QUALIFICATION_2.1.0',
        'source_proposal_sha256':verify_frozen(),'source_results_manifest_sha256':sha(original),
        'observational_rows':3408,'feature_columns':168,'target_columns':8,'metadata_columns':27,
        'numeric_target_values':27264,'action_eligibility_counts':{'300':3408,'600':3366,'900':3359,'1800':3338},
        'dependency_groups':['qualification_cool_146','qualification_heat_44'],'all_partitions':'development',
        'independent_final_test_set':False,'QA':'PASS','files':entries,
        'exclusions_from_files_hash_map':['DATASET_MANIFEST.json (self)','MANIFEST_SHA256.txt (self digest)','SHA256SUMS.txt (checksum list)'],
        'simulator_executions':0,'model_fitting_tuning_scoring':False,'automatically_shared':False,'training_release':False})
    digest=sha(manifest)
    with (PACKAGE/'MANIFEST_SHA256.txt').open('x',encoding='utf-8') as f:
        f.write(digest+'  DATASET_MANIFEST.json\n# DEVELOPMENT_ONLY / NON_FINAL_EVALUATION / LOCAL_REVIEW_ONLY\n')
    with (PACKAGE/'SHA256SUMS.txt').open('x',encoding='utf-8') as f:
        f.write('# DEVELOPMENT_ONLY / NON_FINAL_EVALUATION / LOCAL_REVIEW_ONLY\n')
        for path in sorted(PACKAGE.iterdir()):
            if path.is_file() and path.name!='SHA256SUMS.txt':f.write(sha(path)+'  '+path.name+'\n')
    module_spec=importlib.util.spec_from_file_location('local_development_preview_loader',PACKAGE/'load_preview.py')
    module=importlib.util.module_from_spec(module_spec);module_spec.loader.exec_module(module)
    loaded=module.load_preview()
    assert len(loaded['X'])==len(loaded['Y'])==3408 and len(loaded['X'][0])==168 and len(loaded['Y'][0])==8
    assert set(loaded['groups'])=={'qualification_cool_146','qualification_heat_44'}
    archive=HOME/(PACKAGE.name+'.zip')
    with zipfile.ZipFile(archive,'x',compression=zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        for path in sorted(PACKAGE.iterdir()):
            if path.is_file():z.write(path,arcname=PACKAGE.name+'/'+path.name)
    with zipfile.ZipFile(archive) as z:
        assert z.testzip() is None
        for name,entry in entries.items():assert hashlib.sha256(z.read(PACKAGE.name+'/'+name)).hexdigest()==entry['sha256']
        assert hashlib.sha256(z.read(PACKAGE.name+'/DATASET_MANIFEST.json')).hexdigest()==digest
    save_new(HOME/'FINAL_PACKAGING_VERIFICATION.json',{**STATUS,'classification':'PASS','utc':utc(),
        'minimal_loader_executed_offline':True,'loaded_rows':3408,'loaded_X_shape':[3408,168],'loaded_Y_shape':[3408,8],
        'all_package_file_hashes_verified':True,'zip_CRC_and_file_hashes_verified':True,
        'dataset_manifest_sha256':digest,'zip_sha256':sha(archive),'zip_bytes':archive.stat().st_size,
        'source_proposal_and_results_unchanged':True,'automatically_shared':False,'training_release':False})
    with (HOME/'PREVIEW_DELIVERY_RECEIPT.md').open('x',encoding='utf-8') as f:
        f.write('# DEVELOPMENT_ONLY preview delivery receipt\n\nNON_FINAL_EVALUATION. LOCAL_REVIEW_ONLY. Not shared or released for training.\n\n')
        f.write('Dataset manifest SHA-256: `'+digest+'`.\n\nZIP SHA-256: `'+sha(archive)+'`.\n\n')
        f.write('QA PASS; 3408 rows, 168 features, eight targets, 27264 label values. Action eligibility 3408/3366/3359/3338. Minimal loader and ZIP integrity verified offline.\n')
    print(json.dumps(read(HOME/'FINAL_PACKAGING_VERIFICATION.json'),indent=2))

if __name__=='__main__':
    with patch.object(socket.socket,'connect',side_effect=RuntimeError('Network forbidden in D1P')),patch.object(subprocess,'Popen',side_effect=RuntimeError('Docker/process dispatch forbidden in D1P')):main()
