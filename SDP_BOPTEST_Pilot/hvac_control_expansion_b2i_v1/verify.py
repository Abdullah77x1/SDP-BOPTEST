"""Read-only reconstruction of sealed evidence, ledgers, and derived analysis."""
from pathlib import Path
from . import HOME,IDS,STATE
from .integrity import verify_frozen,historical
from .launcher import G146Registry
from .reports import derive
from hvac_control_expansion_b2f_v1.packaging import read,sha,require,inventory,verify_package,write_new

def verify():
    identity=verify_frozen();r=G146Registry(STATE,read(HOME/'LEDGER_BASELINE.json'));r.verify_evidence()
    require([s['status'] for s in r.inventory()]==['CONSUMED_COMPLETED']*6,'Six effective slots not completed')
    outputs=read(HOME/'LIVE_EXECUTION.json');require(outputs['status']=='PASS_ALL_THREE_G146','Campaign incomplete')
    for o in outputs['runs']:require(verify_package(o['source_batch'],o['package_path'])==o['corrected_finalization'],'Corrected package changed')
    groups,metadata=derive();require(groups==read(HOME/'ANALYSIS.json') and metadata==read(HOME/'ORIGIN_METADATA_REVIEW.json'),'Derived evidence mismatch')
    historical()
    if (HOME/'DELIVERY_MANIFEST.json').exists():
        data=inventory(HOME);actual=data.pop('DELIVERY_MANIFEST.json');require(data==read(HOME/'DELIVERY_MANIFEST.json')['files'],'Delivered artifact scope/hash changed')
    return dict(status='PASS_READ_ONLY',implementation_sha256=identity,real_G146_runs=3,all_B1_slots_completed=6,live_requests=0,models_run=0,dataset_released=False)

def seal_delivery():
    result=verify();write_new(HOME/'FINAL_VERIFICATION.json',result)
    write_new(HOME/'DELIVERY_MANIFEST.json',dict(version='B2I_DELIVERY_1.0.0',files=inventory(HOME)))
    return verify()
