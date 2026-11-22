"""FABRICATED software tests. Network/process dispatch blocked by run_tests()."""
import contextlib,io,json,math,sqlite3,tempfile,unittest
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch
from .campaign import *
from .comparison import compare_endpoints
from .analysis import recovery_time,comfort
from .contracts import labels,planned_at_origin,validate_origin_path,overlay_metadata,matched_size_plan
from .integrity import reservation_check,source_evidence
from .live import baseline,authorize
from .registry import Registry
from .collector import collect_mock
from stage4e_d0.plan import Safety,FLAGS,FLAG,SET,TEMP,LOW,UP,OCC,COOL,FAN,HEAT,append_native,energy_audit
from stage4e_d2i_1.transport import BudgetedTransport,initialize_run
from stage4e_d2i_1.common import ContractError
from stage4e_d2i_1_v1_0_1.fixtures import FakeTransport,faulty
from stage4e_d1_v2.validation import endpoint,initial_native,history,EventTracker,command_guard,REFERENCE

class B1Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.m=canonical_manifest();cls.n,cls.c15,cls.c45=cls.m['runs'][:3]
    def context(self,run=None,t=None,temp=296.15):
        run=run or self.c15;t=t or run['start']+39600
        obs={TEMP:temp,'con_oveTSetHea_u':294.15,'con_oveTSetCoo_u':297.15,'time':t,**dict.fromkeys(FLAGS,0)}
        bound={'time':t,LOW:294.15,UP:297.15,OCC:1.}
        return nominal(run,t),obs,bound

    def test_01_exact_schedules_all_days(self):
        for run in self.m['runs']:
            commands=[nominal(run,t) for t in range(run['start'],run['end'],300)]
            self.assertEqual(sum(r['command'][FLAG] for r in commands),3*DURATIONS[run['arm']]//300)
            for r in commands:
                c=r['command'];t=r['start']%86400
                self.assertFalse(any(c[f] for f in FLAGS[1:]))
                if c[FLAG]:self.assertTrue(39600<=t<39600+DURATIONS[run['arm']]);self.assertAlmostEqual(c[SET]-273.15,23.75)
                else:self.assertEqual(c,native_command())
            for day in range(3):
                start=run['start']+day*86400+39600;release=start+DURATIONS[run['arm']]
                self.assertEqual(nominal(run,start-300)['command'],native_command())
                self.assertEqual(nominal(run,release)['command'],native_command())
            self.assertEqual(commands[-1]['command'],native_command())
            for t in (run['start']-300,run['end'],run['start']+1):
                with self.assertRaises(ContractError):nominal(run,t)

    def test_02_safety_activation_and_latched_release(self):
        p,o,b=self.context(temp=294.90);s=Safety(self.m['policy'])
        self.assertEqual(s.decide(p,o,b,0)[0][FLAG],1) # equality is allowed
        o[TEMP]=294.65;self.assertEqual(s.decide(p,o,b,0)[0][FLAG],1)
        o[TEMP]=294.6499;self.assertEqual(s.decide(p,o,b,0)[0],native_command())
        o[TEMP]=296.;self.assertIn('latched',s.decide(p,o,b,0)[1])
        p2,o2,b2=self.context(t=p['start']+86400)
        self.assertEqual(s.decide(p2,o2,b2,0)[0][FLAG],1)

    def test_03_safety_adversaries(self):
        for kind in ('unoccupied','cold','hot','infeasible','stale','future','nonfinite','schedule'):
            p,o,b=self.context();s=Safety(self.m['policy'])
            if kind=='unoccupied':b[OCC]=0
            if kind=='cold':o[TEMP]=294.8999
            if kind=='hot':o[TEMP]=297.6501
            if kind=='infeasible':o['con_oveTSetHea_u']=296.8
            if kind=='future':o['time']+=300
            if kind=='nonfinite':o[TEMP]=math.nan
            if kind=='schedule':b[UP]=298.15
            if kind in ('stale','future','nonfinite','schedule'):
                with self.assertRaises(ContractError):s.decide(p,o,b,31 if kind=='stale' else 0)
            else:self.assertEqual(s.decide(p,o,b,0)[0],native_command())

    def test_04_manifest_three_arm_mapping_and_initialization(self):
        self.assertTrue(validate_manifest(self.m));self.assertEqual(len({r['group_id'] for r in self.m['runs']}),2)
        for r in self.m['runs']:
            self.assertEqual(r['initialization']['warmup_period'],604800)
            self.assertEqual(r['partition'],'development');self.assertFalse(r['reused'])
            self.assertEqual(r['initialization']['method'],'custom' if r['group_id']=='D2_G174' else 'scenario')
            if r['group_id']=='D2_G146':self.assertEqual(r['initialization']['scenario_key'],'typical_cool_day')
        for field,value in [('group_id','fake'),('partition','validation'),('run_id','old'),('start',0),('arm','C99')]:
            m=deepcopy(self.m);m['runs'][1][field]=value
            with self.assertRaises(ContractError):validate_manifest(m)

    def test_05_common_prefix_and_carryover(self):
        self.assertEqual(first_divergence(self.n,self.c15),self.n['start']+39600)
        self.assertEqual(first_divergence(self.c15,self.c45),self.n['start']+40500)
        a=[{'time':t,TEMP:296.} for t in range(self.n['start'],self.n['end']+1,300)]
        b=deepcopy(a);b[120][TEMP]+=.1 # 10:00, missed by old 09:00 gate
        with self.assertRaises(ContractError):compare_endpoints(a,b,self.n['start']+39600)
        b=deepcopy(a);b[200][TEMP]+=.1;b[420][TEMP]+=.2
        compare_endpoints(a,b,self.n['start']+39600) # legitimate later divergence
        with self.assertRaises(ContractError):compare_endpoints(a,b,self.n['end'],True)
        b=deepcopy(a);[r.update(optional_extra=1) for r in b]
        compare_endpoints(a,b,self.n['end'],True)

    def fixture_records(self,run):
        records=[]
        for t in range(run['start'],run['end'],300):
            c=nominal(run,t)['command']
            records.append(dict(start=t,end=t+300,applied_command=c,reason='fixture'))
        return records

    def test_06_duration_and_two_hour_coverage(self):
        for run in (self.c15,self.c45):
            rec=self.fixture_records(run);c=coverage(rec,None,{},run)
            self.assertEqual(len(c['episodes']),3);self.assertTrue(all(e['complete'] for e in c['episodes']))
            self.assertTrue(all(e['recovery_native_intervals']==24 for e in c['episodes']))
            self.assertEqual(c['applied_intervals'],9 if run['arm']=='C15' else 27)
            rec[133]['applied_command']=native_command()
            self.assertFalse(coverage(rec,None,{},run)['episodes'][0]['complete'])
        rec=self.fixture_records(self.c15)
        for r in rec:r['applied_command']=native_command();r['reason']='unoccupied_veto'
        self.assertEqual(coverage(rec,None,{},self.c15)['applied_intervals'],0)
        rec=self.fixture_records(self.c15)[:140]
        self.assertFalse(coverage(rec,None,{},self.c15)['episodes'][0]['complete'])

    def test_07_recovery_joint_three_pair_rule(self):
        pairs=[dict(time_s=t,delta_temperature_k=.04,delta_electric_kw=.009) for t in range(0,7201,300)]
        self.assertEqual(recovery_time(pairs,0),0)
        pairs[1]['delta_electric_kw']=.011;self.assertEqual(recovery_time(pairs,0),10)
        for p in pairs:p['delta_temperature_k']=.051
        self.assertIsNone(recovery_time(pairs,0))

    def test_08_native_interval_energy_and_duplicates(self):
        from stage4e.dataset import NativeElectric
        ts=list(range(0,1801,30));power=[float(t) for t in ts]
        native={'time':ts,COOL:power,FAN:[10.]*len(ts),HEAT:[20.]*len(ts)}
        e=NativeElectric(native).interval(0,300)
        self.assertAlmostEqual(e['average_kw'],.160)
        self.assertNotEqual(e['average_kw'],(native[COOL][10]+10)/1000)
        chunk={k:v[:11] for k,v in native.items()};combined={};append_native(combined,chunk,0,300)
        chunk2={k:v[10:21] for k,v in native.items()};append_native(combined,chunk2,300,600)
        self.assertEqual(len(combined['time']),21)
        dup={'time':[0,30,30,60],COOL:[0,0,100,100],FAN:[0]*4}
        # zero-time jumps preserve each side of the event
        from stage4e_d2_public.export import interval
        self.assertEqual(interval(dup,0,60,[COOL]),50)
        bad=deepcopy(native);bad['time'][1]=31
        with self.assertRaises(ContractError):NativeElectric(bad)

    def test_09_original_sixteen_target_last_interval_contract(self):
        ts=list(range(0,1801,30));native={'time':ts,COOL:list(map(float,ts)),FAN:[100.]*len(ts),HEAT:[200.]*len(ts)}
        endpoints=[{'time':t,TEMP:273.15+t/300} for t in range(0,1801,300)]
        out=labels(endpoints,native,0)
        self.assertEqual(len(out),16);self.assertAlmostEqual(out['target_indoor_temp_30min_c'],6.)
        self.assertAlmostEqual(out['target_cooling_electric_power_30min_kw'],1.65)
        self.assertAlmostEqual(out['target_heating_thermal_power_30min_kw'],.18)

    def test_10_future_leakage_and_parent_fold_overlay(self):
        t=self.c15['start']+39600;path=planned_at_origin(self.c15,t);validate_origin_path(path,t)
        self.assertEqual(path[3]['command'],native_command())
        for key,value in [('future_veto',True),('known_at_sim',t+1),('source','realized_future_command')]:
            bad=deepcopy(path);bad[0][key]=value
            with self.assertRaises(ContractError):validate_origin_path(bad,t)
        for r in self.m['runs']:
            overlay=overlay_metadata(r);self.assertEqual(len(overlay['origins']),852)
            self.assertEqual(overlay['training_default'],r['arm']!='NREF')
            self.assertEqual(overlay['outer_held_fold'],4 if r['group_id']=='D2_G174' else 1)

    def test_11_append_only_consumption_and_output_path_retry(self):
        with tempfile.TemporaryDirectory() as td:
            reg=Registry.create(Path(td)/'ledger',baseline(self.m));runs=self.m['runs'][:2]
            batch=reg.new_batch('test',runs,{})
            p=reg.reserve('test',runs[0]);self.assertFalse(p.exists()) # consumed before collect
            with self.assertRaises(Exception):reg.reserve('test',runs[0])
            with self.assertRaises(ContractError):reg.new_batch('changed_output',runs,{})
            with reg.connect() as db:
                with self.assertRaises(sqlite3.IntegrityError):db.execute("DELETE FROM reservations")
            with self.assertRaises(ContractError):reg.reserve('test',runs[1]) # unresolved previous instance

    def test_12_transport_no_retry_no_extra_advance(self):
        class Inner:
            last_receipt_order=1
            def deploy(self):return 'fixture'
            def request(self,method,key,data):return 300 if key=='step' else {}
            def stop(self):return {}
        r=deepcopy(self.c15);r['maximum_advances']=1;c=BudgetedTransport(Inner(),r)
        c.deploy()
        with self.assertRaises(ContractError):c.deploy()
        initialize_run(c,r)
        with self.assertRaises(ContractError):initialize_run(c,r)
        c.request('PUT','step',{'step':300});c.request('GET','step')
        c.request('POST','advance',native_command())
        with self.assertRaises(ContractError):c.request('POST','advance',native_command())

    def test_13_source_hashes_and_reserved_periods(self):
        self.assertEqual(len(source_evidence()),33)
        self.assertGreater(reservation_check(self.m)['metadata_comparisons'],90)

    def test_14_readbacks_and_pending_events(self):
        p,o,b=self.context();c=p['command'];obs=deepcopy(o);obs.update(time=p['start']+300);obs.update(c)
        fc={'time':obs['time'],'issued_at':p['start'],'lower_k':294.15,'upper_k':297.15,'occupancy':1}
        orders=dict(observation=1,forecast=2,cutoff=3,response=4)
        endpoint(p['start'],c,obs,fc,orders,0)
        for k,v in [(FLAG,0),(SET,297.15),(FLAGS[1],1)]:
            wrong=deepcopy(obs);wrong[k]=v
            with self.assertRaises(ValueError):endpoint(p['start'],c,wrong,fc,orders,0)
        tracker=EventTracker();tracker.pending=dict(event_time=p['start'],endpoint_at_event=o)
        with self.assertRaises(ValueError):tracker.guard(p['start'],c,o,0,1)
        with self.assertRaises(ValueError):tracker.guard(p['start'],native_command(),o,0,0)

    def test_15_sampled_comfort_keeps_native_violations(self):
        p,o,b=self.context(temp=298.15)
        rec=[dict(start=p['start'],current_observation=o,current_boundary=b)]
        c=comfort(rec,p['start'],p['start']+300,True)
        self.assertAlmostEqual(c['degree_hours'],1/12);self.assertEqual(c['violation_minutes'],5)

    def test_16_complete_fabricated_collection(self):
        # Full 864 advances/865 endpoints, native events, history, forecasts, energy & cleanup.
        with tempfile.TemporaryDirectory() as td:
            for run in (self.n,self.c15,self.c45,self.m['runs'][3]):
                result=collect_mock(self.m,run['run_id'],Path(td)/run['run_id'])
                self.assertEqual(result['classification'],'PASS_VALID_RAW',result)
                self.assertEqual(result['advances'],864);self.assertEqual(result['endpoints'],865)
                self.assertEqual(result['native_samples'],8641);self.assertEqual(result['unresolved_events'],0)
                self.assertEqual(result['cleanup'],'STOP_ACK_AND_REMOVAL_VERIFIED')
                if run['arm']!='NREF':self.assertTrue(all(e['complete'] for e in result['coverage']['episodes']))

    def test_17_failed_collection_stops_and_cleanup_once(self):
        with tempfile.TemporaryDirectory() as td:
            for fault in ('wrong_active','advance_error','wrong_unit','warmup_offgrid','missing_gas','cleanup_bad_ack'):
                result=collect_mock(self.m,self.c15['run_id'],Path(td)/fault,faulty(fault))
                self.assertEqual(result['classification'],'FAILED',fault)
                if fault=='advance_error':self.assertEqual(result['advance_requests_attempted'],1)

    def test_18_authorization_denies_missing_or_wrong_binding(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/'approval.json';p.write_text('{}')
            # isolate only identity I/O; authorization itself is unchanged and still must reject.
            with patch('hvac_control_expansion_v1.live.verify_frozen',return_value='test'):
                with self.assertRaises(ContractError):authorize(self.m,p)

    def test_19_matched_size_metadata_plan(self):
        for run in self.m['runs'][::3]:
            rows=matched_size_plan(run)
            self.assertEqual(len(rows),852);self.assertEqual(rows,matched_size_plan(run))
            self.assertEqual(sum(r['policy_pair']=='C15_C45' for r in rows),426)
            self.assertEqual(len({r['time_s'] for r in rows}),852)
            self.assertTrue(all(r['group_id']==run['group_id'] for r in rows))
            self.assertTrue(all(r['selection_inputs']=='METADATA_ONLY_NOT_OUTCOMES' for r in rows))

def run_tests(stream):
    denial=AssertionError('OFFLINE_NETWORK_PROCESS_DISPATCH_FORBIDDEN')
    with contextlib.ExitStack() as stack:
        for name in ('socket.socket.connect','socket.socket.connect_ex','socket.create_connection','socket.getaddrinfo','subprocess.Popen','os.system','os.startfile'):
            stack.enter_context(patch(name,side_effect=denial))
        return unittest.TextTestRunner(stream=stream,verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(B1Tests))

if __name__=='__main__':
    import sys
    require(not (HOME/'IMPLEMENTATION_MANIFEST.json').exists(),'Frozen QA cannot be overwritten; use unittest for read-only verification')
    log=io.StringIO();result=run_tests(log);print(log.getvalue())
    (HOME/'OFFLINE_TEST_RESULTS.txt').write_text(log.getvalue(),encoding='utf-8')
    (HOME/'OFFLINE_QA.json').write_text(json.dumps(dict(status='PASS' if result.wasSuccessful() else 'FAIL',tests=result.testsRun,
        failures=len(result.failures),errors=len(result.errors),fixtures='FABRICATED_NOT_BOPTEST_EVIDENCE',
        network_and_process_dispatch_blocked=True,real_instances=0,real_advances=0),indent=2))
    sys.exit(0 if result.wasSuccessful() else 1)
