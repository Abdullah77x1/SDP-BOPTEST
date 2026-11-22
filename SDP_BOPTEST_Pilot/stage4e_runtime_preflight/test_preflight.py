"""Fabricated software checks only; no network or simulator."""
import copy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from stage4e_runtime_preflight.preflight import NativeOnlyClient,warmup_gate,long_forecast_gate
from stage4e_d0.plan import configuration,POINTS,LOW,UP,OCC,COOL,FAN,HEAT,FLAGS
from stage4e.dataset import ContractError


class PreflightTests(unittest.TestCase):
    def test_no_external_command_and_no_second_advance(self):
        with tempfile.TemporaryDirectory() as d:
            c=NativeOnlyClient('http://invalid',d,object())
            with self.assertRaises(ContractError):c.request('POST','advance',{FLAGS[0]:0})
            with patch('stage4e_runtime_preflight.preflight.OrderedClient.request',return_value={'fixture':True}):
                self.assertEqual(c.request('POST','advance',{}),{'fixture':True})
            with self.assertRaises(ContractError):c.request('POST','advance',{})
            self.assertEqual(c.advance_attempts,1)
    def test_no_deployment_retry_or_extra_initialization(self):
        with tempfile.TemporaryDirectory() as d:
            c=NativeOnlyClient('http://invalid',d,object())
            with patch('stage4e_runtime_preflight.preflight.OrderedClient.deploy',return_value='FAKE'):
                c.deploy()
                with self.assertRaises(ContractError):c.deploy()
            with self.assertRaises(ContractError):c.request('PUT','initialize',{})
    def test_warmup_exact_coverage_and_native_flags(self):
        start=12614400;t=list(range(start-604800,start+1,30))
        data={'time':t,**{n:[0]*len(t) for n in [COOL,FAN,HEAT,*FLAGS]}}
        self.assertEqual(warmup_gate(data,start)['samples'],20161)
        data[FLAGS[0]][5]=1
        with self.assertRaises(ContractError):warmup_gate(data,start)
    def test_truncated_warmup_is_not_claimed_seven_days(self):
        data={'time':[0,30]}
        with self.assertRaises(ContractError):warmup_gate(data,604800)
    def test_passive_72h_forecast_pulses(self):
        c=configuration();r=c['runs'][0];ts=list(range(r['start'],r['end']+1,300))
        data={'time':ts,**{n:[0.]*len(ts) for n in POINTS}}
        data[LOW]=[294.15]*len(ts);data[UP]=[297.15]*len(ts);data[OCC]=[2]*len(ts)
        self.assertEqual(len(long_forecast_gate(data,r,c)),9)
        idx=ts.index(r['start']+32400);data[OCC][idx]=0
        with self.assertRaises(ContractError):long_forecast_gate(data,r,c)
    def test_missing_long_forecast_channel_rejected(self):
        c=configuration();r=c['runs'][0];ts=list(range(r['start'],r['end']+1,300))
        with self.assertRaises(ContractError):long_forecast_gate({'time':ts},r,c)


if __name__=='__main__':unittest.main()
