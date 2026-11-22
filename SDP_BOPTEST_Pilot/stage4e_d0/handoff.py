"""Offline handoff for FUTURE qualified evidence; no data released in D0."""
import json
from pathlib import Path
from stage4e.dataset import Run,Boundary,FeatureSpec,build_rows,ContractError
from .plan import POINTS,sha


def verify_artifacts(directory):
    directory=Path(directory)
    manifest=json.loads((directory/'ARTIFACT_MANIFEST.json').read_text())
    for name,digest in manifest['files'].items():
        target=(directory/name).resolve()
        if not target.is_relative_to(directory.resolve()):raise ContractError('Unsafe evidence manifest path')
        if sha(target)!=digest:raise ContractError('Evidence integrity failure')


def read_qualified_run(campaign,run_config):
    campaign=Path(campaign);verify_artifacts(campaign)
    result=json.loads((campaign/'CAMPAIGN_COMPLETED.json').read_text())
    if result['classification']!='PASS_QUALIFICATION':
        raise ContractError('Failed/inconclusive campaign remains quarantined')
    d=campaign/run_config['attempt_id'];verify_artifacts(d)
    started=json.loads((d/'ATTEMPT_STARTED.json').read_text())
    if started['run']!=run_config:raise ContractError('Run configuration differs from immutable attempt record')
    completion=json.loads((d/'RUN_COMPLETED.json').read_text())
    if completion['classification']!='PASS_VALID_RAW' or completion['cleanup']!='STOP_ACK_VERIFIED':
        raise ContractError('Unqualified/interrupted run remains quarantined')
    records=[json.loads(s) for s in (d/'steps.jsonl').read_text().splitlines()]
    bounds=[]
    for i,record in enumerate(records):
        f=json.loads((d/f'forecast_{i:04d}.json').read_text())
        cutoff=record['origin_cutoff_order']
        if not (record['observation_received_order']<cutoff and f['received_order']<cutoff
                and f['received_order']==record['forecast_received_order']
                and record['endpoint_received_order']>cutoff and f['issued_at_sim']==record['start']):
            raise ContractError('Receipt order violates origin knowledge cutoff')
        for name in POINTS:
            bounds.extend(Boundary(name,record['start'],t,v)
                for t,v in zip(f['data']['time'],f['data'][name]))
    run=Run(run_config['attempt_id'],run_config['scenario'],run_config['mode'],
        run_config['attempt_id']+'_fresh_init','bestest_air_v090_weather',run_config['group_id'],
        'development',run_config['start'],run_config['end'],run_config['warmup_start'],
        json.loads((d/'endpoints.json').read_text()),json.loads((d/'native_results.json').read_text()),
        boundaries=bounds,provenance='future_qualification_development_only',control_history=records)
    return run


def known_path_annotations(origin,record,records):
    paths={};eligible={}
    for horizon in (300,600,900,1800):
        path=record['known_path'][:horizon//300]
        paths[horizon]=path
        eligible[horizon]=len(path)==horizon//300 and all(
            p['start']==origin+i*300 and p['command']==records[p['start']]['applied_command']
            for i,p in enumerate(path))
    return paths,eligible


def development_rows(campaign,run_config,spec=FeatureSpec()):
    run=read_qualified_run(campaign,run_config)
    rows=build_rows(run,spec,task='observational')
    records={r['start']:r for r in run.control_history}
    for row in rows:
        origin=row['origin_time'];record=records[origin]
        row['origin_cutoff_order']=record['origin_cutoff_order']
        row['action_conditioned_paths'],row['exact_applied_path_eligible']=known_path_annotations(origin,record,records)
        # Actual future commands are consulted ONLY for eligibility, never copied
        # into features or used to repair an unavailable proposed path.
    return rows
