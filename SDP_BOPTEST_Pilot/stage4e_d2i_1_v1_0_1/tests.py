"""Run corrected-version compatibility and actual-discovery regressions offline."""
import argparse,contextlib,io,json,time,unittest
from unittest.mock import patch
from . import HOME,VERSION
from . import tests_compatibility,tests_receipt
from stage4e_d2i_1.common import require

def run_tests(stream=None,receipt_only=False):
    modules=[tests_receipt] if receipt_only else [tests_compatibility,tests_receipt]
    denial=AssertionError('NETWORK_OR_EXTERNAL_PROCESS_FORBIDDEN_IN_OFFLINE_SUITE')
    with contextlib.ExitStack() as stack:
        for target in ('socket.socket.connect','socket.socket.connect_ex','socket.create_connection',
            'socket.socket.sendto','socket.socket.sendmsg' if hasattr(__import__('socket').socket,'sendmsg') else 'socket.getaddrinfo',
            'subprocess.Popen','os.system','os.startfile'):
            stack.enter_context(patch(target,side_effect=denial))
        suite=unittest.TestSuite(unittest.defaultTestLoader.loadTestsFromModule(m) for m in modules)
        return unittest.TextTestRunner(stream=stream,verbosity=2).run(suite)

def main():
    p=argparse.ArgumentParser(description='Fabricated offline tests only; no Docker/API/process execution')
    p.add_argument('--record-results',action='store_true');p.add_argument('--receipt-only',action='store_true')
    a=p.parse_args()
    if a.record_results:require(not (HOME/'IMPLEMENTATION_MANIFEST.json').exists(),'Cannot overwrite frozen QA')
    started=time.monotonic();log=io.StringIO();result=run_tests(log,a.receipt_only)
    summary={'version':VERSION,'classification':'PASS_OFFLINE_QA' if result.wasSuccessful() else 'FAILED_OFFLINE_QA',
        'tests_run':result.testsRun,'failures':len(result.failures),'errors':len(result.errors),'duration_s':time.monotonic()-started,
        'original_compatibility_tests':0 if a.receipt_only else unittest.defaultTestLoader.loadTestsFromModule(tests_compatibility).countTestCases(),
        'actual_discovery_and_receipt_tests':unittest.defaultTestLoader.loadTestsFromModule(tests_receipt).countTestCases(),
        'network_and_external_process_dispatch_blocked':True,'fixtures':'FABRICATED_SOFTWARE_TESTS_NO_BUILDING_SOLVER',
        'real_instances':0,'real_advances':0,'real_preflight_slots_consumed':0,'dataset_created':False}
    print(log.getvalue());print(json.dumps(summary,indent=2))
    if a.record_results:
        evidence=HOME/'offline_verification';evidence.mkdir(exist_ok=True)
        (evidence/'OFFLINE_TEST_RESULTS.txt').write_text(log.getvalue(),encoding='utf-8')
        (evidence/'QA_RESULTS.json').write_text(json.dumps(summary,indent=2)+'\n',encoding='utf-8')
    return 0 if result.wasSuccessful() else 1

if __name__=='__main__':raise SystemExit(main())
