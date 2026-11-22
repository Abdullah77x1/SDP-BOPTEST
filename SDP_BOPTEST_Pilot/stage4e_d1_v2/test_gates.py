"""Focused offline campaign/handoff gates; no transport or simulator."""
import tempfile,unittest,json
from pathlib import Path
from unittest.mock import patch
from . import runner,handoff
from .test_contract import obs,check

class GateTests(unittest.TestCase):
    def test_exact_four_new_slots_and_two_pairs(self):
        from . import runtime
        config=runner.read(runner.HERE/'campaign.json');seen=[]
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);runner.save_new(root/'campaign.json',config)
            def fake_collect(run,c,d,ref,binding):
                seen.append(run['attempt_id']);d.mkdir()
                return {'attempt_id':run['attempt_id'],'classification':'PASS_VALID_RAW'}
            with patch.object(runner,'HERE',root),patch.object(runner,'verify_frozen',return_value='FIXTURE'),patch.object(runner,'authorize',return_value={'proposal_sha256':'FIXTURE'}),patch.object(runtime,'verify_runtime',return_value={'fabricated':True}),patch.object(runner,'collect_one',side_effect=fake_collect),patch.object(runner,'pair_gate',return_value=True) as pairs,patch.object(runner,'campaign_gate',return_value='INCONCLUSIVE_EXCITATION'):
                result=runner.execute('fixture')
                self.assertEqual(seen,[r['attempt_id'] for r in config['runs']]);self.assertEqual(pairs.call_count,2)
                self.assertEqual(result['unused_attempt_ids'],[]);self.assertFalse(result['training_release'])
    def gate_fixture(self,p):
        run=runner.read(runner.HERE/'campaign.json')['runs'][0];d=p/run['attempt_id'];d.mkdir()
        runner.save_new(p/'CAMPAIGN_COMPLETED.json',{'classification':'PASS_QUALIFICATION','campaign_id':runner.CAMPAIGN_ID,'binding':{'proposal_sha256':'FIXTURE'}})
        runner.save_new(p/'ARTIFACT_MANIFEST.json',{'files':{}})
        return run,d
    def test_unresolved_complete_campaign_cannot_hand_off(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp);r,d=self.gate_fixture(p);runner.save_new(d/'RUN_COMPLETED.json',{'unresolved_events':1})
            with patch.object(handoff,'verify_frozen',return_value='FIXTURE'),patch.object(handoff,'original_read') as original,self.assertRaises(runner.ContractError):handoff.read_qualified_run(p,r)
            original.assert_not_called()
    def test_missing_resolution_cannot_hand_off(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp);r,d=self.gate_fixture(p);runner.save_new(d/'RUN_COMPLETED.json',{'unresolved_events':0})
            (d/'steps.jsonl').write_text(json.dumps({'end':r['start']+28800,'setpoint_validation_at_receipt':{'status':'PENDING_EVENT_VERIFICATION'}})+'\n')
            runner.save_new(d/'event_resolutions.json',[])
            with patch.object(handoff,'verify_frozen',return_value='FIXTURE'),patch.object(handoff,'original_read') as original,self.assertRaises(runner.ContractError):handoff.read_qualified_run(p,r)
            original.assert_not_called()
    def test_resolved_gate_preserves_original_endpoint_for_builder(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp);r,d=self.gate_fixture(p);t=r['start']+28800;x=obs(t)
            runner.save_new(d/'RUN_COMPLETED.json',{'unresolved_events':0})
            (d/'steps.jsonl').write_text(json.dumps({'end':t,'setpoint_validation_at_receipt':{'status':'PENDING_EVENT_VERIFICATION'}})+'\n')
            runner.save_new(d/'endpoint_0096.json',x)
            runner.save_new(d/'event_resolutions.json',[{'event_time':t,'status':'RESOLVED_EVENT_VERIFICATION','resolved_at_sim':t+300,'endpoint_at_event':x}])
            with patch.object(handoff,'verify_frozen',return_value='FIXTURE'),patch.object(handoff,'original_read',return_value='ORIGINAL_BUILDER') as original:
                self.assertEqual(handoff.read_qualified_run(p,r),'ORIGINAL_BUILDER');original.assert_called_once_with(p,r)
            self.assertEqual(runner.read(d/'endpoint_0096.json'),x)

if __name__=='__main__':unittest.main(verbosity=2)
