"""Fabricated Docker responses only. Never dispatch a Docker command."""
import copy,json,unittest
from unittest.mock import patch
from . import runtime
from .runner import read,ROOT

class RuntimeGateTests(unittest.TestCase):
    def fixture(self,fault=None):
        reference=read(ROOT/'stage4e_d0/RUNTIME_REFERENCE_IDENTITIES.json');rows=[]
        worker=read(ROOT/'stage4e_runtime_preflight/evidence/WORKER_EXECUTABLE_AND_DEPENDENCIES.json')
        for service,image in reference['container_image_ids'].items():
            ports={}
            for inside,host in ([('80/tcp','80')] if service=='web' else [('9000/tcp','9000'),('9001/tcp','9001')] if service=='minio' else []):
                ports[inside]=[{'HostIp':'127.0.0.1','HostPort':host}]
            rows.append({'Config':{'Labels':{'com.docker.compose.service':service}},'Image':image,
                'HostConfig':{'PortBindings':ports},'State':{'Running':service not in ('mc','provision'),'ExitCode':0}})
        if fault=='image':rows[0]['Image']='sha256:UNRELATED'
        if fault=='dependencies':worker['packages']['numpy']='UNRELATED'
        if fault=='port':next(r for r in rows if r['Config']['Labels']['com.docker.compose.service']=='web')['HostConfig']['PortBindings']['80/tcp'][0]['HostPort']='81'
        if fault=='public':next(r for r in rows if r['Config']['Labels']['com.docker.compose.service']=='web')['HostConfig']['PortBindings']['80/tcp'][0]['HostIp']='0.0.0.0'
        def fake(*args):
            if args[0]=='ps':return ' '.join('FIXTURE_'+str(i) for i in range(6))
            if args[0]=='inspect':return json.dumps(rows)
            if args[0]=='version':return json.dumps({'Server':{'Os':'linux','Arch':'amd64'}})
            if args[0]=='exec':return json.dumps(worker)
            raise AssertionError(args)
        return fake
    def test_exact_pinned_runtime_accepted_read_only(self):
        with patch.object(runtime,'docker_read',side_effect=self.fixture()):self.assertEqual(runtime.verify_runtime()['classification'],'PASS')
    def test_changed_image_or_dependencies_rejected(self):
        for fault in ('image','dependencies'):
            with self.subTest(fault=fault),patch.object(runtime,'docker_read',side_effect=self.fixture(fault)),self.assertRaises(ValueError):runtime.verify_runtime()
    def test_wrong_port_or_public_binding_rejected(self):
        for fault in ('port','public'):
            with self.subTest(fault=fault),patch.object(runtime,'docker_read',side_effect=self.fixture(fault)),self.assertRaises(ValueError):runtime.verify_runtime()
    def test_absent_stack_rejected_without_deployment(self):
        with patch.object(runtime,'docker_read',return_value=''),self.assertRaises(ValueError):runtime.verify_runtime()

if __name__=='__main__':unittest.main(verbosity=2)
