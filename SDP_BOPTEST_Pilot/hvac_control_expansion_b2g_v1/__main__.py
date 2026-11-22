"""Explicit bounded lifecycle; qualification failure and consumed slots fail closed."""
import argparse,json
from . import HOME,RID,STATE,BATCH_ID
from hvac_control_expansion_b2f_v1.packaging import read,sha,require,write_new,verify_package

def main():
    p=argparse.ArgumentParser();p.add_argument('action',choices=['qualify','freeze','execute','analyze','report','verify']);p.add_argument('--request');a=p.parse_args()
    if a.action=='qualify':
        from .tests import qualify
        result=qualify();print(json.dumps(result,indent=2));raise SystemExit(0 if result['status']=='PASS' else 1)
    if a.action=='freeze':
        require(a.request,'Exact user request required')
        from .integrity import freeze
        print(json.dumps(freeze(a.request),indent=2));return
    if a.action=='execute':
        from .launcher import execute
        result=execute();print(json.dumps(result,indent=2));return
    if a.action=='analyze':
        from .analysis import analyze
        from hvac_control_expansion_b2f_v1.tests import offline_guard
        with offline_guard():result=analyze(read(HOME/'LIVE_EXECUTION.json'))
        print(json.dumps(result,indent=2));return
    if a.action=='report':
        from .reporting import publish,seal_delivery
        publish();seal_delivery();return
    from .integrity import verify_frozen,historical_integrity
    from .launcher import C45Registry
    from hvac_control_expansion_b2f_v1.tests import offline_guard
    with offline_guard():
        identity=verify_frozen();history=historical_integrity();reg=C45Registry(STATE,read(HOME/'LEDGER_BASELINE.json'));reg.verify_evidence()
        package=verify_package(STATE/'batches'/BATCH_ID,HOME/'corrected_c45_package')
        if (HOME/'DELIVERY_MANIFEST.json').exists():
            for name,h in read(HOME/'DELIVERY_MANIFEST.json')['files'].items():require(sha(HOME/name)==h,'Delivery changed: '+name)
        print(json.dumps(dict(implementation_sha256=identity,historical_preservation='PASS',ledger='PASS',corrected_finalization=package,live_requests=0),indent=2))

if __name__=='__main__':main()
