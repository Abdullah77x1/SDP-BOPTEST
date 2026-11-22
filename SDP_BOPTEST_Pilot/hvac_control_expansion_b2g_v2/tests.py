"""Mandatory offline C45 qualification. Any failure blocks live execution."""
import contextlib,io,json,tempfile,unittest,sqlite3
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch
from . import HOME,RID,BATCH_ID
from .integrity import manifest,run_definition,require_only
from .launcher import C45Registry,execute_one,authorize
from hvac_control_expansion_b2f_v1.tests import offline_guard,FinalizationTests,ReviewTests
from hvac_control_expansion_b2f_v1.packaging import read,sha,digest,write_new,require,chain,verify_package
from stage4e_d2i_1_v1_0_1.fixtures import FakeTransport
from hvac_control_expansion_v1.campaign import nominal,coverage,first_divergence
from stage4e_d0.plan import native_command,FLAG,SET,FLAGS

class FabricatedC45(FakeTransport):
    deployments=0
    def deploy(self):
        type(self).deployments+=1
        (self.directory/'raw_api.jsonl').write_text('{"data_is_fabricated":true,"scope":"SOFTWARE_TEST_NOT_BOPTEST_EVIDENCE"}\n',encoding='utf-8')
        return super().deploy()

class FabricatedWrongFMU(FabricatedC45):
    def fmu_identity(self):return dict(sha256='0'*64,evidence='FABRICATED_BAD_HASH')

def fabricated_baseline():
    return dict(version='FABRICATED_LEDGER_NOT_RUNTIME',slots=[dict(run_id=r['run_id'],group_id=r['group_id'],partition='development',category='development',
        status='CONSUMED_COMPLETED' if r['arm'] in ('NREF','C15') and r['group_id']=='D2_G174' else 'UNUSED_NOT_AUTHORIZED',run_sha256=digest(r)) for r in manifest()['runs']])

def fabricated_verify(path,run,policy):
    s=read(path/'RUN_COMPLETED.json');require(s['data_is_fabricated'] is True,'Fixture boundary')
    require(s['advances']==864 and s['endpoints']==865 and s['native_samples']==8641,'Fabricated full-length collection support')
    require(s['coverage']['requested_intervals']==27 and s['coverage']['applied_intervals']==27,'Fabricated C45 dose')
    require(all(e['complete'] and e['recovery_native_intervals']==24 for e in s['coverage']['episodes']),'Fabricated release/recovery')
    return dict(status='FABRICATED_PASS_NOT_REAL_EVIDENCE',receipt_chain=chain(path/'receipt_order.jsonl'))

class C45Tests(unittest.TestCase):
    def test_01_exact_C45_contract_all_days(self):
        r=run_definition();self.assertEqual((r['start'],r['end'],r['warmup_start']),(15033600,15292800,14428800))
        self.assertEqual(r['initialization'],dict(method='custom',start_time=15033600,warmup_period=604800,scenario_key=None))
        self.assertEqual((r['group_id'],r['outer_held_fold'],r['partition']),('D2_G174',4,'development'))
        active=[]
        for t in range(r['start'],r['end'],300):
            c=nominal(r,t)['command'];self.assertFalse(any(c[f] for f in FLAGS[1:]))
            if c[FLAG]:active.append(t);self.assertEqual(c[SET],296.90)
            else:self.assertEqual(c,native_command())
        self.assertEqual(len(active),27)
        for day in range(3):
            start=r['start']+day*86400+39600
            self.assertEqual([t for t in active if (t-r['start'])//86400==day],list(range(start,start+2700,300)))
            self.assertEqual(nominal(r,start+2700)['command'],native_command())
        m=manifest();self.assertEqual(first_divergence(m['runs'][1],r),r['start']+40500)
    def test_02_selection_blocks_every_other_arm(self):
        require_only([RID])
        for ids in ([],[RID,RID],[RID,'B1V01_G174_C15'],['B1V01_G174_NREF'],['B1V01_G174_C15'],['B1V01_G146_NREF'],['B1V01_G146_C15'],['B1V01_G146_C45']):
            with self.assertRaises(ValueError):require_only(ids)
    def test_03_registry_imports_consumed_pilot_and_rejects_duplicates(self):
        with tempfile.TemporaryDirectory() as td:
            reg=C45Registry.create(Path(td)/'ledger',fabricated_baseline());run=run_definition()
            for old in manifest()['runs']:
                if old['run_id']!=RID:
                    with self.assertRaises(ValueError):reg.check_selection([old])
            reg.new_batch(BATCH_ID,[run],{});reg.reserve(BATCH_ID,run)
            with self.assertRaises(Exception):reg.reserve(BATCH_ID,run)
            with self.assertRaises(ValueError):reg.new_batch('DIFFERENT_OUTPUT',[run],{})
            with reg.connect() as db:
                with self.assertRaises(sqlite3.IntegrityError):db.execute('DELETE FROM reservations')
                columns=[r[1] for r in db.execute('PRAGMA table_info(slots)')]
                self.assertEqual(columns,['run_id','definition'])
                before=list(db.execute('SELECT run_id,definition FROM slots ORDER BY run_id'))
                triggers_before=list(db.execute("SELECT name,sql FROM sqlite_master WHERE type='trigger' ORDER BY name"))
                trigger=dict(triggers_before)['no_UPDATE_slots']
                self.assertIn("RAISE(ABORT,'APPEND_ONLY_NO_RESET')",trigger)
                with self.assertRaises(sqlite3.IntegrityError) as noop:
                    db.execute('UPDATE slots SET definition=definition')
                self.assertEqual(str(noop.exception),'APPEND_ONLY_NO_RESET')
                self.assertEqual(before,list(db.execute('SELECT run_id,definition FROM slots ORDER BY run_id')))
                altered=json.loads(next(definition for rid,definition in before if rid==RID))
                altered['status']='FABRICATED_ATTEMPTED_CHANGE'
                with self.assertRaises(sqlite3.IntegrityError) as mutation:
                    db.execute('UPDATE slots SET definition=? WHERE run_id=?',(json.dumps(altered,sort_keys=True),RID))
                self.assertEqual(str(mutation.exception),'APPEND_ONLY_NO_RESET')
                after=list(db.execute('SELECT run_id,definition FROM slots ORDER BY run_id'))
                triggers_after=list(db.execute("SELECT name,sql FROM sqlite_master WHERE type='trigger' ORDER BY name"))
                self.assertEqual(before,after);self.assertEqual(triggers_before,triggers_after)
                self.trigger_evidence=dict(scope='FABRICATED_TEMPORARY_LEDGER_ONLY',schema_columns=columns,
                    trigger_name='no_UPDATE_slots',trigger_sql=trigger,trigger_sql_sha256=digest(trigger),
                    noop_update=dict(sql='UPDATE slots SET definition=definition',exception=type(noop.exception).__name__,
                        message=str(noop.exception),sqlite_errorname=getattr(noop.exception,'sqlite_errorname',None)),
                    actual_change_update=dict(sql='UPDATE slots SET definition=? WHERE run_id=?',exception=type(mutation.exception).__name__,
                        message=str(mutation.exception),sqlite_errorname=getattr(mutation.exception,'sqlite_errorname',None)),
                    records_before_sha256=digest(before),records_after_sha256=digest(after),records_unchanged=before==after,
                    triggers_before_sha256=digest(triggers_before),triggers_after_sha256=digest(triggers_after),triggers_unchanged=triggers_before==triggers_after)
    def test_04_full_fabricated_C45_corrected_finalization_path(self):
        with tempfile.TemporaryDirectory() as td:
            base=Path(td);reg=C45Registry.create(base/'ledger',fabricated_baseline());FabricatedC45.deployments=0
            result=execute_one(manifest(),run_definition(),reg,dict(data_is_fabricated=True),FabricatedC45,'FABRICATED_OFFLINE_TEST_ONLY',fabricated_verify,base/'package')
            self.assertEqual(result['state'],'CONSUMED_COMPLETED');self.assertEqual(FabricatedC45.deployments,1)
            self.assertEqual(result['corrected_finalization']['status'],'PASS_CORRECTED_OFFLINE_FINALIZATION')
            verify_package(result['source_batch'],base/'package')
            files=read(base/'package/BATCH_ARTIFACT_MANIFEST.json')['files']
            self.assertIn(RID+'/ARTIFACT_MANIFEST.json',files)
            self.integration_evidence=dict(scope='FABRICATED_SOFTWARE_ONLY_NOT_BOPTEST_EVIDENCE',
                orchestrator='hvac_control_expansion_b2g_v1.launcher.execute_one (unchanged, reused by v2)',
                finalizer='hvac_control_expansion_b2f_v1.packaging.finalize',status=result['corrected_finalization']['status'],
                fabricated_deployments=FabricatedC45.deployments,advances=result['raw_result']['advances'],
                endpoints=result['raw_result']['endpoints'],native_samples=result['raw_result']['native_samples'],
                requested_intervals=result['raw_result']['coverage']['requested_intervals'],
                applied_intervals=result['raw_result']['coverage']['applied_intervals'],
                nested_manifest_in_outer_scope=RID+'/ARTIFACT_MANIFEST.json' in files,
                all_three_recoveries_complete=all(e['complete'] and e['recovery_native_intervals']==24 for e in result['raw_result']['coverage']['episodes']),
                duplicate_attempt_rejected=True,real_instances=0,real_advances=0)
            with self.assertRaises(ValueError):execute_one(manifest(),run_definition(),reg,{},FabricatedC45,'FABRICATED_OFFLINE_TEST_ONLY',fabricated_verify,base/'different-package')
            self.assertEqual(FabricatedC45.deployments,1)
    def test_05_wrong_FMU_stops_before_initialization_and_no_retry(self):
        with tempfile.TemporaryDirectory() as td:
            base=Path(td);reg=C45Registry.create(base/'ledger',fabricated_baseline());FabricatedWrongFMU.deployments=0
            result=execute_one(manifest(),run_definition(),reg,dict(data_is_fabricated=True),FabricatedWrongFMU,'FABRICATED_OFFLINE_TEST_ONLY',fabricated_verify,base/'package')
            self.assertEqual(result['state'],'CONSUMED_FAILED');self.assertEqual(result['raw_result']['initialization_attempts'],0)
            self.assertEqual(result['raw_result']['advance_requests_attempted'],0);self.assertEqual(FabricatedWrongFMU.deployments,1)
            with self.assertRaises(ValueError):reg.check_selection([run_definition()])
    def test_06_authorization_exact_binding(self):
        # Isolate immutable-file I/O, never the authorization comparisons or simulator gate.
        fakehome=None
        with tempfile.TemporaryDirectory() as td:
            fakehome=Path(td);write_new(fakehome/'RUN_MANIFEST.json',{})
            write_new(fakehome/'REQUEST_SOURCE.json',dict(text='FABRICATED AUTHORIZATION TEST'))
            write_new(fakehome/'OFFLINE_QUALIFICATION.json',dict(status='PASS'))
            a=dict(version='SDP_B2G_2.0.0',status='EXPLICITLY_AUTHORIZED_FOR_LIVE_C45',implementation_sha256='fixture',
                run_manifest_sha256=sha(fakehome/'RUN_MANIFEST.json'),campaign_sha256=digest(manifest()),run_ids=[RID],maximum_instances=1,maximum_advances=864,
                request_sha256=sha(fakehome/'REQUEST_SOURCE.json'),user_authorization_text='FABRICATED AUTHORIZATION TEST')
            with patch('hvac_control_expansion_b2g_v2.launcher.HOME',fakehome),patch('hvac_control_expansion_b2g_v2.launcher.verify_frozen',return_value='fixture'):
                write_new(fakehome/'good.json',a);authorize(fakehome/'good.json',[RID])
                for i,(key,value) in enumerate([('maximum_instances',2),('maximum_advances',865),('run_ids',['B1V01_G146_C45']),('campaign_sha256','bad'),('implementation_sha256','bad')]):
                    bad=dict(a);bad[key]=value;write_new(fakehome/f'bad{i}.json',bad)
                    with self.assertRaises(ValueError):authorize(fakehome/f'bad{i}.json',[RID])
    def test_07_historical_source_hashes_and_runtime_reference(self):
        from . import PILOT,B2F,ROOT
        for name,h in read(PILOT/'IMPLEMENTATION_MANIFEST.json')['files'].items():self.assertEqual(sha(name),h)
        self.assertEqual(sha(B2F/'B2F_IMPLEMENTATION_MANIFEST.json'),'917a80c01efde5d9615bafa4f5dc84914ae1851b85fa4f9058f12a69841a3992')
        reference=read(ROOT/'stage4e_d0/RUNTIME_REFERENCE_IDENTITIES.json')
        self.assertEqual(reference['building_fmu_sha256'],'158008fa3b635280a67dfed8bab5804d1f9a96d218b467dfebab77e5cbf8b86a')
    def test_08_frozen_source_tampering_rejected(self):
        from .integrity import verify_frozen
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);p=root/'source.py';p.write_text('ORIGINAL')
            write_new(root/'IMPLEMENTATION_MANIFEST.json',dict(version='SDP_B2G_2.0.0',execution_authorized=False,files={str(p):sha(p)}))
            p.write_text('TAMPERED')
            with patch('hvac_control_expansion_b2g_v2.integrity.HOME',root):
                with self.assertRaises(ValueError):verify_frozen()

    def test_09_absent_new_approval_blocks_before_any_runtime_or_ledger(self):
        from .launcher import execute
        with patch('hvac_control_expansion_b2g_v2.launcher.verify_frozen',side_effect=AssertionError('MUST_NOT_REACH_FROZEN_OR_RUNTIME_CHECK')):
            with self.assertRaisesRegex(ValueError,'NOT AUTHORIZED FOR EXECUTION'):execute(None)
    def test_10_readiness_artifact_is_not_authorization(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/'readiness.json';write_new(p,dict(status='PASS',permission='NOT AUTHORIZED FOR EXECUTION'))
            with patch('hvac_control_expansion_b2g_v2.launcher.verify_frozen',side_effect=AssertionError('MUST_REJECT_BEFORE_IDENTITY')):
                with self.assertRaisesRegex(ValueError,'not execution permission'):authorize(p,[RID])
    def test_11_v1_failure_evidence_preserved(self):
        from .integrity import verify_v1
        self.assertEqual(verify_v1()['status'],'PASS_UNCHANGED')
    def test_12_runtime_identity_requirements_are_offline(self):
        from .integrity import runtime_requirements
        r=runtime_requirements()
        self.assertFalse(r['current_runtime_contacted']);self.assertEqual(r['BOPTEST_version'],'0.9.0')
        self.assertEqual(r['testcase'],'bestest_air');self.assertIn('MANDATORY',r['current_runtime_verification'])

def targeted():
    require(not (HOME/'TARGETED_LEDGER_RESULT.json').exists(),'Targeted result is exclusive')
    log=io.StringIO();case=C45Tests('test_03_registry_imports_consumed_pilot_and_rejects_duplicates')
    with offline_guard():result=unittest.TextTestRunner(stream=log,verbosity=2).run(unittest.TestSuite([case]))
    print(log.getvalue());(HOME/'TARGETED_LEDGER_TEST.txt').write_text(log.getvalue(),encoding='utf-8')
    report=dict(status='PASS' if result.wasSuccessful() else 'BLOCKED',tests=result.testsRun,errors=len(result.errors),failures=len(result.failures),live_operations=0)
    write_new(HOME/'TARGETED_LEDGER_RESULT.json',report)
    if result.wasSuccessful():write_new(HOME/'TRIGGER_VERIFICATION.json',case.trigger_evidence)
    return report

def qualify():
    require(read(HOME/'TARGETED_LEDGER_RESULT.json')['status']=='PASS','Corrected targeted check must pass first')
    require(not (HOME/'OFFLINE_QUALIFICATION.json').exists(),'Qualification result is exclusive')
    log=io.StringIO()
    with offline_guard():
        suite=unittest.defaultTestLoader.loadTestsFromTestCase(C45Tests)
        integration_case=next(case for case in suite if case._testMethodName=='test_04_full_fabricated_C45_corrected_finalization_path')
        suite.addTests(unittest.defaultTestLoader.loadTestsFromTestCase(FinalizationTests))
        suite.addTests(unittest.defaultTestLoader.loadTestsFromTestCase(ReviewTests))
        from hvac_control_expansion_v1.postpilot_audit_v1.tests import PackagingTests
        suite.addTests(unittest.defaultTestLoader.loadTestsFromTestCase(PackagingTests))
        from hvac_control_expansion_v1.tests import B1Tests
        for name in ('test_02_safety_activation_and_latched_release','test_03_safety_adversaries','test_04_manifest_three_arm_mapping_and_initialization',
                     'test_05_common_prefix_and_carryover','test_06_duration_and_two_hour_coverage','test_07_recovery_joint_three_pair_rule',
                     'test_08_native_interval_energy_and_duplicates','test_10_future_leakage_and_parent_fold_overlay',
                     'test_12_transport_no_retry_no_extra_advance','test_14_readbacks_and_pending_events'):
            suite.addTest(B1Tests(name))
        result=unittest.TextTestRunner(stream=log,verbosity=2).run(suite)
    (HOME/'OFFLINE_TEST_RESULTS.txt').write_text(log.getvalue(),encoding='utf-8');print(log.getvalue())
    report=dict(status='PASS' if result.wasSuccessful() else 'BLOCKED',tests=result.testsRun,
        errors=len(result.errors),failures=len(result.failures),real_instances=0,real_advances=0,
        Docker_contacted=False,network_and_process_dispatch_blocked=True,fixtures='FABRICATED_SOFTWARE_ONLY_NOT_SIMULATOR_EVIDENCE',
        inherited_mandatory_B2G_tests=38,additional_readiness_and_preservation_tests=4)
    write_new(HOME/'OFFLINE_QUALIFICATION.json',report)
    if result.wasSuccessful():write_new(HOME/'FINALIZER_INTEGRATION_RESULT.json',integration_case.integration_evidence)
    return report
