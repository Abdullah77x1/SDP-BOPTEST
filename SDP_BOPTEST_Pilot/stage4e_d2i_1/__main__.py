"""Default is offline metadata validation. No default client or process launch."""
import argparse,json
from .common import HOME,read
from .manifest import validate_manifest
from .planner import dry_run

def main(argv=None):
    p=argparse.ArgumentParser(description='D2 offline tools; future-live requires separately granted authorization')
    p.add_argument('operation',nargs='?',default='validate',choices=('validate','dry-run','mock-tests','future-live'))
    p.add_argument('--config',default=str(HOME/'campaign_manifest.json'))
    p.add_argument('--approval');p.add_argument('--prerequisite');p.add_argument('--run-ids',nargs='+')
    a=p.parse_args(argv)
    if a.operation=='mock-tests':
        from .tests import run_tests
        return 0 if run_tests().wasSuccessful() else 1
    config=read(a.config)
    if a.operation=='validate':result=validate_manifest(config)
    elif a.operation=='dry-run':result=dry_run(config)
    else:
        if not a.approval or not a.run_ids:p.error('future-live requires explicit --approval and --run-ids; not authorized in D2I-1')
        from .live import future_live
        result=future_live(config,a.run_ids,a.approval,a.prerequisite)
    print(json.dumps(result,indent=2,allow_nan=False));return 0

if __name__=='__main__':raise SystemExit(main())
