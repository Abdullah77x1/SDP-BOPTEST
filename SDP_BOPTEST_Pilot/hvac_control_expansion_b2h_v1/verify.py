"""Repeatable read-only verification and analysis reconstruction; never calls BOPTEST."""
import csv
from . import HOME,V2,PILOT,RID
from .postflight import verify_historical
from .analysis import analyze
from .comfort_details import derive
from hvac_control_expansion_b2f_v1.packaging import read,sha,require,inventory,chain,verify_package

def verify():
    if (HOME/'DELIVERY_MANIFEST.json').exists():
        m=read(HOME/'DELIVERY_MANIFEST.json')
        for name,h in m['files'].items():require(sha(HOME/name)==h,'B2-H delivery hash mismatch: '+name)
        actual={p.relative_to(HOME).as_posix() for p in HOME.rglob('*') if p.is_file() and '__pycache__' not in p.parts and p.name!='DELIVERY_MANIFEST.json'}
        require(actual==set(m['files']),'Unexpected/missing B2-H deliverable')
    raw=read(HOME/'RAW_C45_ARTIFACT_INDEX.json');require(inventory(raw['source_root'])==raw['files'],'C45 raw indexed scope/hash mismatch')
    require(sha(raw['source_seal_path'])==raw['source_seal_sha256'],'C45 seal changed')
    require(chain(__import__('pathlib').Path(raw['source_root'])/'receipt_order.jsonl')==read(HOME/'POSTRUN_VERIFICATION.json')['receipt_chain'],'C45 receipt chain changed')
    package=verify_package(V2/'runtime_state/batches/B2G_G174_C45_ONLY',V2/'corrected_c45_package')
    ledger=read(HOME/'CONTINUATION_LEDGER_INDEX.json')
    require(sha(ledger['parent_path'])==ledger['parent_sha256'] and sha(ledger['extension_path'])==ledger['extension_sha256'],'Parent/extension ledger changed')
    with (HOME/'SOURCE_HASHES.csv').open() as f:
        for row in csv.DictReader(f):require(sha(row['absolute_path'])==row['sha256'],'Source/configuration changed: '+row['absolute_path'])
    a=analyze(read(V2/'LIVE_EXECUTION.json'),verify_outputs=True);derive(verify=True)
    old=PILOT/'runtime_state/batches/B1_G174_INITIAL_PILOT'
    dirs=[old/'B1V01_G174_NREF',old/'B1V01_G174_C15',V2/'runtime_state/batches/B2G_G174_C45_ONLY'/RID]
    for e,d in zip(a['full_energy'],dirs):
        audit=read(d/'energy_audit.json')
        require(abs(e['electric_kwh']*3600000-audit['electrical_j'])<=audit['internal_tolerance_j'],'Analysis/audited native-energy mismatch')
    h=verify_historical()
    return dict(status='PASS_READ_ONLY',raw_files_verified=len(raw['files']),corrected_finalization=package['status'],
        data_analysis_reconstructed=True,historical_preservation=h['status'],C45_consumed=True,G146_initiated=0,live_requests=0,models_executed=0)

if __name__=='__main__':
    import json
    from hvac_control_expansion_b2f_v1.tests import offline_guard
    with offline_guard():print(json.dumps(verify(),indent=2))
