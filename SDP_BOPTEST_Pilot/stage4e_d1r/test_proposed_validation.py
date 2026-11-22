"""Fabricated values only; no simulation, network or training."""
import unittest
from .proposed_validation import (validate_endpoint,precommand_guard,validate_boundary_followup_history,NativeReference,
    Violation,FLAGS,CA,COOL,HEAT,TEMP)


def command(active=False,value=296.90):
    c=dict.fromkeys(FLAGS,0)
    if active:c.update({CA:1,COOL:value})
    return c


def fixture(end,heat=None,cool=None,active=False,comfort=None):
    h,c=NativeReference().pair(end)
    obs={'time':end,HEAT:h if heat is None else heat,COOL:c if cool is None else cool,
         TEMP:296.15,**dict.fromkeys(FLAGS,0)}
    if active:obs[CA]=1;obs[COOL]=296.90 if cool is None else cool
    l,u=comfort or (h,c)
    fc={'time':end,'issued_at':end-300,'lower_k':l,'upper_k':u,'occupancy':2 if l==294.15 else 0}
    return obs,fc


def evaluate(end,**kwargs):
    active=kwargs.get('active',False);obs,fc=fixture(end,**kwargs)
    return validate_endpoint(end-300,command(active),obs,fc,
        {'observation':1,'forecast':2,'cutoff':3,'response':4},.1)


class BoundaryContractTests(unittest.TestCase):
    def test_normal_unoccupied_native(self):
        self.assertEqual(evaluate(300).status,'VERIFIED_REFERENCE')
    def test_normal_occupied_native(self):
        self.assertEqual(evaluate(9*3600).status,'VERIFIED_REFERENCE')
    def test_correct_external_command(self):
        r=evaluate(9*3600,active=True)
        self.assertTrue(r.external_control_verified);self.assertFalse(r.training_release)
    def test_exact_morning_old_pair_is_unresolved_not_pass(self):
        r=evaluate(8*3600,heat=288.15,cool=303.15,comfort=(294.15,297.15))
        self.assertEqual(r.status,'UNRESOLVED_BOUNDARY');self.assertTrue(r.stop_production)
    def test_exact_morning_new_pair_observed(self):
        self.assertEqual(evaluate(8*3600).status,'VERIFIED_EVENT_NEW_REFERENCE')
    def test_exact_evening_old_pair_unresolved(self):
        r=evaluate(18*3600,heat=294.15,cool=297.15,comfort=(294.15,297.15))
        self.assertEqual(r.status,'UNRESOLVED_BOUNDARY')
    def test_evening_new_pair_can_differ_from_comfort_csv(self):
        r=evaluate(18*3600,comfort=(294.15,297.15))
        self.assertEqual(r.status,'VERIFIED_EVENT_NEW_REFERENCE')
    def test_1805_native_reference_and_csv_semantics_separate(self):
        r=evaluate(18*3600+300,comfort=(294.15,297.15))
        self.assertEqual(r.status,'VERIFIED_REFERENCE')
        self.assertIn('comfort_signal_difference',r.reason)
    def test_persistent_0805_old_pair_fails(self):
        with self.assertRaisesRegex(Violation,'persistent'):
            evaluate(8*3600+300,heat=288.15,cool=303.15)
    def test_1805_old_pair_fails_even_if_matching_csv(self):
        with self.assertRaisesRegex(Violation,'persistent'):
            evaluate(18*3600+300,heat=294.15,cool=297.15,comfort=(294.15,297.15))
    def test_bad_pair_away_from_event_fails(self):
        with self.assertRaises(Violation):evaluate(12*3600,cool=300)
    def test_mixed_old_and_new_event_pair_fails(self):
        with self.assertRaisesRegex(Violation,'incoherent'):
            evaluate(8*3600,heat=288.15,cool=297.15)
    def test_boundary_never_excuses_wrong_external_setpoint(self):
        with self.assertRaisesRegex(Violation,'external_setpoint'):
            evaluate(8*3600,active=True,cool=303.15)
    def test_wrong_external_activation_at_boundary_fails(self):
        obs,fc=fixture(8*3600)
        with self.assertRaisesRegex(Violation,'external_activation'):
            validate_endpoint(8*3600-300,command(True),obs,fc,
                {'observation':1,'forecast':2,'cutoff':3,'response':4},.1)
    def test_wrong_external_setpoint_away_from_event_fails(self):
        with self.assertRaisesRegex(Violation,'external_setpoint'):
            evaluate(9*3600,active=True,cool=297.15)
    def test_other_override_not_allowed(self):
        c=command();c[FLAGS[1]]=1;obs,fc=fixture(3600)
        with self.assertRaises(Violation):validate_endpoint(3300,c,obs,fc,{},.1)
    def test_missing_each_required_readback_fails(self):
        for key in (HEAT,COOL,TEMP,*FLAGS):
            obs,fc=fixture(9*3600);del obs[key]
            with self.subTest(key=key),self.assertRaises(Violation):
                validate_endpoint(9*3600-300,command(),obs,fc,
                    {'observation':1,'forecast':2,'cutoff':3,'response':4},.1)
    def test_missing_or_nonfinite_forecast_fails(self):
        for key in ('lower_k','upper_k','occupancy'):
            obs,fc=fixture(3600);fc[key]=float('nan')
            with self.subTest(key=key),self.assertRaises(Violation):
                validate_endpoint(3300,command(),obs,fc,{'observation':1,'forecast':2,'cutoff':3,'response':4},.1)
    def test_wrong_endpoint_and_forecast_time_fail(self):
        for which in ('obs','forecast'):
            obs,fc=fixture(3600)
            (obs if which=='obs' else fc)['time']+=300
            with self.subTest(which=which),self.assertRaises(Violation):
                validate_endpoint(3300,command(),obs,fc,{'observation':1,'forecast':2,'cutoff':3,'response':4},.1)
    def test_off_grid_not_tolerated_as_event_grace(self):
        obs,fc=fixture(28801)
        with self.assertRaises(Violation):validate_endpoint(28501,command(),obs,fc,{'observation':1,'forecast':2,'cutoff':3,'response':4},.1)
    def test_future_forecast_receipt_or_bad_issue_time_fail(self):
        obs,fc=fixture(3600)
        with self.assertRaises(Violation):
            validate_endpoint(3300,command(),obs,fc,{'observation':1,'forecast':5,'cutoff':3,'response':4},.1)
        fc['issued_at']=3600
        with self.assertRaises(Violation):validate_endpoint(3300,command(),obs,fc,{'observation':1,'forecast':2,'cutoff':3,'response':4},.1)
    def test_stale_observation_fails(self):
        obs,fc=fixture(3600)
        with self.assertRaises(Violation):validate_endpoint(3300,command(),obs,fc,{'observation':1,'forecast':2,'cutoff':3,'response':4},31)
    def test_next_nonevent_good_pair_can_resolve_only_in_test_or_authorized_diagnostic(self):
        self.assertTrue(evaluate(28800,heat=288.15,cool=303.15,comfort=(294.15,297.15)).stop_production)
        self.assertEqual(evaluate(29100).status,'VERIFIED_REFERENCE')
    def test_valid_precommand_guards(self):
        t=9*3600;obs,_=fixture(t);fc={'time':t,'lower_k':294.15,'upper_k':297.15,'occupancy':2}
        self.assertTrue(precommand_guard(t,command(True),obs,fc,.1,'VERIFIED_REFERENCE'))
    def test_no_override_when_boundary_unresolved(self):
        t=9*3600;obs,_=fixture(t);fc={'time':t,'lower_k':294.15,'upper_k':297.15,'occupancy':2}
        with self.assertRaises(Violation):precommand_guard(t,command(True),obs,fc,.1,'UNRESOLVED_BOUNDARY')
    def test_no_new_override_at_exact_native_event(self):
        t=8*3600;obs,_=fixture(t);fc={'time':t,'lower_k':294.15,'upper_k':297.15,'occupancy':2}
        with self.assertRaises(Violation):precommand_guard(t,command(True),obs,fc,.1,'VERIFIED_EVENT_NEW_REFERENCE')
    def test_precommand_deadband_occupancy_and_actuator_checks(self):
        for bad in ('heat_gap','unoccupied','outside_bounds','missing_current'):
            t=9*3600;obs,_=fixture(t);fc={'time':t,'lower_k':294.15,'upper_k':297.15,'occupancy':2};cmd=command(True)
            if bad=='heat_gap':obs[HEAT]=296.8
            elif bad=='unoccupied':fc['occupancy']=0
            elif bad=='outside_bounds':cmd[COOL]=310
            else:del obs[HEAT]
            with self.subTest(bad=bad),self.assertRaises(Violation):precommand_guard(t,cmd,obs,fc,.1,'VERIFIED_REFERENCE')
    def test_absolute_day_offset_reference(self):
        self.assertEqual(evaluate(146*86400+9*3600).status,'VERIFIED_REFERENCE')
    def test_unexpected_current_fan_override_blocks_new_action(self):
        t=9*3600;obs,_=fixture(t);obs['fcu_oveFan_activate']=1
        fc={'time':t,'lower_k':294.15,'upper_k':297.15,'occupancy':2}
        with self.assertRaises(Violation):precommand_guard(t,command(True),obs,fc,.1,'VERIFIED_REFERENCE')


class NativeHistoryTests(unittest.TestCase):
    def fixture(self):
        t=28800;ts=list(range(t,t+301,30))
        return {'time':ts,HEAT:[288.15]+[294.15]*10,COOL:[303.15]+[297.15]*10,
            TEMP:[296.15]*11,**{f:[0]*11 for f in FLAGS}}
    def test_first_positive_sample_matches_new_pair(self):
        result=validate_boundary_followup_history(28800,self.fixture())
        self.assertEqual(result['first_positive_sample_time'],28830)
        self.assertFalse(result['production_continuation_authorized'])
    def test_persistent_native_mismatch_not_hidden_by_good_last_endpoint(self):
        h=self.fixture();h[COOL][1]=303.15;h[HEAT][1]=288.15
        with self.assertRaises(Violation):validate_boundary_followup_history(28800,h)
    def test_native_history_external_flag_mismatch_fails(self):
        h=self.fixture();h[CA][3]=1
        with self.assertRaises(Violation):validate_boundary_followup_history(28800,h)
    def test_missing_first_30s_sample_fails(self):
        h=self.fixture()
        for v in h.values():v.pop(1)
        with self.assertRaises(Violation):validate_boundary_followup_history(28800,h)
    def test_event_old_and_new_duplicates_preserved(self):
        h=self.fixture()
        for k,v in h.items():v.insert(1,v[0] if k not in (HEAT,COOL) else (294.15 if k==HEAT else 297.15))
        result=validate_boundary_followup_history(28800,h)
        self.assertEqual(result['event_samples_sides'],['old','new'])
    def test_missing_native_signal_fails(self):
        h=self.fixture();del h[HEAT]
        with self.assertRaises(Violation):validate_boundary_followup_history(28800,h)


if __name__=='__main__':unittest.main()
