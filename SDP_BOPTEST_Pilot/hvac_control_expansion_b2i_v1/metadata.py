"""Review saved origin-known plans; never constructs features or targets."""
import json
from hvac_control_expansion_v1.campaign import action_path
from hvac_control_expansion_b2f_v1.packaging import read,digest,require

def verify_origin_metadata(directory,run):
    from pathlib import Path
    d=Path(directory);steps=[json.loads(s) for s in (d/'steps.jsonl').read_text().splitlines()]
    receipts={r['order']:r for r in map(json.loads,(d/'receipt_order.jsonl').read_text().splitlines())}
    for r in steps:
        t=r['start'];planned=action_path(run,t);known=r['known_path']
        require(r['proposed_path']==planned,'Nominal origin plan altered')
        require(len(known)==len(planned) and known[0]['command']==r['applied_command'],'Issued current command not encoded')
        for i,p in enumerate(known):
            require(p['known_at_sim']<=t and p['effective_available_at_sim']<=t,'Future plan unavailable at origin')
            require(p['start']==planned[i]['start'] and p['end']==planned[i]['end'],'Plan clock changed')
            if i:require(p['command']==planned[i]['command'] and p['source']=='frozen_nominal_plan','Future realized veto leaked into plan')
        cut=receipts[r['origin_cutoff_order']]
        require(cut['known_path']==known and cut['issued_command']==r['applied_command'],'Saved plan not bound to cutoff')
        require(r['observation_received_order']<r['origin_cutoff_order'] and r['forecast_received_order']<r['origin_cutoff_order']<r['endpoint_received_order'],'Future receipt leaked')
        require(r['future_safety_veto_unknown_at_origin'] and r['posthoc_resolution_is_not_an_origin_feature'],'Leakage annotation changed')
    return dict(status='PASS_AS_ISSUED_ORIGIN_METADATA',origins=len(steps),nominal_future_not_realized_veto=True,features_built=0,models_run=0)
