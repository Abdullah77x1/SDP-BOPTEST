"""Versioned approval wrapper reusing v1 collection/ledger/finalization unchanged.

This module creates no permission. execute() requires a NEW externally supplied
manifest-bound live approval. The current v2 request authorizes offline work only.
"""
from . import HOME,RID,VERSION,STATE
from .integrity import (require_only,manifest,run_definition,verify_frozen,preservation,
    deny_existing_c45_claim,historical_integrity)
from hvac_control_expansion_b2g_v1.launcher import C45Registry,execute_one,real_factory,validate_real
from hvac_control_expansion_b2f_v1.packaging import read,sha,digest,require,write_new

def authorize(approval_path,ids):
    require_only(ids);require(approval_path is not None,'NOT AUTHORIZED FOR EXECUTION: new explicit live approval required')
    a=read(approval_path)
    require(a.get('status')=='EXPLICITLY_AUTHORIZED_FOR_LIVE_C45','Readiness/offline request is not execution permission')
    identity=verify_frozen();m=manifest()
    expected=dict(version=VERSION,status='EXPLICITLY_AUTHORIZED_FOR_LIVE_C45',implementation_sha256=identity,
        run_manifest_sha256=sha(HOME/'RUN_MANIFEST.json'),campaign_sha256=digest(m),run_ids=[RID],maximum_instances=1,maximum_advances=864,
        request_sha256=sha(HOME/'REQUEST_SOURCE.json'))
    require(all(a.get(k)==v for k,v in expected.items()),'Exact new v2 C45 approval/source/budget mismatch')
    require(isinstance(a.get('user_authorization_text'),str) and a['user_authorization_text'].strip(),'Explicit new user authorization record missing')
    require(read(HOME/'OFFLINE_QUALIFICATION.json')['status']=='PASS','Qualification not passed')
    return dict(**expected,authorization_sha256=sha(approval_path))

def execute(approval_path=None):
    # Gate FIRST: absent approval cannot contact runtime, initialize a ledger or deploy.
    binding=authorize(approval_path,[RID]);deny_existing_c45_claim()
    history=historical_integrity();frozen_baseline=read(HOME/'LEDGER_BASELINE.json')
    from stage4e_d1_v2.runtime import verify_runtime
    runtime=verify_runtime();require(runtime['classification']=='PASS','Current runtime rejected')
    if not STATE.exists():C45Registry.create(STATE,frozen_baseline)
    registry=C45Registry(STATE,frozen_baseline);registry.verify_evidence();registry.check_selection([run_definition()])
    try:
        output=execute_one(manifest(),run_definition(),registry,dict(v2_authorization=binding,runtime=runtime,historical_integrity=history),
            real_factory,'AUTHORIZED_B2G_V2_C45_ONLY',validate_real,HOME/'corrected_c45_package')
    except BaseException as exc:
        output=dict(run_id=RID,status='FAILED_OR_INTERRUPTED_NO_RETRY',error=f'{type(exc).__name__}: {exc}',automatic_retry=False)
    write_new(HOME/'LIVE_EXECUTION.json',output);write_new(HOME/'LEDGER_INVENTORY_AFTER.json',registry.inventory())
    write_new(HOME/'HISTORICAL_PRESERVATION_AFTER.json',historical_integrity())
    return output
