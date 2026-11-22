"""Read-only historical/source and configuration review. No API or Docker."""
import json,math
from dataclasses import asdict
from .runner import ROOT,HERE,read,save_new,sha
from .validation import REFERENCE,HISTORY_POINTS

def main():
    preserved={}
    for name in ('stage4e_d0/FROZEN_MANIFEST.json','stage4e_d1/FINAL_ARTIFACT_MANIFEST.json',
                 'stage4e_d1r/FINAL_ARTIFACT_MANIFEST.json','stage4e_d1r_bm01/FINAL_ARTIFACT_MANIFEST.json',
                 'stage4e_runtime_preflight/FINAL_ARTIFACT_MANIFEST.json'):
        items=read(ROOT/name)['files']
        for path,digest in items.items():assert sha(ROOT/path)==digest,(name,path)
        preserved[name]={'sha256':sha(ROOT/name),'entries_verified':len(items)}
    for path,digest in read(ROOT/'stage4e_d0/PRESERVED_DEPENDENCY_HASHES.json').items():assert sha(ROOT/path)==digest
    assert asdict(REFERENCE)==read(ROOT/'stage4e_d1r/REFERENCE_BINDING.json')['reference']
    for source in read(ROOT/'stage4e_d1r/SOURCE_LOCATORS.json')['sources']:
        assert sha(ROOT/source['path'])==source['sha256']
    a=read(ROOT/'evidence/local_matched_AB/A/native_results.json')
    availability={}
    for key in HISTORY_POINTS:
        values=a.get(key,[])
        availability[key]={'Stage4C_actual_samples':len(values),'complete_finite':len(values)==len(a['time']) and all(math.isfinite(x) for x in values)}
        assert availability[key]['complete_finite']
    old=read(ROOT/'stage4e_d0/campaign.json');new=read(HERE/'campaign.json')
    for key in old:
        if key not in ('protocol','runs'):assert old[key]==new[key]
    for x,y in zip(old['runs'],new['runs']):
        assert {k:v for k,v in x.items() if k not in ('attempt_id','evidence_directory')}=={k:v for k,v in y.items() if k not in ('attempt_id','evidence_directory')}
    assert not (HERE/'campaign_evidence').exists()
    save_new(HERE/'OFFLINE_EVIDENCE_AUDIT.json',{'classification':'PASS_OFFLINE_PREPARATION_ONLY',
        'preserved_manifests':preserved,'native_reference_bound_to_preserved_XML_and_source':True,
        'actual_Stage4C_native_history_availability':availability,
        'BM01_scored_gas_history_requested':False,'BM01_missing_gas_not_invented':True,
        'complete_v2_combined_reporting_request_runtime_tested':False,
        'original_D1':'FAILED','original_Q01_N':'CONSUMED_FAILED','original_unused':['Q02_X','Q03_N','Q04_X'],
        'new_attempts_all_unused':True,'BOPTEST_execution':False,'Docker_commands':0,
        'supervised_datasets_generated':False,'ML_training':False})

if __name__=='__main__':main()
