"""DEVELOPMENT_ONLY adversarial unit/support tests, fabricated values only."""
import math,unittest
from .qa import mean_kw,close
from .build import independent_interval
from stage4e.dataset import COOL,FAN,NativeElectric

class LabelTests(unittest.TestCase):
    def fixture(self):return {'time':list(range(0,301,30)),COOL:[1000.]*11,FAN:[200.]*11}
    def test_watts_seconds_to_kw(self):
        d=self.fixture();self.assertEqual(mean_kw(d,0,300),1.2)
        self.assertEqual(NativeElectric(d).interval(0,300)['average_kw'],1.2)
    def test_endpoint_is_not_average(self):
        d=self.fixture();d[COOL]=d['time'];d[FAN]=[0.]*11
        self.assertEqual(mean_kw(d,0,300),.15);self.assertNotEqual(mean_kw(d,0,300),d[COOL][-1]/1000)
    def test_duplicate_time_step_not_smoothed(self):
        ts=list(range(0,151,30))+[150]+list(range(180,301,30))
        d={'time':ts,COOL:[0.]*6+[1000.]*6,FAN:[0.]*12}
        self.assertEqual(mean_kw(d,0,300),.5)
        self.assertEqual(independent_interval(d,0,300),.5)
        self.assertEqual(NativeElectric(d).interval(0,300)['average_kw'],.5)
    def test_missing_support_rejected(self):
        d=self.fixture()
        for key in d:d[key].pop()
        with self.assertRaises(ValueError):mean_kw(d,0,300)
    def test_missing_middle_sample_rejected(self):
        d=self.fixture()
        for key in d:d[key].pop(5)
        with self.assertRaises(ValueError):mean_kw(d,0,300)
    def test_missing_nonfinite_and_boolean_rejected(self):
        for value in (None,float('nan'),float('inf'),True):
            with self.subTest(value=value),self.assertRaises(ValueError):close(value,1.)
    def test_wrong_unit_or_shift_rejected(self):
        with self.assertRaises(ValueError):close(1200.,1.2)
        with self.assertRaises(ValueError):close(22.,23.)

if __name__=='__main__':unittest.main(verbosity=2)
