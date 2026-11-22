"""One-time offline freeze. Refuses to overwrite an existing proposal."""
import json
import sys
from datetime import datetime,timezone
from .plan import ROOT,HERE,sha,save_new,configuration


def main():
    if (HERE/'FROZEN_MANIFEST.json').exists():raise FileExistsError('Already frozen; create an isolated new revision')
    previous=json.loads((HERE/'PRESERVED_DEPENDENCY_HASHES.json').read_text())
    for path,digest in previous.items():
        if sha(ROOT/path)!=digest:raise RuntimeError('Preserved file changed: '+path)
    if json.loads((HERE/'campaign.json').read_text())!=configuration():raise RuntimeError('Configuration mismatch')
    ledger=json.loads((HERE/'attempt_ledger.json').read_text())
    if len(ledger['attempts'])!=4 or any(r['status']!='UNUSED' for r in ledger['attempts']):raise RuntimeError('Ledger not unused')
    if (HERE/'campaign_evidence').exists():raise RuntimeError('Unexpected real campaign directory')
    excluded={'FROZEN_MANIFEST.json','PROPOSAL_SHA256.txt','DELIVERY_MANIFEST.json','FINAL_VERIFICATION.json'}
    files={f.relative_to(ROOT).as_posix():sha(f) for f in HERE.iterdir() if f.is_file() and f.name not in excluded}
    files.update(previous)
    names=['STAGE4E_QUALIFICATION_FROZEN_PROTOCOL.md','STAGE4E_FOUR_RUN_SCHEDULE.csv',
        'STAGE4E_CAUSAL_COLLECTION_CONTRACT.md','STAGE4E_DATA_VALIDITY_GATES.md',
        'STAGE4E_FUTURE_SPLIT_REGISTRY.md','STAGE4E_D0_CONTRACT_REVIEW.md',
        'run_stage4e_d0.py','tests/test_stage4e_d0.py',
        'deployment/compose.localhost.override.yml',
        'deployment/official_v0.9.0/project1-boptest-0.9.0/docker-compose.yml']
    source=json.loads((HERE/'SOURCE_FEASIBILITY_REVIEW.json').read_text())
    for name,d in source['source_hashes'].items():
        name='deployment/official_v0.9.0/project1-boptest-0.9.0/'+name
        if sha(ROOT/name)!=d:raise RuntimeError('Pinned source changed')
        files[name]=d
    files.update({name:sha(ROOT/name) for name in names})
    manifest={'protocol':'SDP_STAGE4E_D0_1.0.0','frozen_utc':datetime.now(timezone.utc).isoformat(),
        'classification':'FROZEN_OFFLINE_PROPOSAL_NOT_EXECUTION_AUTHORIZATION',
        'runtime_prerequisites_qualified':False,'ledger_attempts_unused':4,
        'maximum_future_advances':3456,'python_version':sys.version,
        'software_tests_passed':112,'new_D0_tests_passed':33,
        'earlier_artifacts_unchanged':len(previous),'files':dict(sorted(files.items())),
        'companion_report_rule':'Authorization review/handoff and seal are post-freeze companions, covered by DELIVERY_MANIFEST; authorization binds this primary manifest SHA-256.'}
    save_new(HERE/'FROZEN_MANIFEST.json',manifest)
    digest=sha(HERE/'FROZEN_MANIFEST.json')
    with (HERE/'PROPOSAL_SHA256.txt').open('x',encoding='ascii') as f:f.write(digest+'\n')
    print(json.dumps({'proposal_sha256':digest,'frozen_files':len(files),
        'execution_authorized':False,'runtime_qualified':False,'attempts_unused':4},indent=2))


if __name__=='__main__':main()
