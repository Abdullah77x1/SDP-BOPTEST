"""Offline mandatory qualification; any failure permanently blocks this version's live entry."""
import io,json,tempfile,unittest,sqlite3,base64
from pathlib import Path
from copy import deepcopy
from unittest.mock import patch
from . import HOME,IDS
from .integrity import manifest,runs,baseline,historical,expected_approval,authorize
from .launcher import G146Registry,execute_one
from .validation import verify_run
from .metadata import verify_origin_metadata
from hvac_control_expansion_b2f_v1.packaging import read,sha,digest,require,write_new,verify_package
from hvac_control_expansion_b2f_v1.tests import offline_guard,FinalizationTests,ReviewTests
from stage4e_d2i_1_v1_0_1.fixtures import FakeTransport
from hvac_control_expansion_v1.campaign import nominal
from stage4e_d0.plan import FLAG,SET,FLAGS,native_command

class Fabricated(FakeTransport):
    deployments=0
    def log(self,method,key,request,value):
        row=dict(data_is_fabricated=True,http_status=200,attempt=1,method=method,url='http://FABRICATED/'+key,
            request=request,raw_body_base64=base64.b64encode(json.dumps(dict(payload=value)).encode()).decode())
        with (self.directory/'raw_api.jsonl').open('a',encoding='utf-8') as f:f.write(json.dumps(row)+'\n')
    def deploy(self):
        type(self).deployments+=1;value=super().deploy();self.log('POST','testcases',{},value);return value
    def request(self,method,key,data=None):
        value=super().request(method,key,data);self.log(method,key,data,value);return value
    def stop(self):
        value=super().stop();self.log('PUT','stop',{},dict(acknowledgement='OK'));return value

class WrongFMU(Fabricated):
    def fmu_identity(self):return dict(sha256='0'*64,evidence='FABRICATED_BAD_HASH')

def fakebase():
    return dict(version='FABRICATED_ONLY',slots=[dict(run_id=r['run_id'],group_id=r['group_id'],partition=r['partition'],category='development',
        status='CONSUMED_COMPLETED' if 'G174' in r['run_id'] else 'UNUSED_NOT_AUTHORIZED',run_sha256=digest(r)) for r in manifest()['runs']])

def verify_fake(path,run,policy):return verify_run(path,run,policy,fabricated=True)

class G146Tests(unittest.TestCase):
    def test_01_exact_three_schedules_named_init_and_fold(self):
        rr=runs();self.assertEqual([r['run_id'] for r in rr],IDS)
        for run,count,seconds in zip(rr,(0,9,27),(0,900,2700)):
            self.assertEqual((run['start'],run['end'],run['warmup_start']),(12614400,12873600,12009600))
            self.assertEqual(run['initialization'],dict(method='scenario',start_time=12614400,warmup_period=604800,scenario_key='typical_cool_day'))
            self.assertEqual((run['group_id'],run['partition'],run['dataset_partition'],run['outer_held_fold']),('D2_G146','development','development',1))
            active=[]
            for t in range(run['start'],run['end'],300):
                c=nominal(run,t)['command'];self.assertFalse(any(c[f] for f in FLAGS[1:]))
                if c[FLAG]:active.append(t);self.assertEqual(c[SET],296.90)
                else:self.assertEqual(c,native_command())
            self.assertEqual(len(active),count)
            self.assertEqual(active,[run['start']+d*86400+39600+x for d in range(3) for x in range(0,seconds,300)])
            for d in range(3):self.assertEqual(nominal(run,run['start']+d*86400+39600+seconds)['command'],native_command())
    def test_02_order_unauthorized_and_immutable_triggers(self):
        with tempfile.TemporaryDirectory() as td:
            reg=G146Registry.create(Path(td)/'ledger',fakebase());reg.check_selection([runs()[0]])
            for r in manifest()['runs'][:3]+runs()[1:]+[dict(runs()[0],run_id='UNKNOWN')]:
                with self.assertRaises(ValueError):reg.check_selection([r])
            for selected in ([],runs(),[runs()[0],runs()[0]]):
                with self.assertRaises(ValueError):reg.check_selection(selected)
            with reg.connect() as db:
                before=list(db.execute('SELECT * FROM slots'));ddl=list(db.execute("SELECT name,sql FROM sqlite_master WHERE type='trigger' ORDER BY name"))
                self.assertEqual(len(ddl),10);self.assertEqual([v[1] for v in db.execute('PRAGMA table_info(slots)')],['run_id','definition'])
                for sql,args in [('UPDATE slots SET definition=definition',()),('UPDATE slots SET definition=? WHERE run_id=?',('{}',IDS[0])),('DELETE FROM slots',())]:
                    with self.assertRaises(sqlite3.IntegrityError) as error:db.execute(sql,args)
                    self.assertEqual(str(error.exception),'APPEND_ONLY_NO_RESET');self.assertEqual(error.exception.sqlite_errorname,'SQLITE_CONSTRAINT_TRIGGER')
                self.assertEqual(before,list(db.execute('SELECT * FROM slots')));self.assertEqual(ddl,list(db.execute("SELECT name,sql FROM sqlite_master WHERE type='trigger' ORDER BY name")))
            reg.new_batch('test',[runs()[0]],{});reg.reserve('test',runs()[0])
            for r in runs():
                with self.assertRaises(ValueError):reg.check_selection([r])
            with self.assertRaises(ValueError):reg.reserve('test',runs()[0])
    def test_03_full_fabricated_three_arm_launcher_and_finalizer(self):
        with tempfile.TemporaryDirectory() as td:
            base=Path(td);reg=G146Registry.create(base/'ledger',fakebase());Fabricated.deployments=0;results=[]
            for run,expected in zip(runs(),(0,9,27)):
                out=execute_one(manifest(),run,reg,dict(fabricated=True),Fabricated,'FABRICATED_OFFLINE_TEST_ONLY',verify_fake,base/run['arm'])
                self.assertEqual(out['state'],'CONSUMED_COMPLETED',out.get('error'));results.append(out)
                self.assertEqual(out['raw_result']['coverage']['applied_intervals'],expected)
                self.assertTrue(all(e['complete'] and e['recovery_native_intervals']==24 for e in out['raw_result']['coverage']['episodes']))
                verify_package(out['source_batch'],base/run['arm'])
                self.assertIn(run['run_id']+'/ARTIFACT_MANIFEST.json',read(base/run['arm']/'BATCH_ARTIFACT_MANIFEST.json')['files'])
                self.assertEqual(out['validation']['origin_metadata']['origins'],864)
                with self.assertRaises(ValueError):reg.check_selection([run])
            self.assertEqual(Fabricated.deployments,3)
            self.integration=dict(status='PASS_FABRICATED_THREE_ARM_CAMPAIGN',results=results,real_instances=0)
            # The actual raw validator was used on all fabricated HTTP records, not a stub.
            path=Path(results[2]['run_path']);lines=(path/'steps.jsonl').read_text().splitlines();r=json.loads(lines[0]);r['known_path'][1]['known_at_sim']=r['start']+300
            lines[0]=json.dumps(r);(path/'steps.jsonl').write_text('\n'.join(lines)+'\n')
            with self.assertRaises(ValueError):verify_origin_metadata(path,runs()[2])
            with self.assertRaises(ValueError):verify_package(results[2]['source_batch'],base/'C45')
    def test_04_wrong_fmu_stops_entire_campaign(self):
        with tempfile.TemporaryDirectory() as td:
            base=Path(td);reg=G146Registry.create(base/'ledger',fakebase());WrongFMU.deployments=0
            out=execute_one(manifest(),runs()[0],reg,{},WrongFMU,'FABRICATED_OFFLINE_TEST_ONLY',verify_fake,base/'package')
            self.assertEqual(out['state'],'CONSUMED_FAILED');self.assertEqual(WrongFMU.deployments,1)
            self.assertEqual(out['raw_result']['initialization_attempts'],0);self.assertEqual(out['raw_result']['advance_requests_attempted'],0)
            self.assertEqual(out['raw_result']['cleanup'],'STOP_ACK_AND_REMOVAL_VERIFIED')
            for run in runs():
                with self.assertRaises(ValueError):reg.check_selection([run])
    def test_05_finalizer_failure_blocks_next_arm(self):
        def fail(*args):raise ValueError('FABRICATED finalizer interruption')
        with tempfile.TemporaryDirectory() as td:
            base=Path(td);reg=G146Registry.create(base/'ledger',fakebase())
            out=execute_one(manifest(),runs()[0],reg,{},Fabricated,'FABRICATED_OFFLINE_TEST_ONLY',verify_fake,base/'package',finalizer=fail)
            self.assertEqual(out['state'],'CONSUMED_FAILED');self.assertIsNotNone(out['validation'])
            with self.assertRaises(ValueError):reg.check_selection([runs()[1]])
    def test_06_approval_exact_schema_budget_order(self):
        with tempfile.TemporaryDirectory() as td:
            h=Path(td);write_new(h/'RUN_MANIFEST.json',{});write_new(h/'REQUEST_SOURCE.json',dict(text='FABRICATED APPROVAL'));write_new(h/'OFFLINE_QUALIFICATION.json',dict(status='PASS'))
            a=expected_approval(h,'FABRICATED_ID');p=h/'approval.json';write_new(p,a)
            with patch('hvac_control_expansion_b2i_v1.integrity.verify_frozen',return_value='FABRICATED_ID'):
                authorize(p,h)
                for field,value in [('run_ids',IDS[::-1]),('maximum_instances',4),('maximum_advances',2593),('implementation_sha256','bad'),('status','READY'),('user_authorization_text','bad'),('individual_budgets',{})]:
                    bad=dict(a);bad[field]=value;p.write_text(json.dumps(bad))
                    with self.assertRaises(ValueError):authorize(p,h)
                with self.assertRaises(ValueError):authorize(None,h)
    def test_07_history_group_and_reservations_unchanged(self):
        self.assertEqual(historical()['status'],'PASS_READ_ONLY');b=baseline()
        self.assertEqual([s['status'] for s in b['slots']],['CONSUMED_COMPLETED']*3+['UNUSED_NOT_AUTHORIZED']*3)
        from hvac_control_expansion_v1.integrity import source_evidence,reservation_check
        self.assertEqual(len(source_evidence()),33);self.assertEqual(reservation_check(manifest())['metadata_comparisons'],98)

def qualify():
    require(not (HOME/'OFFLINE_QUALIFICATION.json').exists(),'No requalification after failure in this version')
    log=io.StringIO();suite=unittest.defaultTestLoader.loadTestsFromTestCase(G146Tests)
    integration=next(t for t in suite if t._testMethodName=='test_03_full_fabricated_three_arm_launcher_and_finalizer')
    suite.addTests(unittest.defaultTestLoader.loadTestsFromTestCase(FinalizationTests));suite.addTests(unittest.defaultTestLoader.loadTestsFromTestCase(ReviewTests))
    from hvac_control_expansion_v1.tests import B1Tests
    for name in ('test_02_safety_activation_and_latched_release','test_03_safety_adversaries','test_04_manifest_three_arm_mapping_and_initialization',
        'test_05_common_prefix_and_carryover','test_06_duration_and_two_hour_coverage','test_07_recovery_joint_three_pair_rule',
        'test_08_native_interval_energy_and_duplicates','test_09_original_sixteen_target_last_interval_contract','test_10_future_leakage_and_parent_fold_overlay',
        'test_12_transport_no_retry_no_extra_advance','test_14_readbacks_and_pending_events','test_15_sampled_comfort_keeps_native_violations',
        'test_17_failed_collection_stops_and_cleanup_once'):suite.addTest(B1Tests(name))
    with offline_guard():result=unittest.TextTestRunner(stream=log,verbosity=2).run(suite)
    (HOME/'OFFLINE_TEST_RESULTS.txt').write_text(log.getvalue(),encoding='utf-8');print(log.getvalue())
    report=dict(status='PASS' if result.wasSuccessful() else 'FAIL_STOP_NO_LIVE',tests=result.testsRun,failures=len(result.failures),errors=len(result.errors),real_instances=0,real_advances=0,network_and_process_dispatch_blocked=True)
    write_new(HOME/'OFFLINE_QUALIFICATION.json',report)
    if result.wasSuccessful():write_new(HOME/'FABRICATED_CAMPAIGN_RESULT.json',integration.integration)
    return report
