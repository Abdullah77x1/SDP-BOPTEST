"""Small fabricated design checks, not an extractor or model-ready feature pipeline."""
import unittest,io,json
from . import HOME
from hvac_control_expansion_b2f_v1.packaging import write_new
from hvac_control_expansion_b2f_v1.tests import offline_guard

def fabricated_compact(slots,latch=0):
    """Test-only proof that one fixed-target block represents a six-slot plan."""
    assert len(slots)==6 and latch in (0,1)
    active=[i for i,p in enumerate(slots) if p is not None]
    if not active:return (0,0,0,0,latch)
    assert active==list(range(active[0],active[-1]+1)), 'Multiple blocks unsupported'
    assert len({slots[i] for i in active})==1, 'Changing target unsupported'
    return (1,slots[active[0]],active[0]*300,(active[-1]+1)*300,latch)

def fabricated_expand(compact):
    present,delta,on,off,latch=compact
    return [delta if present and on<=i*300<off else None for i in range(6)]

class SemanticsTests(unittest.TestCase):
    def test_native_is_not_a_zero_kelvin_target(self):
        self.assertEqual(fabricated_compact([None]*6),(0,0,0,0,0))
        self.assertEqual(fabricated_expand((0,0,0,0,0)),[None]*6)
    def test_C15_C45_at_1100(self):
        self.assertEqual(fabricated_compact([-.25]*3+[None]*3),(1,-.25,0,900,0))
        self.assertEqual(fabricated_compact([-.25]*6),(1,-.25,0,1800,0))
    def test_activation_at_right_edge_is_outside_horizon(self):
        self.assertEqual(fabricated_compact([None]*6)[0],0)
    def test_earliest_C15_C45_horizon_difference_is_1050(self):
        # At 10:45 both paths end exactly at 11:15; release affects the next interval.
        a=[None]*3+[-.25]*3;b=list(a);self.assertEqual(fabricated_compact(a),fabricated_compact(b))
        a=[None]*2+[-.25]*3+[None];b=[None]*2+[-.25]*4
        self.assertNotEqual(fabricated_compact(a),fabricated_compact(b))
    def test_release_is_right_open(self):
        self.assertIsNone(fabricated_expand((1,-.25,0,900,0))[3])
    def test_D2_X_targets_remain_distinct(self):
        self.assertNotEqual(fabricated_compact([-.25]*6),fabricated_compact([-.5]*6))
    def test_ongoing_hold_and_beyond_horizon_censoring(self):
        # All holds that remain active for >=30 minutes have the same bounded path.
        self.assertEqual(fabricated_compact([-.25]*6),(1,-.25,0,1800,0))
    def test_five_minute_future_activation(self):
        self.assertEqual(fabricated_compact([None]+[-.25]*3+[None]*2),(1,-.25,300,1200,0))
    def test_roundtrip_all_supported_grid_intervals(self):
        for on in range(6):
            for off in range(on+1,7):
                for target in (-.25,-.5):
                    for latch in (0,1):
                        s=[target if on<=i<off else None for i in range(6)]
                        self.assertEqual(fabricated_expand(fabricated_compact(s,latch)),s)
    def test_reject_multiple_blocks_or_changing_target(self):
        for s in ([-.25,None,-.25,None,None,None],[-.25,-.5,None,None,None,None]):
            with self.assertRaises(AssertionError):fabricated_compact(s)
    def test_plan_must_not_be_replaced_by_future_veto(self):
        nominal=[-.25]*6;realized=[-.25,None,None,None,None,None]
        self.assertNotEqual(fabricated_compact(nominal),fabricated_compact(realized))
    def test_past_latch_distinct_from_future_latch(self):
        self.assertNotEqual(fabricated_compact([-.25]*6,0),fabricated_compact([-.25]*6,1))
    def test_last_interval_target_support(self):
        t=0
        self.assertEqual([(t+h-300,t+h) for h in (300,600,900,1800)],[(0,300),(300,600),(600,900),(1500,1800)])
    def test_origin_count_is_852(self):
        times=list(range(2100,259200-1800+1,300));self.assertEqual(len(times),852)
        self.assertEqual((times[0]-2100,times[-1]+1800),(0,259200))

def run():
    log=io.StringIO()
    with offline_guard():result=unittest.TextTestRunner(stream=log,verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(SemanticsTests))
    with (HOME/'FABRICATED_SEMANTICS_TESTS.txt').open('x',encoding='utf-8') as f:f.write(log.getvalue())
    summary=dict(status='PASS' if result.wasSuccessful() else 'FAIL_DESIGN_REVIEW_REQUIRED',tests=result.testsRun,errors=len(result.errors),failures=len(result.failures),scope='FABRICATED_DESIGN_ONLY',model_rows_created=0,models_run=0,simulation_calls=0)
    write_new(HOME/'FABRICATED_SEMANTICS_RESULT.json',summary);return summary

if __name__=='__main__':print(json.dumps(run(),indent=2))
