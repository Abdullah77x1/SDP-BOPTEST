"""Fabricated offline software tests; network and process creation forbidden."""
import contextlib,io,json,socket,subprocess,tempfile,time,unittest
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch
from stage4e_d2i_1.common import *
from stage4e_d2i_1.manifest import *
from stage4e_d2i_1.schema import *
from stage4e_d2i_1.planner import dry_run
from .collector import collect_mock
from .fixtures import FakeTransport,faulty
from stage4e_d2i_1.transport import BudgetedTransport,initialize_run
from .live import authorize
from stage4e.dataset import Run,FeatureSpec,build_rows,OUT
from stage4e_d0.runner import Journal
from stage4e_d0.plan import FLAGS,COOL,FAN,HEAT,TEMP,SET,LOW,UP,OCC,nominal
from stage4e_d1_v2.validation import HISTORY_POINTS,history,REFERENCE
from . import VERSION

class MetadataTests(unittest.TestCase):
    def setUp(self):self.m=canonical_manifest();self.s=canonical_schema()
    def test_expected_arithmetic(self):
        got=validate_manifest(self.m)
        for k,v in {'dependency_groups':16,'runs_total':32,'reused_development_runs':4,'new_runs':28,
            'new_scored_advances':24192,'projected_new_joint_origins':23856,'projected_cumulative_joint_origins':27264}.items():self.assertEqual(got[k],v)
        self.assertEqual(got['partition_group_counts'],{'development':8,'validation':4,'protected_final_test':4})
    def test_all_custom_boundaries(self):
        for r in self.m['runs']:
            self.assertEqual(r['end']-r['start'],259200);self.assertEqual(r['start']-r['warmup_start'],604800)
            self.assertEqual(r['start']%300,0);self.assertEqual(r['maximum_advances'],864)
    def test_preflight_bounds(self):
        m=canonical_manifest('preflight');a=validate_manifest(m)
        self.assertEqual(a['new_scored_advances'],12);self.assertEqual(a['runs_total'],4)
        self.assertTrue(all(r['mode']=='native' and r['maximum_advances']==3 for r in m['runs']))
        self.assertEqual([r['start']//86400 for r in m['runs']],[20,74,174,258])
    def test_policy_unchanged(self):
        self.assertEqual(self.m['policy'],policy_config())
        r=self.m['runs'][1]
        intents=[nominal(r,t,self.m['policy']) for t in range(r['start'],r['end'],300)]
        self.assertEqual(sum(p['command'][FLAGS[0]] for p in intents),54)
        self.assertEqual({p['command'][SET] for p in intents if p['command'][FLAGS[0]]},{296.65,296.90})
    def test_origin_semantics_with_existing_builder(self):
        r=self.m['runs'][0];start,end=r['start'],r['end']
        endpoints=[{'time':t,TEMP:296.15,OUT:289.15,COOL:1e9,FAN:1e9} for t in range(start,end+1,300)]
        ts=list(range(start,end+1,30));native={'time':ts,COOL:[400.]*len(ts),FAN:[100.]*len(ts)}
        fabricated=Run('FABRICATED','FABRICATED','native','FABRICATED','FABRICATED','FABRICATED','development',start,end,start-604800,endpoints,native)
        rows=build_rows(fabricated)
        self.assertEqual(len(rows),852)
        self.assertEqual([row['origin_time'] for row in rows],origin_times(start,end))
        for h,count in ((300,857),(600,856),(900,855),(1800,852)):
            self.assertEqual(len(origin_times(start,end,horizons=(h,))),count)
        self.assertTrue(all(abs(v-.5)<1e-12 for row in rows for k,v in row['targets'].items() if k.startswith('hvac_interval')))
        self.assertTrue(all(len(row['targets'])==8 for row in rows))
    def test_schema_groups_compatibility(self):
        self.assertEqual(validate_schema(self.s)['candidate_features'],168)
        self.assertEqual(len(self.s['prediction_targets']),8);self.assertEqual(len(self.s['raw_observations']),39)
        self.assertEqual(len(self.s['optional_collected_variables']),9)
        self.assertTrue(all(not v['auto_ML_input'] for v in self.s['raw_observations'].values()))
        self.assertFalse(self.s['dataset_construction_enabled'])
        self.assertEqual(self.s['electrical_target_boundary']['window'],'[origin+horizon-300,origin+horizon]')
    def test_source_preservation(self):self.assertEqual(verify_preservation()['status'],'PRESERVED_HASHES_VERIFIED')
    def test_select_unknown_slot(self):
        with self.assertRaises(ContractError):select_run(self.m,'replacement')
    def test_reused_slots_not_reexecuted(self):
        for r in self.m['runs']:
            if r['reused']:
                with self.assertRaisesRegex(ContractError,'REEXECUTED'):require_public_collection(r)
    def test_protected_collection_before_factory_and_file_access(self):
        r=next(r for r in self.m['runs'] if r['partition']=='protected_final_test')
        with tempfile.TemporaryDirectory() as tmp:
            out=Path(tmp)/'NOT_CREATED'
            with self.assertRaisesRegex(ContractError,'PROTECTED_COLLECTION_REFUSED'):collect_mock(self.m,r['run_id'],out)
            self.assertFalse(out.exists())
            with patch('stage4e_d2i_1_v1_0_1.live.read',side_effect=AssertionError('must not read authorization/private proofs')):
                with self.assertRaisesRegex(ContractError,'PROTECTED_COLLECTION_REFUSED'):
                    authorize(self.m,[r['run_id']],Path(tmp)/'protected_private')
    def test_fake_custody_attestation_cannot_enable(self):
        r=next(r for r in self.m['runs'] if r['partition']=='protected_final_test')
        r['custody_verified']=True;r['private_attestation']='PASS'
        with self.assertRaisesRegex(ContractError,'PROTECTED_COLLECTION_REFUSED'):require_public_collection(r)
    def test_live_no_authorization(self):
        ids=[r['run_id'] for r in self.m['runs'][:2]]
        with self.assertRaisesRegex(ContractError,'authorization file required'):authorize(self.m,ids,None)
    def test_live_incomplete_pair(self):
        with self.assertRaisesRegex(ContractError,'complete native/variation pairs'):authorize(self.m,['D2_G020_N'],None)
    def test_live_incorrect_order(self):
        with self.assertRaisesRegex(ContractError,'ordering'):authorize(self.m,['D2_G020_X','D2_G020_N'],None)
    def test_nonfixture_adapter_denied(self):
        with self.assertRaisesRegex(ContractError,'fabricated fixture'):collect_mock(self.m,'D2_G020_N','unused',object)
    def test_dry_run_only_intentions(self):
        with patch('stage4e_d2i_1_v1_0_1.collector._collect',side_effect=AssertionError('no collector')):
            result=dry_run(self.m)
        self.assertEqual(result['instances_initialized'],0);self.assertFalse(result['protected_results_access'])
        self.assertEqual(sum(p['planned_advances'] for p in result['run_intentions']),24192)
        self.assertTrue(all(p['applied_actions'].startswith('UNKNOWN') for p in result['run_intentions']))
    def test_default_cli_is_validation(self):
        from .__main__ import main
        with contextlib.redirect_stdout(io.StringIO()) as out:
            main(['--config',str(HOME/'campaign_manifest.json')])
        self.assertEqual(json.loads(out.getvalue())['status'],'MANIFEST_VALID_METADATA_ONLY')
    def test_future_cli_without_approval(self):
        from .__main__ import main
        with contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit):main(['future-live'])
    def test_named_initialization_validated(self):
        for r in self.m['runs']:
            if r['reused']:self.assertTrue(validate_initialization(r['initialization'],r['start'],r['end']))
    def test_zero_optional_not_fabricated(self):
        r=canonical_manifest('preflight')['runs'][0]
        with tempfile.TemporaryDirectory() as tmp:
            f=faulty('optional_absent')('',Path(tmp),Journal(Path(tmp)/'j'),r,self.m)
            cat=catalog_gate(f.discover(),self.s)
            fc=f.forecast({'point_names':list(POINTS),'horizon':1800,'interval':300})
            avail=forecast_gate(fc,r['start'],self.s)
            self.assertTrue(all(avail[k]['values'] is None and not cat[k]['available'] for k in self.s['optional_collected_variables']))
            with self.assertRaises(ContractError):forecast_gate(fc,r['start'],self.s,list(self.s['optional_collected_variables']))
    def test_null_required_forecast_fails(self):
        with self.assertRaises(ContractError):forecast_gate({'time':list(range(0,1801,300)),LOW:None},0,self.s)
    def test_outbound_guard_active(self):
        with socket.socket() as sock:
            with self.assertRaisesRegex(AssertionError,'FORBIDDEN'):sock.connect(('127.0.0.1',80))
    def test_process_guard_active(self):
        with self.assertRaisesRegex(AssertionError,'FORBIDDEN'):subprocess.Popen(['DO_NOT_EXECUTE_A_SIMULATOR'])
    def test_new_source_binding_matches_metadata(self):
        self.assertEqual(self.m['source_bindings'][META_PATH],sha(ROOT/META_PATH))
    def test_live_missing_preflight_denied_before_factory(self):
        ids=['D2_G020_N','D2_G020_X']
        with tempfile.TemporaryDirectory() as tmp:
            a=Path(tmp)/'FABRICATED_APPROVAL.json'
            a.write_text(json.dumps({'version':VERSION,'status':'EXPLICITLY_AUTHORIZED','purpose':'production',
                'config_sha256':digest(self.m),'implementation_manifest_sha256':'FABRICATED',
                'run_ids':ids,'maximum_fresh_instances':2,'maximum_advances':1728,
                'user_authorization_text':'FABRICATED SOFTWARE TEST ONLY','authorized_utc':'FABRICATED'}))
            with patch('stage4e_d2i_1_v1_0_1.live.implementation_identity',return_value='FABRICATED'):
                with self.assertRaisesRegex(ContractError,'preflight required'):authorize(self.m,ids,a)
    def test_draft_authorization_not_sufficient(self):
        m=canonical_manifest('preflight');ids=[r['run_id'] for r in m['runs']]
        with patch('stage4e_d2i_1_v1_0_1.live.implementation_identity',return_value='FABRICATED'):
            with self.assertRaisesRegex(ContractError,'not authorized'):
                authorize(m,ids,HOME/'preflight_approval_NOT_AUTHORIZED.json')
    def test_forecast_pair_mismatch_is_critical(self):
        from stage4e_d2i_1.pairing import forecast_pair_gate
        with tempfile.TemporaryDirectory() as tmp:
            a=Path(tmp)/'a';a.mkdir();b=Path(tmp)/'b';b.mkdir()
            value={'issued_at_sim':0,'data':{'time':[0,300],LOW:[288.15,288.15]}}
            save_new(a/'forecast_0000.json',value);save_new(b/'forecast_0000.json',value)
            self.assertTrue(forecast_pair_gate(a,b,1)['paired_issued_forecasts_verified'])
            value['data'][LOW][1]=294.15
            (b/'forecast_0000.json').write_text(json.dumps(value))
            with self.assertRaisesRegex(ContractError,'boundary values differ'):forecast_pair_gate(a,b,1)
    def test_public_acceptance_uses_native_gas_thermal_proxy(self):
        from stage4e_d2i_1.acceptance import public_pair_audit,LIMITS
        r=self.m['runs'][0]
        c={k:0 for k in LIMITS['aggregate_floor']};c['level_interval_counts']={}
        n={'time':list(range(r['start'],r['end']+1,30)),HEAT:[200.]*8641}
        result=public_pair_audit({'coverage':c},{'coverage':c},n,n,r,self.m['policy'])
        self.assertEqual(result['heating_active_intervals'],1728);self.assertTrue(result['heating_group_qualified'])
        self.assertIn('NOT_ESTABLISHED',result['campaign_decision'])
    def test_duplicate_timestamp_history_preserved(self):
        # Both coherent old/new samples at an exact event are legal evidence.
        start=20*86400+8*3600;ts=[start,start,start+30,start+60]
        pairs=[REFERENCE.pair(start-1),REFERENCE.pair(start),REFERENCE.pair(start+30),REFERENCE.pair(start+60)]
        from stage4e_d1r.proposed_validation import HEAT as HS,COOL as CS
        data={'time':ts,**{k:[0.]*4 for k in HISTORY_POINTS}}
        data[HS]=[p[0] for p in pairs];data[CS]=[p[1] for p in pairs];data[TEMP]=[296.15]*4
        self.assertTrue(history(data,start,start+60));self.assertEqual(data['time'].count(start),2)

def mutation_test(mutator):
    def test(self):
        mutator(self.m)
        with self.assertRaises((ContractError,KeyError,TypeError)):validate_manifest(self.m)
    return test

MUTATIONS={
 'duplicate_run':lambda m:m['runs'].append(deepcopy(m['runs'][0])),
 'duplicate_group':lambda m:m['groups'].append(deepcopy(m['groups'][0])),
 'missing_partition':lambda m:m['groups'][0].pop('partition'),
 'wrong_partition':lambda m:m['runs'][0].update(partition='validation'),
 'protected_relabel':lambda m:next(r for r in m['runs'] if r['partition']=='protected_final_test').update(dataset_partition='development'),
 'pair_removed':lambda m:m['runs'].pop(1),
 'wrong_mode':lambda m:m['runs'][1].update(mode='native'),
 'wrong_step':lambda m:m['runs'][0].update(step=600),
 'bool_step':lambda m:m['runs'][0].update(step=True),
 'wrong_native_step':lambda m:m['runs'][0].update(native_step=60),
 'wrong_duration':lambda m:m['groups'][0].update(end=m['groups'][0]['end']+300),
 'wrong_warmup':lambda m:m['runs'][0]['initialization'].update(warmup_period=0),
 'clipped_warmup':lambda m:m['groups'][0].update(warmup_start=0),
 'unaligned_start':lambda m:m['runs'][0].update(start=m['runs'][0]['start']+1),
 'bad_scenario':lambda m:m['runs'][2]['initialization'].update(scenario_key='invalid'),
 'custom_named_masquerade':lambda m:m['runs'][0]['initialization'].update(scenario_key='typical_cool_day'),
 'overlap':lambda m:m['groups'][1].update(warmup_start=m['groups'][0]['start'],start=m['groups'][0]['start']+604800,end=m['groups'][0]['start']+864000),
 'altered_slot':lambda m:m['runs'][0].update(run_id='D2_REPLACEMENT'),
 'hash_mismatch':lambda m:m['source_bindings'].update({'stage4e_d0/plan.py':'0'*64}),
 'hash_removed':lambda m:m['source_bindings'].clear(),
 'wrong_signal':lambda m:m['reporting']['core_forecasts'].append('invented'),
 'policy_change':lambda m:m['policy'].update(cold_activation_margin_k=0),
 'reuse_new':lambda m:m['runs'][0].update(reused=True),
 'origin_lags':lambda m:m['origin_support'].update(lags_s=[0]),
 'extra_budget':lambda m:m['runs'][0].update(maximum_advances=865),
 'bad_initial_method':lambda m:m['runs'][0]['initialization'].update(method='fallback'),
 'window_end_year':lambda m:m['runs'][0].update(end=31536000),
 'custody_bypass':lambda m:m.update(protected_custody_status='VERIFIED'),
 'new_derived_units':lambda m:m.update(schema_sha256='0'*64),
 'acceptance_relaxation':lambda m:m['acceptance']['cooling_group_floor'].update(cooling_active=0),
}
for name,mutation in MUTATIONS.items():setattr(MetadataTests,'test_reject_'+name,mutation_test(mutation))

def schema_mutation(path,value):
    def test(self):
        obj=self.s
        for key in path[:-1]:obj=obj[key]
        obj[path[-1]]=value
        with self.assertRaises(ContractError):validate_schema(self.s)
    return test
for name,path,value in (
 ('unit',['raw_observations',TEMP,'unit'],'degC'),
 ('targets',['prediction_targets'],{}),
 ('feature_role',['model_feature_candidates'],{}),
 ('electrical_window',['electrical_target_boundary','average_interval_s'],1800),
 ('gas_label',['electrical_target_boundary','gas_excluded'],False),
 ('static_timeseries',['static_specifications','role'],'feature'),
 ('source',['raw_observations',TEMP,'source'],'unknown'),
 ('optional_zero',['optional_collected_variables','relHum','missing_policy'],'ZERO')):
    setattr(MetadataTests,'test_schema_reject_'+name,schema_mutation(path,value))

class CollectorTests(unittest.TestCase):
    def preflight(self,fault=None):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        m=canonical_manifest('preflight');d=Path(self.tmp.name)/'FABRICATED'
        return collect_mock(m,m['runs'][0]['run_id'],d,faulty(fault) if fault else FakeTransport),d
    def test_preflight_three_native_advances(self):
        result,d=self.preflight()
        self.assertEqual(result['classification'],'PASS_PREFLIGHT_RAW',result)
        self.assertEqual(result['advance_requests_attempted'],3);self.assertEqual(result['native_samples'],31)
        self.assertTrue(result['data_is_fabricated']);self.assertFalse(result['training_release'])
        self.assertEqual(read(d/'NATIVE_WARMUP_HISTORY.json')['time'][-1]-read(d/'NATIVE_WARMUP_HISTORY.json')['time'][0],604800)
    def test_missing_optional_preflight_is_inconclusive(self):
        result,d=self.preflight('optional_absent')
        self.assertEqual(result['classification'],'INCONCLUSIVE_OPTIONAL_REPORTING',result)
        self.assertEqual(result['advance_requests_attempted'],3)
        data=read(d/'PREFLIGHT_72H_PASSIVE_FORECAST.json')['availability']
        self.assertIsNone(data['relHum']['values']);self.assertEqual(data['relHum']['status'],'UNAVAILABLE_NOT_ZERO')
    def test_optional_value_absence_is_not_zero(self):
        result,d=self.preflight('optional_values_absent')
        self.assertEqual(result['classification'],'INCONCLUSIVE_OPTIONAL_REPORTING',result)
    def test_no_mock_retry_output_directory(self):
        result,d=self.preflight()
        m=canonical_manifest('preflight')
        with self.assertRaises(FileExistsError):collect_mock(m,m['runs'][0]['run_id'],d)
    def test_no_initialization_retry_or_fallback(self):
        result,d=self.preflight('initialize_error')
        self.assertEqual(result['classification'],'FAILED');self.assertEqual(result['initialization_attempts'],1)
        self.assertEqual(result['advance_requests_attempted'],0)
    def test_lost_advance_response_consumes_attempt(self):
        result,d=self.preflight('advance_error')
        self.assertEqual(result['advance_requests_attempted'],1);self.assertEqual(result['advance_responses_received'],0)
        self.assertEqual(result['cleanup'],'STOP_ACK_AND_REMOVAL_VERIFIED');self.assertEqual(result['classification'],'FAILED')
    def test_interrupted_mock_stops(self):
        result,d=self.preflight('interrupt')
        self.assertEqual(result['advance_requests_attempted'],1);self.assertEqual(result['classification'],'FAILED')
        self.assertIn('KeyboardInterrupt',result['error']);self.assertFalse(result['training_release'])
    def test_missing_native_gas_fails(self):
        result,d=self.preflight('missing_gas')
        self.assertEqual(result['classification'],'FAILED');self.assertEqual(result['advance_requests_attempted'],0)
    def test_wrong_catalog_units_fails_before_init(self):
        result,d=self.preflight('wrong_unit')
        self.assertEqual(result['classification'],'FAILED');self.assertEqual(result['initialization_attempts'],0)
    def test_wrong_clock_fails_first_advance(self):
        result,d=self.preflight('wrong_time')
        self.assertEqual(result['classification'],'FAILED');self.assertEqual(result['advance_requests_attempted'],1)
    def test_cleanup_failure_invalidates(self):
        result,d=self.preflight('cleanup_error')
        self.assertEqual(result['classification'],'FAILED');self.assertEqual(result['cleanup'],'STOP_UNCONFIRMED')
    def test_bad_cleanup_ack_invalidates(self):
        result,d=self.preflight('cleanup_bad_ack')
        self.assertEqual(result['classification'],'FAILED');self.assertEqual(result['cleanup'],'STOP_UNCONFIRMED')
    def test_native_warmup_missing_regular_sample(self):
        result,d=self.preflight('warmup_offgrid')
        self.assertEqual(result['classification'],'FAILED');self.assertEqual(result['advance_requests_attempted'],0)
        self.assertIn('regular native warmup',result['error'])
    def test_campaign_critical_failure_stops_remaining_slots(self):
        from .live import future_live
        m=canonical_manifest('preflight');ids=[r['run_id'] for r in m['runs']]
        with tempfile.TemporaryDirectory() as tmp:
            with patch('stage4e_d2i_1_v1_0_1.live.authorize',return_value={'evidence':'FABRICATED'}), \
                patch('stage4e_d2i_1_v1_0_1.live.verify_preservation'), \
                patch('stage4e_d1_v2.runtime.verify_runtime',return_value={'evidence':'FABRICATED_NO_DOCKER_CALL'}), \
                patch('stage4e_d2i_1_v1_0_1.live.HOME',Path(tmp)), \
                patch('stage4e_d2i_1_v1_0_1.collector._collect',return_value={'classification':'FAILED','data_is_fabricated':True}) as collect:
                result=future_live(m,ids,'FABRICATED_APPROVAL_BYPASSED_FOR_ORCHESTRATOR_UNIT_TEST')
            self.assertEqual(collect.call_count,1);self.assertEqual(result['unused_attempt_ids'],ids[1:])
            self.assertEqual(result['classification'],'FAILED_OR_INCOMPLETE_STOPPED')
    def test_named_api_adapter(self):
        m=canonical_manifest();r=next(r for r in m['runs'] if r['reused'])
        with tempfile.TemporaryDirectory() as tmp:
            f=FakeTransport('',Path(tmp),Journal(Path(tmp)/'j'),r,m);c=BudgetedTransport(f,r)
            self.assertEqual(initialize_run(c,r)['time'],r['start'])
            with self.assertRaisesRegex(ContractError,'retry'):initialize_run(c,r)
    def test_native_mutation_forbidden(self):
        m=canonical_manifest('preflight');r=m['runs'][0]
        with tempfile.TemporaryDirectory() as tmp:
            c=BudgetedTransport(FakeTransport('',Path(tmp),Journal(Path(tmp)/'j'),r,m),r)
            initialize_run(c,r);c.request('PUT','step',{'step':300});c.request('GET','step')
            with self.assertRaises(ContractError):c.request('POST','advance',{**dict.fromkeys(FLAGS,0),FLAGS[0]:1,SET:296.9})
            self.assertEqual(c.advance_attempts,0)
            for i in range(3):c.request('POST','advance',dict.fromkeys(FLAGS,0))
            with self.assertRaisesRegex(ContractError,'budget'):c.request('POST','advance',dict.fromkeys(FLAGS,0))
    def test_full_custom_native(self):self.full('D2_G020_N')
    def test_full_custom_variation_and_unchanged_events(self):self.full('D2_G020_X')
    def test_validation_partition_preserved(self):
        # Full original window; never relabeled to development for test convenience.
        self.full('D2_G100_N')
    def full(self,rid):
        m=canonical_manifest()
        with tempfile.TemporaryDirectory() as tmp:
            d=Path(tmp)/'FABRICATED'
            result=collect_mock(m,rid,d)
            self.assertEqual(result['classification'],'PASS_VALID_RAW',result)
            self.assertEqual(result['advance_requests_attempted'],864);self.assertEqual(result['endpoints'],865)
            self.assertEqual(result['native_samples'],8641);self.assertEqual(result['pending_events_resolved'],6)
            self.assertEqual(result['partition'],select_run(m,rid)['partition'])
            resolutions=read(d/'event_resolutions.json');ends=read(d/'endpoints.json')
            records=[json.loads(line) for line in (d/'steps.jsonl').read_text().splitlines()]
            for record in records:
                self.assertEqual(record['known_path'][0]['known_at_sim'],record['start'])
                self.assertEqual(record['known_path'][0]['command'],record['applied_command'])
                self.assertLess(record['observation_received_order'],record['origin_cutoff_order'])
                self.assertLess(record['forecast_received_order'],record['origin_cutoff_order'])
                self.assertLess(record['origin_cutoff_order'],record['endpoint_received_order'])
                self.assertTrue(record['future_safety_veto_unknown_at_origin'])
            for event in resolutions:
                original=next(e for e in ends if e['time']==event['event_time'])
                self.assertEqual(original,event['endpoint_at_event']);self.assertFalse(event['extra_advance_inserted'])
            if rid.endswith('_X'):
                self.assertEqual(result['coverage']['verified_full_pulses'],9)
                self.assertEqual(sum(result['coverage']['level_interval_counts'].values()),54)
            self.assertFalse(any('dataset' in p.name.lower() and p.suffix=='.csv' for p in d.iterdir()))
    def test_production_missing_optional_stops_before_init(self):
        m=canonical_manifest()
        with tempfile.TemporaryDirectory() as tmp:
            result=collect_mock(m,'D2_G020_N',Path(tmp)/'FABRICATED',faulty('optional_absent'))
            self.assertEqual(result['classification'],'FAILED');self.assertEqual(result['initialization_attempts'],0)
    def test_persistent_event_mismatch_fails_without_extra_advance(self):
        m=canonical_manifest()
        with tempfile.TemporaryDirectory() as tmp:
            result=collect_mock(m,'D2_G020_N',Path(tmp)/'FABRICATED',faulty('persistent_native'))
            self.assertEqual(result['classification'],'FAILED',result);self.assertEqual(result['advance_requests_attempted'],97)
    def test_wrong_active_readback_fails(self):
        m=canonical_manifest()
        with tempfile.TemporaryDirectory() as tmp:
            result=collect_mock(m,'D2_G020_X',Path(tmp)/'FABRICATED',faulty('wrong_active'))
            self.assertEqual(result['classification'],'FAILED',result);self.assertEqual(result['advance_requests_attempted'],109)
