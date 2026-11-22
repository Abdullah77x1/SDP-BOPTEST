"""Explicit CLI: tests and freeze are offline; pilot alone can deploy."""
import argparse,json
from . import HOME,VERSION
from .campaign import canonical_manifest,PILOT
from stage4e_d2i_1.common import read,save_new,digest,sha,require
from stage4e_d0.runner import utc

def main():
    p=argparse.ArgumentParser();p.add_argument('action',choices=['validate','freeze','pilot'])
    p.add_argument('--authorization-source');a=p.parse_args()
    if a.action=='validate':
        from .integrity import verify_sources
        print(json.dumps(verify_sources(),indent=2));return
    if a.action=='freeze':
        from .integrity import freeze
        from .live import Registry,STATE,baseline
        require(a.authorization_source,'Exact supplied authorization text path required')
        require(read(HOME/'OFFLINE_QA.json')['status']=='PASS','Offline qualification incomplete')
        text=__import__('pathlib').Path(a.authorization_source).read_text(encoding='utf-8-sig')
        require('B1V01_G174_NREF' in text and 'B1V01_G174_C15' in text and 'Initial Pilot Only' in text,'Wrong source authorization')
        save_new(HOME/'AUTHORIZATION_SOURCE.json',dict(text=text,source_sha256=sha(a.authorization_source),source_path=a.authorization_source))
        identity=freeze();m=canonical_manifest()
        save_new(HOME/'PILOT_AUTHORIZATION.json',dict(version=VERSION,status='EXPLICITLY_AUTHORIZED',
            implementation_manifest_sha256=identity,campaign_sha256=digest(m),run_ids=PILOT,
            maximum_fresh_instances=2,maximum_advances=1728,authorized_utc=utc(),
            user_authorization_text=text,source='USER_SUPPLIED_B2_REQUEST_SECTION_7',remaining_runs_authorized=False))
        Registry.create(STATE,baseline(m))
        print(json.dumps(dict(status='FROZEN_PILOT_ONLY',implementation_sha256=identity,campaign_sha256=digest(m)),indent=2));return
    from .live import execute
    print(json.dumps(execute(HOME/'PILOT_AUTHORIZATION.json'),indent=2))

if __name__=='__main__':main()
