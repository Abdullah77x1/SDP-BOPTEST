"""Offline tests for the new guard, command delivery, raw replay, and exclusive budget."""
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from copy import deepcopy

from hvac_control_expansion_b2f_v1.packaging import verify_package,write_new
from hvac_control_expansion_b2f_v1.tests import offline_guard
from hvac_control_expansion_b2i_v1.tests import Fabricated
from hvac_control_expansion_v1.registry import Registry
from stage4e_d0.plan import FLAG, FLAGS, OCC, SET, TEMP, UP, native_command
from stage4e_d1_v2.validation import command_guard as old_guard
from .campaign import baseline, execute_attempt
from .policy import HOME, ON, RID, TARGET, Safety, action_path, command_guard, definitions, nominal
from .validation import verify_run

class PolicyTests(unittest.TestCase):
    def setUp(self):
        self.m,self.run,self.native=definitions()
        self.t=self.run["start"]+ON
        self.p=nominal(self.run,self.t)
        self.obs={"time":self.t,TEMP:297.15,SET:297.15,"con_oveTSetHea_u":294.15,**native_command()}
        self.bc={"time":self.t,"LowerSetp[1]":294.15,UP:297.15,OCC:2.}

    def decide(self,t,obs=None,bc=None,safety=None,age=0.):
        return (safety or Safety(self.m["policy"])).decide(
            nominal(self.run,t),{**self.obs,**(obs or {}),"time":t},
            {**self.bc,**(bc or {}),"time":t},age)

    def test_only_twenty_seven_grid_slots(self):
        active=[t for t in range(self.run["start"],self.run["end"],300) if nominal(self.run,t)["command"][FLAG]]
        self.assertEqual(len(active),27)
        self.assertEqual(active,[self.t+d*86400+j*300 for d in range(3) for j in range(9)])
        self.assertTrue(all(nominal(self.run,t)["command"]==self.p["command"] for t in active))
        self.assertEqual(nominal(self.run,self.t+2700)["command"],native_command())
        self.assertEqual(action_path(self.run,self.t+2400)[1]["command"],native_command())

    def test_official_and_experimental_guards_are_separate(self):
        with self.assertRaises(ValueError):
            old_guard(self.p["command"],self.obs,self.bc,self.t,0.)
        cmd,reason=self.decide(self.t)
        self.assertTrue(command_guard(cmd,self.obs,self.bc,self.t,0.))
        self.assertEqual(cmd[SET],TARGET)
        self.assertEqual(reason,"scheduled_warmer_pulse_applied")
        self.assertEqual(self.bc[UP],297.15)

    def test_reject_wrong_magnitude_or_noncooling_override(self):
        for cmd in ({**self.p["command"],SET:298.15},{**self.p["command"],FLAGS[1]:1}):
            with self.assertRaises(ValueError):
                command_guard(cmd,self.obs,self.bc,self.t,0.)

    def test_reject_stale_or_published_schedule_drift(self):
        with self.assertRaises(ValueError):
            self.decide(self.t,age=30.001)
        with self.assertRaises(ValueError):
            self.decide(self.t,bc={UP:299.15})

    def test_veto_and_latch_hot_then_native_release(self):
        safety=Safety(self.m["policy"])
        self.assertEqual(self.decide(self.t,safety=safety)[0][FLAG],1)
        self.assertEqual(self.decide(self.t+300,obs={TEMP:298.65},safety=safety),
                         (native_command(),"project_upper_margin_native_fallback"))
        self.assertEqual(self.decide(self.t+600,safety=safety),(native_command(),"latched_veto_rest_of_pulse"))
        self.assertEqual(self.decide(self.t+2700,safety=safety)[0],native_command())
        self.assertTrue(self.decide(self.t+86400,safety=safety)[0][FLAG])

    def test_veto_cold_unoccupied_and_heating_readback(self):
        self.assertEqual(self.decide(self.t,obs={TEMP:294.89})[1],"cold_margin_veto")
        self.assertEqual(self.decide(self.t,bc={OCC:0.})[1],"unoccupied_veto")
        self.assertEqual(self.decide(self.t,obs={"con_oveTSetHea_u":297.25})[1],"native_heating_readback_veto")

    def test_fabricated_full_budget_replay_and_seal(self):
        with TemporaryDirectory() as d:
            p=Path(d)
            reg=Registry.create(p/"ledger",baseline(self.run))
            result=execute_attempt(self.m,self.run,reg,{"read_only_test":True},Fabricated,
                                   "FABRICATED_OFFLINE_TEST_ONLY",
                                   lambda path:(verify_run(path,self.run,self.m["policy"],fabricated=True),None),
                                   p/"sealed")
            self.assertEqual(result["state"],"CONSUMED_COMPLETED",result["error"])
            self.assertEqual(result["validation"]["coverage"]["applied_intervals"],27)
            self.assertTrue(all(r["native_recovery_intervals"]==24 for r in result["validation"]["coverage"]["episodes"]))
            self.assertEqual(result["validation"]["origin_metadata"]["origins"],864)
            verify_package(result["source_batch"],p/"sealed")
            with self.assertRaises(ValueError):
                reg.check_selection([self.run])

    def test_wrong_scenario_and_budget_at_ledger(self):
        with TemporaryDirectory() as d:
            reg=Registry.create(Path(d)/"ledger",baseline(self.run))
            for mutated in (dict(self.run,maximum_advances=865),dict(self.run,group_id="D2_G146"),
                            dict(self.run,run_id=self.native["run_id"])):
                with self.assertRaises(ValueError):
                    reg.check_selection([mutated])
            self.assertEqual(reg.inventory()[0]["status"],"UNUSED_NOT_AUTHORIZED")

def qualification():
    with offline_guard():
        suite=unittest.defaultTestLoader.loadTestsFromTestCase(PolicyTests)
        result=unittest.TextTestRunner(verbosity=2).run(suite)
    if not result.wasSuccessful():
        raise SystemExit(1)
    write_new(HOME/"OFFLINE_QUALIFICATION.json",dict(status="PASS",tests=result.testsRun,real_simulator_instances=0,
                                                     real_advances=0,scope="FABRICATED_SOFTWARE_AND_STATIC_ONLY"))

if __name__=="__main__":
    qualification()

