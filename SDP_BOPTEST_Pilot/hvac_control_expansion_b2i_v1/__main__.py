import argparse,json
from .integrity import freeze
from hvac_control_expansion_b2f_v1.tests import offline_guard
p=argparse.ArgumentParser();p.add_argument('command',choices=['qualify','freeze','execute','report','verify','seal']);p.add_argument('--request');a=p.parse_args()
if a.command=='execute':
    from .launcher import execute
    result=execute()
else:
    with offline_guard():
        if a.command=='qualify':
            from .tests import qualify
            result=qualify()
        elif a.command=='freeze':result=freeze(a.request)
        elif a.command=='report':
            from .reports import publish
            result=publish()
        else:
            from .verify import verify,seal_delivery
            result=verify() if a.command=='verify' else seal_delivery()
print(json.dumps(result,indent=2))
