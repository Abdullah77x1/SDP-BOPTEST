"""Actual-discovery metadata receipt regressions; fabricated responses only."""
import json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from stage4e_d2i_1.common import ROOT,HOME as ORIGINAL_HOME,read,save_new,sha,digest,ContractError
from stage4e_d2i_1.manifest import canonical_manifest,validate_manifest
from stage4e_d0.runner import Journal
from . import VERSION
from .collector import collect_mock
from .fixtures import ActualDiscoveryFixture,FakeTransport
from .metadata import validate_metadata_receipt
from .live import authorize

class ReceiptTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.m=canonical_manifest('preflight');self.r=self.m['runs'][0]
    def metadata(self):
        d=self.root/'FABRICATED_METADATA';d.mkdir()
        client=ActualDiscoveryFixture(self.m['policy']['base'],d,Journal(d/'journal.jsonl'),self.r,self.m)
        return d,client.discover()
    def collect(self,cls=ActualDiscoveryFixture):
        d=self.root/'FABRICATED_COLLECTION'
        return collect_mock(self.m,self.r['run_id'],d,cls),d
    def test_actual_discovery_writes_one_expected_receipt(self):
        writes=[];original=Path.write_text
        def writer(path,*args,**kwargs):
            if path.name=='runtime_metadata.json':writes.append(path)
            return original(path,*args,**kwargs)
        with patch.object(Path,'write_text',new=writer):
            d,metadata=self.metadata()
            result=validate_metadata_receipt(d,metadata)
        self.assertEqual(writes,[d/'runtime_metadata.json'])
        self.assertEqual(result['collector_receipt_writes'],0)
        self.assertEqual(read(d/'runtime_metadata.json'),metadata)
    def test_corrected_collector_accepts_actual_discovery_and_completes_three_steps(self):
        def exclusive_write(path,data):
            self.assertNotEqual(Path(path).name,'runtime_metadata.json','Collector attempted duplicate create')
            return save_new(path,data)
        with patch('stage4e_d2i_1_v1_0_1.collector.save_new',side_effect=exclusive_write):
            result,d=self.collect()
        self.assertEqual(result['classification'],'PASS_PREFLIGHT_RAW',result)
        self.assertEqual(result['initialization_attempts'],1);self.assertEqual(result['advance_requests_attempted'],3)
        self.assertEqual(result['endpoints'],4);self.assertEqual(result['native_samples'],31)
        self.assertEqual(result['cleanup'],'STOP_ACK_AND_REMOVAL_VERIFIED')
        self.assertEqual(read(d/'ATTEMPT_STARTED.json')['version'],VERSION)
        validation=read(d/'METADATA_RECEIPT_VALIDATION.json')
        self.assertEqual(validation['sha256'],sha(d/'runtime_metadata.json'))
        self.assertTrue(result['data_is_fabricated']);self.assertFalse(result['training_release'])
    def test_valid_existing_receipt_bytes_are_never_modified(self):
        d,metadata=self.metadata();p=d/'runtime_metadata.json'
        p.write_text(json.dumps(metadata,ensure_ascii=True,separators=(', ', ': '))+'\n\n',encoding='utf-8')
        before=p.read_bytes();mtime=p.stat().st_mtime_ns
        validate_metadata_receipt(d,metadata)
        self.assertEqual(p.read_bytes(),before);self.assertEqual(p.stat().st_mtime_ns,mtime)
    def test_missing_receipt_fails_without_fallback(self):
        d,metadata=self.metadata();p=d/'runtime_metadata.json';p.unlink()
        with self.assertRaisesRegex(ContractError,'Missing'):validate_metadata_receipt(d,metadata)
        self.assertFalse(p.exists())
    def test_wrong_filename_does_not_replace_expected_receipt(self):
        d,metadata=self.metadata();p=d/'runtime_metadata.json';other=d/'unexpected_metadata.json';p.rename(other)
        before=other.read_bytes()
        with self.assertRaisesRegex(ContractError,'Missing'):validate_metadata_receipt(d,metadata)
        self.assertEqual(other.read_bytes(),before);self.assertFalse(p.exists())
    def test_regular_file_required(self):
        d,metadata=self.metadata();p=d/'runtime_metadata.json';p.unlink();p.mkdir()
        with self.assertRaisesRegex(ContractError,'regular non-link'):validate_metadata_receipt(d,metadata)
        self.assertTrue(p.is_dir())
    def test_symlink_receipt_rejected(self):
        d,metadata=self.metadata();p=d/'runtime_metadata.json'
        with patch.object(Path,'is_symlink',return_value=True):
            with self.assertRaisesRegex(ContractError,'non-link'):validate_metadata_receipt(d,metadata)
    def test_malformed_receipt_is_retained(self):self.bad_content('{')
    def test_invalid_utf8_receipt_is_retained(self):self.bad_content(b'\xff\xfe\x80')
    def test_unexpected_array_root_is_retained(self):self.bad_content('[]')
    def test_extra_receipt_property_is_conflict(self):
        d,metadata=self.metadata();bad=dict(metadata,unexpected=True)
        self.reject_preserved(d,metadata,json.dumps(bad))
    def test_duplicate_keys_rejected(self):
        d,metadata=self.metadata();bad=json.dumps(metadata)[:-1]+',"version":{"version":"0.9.0"}}'
        self.reject_preserved(d,metadata,bad)
    def test_nonfinite_json_rejected(self):
        d,metadata=self.metadata();bad=json.dumps(metadata)[:-1]+',"unexpected":NaN}'
        self.reject_preserved(d,metadata,bad)
    def test_boolean_and_integer_are_not_equal_metadata(self):
        d,metadata=self.metadata();metadata['test_strict_type']=1
        bad=dict(metadata,test_strict_type=True)
        self.reject_preserved(d,metadata,json.dumps(bad))
    def test_conflicting_model_identity_rejected(self):
        d,metadata=self.metadata();bad=dict(metadata,name={'name':'OTHER_BUILDING'})
        self.reject_preserved(d,metadata,json.dumps(bad))
    def bad_content(self,content):
        d,metadata=self.metadata();self.reject_preserved(d,metadata,content)
    def reject_preserved(self,d,metadata,content):
        p=d/'runtime_metadata.json'
        p.write_bytes(content if isinstance(content,bytes) else content.encode())
        before=p.read_bytes()
        with self.assertRaises(ContractError):validate_metadata_receipt(d,metadata)
        self.assertEqual(p.read_bytes(),before)
    def test_unexpected_read_failure_stops_and_cleans_up(self):
        original=Path.read_text
        def denied(path,*args,**kwargs):
            if path==self.root/'FABRICATED_COLLECTION/runtime_metadata.json':
                raise PermissionError('FABRICATED unreadable receipt')
            return original(path,*args,**kwargs)
        with patch.object(Path,'read_text',new=denied):result,d=self.collect()
        self.assertEqual(result['classification'],'FAILED');self.assertIn('PermissionError',result['error'])
        self.assertEqual(result['initialization_attempts'],0);self.assertEqual(result['advance_requests_attempted'],0)
        self.assertEqual(result['cleanup'],'STOP_ACK_AND_REMOVAL_VERIFIED')
    def test_actual_real_transport_source_unchanged(self):
        manifest=read(ORIGINAL_HOME/'IMPLEMENTATION_MANIFEST.json')
        for p in ('client.py','compat_v1/transport.py','stage4e_d0/runner.py','stage4e_d0/plan.py'):
            self.assertEqual(sha(ROOT/p),manifest['files'][p])
    def test_preflight_configuration_digest_unchanged(self):
        self.assertEqual(digest(self.m),'2f6156d09aad0b8c158ed503e416cee77dd9b1ed9bb5a9ff619d14db15442bbc')
        self.assertEqual(self.m,read(ORIGINAL_HOME/'preflight_manifest.json'))
        self.assertEqual(validate_manifest(self.m)['new_scored_advances'],12)
    def test_original_explicit_authorization_rejected(self):
        old=ROOT/'stage4e_d2pf/v1_0_0/PREFLIGHT_AUTHORIZATION.json'
        ids=[r['run_id'] for r in self.m['runs']]
        with patch('stage4e_d2i_1_v1_0_1.live.implementation_identity',return_value='NEW_IMPLEMENTATION_DIGEST'):
            with self.assertRaisesRegex(ContractError,'not authorized'):authorize(self.m,ids,old)
    def test_relabelled_old_approval_digest_still_rejected(self):
        a=read(ROOT/'stage4e_d2pf/v1_0_0/PREFLIGHT_AUTHORIZATION.json');a['version']=VERSION
        p=self.root/'FABRICATED_APPROVAL.json';save_new(p,a)
        with patch('stage4e_d2i_1_v1_0_1.live.implementation_identity',return_value='NEW_IMPLEMENTATION_DIGEST'):
            with self.assertRaisesRegex(ContractError,'digest mismatch'):
                authorize(self.m,[r['run_id'] for r in self.m['runs']],p)
    def test_version_change_cannot_reset_prior_attempts(self):
        original=Path.exists
        def exists(path):
            if path==ROOT/'stage4e_d2i_1/future_preflight_evidence':return True
            return original(path)
        with patch.object(Path,'exists',new=exists):
            with self.assertRaisesRegex(ContractError,'no version-reset retry'):
                authorize(self.m,[r['run_id'] for r in self.m['runs']],None)

def collection_receipt_fault(name,mutator):
    def test(self):
        snapshots={}
        class InvalidReceiptFixture(ActualDiscoveryFixture):
            def discover(inner):
                metadata=super().discover();path=inner.directory/'runtime_metadata.json'
                mutator(path,metadata)
                snapshots['content']=path.read_bytes() if path.is_file() else None
                return metadata
        result,d=self.collect(InvalidReceiptFixture)
        self.assertEqual(result['classification'],'FAILED',result)
        self.assertEqual(result['initialization_attempts'],0);self.assertEqual(result['advance_requests_attempted'],0)
        self.assertEqual(result['cleanup'],'STOP_ACK_AND_REMOVAL_VERIFIED')
        p=d/'runtime_metadata.json'
        self.assertEqual(p.read_bytes() if p.is_file() else None,snapshots['content'])
        self.assertFalse((d/'METADATA_RECEIPT_VALIDATION.json').exists())
    return test

for name,mutator in {
    'missing':lambda p,m:p.unlink(),
    'malformed':lambda p,m:p.write_text('{'),
    'conflicting':lambda p,m:p.write_text(json.dumps(dict(m,testid='WRONG_INSTANCE'))),
    'unexpected_root':lambda p,m:p.write_text('null'),
}.items():setattr(ReceiptTests,'test_collection_rejects_'+name+'_without_overwriting',collection_receipt_fault(name,mutator))
