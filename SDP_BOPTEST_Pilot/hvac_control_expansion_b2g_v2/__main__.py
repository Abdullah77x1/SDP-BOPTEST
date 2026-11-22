"""Offline readiness CLI; live execution requires a NEW separately supplied approval."""
import argparse,json
from . import HOME,STATE
from hvac_control_expansion_b2f_v1.packaging import read,sha,require
from hvac_control_expansion_b2f_v1.tests import offline_guard

def main():
    p=argparse.ArgumentParser();p.add_argument('action',choices=['targeted','qualify','freeze','verify','execute']);p.add_argument('--request');p.add_argument('--approval');a=p.parse_args()
    if a.action=='execute':
        from .launcher import execute
        # No authority is generated here. Missing/readiness-only approval is rejected first.
        print(json.dumps(execute(a.approval),indent=2));return
    with offline_guard():
        if a.action in ('targeted','qualify'):
            from .tests import targeted,qualify
            result=targeted() if a.action=='targeted' else qualify()
            print(json.dumps(result,indent=2));raise SystemExit(0 if result['status']=='PASS' else 1)
        if a.action=='freeze':
            from .integrity import freeze
            require(a.request,'Exact offline-only user request required');print(json.dumps(freeze(a.request),indent=2));return
        from .integrity import verify_frozen,preservation,runtime_requirements
        identity=verify_frozen();history=preservation();runtime_requirements()
        if (HOME/'DELIVERY_MANIFEST.json').exists():
            for name,h in read(HOME/'DELIVERY_MANIFEST.json')['files'].items():require(sha(HOME/name)==h,'V2 delivery hash changed: '+name)
        print(json.dumps(dict(status='PASS_READ_ONLY',implementation_sha256=identity,historical_preservation=history['status'],
            execution_permission=read(HOME/'EXECUTION_READINESS.json')['permission'],Docker_contacted=False,simulator_operations=0),indent=2))

if __name__=='__main__':main()
