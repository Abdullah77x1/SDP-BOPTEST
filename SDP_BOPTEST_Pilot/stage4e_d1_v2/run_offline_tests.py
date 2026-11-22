"""Durable offline tests; simulator/network/process dispatch forbidden."""
import io,json,socket,subprocess,unittest
from unittest.mock import patch
from .runner import HERE,save_new

def main():
    suite=unittest.TestSuite()
    loader=unittest.TestLoader()
    suite.addTests(loader.discover('tests',pattern='test_stage4e*.py'))
    for name in ('stage4e_d1r.test_proposed_validation','stage4e_d1r_bm01.test_diagnostic','stage4e_d1_v2.test_contract'):
        suite.addTests(loader.loadTestsFromName(name))
    stream=io.StringIO()
    with patch.object(socket.socket,'connect',side_effect=AssertionError('Network forbidden in offline tests')),patch.object(subprocess,'Popen',side_effect=AssertionError('External processes/Docker forbidden in offline tests')):
        result=unittest.TextTestRunner(stream=stream,verbosity=2).run(suite)
    text=stream.getvalue()
    with (HERE/'OFFLINE_TEST_RESULTS.txt').open('x',encoding='utf-8') as f:f.write(text)
    save_new(HERE/'OFFLINE_TEST_SUMMARY.json',{'tests_run':result.testsRun,'failures':len(result.failures),
        'errors':len(result.errors),'passed':result.wasSuccessful(),'network_dispatch_forbidden':True,
        'external_process_and_Docker_dispatch_forbidden':True,'BOPTEST_execution':False})
    print(text[-3500:]);print(json.dumps({'tests':result.testsRun,'success':result.wasSuccessful()}))
    if not result.wasSuccessful():raise SystemExit(1)

if __name__=='__main__':main()
