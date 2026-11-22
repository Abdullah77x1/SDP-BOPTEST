"""Offline-only CLI. No simulator, deployment, training or continuation action exists."""
import argparse,json
from . import HOME,BATCH
from .tests import offline_guard
from .packaging import read,sha,require,verify_package,finalize

def main():
    p=argparse.ArgumentParser();p.add_argument('action',choices=['test','verify','package']);p.add_argument('--output')
    a=p.parse_args()
    with offline_guard():
        if a.action=='test':
            from .tests import run
            raise SystemExit(0 if run() else 1)
        if a.action=='package':
            from pathlib import Path
            require(a.output,'Explicit fresh output directory required')
            out=Path(a.output).resolve();require(out.is_relative_to(HOME.resolve()),'B2F packaging output must remain in the new B2F directory')
            print(json.dumps(finalize(BATCH,read(HOME/'PACKAGING_SCOPE_PLAN.json'),out),indent=2));return
        from .verification import verify_delivery
        historical=verify_delivery();package=verify_package(BATCH,HOME/'corrected_pilot_package')
        frozen=read(HOME/'B2F_IMPLEMENTATION_MANIFEST.json')
        for name,h in frozen['files'].items():require(sha(HOME/name)==h,'B2F frozen artifact changed: '+name)
        import csv
        with (HOME/'SOURCE_HASHES.csv').open(encoding='utf-8') as f:
            for row in csv.DictReader(f):require(sha(row['absolute_path'])==row['sha256'],'Bound input/source changed: '+row['absolute_path'])
        print(json.dumps(dict(historical=historical,corrected_package=package,new_implementation='FROZEN_HASHES_PASS',simulator_calls=0),indent=2))

if __name__=='__main__':main()
