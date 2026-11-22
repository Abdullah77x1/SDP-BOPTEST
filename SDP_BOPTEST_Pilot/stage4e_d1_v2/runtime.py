"""Read-only launch checks; no Docker lifecycle or model execution calls."""
import json
from stage4e_runtime_preflight.preflight import docker_read,WORKER,PYTHON
from .runner import read,ROOT,utc

def verify_runtime():
    reference=read(ROOT/'stage4e_d0/RUNTIME_REFERENCE_IDENTITIES.json')
    ids=docker_read('ps','-aq','--filter','label=com.docker.compose.project=sdp-boptest-v090').split()
    if not ids:raise ValueError('Pinned isolated stack is not running; no deployment attempted')
    rows=json.loads(docker_read('inspect',*ids))
    actual={r['Config']['Labels']['com.docker.compose.service']:r['Image'] for r in rows}
    if actual!=reference['container_image_ids'] or len(rows)!=len(actual):raise ValueError('Image identity/count mismatch')
    ports=[]
    for r in rows:
        for inside,bindings in (r['HostConfig']['PortBindings'] or {}).items():
            if any(b['HostIp']!='127.0.0.1' for b in bindings or []):raise ValueError('Nonlocalhost binding')
            ports.extend((inside,b['HostPort']) for b in bindings or [])
        service=r['Config']['Labels']['com.docker.compose.service']
        if service in ('web','worker','redis','minio') and not r['State']['Running']:
            raise ValueError('Required service not running')
        if service=='provision' and (r['State']['Running'] or r['State']['ExitCode']!=0):
            raise ValueError('Provision not successfully complete')
    if sorted(ports)!=sorted([('80/tcp','80'),('9000/tcp','9000'),('9001/tcp','9001')]):raise ValueError('Pinned port map mismatch')
    version=json.loads(docker_read('version','--format','{{json .}}'))
    if (version['Server']['Os'],version['Server']['Arch'])!=('linux','amd64'):raise ValueError('Wrong runtime platform')
    code="import sys,hashlib,json,platform,importlib.metadata as m,pathlib; paths=['/boptest/lib/testcase.py','/boptest/lib/kpis/kpi_calculator.py','/version.txt']; print(json.dumps(dict(python_executable=sys.executable,python_version=sys.version,python_executable_sha256=hashlib.sha256(pathlib.Path(sys.executable).read_bytes()).hexdigest(),machine=platform.machine(),boptest_version=pathlib.Path('/version.txt').read_text().strip(),source_hashes={p:hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest() for p in paths},packages={d.metadata['Name']:d.version for d in m.distributions()})))"
    worker=json.loads(docker_read('exec',WORKER,PYTHON,'-c',code))
    if worker!=read(ROOT/'stage4e_runtime_preflight/evidence/WORKER_EXECUTABLE_AND_DEPENDENCIES.json'):
        raise ValueError('Worker executable/source/dependencies changed')
    return {'classification':'PASS','utc':utc(),'container_image_ids':actual,'worker_identity':worker,
        'actual_instance_FMU_must_match_before_scenario_initialization':True,'fresh_simulations_for_launch_check':0}
