"""FABRICATED fixtures only; no network or external process dispatch permitted."""
import contextlib,io,json,tempfile,unittest
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch
from .packaging import *
from . import HOME

@contextlib.contextmanager
def offline_guard():
    with contextlib.ExitStack() as s:
        for name in ('socket.socket.connect','socket.socket.connect_ex','socket.create_connection','socket.getaddrinfo','subprocess.Popen','os.system','os.startfile'):
            s.enter_context(patch(name,side_effect=AssertionError('B2F_OFFLINE_NETWORK_OR_PROCESS_FORBIDDEN')))
        yield

def fixture(base):
    """Two explicitly synthetic completed runs, each with raw artifact and receipt chain."""
    root=Path(base)/'FABRICATED_BATCH';root.mkdir()
    write_new(root/'BATCH_STARTED.json',dict(data_is_fabricated=True,run_ids=['MOCK_NREF','MOCK_C15']))
    plan=dict(scope='FABRICATED_SOFTWARE_FIXTURE_NOT_SIMULATOR_EVIDENCE',batch_files={},runs=[])
    for rid in ('MOCK_NREF','MOCK_C15'):
        d=root/rid;d.mkdir();write_new(d/'RUN_COMPLETED.json',dict(run_id=rid,data_is_fabricated=True,status='MOCK_COMPLETED'))
        (d/'raw_api.jsonl').write_text('{"data_is_fabricated":true}\n',encoding='utf-8')
        previous='0'*64;events=[]
        for i in range(1,4):
            e=dict(order=i,previous_sha256=previous,kind='FABRICATED_RECEIPT',monotonic_ns=i)
            e['sha256']=digest(e);previous=e['sha256'];events.append(json.dumps(e))
        (d/'receipt_order.jsonl').write_text('\n'.join(events)+'\n',encoding='utf-8')
        write_new(d/'ARTIFACT_MANIFEST.json',dict(files=inventory(d)))
        seal=rid+'_SEALED_MANIFEST.json';write_new(root/seal,dict(files=inventory(d)))
        plan['runs'].append(dict(run_id=rid,seal_path=seal,required_files=['RUN_COMPLETED.json','raw_api.jsonl','receipt_order.jsonl','ARTIFACT_MANIFEST.json']))
        plan['batch_files'][seal]=sha(root/seal)
    plan['batch_files']['BATCH_STARTED.json']=sha(root/'BATCH_STARTED.json')
    return root,plan

class FinalizationTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.base=Path(self.tmp.name);self.root,self.plan=fixture(self.base)
    def tearDown(self):self.tmp.cleanup()
    def test_01_complete_end_to_end_batch(self):
        original=inventory(self.root);out=self.base/'package'
        result=finalize(self.root,self.plan,out)
        self.assertEqual(result['status'],'PASS_CORRECTED_OFFLINE_FINALIZATION')
        self.assertEqual(inventory(self.root),original)
        m=read(out/'BATCH_ARTIFACT_MANIFEST.json')['files']
        self.assertTrue(all(rid+'/ARTIFACT_MANIFEST.json' in m for rid in ('MOCK_NREF','MOCK_C15')))
        self.assertEqual(len(m),len(original))
    def test_02_missing_nested_manifest(self):
        (self.root/'MOCK_NREF/ARTIFACT_MANIFEST.json').unlink()
        with self.assertRaises(ValueError):finalize(self.root,self.plan,self.base/'out')
    def test_03_missing_required_raw_artifact(self):
        (self.root/'MOCK_C15/raw_api.jsonl').unlink()
        with self.assertRaises(ValueError):verify_source(self.root,self.plan)
    def test_04_unexpected_artifact(self):
        (self.root/'MOCK_C15/extra.txt').write_text('UNREGISTERED')
        with self.assertRaises(ValueError):verify_source(self.root,self.plan)
    def test_05_modified_artifact(self):
        (self.root/'MOCK_NREF/raw_api.jsonl').write_text('TAMPERED')
        with self.assertRaises(ValueError):verify_source(self.root,self.plan)
    def test_06_incorrect_relative_paths(self):
        for path in ('../escape','/absolute','C:/absolute','MOCK_NREF\\raw_api.jsonl','MOCK_NREF/../raw_api.jsonl','./BATCH_STARTED.json','a//b'):
            plan=deepcopy(self.plan);plan['batch_files'][path]='0'*64
            with self.assertRaises(ValueError):verify_source(self.root,plan)
    def test_07_incorrect_hash(self):
        self.plan['batch_files']['BATCH_STARTED.json']='0'*64
        with self.assertRaises(ValueError):verify_source(self.root,self.plan)
    def test_08_duplicate_registration(self):
        self.plan['batch_files']['MOCK_NREF/raw_api.jsonl']=sha(self.root/'MOCK_NREF/raw_api.jsonl')
        with self.assertRaises(ValueError):verify_source(self.root,self.plan)
        p=self.base/'duplicate.json';p.write_text('{"files":{"a":"x","a":"y"}}')
        with self.assertRaises(ValueError):read(p)
    def test_09_interrupted_finalization(self):
        out=self.base/'interrupted'
        def interrupt():raise KeyboardInterrupt('FABRICATED INTERRUPTION')
        with self.assertRaises(KeyboardInterrupt):finalize(self.root,self.plan,out,interrupt)
        self.assertFalse((out/'FINALIZATION_COMPLETED.json').exists())
        with self.assertRaises(ValueError):verify_package(self.root,out)
        with self.assertRaises(FileExistsError):finalize(self.root,self.plan,out)
    def test_10_repeated_readonly_verification(self):
        out=self.base/'package';finalize(self.root,self.plan,out);before=inventory(out)
        self.assertEqual(verify_package(self.root,out),verify_package(self.root,out));self.assertEqual(before,inventory(out))
    def test_11_receipt_chain_failure_even_with_updated_file_hashes(self):
        d=self.root/'MOCK_NREF';lines=(d/'receipt_order.jsonl').read_text().splitlines()
        e=json.loads(lines[1]);e['kind']='TAMPERED';lines[1]=json.dumps(e);(d/'receipt_order.jsonl').write_text('\n'.join(lines)+'\n')
        (d/'ARTIFACT_MANIFEST.json').unlink();write_new(d/'ARTIFACT_MANIFEST.json',dict(files=inventory(d)))
        seal=self.root/'MOCK_NREF_SEALED_MANIFEST.json';seal.unlink();write_new(seal,dict(files=inventory(d)))
        self.plan['batch_files'][seal.name]=sha(seal)
        with self.assertRaises(ValueError):verify_source(self.root,self.plan)
    def test_12_scope_tampering_after_finalization(self):
        out=self.base/'package';finalize(self.root,self.plan,out);(out/'unexpected.txt').write_text('extra')
        with self.assertRaises(ValueError):verify_package(self.root,out)
    def test_13_no_output_inside_evidence(self):
        with self.assertRaises(ValueError):finalize(self.root,self.plan,self.root/'out')

class ReviewTests(unittest.TestCase):
    def test_episode_splitting_reduces_total_but_increases_count(self):
        from .review import total
        a=total([.1,.1,.1]);b=total([.1,0,.1])
        self.assertEqual((a['episodes'],b['episodes']),(1,2))
        self.assertLess(b['minutes'],a['minutes']);self.assertLess(b['degree_hours'],a['degree_hours'])
    def test_original_bounds_and_strict_excess(self):
        from .review import excess,TEMP,LOW,UP
        r=dict(start=39600,current_boundary={LOW:294.15,UP:297.15},current_observation={TEMP:297.15})
        self.assertEqual(excess(r),(0,0));r['current_observation'][TEMP]=298.15;self.assertEqual(excess(r),(0,1))
        r['current_observation'][TEMP]=293.15;self.assertEqual(excess(r),(1,0))
    def test_quantile_definition(self):
        from .review import quantiles
        q=quantiles([0,1,2,3,4]);self.assertEqual(q['p50'],2);self.assertEqual(q['p90'],3.6)
    def test_phase_boundaries(self):
        from .review import phase
        self.assertEqual(phase(39600),'hold_11to1115');self.assertEqual(phase(40500),'recovery_1115to1315')
        self.assertEqual(phase(47700),'later_1315to2400')

def run(record_stem=None):
    log=io.StringIO()
    with offline_guard():
        suite=unittest.defaultTestLoader.loadTestsFromTestCase(FinalizationTests)
        suite.addTests(unittest.defaultTestLoader.loadTestsFromTestCase(ReviewTests))
        # Existing three packaging regressions, unchanged and fabricated only.
        from hvac_control_expansion_v1.postpilot_audit_v1.tests import PackagingTests
        suite.addTests(unittest.defaultTestLoader.loadTestsFromTestCase(PackagingTests))
        from hvac_control_expansion_v1.tests import B1Tests
        for name in ('test_07_recovery_joint_three_pair_rule','test_08_native_interval_energy_and_duplicates','test_15_sampled_comfort_keeps_native_violations'):
            suite.addTest(B1Tests(name))
        result=unittest.TextTestRunner(stream=log,verbosity=2).run(suite)
    print(log.getvalue())
    if record_stem:
        require(re.fullmatch('[A-Za-z0-9_-]+',record_stem),'Unsafe test record name')
        write_new(HOME/(record_stem+'.json'),dict(tests=result.testsRun,failures=len(result.failures),errors=len(result.errors),
            status='PASS' if result.wasSuccessful() else 'FAIL',network_process_dispatch_blocked=True,simulator_calls=0,fixtures='FABRICATED_TEMPORARY_ONLY'))
        with (HOME/(record_stem+'.txt')).open('x',encoding='utf-8') as f:f.write(log.getvalue())
    return result.wasSuccessful()

if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('--record-stem');a=p.parse_args()
    raise SystemExit(0 if run(a.record_stem) else 1)
