"""Offline-only documentation and delivery sealing, with no physical result outputs."""
import csv,difflib,json
from . import HOME,ROOT,V1,PILOT,B2F,RID,VERSION,STATE
from .integrity import verify_frozen,verify_v1,preservation
from hvac_control_expansion_b2f_v1.packaging import read,sha,write_new,require
from hvac_control_expansion_b2f_v1.tests import offline_guard

def md(name,text):
    with (HOME/name).open('x',encoding='utf-8') as f:f.write(text)

def lineage():
    require(not (HOME/'V1_TO_V2_SOURCE_DIFF.patch').exists(),'Lineage artifact already recorded')
    names=['__init__.py','__main__.py','integrity.py','launcher.py','tests.py'];diff=[];mapping=[]
    for name in names:
        old=V1/name;new=HOME/name
        diff.extend(difflib.unified_diff(old.read_text().splitlines(True),new.read_text().splitlines(True),
                                       fromfile='hvac_control_expansion_b2g_v1/'+name,tofile='hvac_control_expansion_b2g_v2/'+name))
        mapping.append(dict(old_source=str(old),old_sha256=sha(old),new_source=str(new),new_sha256=sha(new)))
    (HOME/'V1_TO_V2_SOURCE_DIFF.patch').write_text(''.join(diff),encoding='utf-8')
    write_new(HOME/'V1_TO_V2_SOURCE_RELATIONSHIP.json',dict(version=VERSION,source_pairs=mapping,
        additional_v2_source='reports.py',reused_unchanged_modules=[str(V1/'launcher.py'),str(V1/'validation.py'),
        str(PILOT/'registry.py'),str(PILOT/'collector.py'),str(B2F/'packaging.py')],
        no_historical_source_changes=True,experimental_changes=False))
    sources=list(HOME.glob('*.py'))+list(V1.glob('*.py'))+[PILOT/'campaign_manifest.json',PILOT/'runtime_state/attempts.sqlite3',
        B2F/'packaging.py',B2F/'B2F_IMPLEMENTATION_MANIFEST.json',V1/'B2G_PARTIAL_DELIVERY_MANIFEST.json',
        ROOT/'stage4e_d0/RUNTIME_REFERENCE_IDENTITIES.json',ROOT/'stage4e_runtime_preflight/evidence/WORKER_EXECUTABLE_AND_DEPENDENCIES.json']
    with (HOME/'SOURCE_HASHES.csv').open('x',newline='',encoding='utf-8') as f:
        w=csv.DictWriter(f,fieldnames=['absolute_path','sha256','bytes']);w.writeheader()
        for p in sources:w.writerow(dict(absolute_path=str(p.resolve()),sha256=sha(p),bytes=p.stat().st_size))

def publish():
    qa=read(HOME/'OFFLINE_QUALIFICATION.json');target=read(HOME/'TARGETED_LEDGER_RESULT.json')
    require(qa['status']==target['status']=='PASS','Qualification blocked; no readiness success report')
    identity=verify_frozen();h=read(HOME/'HISTORICAL_PRESERVATION.json');runtime=read(HOME/'RUNTIME_IDENTITY_REQUIREMENTS.json')
    trigger=read(HOME/'TRIGGER_VERIFICATION.json');integration=read(HOME/'FINALIZER_INTEGRATION_RESULT.json')
    readiness=read(HOME/'EXECUTION_READINESS.json')
    require(readiness['permission']=='NOT AUTHORIZED FOR EXECUTION','Readiness must not activate execution')
    md('B2G_V2_QUALIFICATION_REPORT.md',f'''# B2-G v2 offline qualification

**PASS.** The corrected ledger test passed first (1 test, no errors/failures), followed by the complete mandatory suite: **{qa['tests']} tests, {qa['tests']-qa['errors']-qa['failures']} passed, {qa['errors']} errors, {qa['failures']} failures**. This is {qa['tests']+target['tests']} successful test executions across two stages, with the targeted case repeated in the full suite. No Docker contact, BOPTEST request, external simulator process, real instance, initialization, advance, model execution or training-data release occurred.

## Correction and evidence

V1's actual recorded error was `sqlite3.OperationalError: no such column: status`: the test issued `UPDATE slots SET status='UNUSED_NOT_AUTHORIZED'`, but the table columns are `run_id` and `definition`. That malformed query did not establish trigger protection. V1 remains unchanged at its original 37-pass/one-error result.

V2 issues the valid `UPDATE slots SET definition=definition` and still requires **sqlite3.IntegrityError**. It additionally checks the real schema, exact trigger message and SQLite trigger-error origin; attempts a real changed JSON definition; and compares every slot row and every trigger definition before and after. The trigger is neither disabled nor replaced. Production ledger behavior, schema and DDL are reused unchanged.

Both no-op and actual-change attempts returned `IntegrityError`, `APPEND_ONLY_NO_RESET`, and `SQLITE_CONSTRAINT_TRIGGER`. Record hashes before/after both equal `{trigger['records_before_sha256']}`. Trigger hashes before/after both equal `{trigger['triggers_before_sha256']}`. `TRIGGER_VERIFICATION.json` records SQL statements, exact DDL, schema and error identities. These are labeled fabricated temporary-ledger checks, not writes to a production ledger.

## Full qualification coverage

The original 38 mandatory B2-G checks were rerun with the corrected/strengthened test and v2 binding expectations. Four additional checks verify absent-approval rejection before runtime/ledger access, readiness-artifact rejection as authorization, preserved v1 failure evidence, and offline pinned runtime requirements. The inherited collection/finalization implementations were not modified.

The suite covers exact daily 11:00 activation/11:45 release, nine active intervals per day/27 total, 296.90 K units, canonical native behavior and all four flags, G174 custom initialization/seven-day warmup/parent development fold 4, latched safety and fallback, readbacks/timestamps/native energy/recovery, future-information leakage, source/configuration integrity, wrong-FMU rejection before initialization, pilot/G146 rejection, duplicate-slot and extra-advance prevention, immutable ledger behavior, and corrected nested-manifest finalization. Applicable unchanged B2-F and B1 regressions were included. Exact individual outcomes are in `OFFLINE_TEST_RESULTS.txt`.

## Corrected-finalizer integration

The full-length FABRICATED C45 fixture used the unchanged `hvac_control_expansion_b2g_v1.launcher.execute_one` core that v2 reuses, and the actual unchanged `hvac_control_expansion_b2f_v1.packaging.finalize` function. It completed {integration['advances']} fabricated advances, {integration['endpoints']} endpoints, {integration['native_samples']} native samples and {integration['applied_intervals']}/27 requested active intervals. All three 24-interval recovery observations passed; the nested ARTIFACT_MANIFEST.json was included in the final outer scope. Corrected finalization result: **{integration['status']}**. A changed output path did not allow a second attempt. Missing/tampered/duplicated/path-invalid/interrupted packaging regressions rejected their fixtures.

`FINALIZER_INTEGRATION_RESULT.json` records that software-only outcome. All fabricated raw fixtures were temporary and explicitly labeled. No C45 physical response, temperature, comfort or energy result CSV was generated.

## Preservation and identity

Read-only historical checks passed: v1's {h['failed_v1']['files']} files including its closing manifest, the original {h['earlier_evidence']['original_delivery']['files']}-file pilot delivery, {h['earlier_evidence']['B2F_frozen_files']} frozen B2-F artifacts, inherited D2 manifests/source hashes and the original parent ledger. C45 has no reservation/attempt in the ledger chain. G146 slots remain unused. The native/C15 matched recordings and original failed-finalization history remain intact. `HISTORICAL_PRESERVATION.json` records the checks; `HISTORICAL_PRESERVATION_AFTER_FREEZE.json` records the final closing check.

Saved runtime/worker identities match the pinned requirements for BOPTEST {runtime['BOPTEST_version']} / {runtime['testcase']}, FMU SHA-256 `{runtime['FMU_sha256']}`. **Current live runtime identity was not queried**: Docker contact is prohibited in this task. It remains a mandatory gate before a future separately authorized BOPTEST request, and the deployed FMU must still be checked before initialization. Recorded-identity verification must not be represented as current runtime verification.

## Frozen result

Version: `{VERSION}`. Implementation manifest SHA-256: `{identity}`. This freezes source/configuration/qualification and readiness only; it does not authorize execution. No AUTHORIZATION.json or live runtime_state directory was created.
''')
    md('B2G_V2_EXECUTION_READINESS.md',f'''# B2-G v2 execution readiness

**PASS — QUALIFIED AND FROZEN. NOT AUTHORIZED FOR EXECUTION.**

Frozen launcher: `{VERSION}`. Implementation manifest SHA-256: `{identity}`. Exact run-manifest SHA-256: `{readiness['run_manifest_sha256']}`. Machine-readable readiness: `EXECUTION_READINESS.json`.

Working directory for commands: `{ROOT}`. Use the existing `.venv/Scripts/python.exe` with `-B` to avoid writing bytecode into preserved source directories.

| Intended setting | Frozen requirement |
|---|---|
| Sole run | B1V01_G174_C45 |
| Parent group / role / held fold | D2_G174 / development / 4 |
| Cooling target | 296.90 K / 23.75°C |
| Daily interval | 11:00–11:45, three scored days |
| Requested active intervals | 9/day, 27 total, subject to unchanged vetoes |
| Scored window | 15033600–15292800 s, 72 hours |
| Step / advances / endpoints | 300 s / 864 / 865 |
| Native history | Existing 30-second convention |
| Initialization / warmup | Original G174 custom, 604800 native seconds |
| Heating/fan/supply overrides | Disabled |
| Native releases / safety / comfort | Original frozen B1 requirements unchanged |
| Matched baselines | Existing G174 NREF and C15; never rerun |
| Finalizer | Unchanged qualified B2-F corrected finalizer |

There is no remaining offline qualification blocker. The live machine's current state is intentionally unknown here. Before any execution, a separate explicit live approval must bind this implementation SHA-256, RUN_MANIFEST.json SHA-256, original campaign SHA-256, offline request provenance, exact `[B1V01_G174_C45]` selection and one-instance/864-advance budget. Readiness cannot serve as that approval: the future gate requires status `EXPLICITLY_AUTHORIZED_FOR_LIVE_C45`, checks exact bindings and a new user authorization record, and rejects absent approval before runtime or ledger access.

After such approval, the preserved current-runtime verifier must pass before BOPTEST requests; the global parent/extension ledger chain must still show C45 unused, and the actual single deployed FMU identity must pass before initialization. No disposable preflight, retry, pilot rerun, G146 slot or model execution is included.

Future execution command, **only after separate authorization**:

```
.venv/Scripts/python.exe -B -m hvac_control_expansion_b2g_v2 execute --approval <NEW_EXPLICIT_LIVE_C45_APPROVAL.json>
```

That approval file was not created by this task. `LEDGER_BASELINE.json` is a read-only plan linked to the original sealed parent ledger, importing its consumed NREF/C15 slots. The actual v2 continuation SQLite ledger is initialized only in a future approved execution after the current-runtime gate; it does not exist now. Once reserved, C45 is consumed even if a later attempt fails. All future continuation launchers must consult the parent-plus-extension chain; no output-path change grants a fresh slot.

Read-only verification command:

```
.venv/Scripts/python.exe -B -m hvac_control_expansion_b2g_v2 verify
```

Preparation commands were `targeted`, then `qualify`, then `freeze --request <the supplied offline v2 request>`. They create exclusive evidence and must not overwrite this frozen delivery. No current AUTHORIZATION.json, real runtime_state, C45 raw observations or physical-response CSVs exist. Stop here; no simulation, ML execution or dataset release is permitted by this readiness package.
''')
    md('V1_TO_V2_CHANGE_SUMMARY.md','''# Exact relationship between B2-G v1 and v2

The preserved v1 failure was caused by one malformed test SQL statement. V2 corrects that statement and strengthens its evidence without changing production ledger schema or trigger definitions.

The machine-readable source pair hashes are in V1_TO_V2_SOURCE_RELATIONSHIP.json; V1_TO_V2_SOURCE_DIFF.patch provides the complete unified diff for every corresponding versioned file. SOURCE_HASHES.csv records new and reused source/configuration identities. No large evidence directory was copied.

| File / component | Exact scope of change or reuse |
|---|---|
| tests.py | Replace nonexistent-column UPDATE with `UPDATE slots SET definition=definition`; retain IntegrityError assertion; add real-column, trigger-specific rejection, actual-change, unchanged-row and unchanged-DDL assertions. Retarget version/patch bindings to v2, add targeted-first runner and software integration evidence, and four approval/readiness/preservation/identity tests. All 38 mandatory cases remain in the full suite. |
| __init__.py | New v2 namespace, version, output paths and link to v1; sole C45 run identity unchanged. |
| launcher.py | Thin new approval wrapper reusing v1 C45Registry, execute_one, real_factory and validate_real unchanged. No current permission is generated; missing approval and readiness artifacts are rejected before runtime/ledger access. Actual ledger initialization is deferred to separately approved execution. |
| integrity.py | Reuse v1 immutable run/campaign, ledger-chain and historical-check helpers. Replace v1 live-authorizing freeze with an offline-only readiness freeze, recorded runtime requirements, v1 preservation checks, and NOT AUTHORIZED output. No Docker/runtime query or ledger creation occurs in preparation. |
| __main__.py | Expose targeted-first/offline qualification, offline freeze and read-only verification; future execute requires an explicit separate approval argument. |
| reports.py | New offline qualification, readiness and preservation documentation/delivery records only. |
| Production ledger / collector / Safety / transport / event / energy / B2-F finalizer | Reused directly, unchanged and hash-bound. No control policy, parameter, schema, trigger or experiment change. |
| V1 analysis.py, validation.py and reporting.py | Preserved in v1. The existing validated-run replay is reused by the continuation core; no physical analysis or historical reports are regenerated. |

The lifecycle-wrapper changes are necessary to honor this request's offline-only scope: the v1 freeze would have queried Docker, generated live authorization and initialized a ledger. Those actions are expressly excluded in v2 preparation. This is a restriction of present authority, not a bypass or weakening of collection/ledger safeguards. The old failed source and logs remain intact.
''')
    md('HISTORICAL_PRESERVATION_REPORT.md',f'''# B2-G v2 historical preservation

PASS, read-only verification. V1's {h['failed_v1']['files']} files, including its original failure, invalid SQL, test log, blocker and closing manifest, remain unchanged. Original v1 status remains 37 passes/one error. The original pilot's {h['earlier_evidence']['original_delivery']['files']} delivery files retain their hashes; B2-F's {h['earlier_evidence']['B2F_frozen_files']} frozen files and corrected packaging remain intact. Inherited D2 evidence/source checks passed. Original failed-finalization history was not rewritten.

The parent SQLite ledger was opened mode=ro, with only completed NREF/C15 reservations. C45 remains unused; G146 has no reservations and remains unauthorized. Cross-namespace C45 claim/orphan checks found no previous attempt. V2 creates only a LEDGER_BASELINE.json planning snapshot, never a real continuation ledger in this task. No existing record, seal, manifest, dataset, model, fold or reservation was rewritten.

The before-freeze evidence is HISTORICAL_PRESERVATION.json; the closing recheck is HISTORICAL_PRESERVATION_AFTER_FREEZE.json. Docker/runtime/simulator requests, real deployments/initializations/advances, ML execution and training-data release all remain zero. The saved runtime pins are checked from historical records only.
''')

def close_delivery():
    identity=verify_frozen();after=preservation()
    write_new(HOME/'HISTORICAL_PRESERVATION_AFTER_FREEZE.json',after)
    require(not (HOME/'AUTHORIZATION.json').exists() and not STATE.exists(),'Offline-only boundary violated')
    files={p.relative_to(HOME).as_posix():sha(p) for p in HOME.rglob('*') if p.is_file() and '__pycache__' not in p.parts}
    write_new(HOME/'DELIVERY_MANIFEST.json',dict(version=VERSION,files=files,implementation_sha256=identity,
        status='PASS_QUALIFIED_FROZEN_NOT_AUTHORIZED',execution_permission=False,real_operations=0,models_run=0))
    print(json.dumps(dict(status='PASS_QUALIFIED_FROZEN_NOT_AUTHORIZED',frozen_implementation_sha256=identity,delivery_files=len(files),
        C45_unused=True,Docker_contacted=False,real_operations=0),indent=2))

if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('action',choices=['lineage','publish']);a=p.parse_args()
    with offline_guard():
        if a.action=='lineage':lineage()
        else:publish();close_delivery()
