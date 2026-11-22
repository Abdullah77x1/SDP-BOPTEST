"""One explicitly authorized experimental slot, with no live default and no retries."""
import argparse
import json
import sqlite3
from pathlib import Path

from hvac_control_expansion_b2f_v1.packaging import digest, finalize, inventory, read, require, sha, write_new
from hvac_control_expansion_v1.registry import Registry
from .collector import collect_run
from .comparison import summarize
from .policy import HOME, ROOT, RID, VERSION, definitions
from .validation import verify_run

STATE = HOME/"runtime_state"
SOURCE_FREEZES = (
    "hvac_control_expansion_v1/IMPLEMENTATION_MANIFEST.json",
    "hvac_control_expansion_b2i_v1/IMPLEMENTATION_MANIFEST.json",
)
FMU = ROOT/"deployment/official_v0.9.0/project1-boptest-0.9.0/testcases/bestest_air/models/wrapped.fmu"

def baseline(run):
    return dict(version=VERSION, slots=[dict(run_id=RID,group_id=run["group_id"],partition="development",
                                            category="development",status="UNUSED_NOT_AUTHORIZED",run_sha256=digest(run))])

def no_claim():
    require(not STATE.exists() and not (HOME/"EXECUTION_RESULT.json").exists(), "Campaign already created; no retry")
    for d in ROOT.glob("hvac_control_expansion*"):
        path=d/"runtime_state/attempts.sqlite3"
        if path.is_file():
            db=sqlite3.connect(path.resolve().as_uri()+"?mode=ro",uri=True)
            try:
                require(db.execute("SELECT 1 FROM reservations WHERE run_id=?", (RID,)).fetchone() is None,
                        "Existing historical reservation")
            finally:
                db.close()

def freeze():
    m,run,nref=definitions()
    require(read(HOME/"OFFLINE_QUALIFICATION.json")["status"]=="PASS","Offline qualification missing")
    require(read(HOME/"NATIVE_REFERENCE_VERIFICATION.json")["status"]=="PASS_ARCHIVED_NATIVE_EQUIVALENCE",
            "Qualified archived reference required")
    require(read(HOME/"HISTORICAL_B1_VERIFICATION.json")["status"]=="PASS_READ_ONLY",
            "Read-only B1 historical checks required")
    no_claim()
    require(sha(FMU)==m["model"]["FMU_sha256"],"Source FMU hash drift")
    write_new(HOME/"CAMPAIGN.json",m)
    files={str(p.resolve()):sha(p) for p in sorted(HOME.glob("*.py"))}
    for rel in SOURCE_FREEZES:
        path=ROOT/rel
        files[str(path.resolve())]=sha(path)
        for raw,expected in read(path)["files"].items():
            p=Path(raw)
            if not p.is_absolute():
                p=ROOT/p
            require(sha(p)==expected,f"Historical source drift: {p}")
            files[str(p.resolve())]=expected
    for rel in (
        "stage4e_d0/RUNTIME_REFERENCE_IDENTITIES.json",
        "stage4e_runtime_preflight/evidence/WORKER_EXECUTABLE_AND_DEPENDENCIES.json",
        "stage4e_d1_v2/runtime.py",
        "stage4e_d2_public/export.py",
    ):
        p=ROOT/rel
        files[str(p.resolve())]=sha(p)
    for name in ("CAMPAIGN.json","OFFLINE_QUALIFICATION.json","NATIVE_REFERENCE_VERIFICATION.json",
                 "HISTORICAL_B1_VERIFICATION.json","RUNTIME_RESTORATION.json","ANALYSIS_REPLAY_VERIFICATION.json"):
        p=HOME/name
        files[str(p.resolve())]=sha(p)
    files[str(FMU.resolve())]=sha(FMU)
    out=HOME/"EXPERIMENT_FREEZE.json"
    write_new(out,dict(version=VERSION,run_id=RID,files=files))
    return dict(status="FROZEN_OFFLINE",run_id=RID,implementation_sha256=sha(out),
                campaign_sha256=sha(HOME/"CAMPAIGN.json"),sources=len(files))

def verify_frozen():
    f=HOME/"EXPERIMENT_FREEZE.json"
    payload=read(f)
    require(payload["version"]==VERSION and payload["run_id"]==RID,"Campaign freeze identity mismatch")
    m=read(HOME/"CAMPAIGN.json")
    require(m==definitions()[0],"Campaign binding changed")
    for path,h in payload["files"].items():
        require(sha(Path(path))==h,"Frozen artifact changed: "+path)
    return dict(implementation_sha256=sha(f), campaign_sha256=sha(HOME/"CAMPAIGN.json"))

def authorization(path):
    binding=verify_frozen()
    a=read(path)
    expected=dict(**binding,version=VERSION,status="EXPLICIT_SINGLE_G174_WARM45_AUTHORIZATION",
                  run_id=RID,maximum_instances=1,maximum_initializations=1,maximum_advances=864,
                  automatic_retries=False)
    require(set(a)==set(expected)|{"user_approval_text"} and all(a.get(k)==v for k,v in expected.items()),
            "Exact campaign authorization is required")
    text=a["user_approval_text"]
    require(type(text) is str and text.strip() and text.lower()!="pending", "Missing affirmative approval")
    return dict(**expected,authorization_sha256=sha(path))

def execute_attempt(manifest,run,registry,binding,factory,mode,verifier,final_path):
    require(run==manifest["runs"][0],"Exact experiment slot only")
    batch=registry.new_batch(RID,[run],binding)
    path=registry.reserve(RID,run)
    result=validation=summary=package=error=None
    try:
        result=collect_run(manifest,run,path,factory,mode)
        require(result["classification"]=="PASS_VALID_RAW" and result["cleanup"]=="STOP_ACK_AND_REMOVAL_VERIFIED",
                "Collection failed: "+str(result.get("error")))
        require(tuple(result[k] for k in ("deploy_attempts","initialization_attempts","advance_requests_attempted",
                                          "advance_responses_received","endpoints","native_samples","unresolved_events"))
                ==(1,1,864,864,865,8641,0),"Live mutation or support budget drift")
        validation,summary=verifier(path)
        write_new(batch/"VALIDATION.json",validation)
        if summary is not None:
            write_new(batch/"PAIRED_ENERGY_COMFORT.json",summary)
    except (Exception,KeyboardInterrupt) as exc:
        error=f"{type(exc).__name__}: {exc}"
    seal=batch/(RID+"_SEALED_MANIFEST.json")
    write_new(seal,dict(run_id=RID,files=inventory(path),training_release=False))
    write_new(batch/"ATTEMPT_VALIDATION_STATUS.json",dict(run_id=RID,result=result,validation=validation,
                                                        error=error,automatic_retry=False))
    top=["BATCH_STARTED.json",RID+"_RESERVATION.json",seal.name,"ATTEMPT_VALIDATION_STATUS.json"]
    top.extend(p for p in ("VALIDATION.json","PAIRED_ENERGY_COMFORT.json") if (batch/p).exists())
    plan=dict(version=VERSION,batch_files={p:sha(batch/p) for p in top},
              runs=[dict(run_id=RID,seal_path=seal.name,required_files=[
                  "ARTIFACT_MANIFEST.json","ATTEMPT_STARTED.json","receipt_order.jsonl","RUN_COMPLETED.json"])])
    try:
        package=finalize(batch,plan,final_path)
    except (Exception,KeyboardInterrupt) as exc:
        error=(error+"; " if error else "")+f"FINALIZATION: {type(exc).__name__}: {exc}"
    state="CONSUMED_FAILED" if error else "CONSUMED_COMPLETED"
    registry.finish(RID,state,dict(seal_sha256=sha(seal),validation_passed=validation is not None and error is None,
                                  batch=str(batch),package=str(final_path),finalization=package,error=error))
    registry.verify_evidence()
    return dict(run_id=RID,state=state,raw_result=result,validation=validation,summary=summary,error=error,
                source_batch=str(batch),run_path=str(path),package_path=str(final_path),automatic_retry=False)

def execute(approval):
    binding=authorization(approval)
    no_claim()
    from stage4e_d1_v2.runtime import verify_runtime
    from hvac_control_expansion_b2g_v1.launcher import real_factory
    m,run,_=definitions()
    require(sha(FMU)==m["model"]["FMU_sha256"],"Source FMU no longer matches")
    runtime=verify_runtime()
    require(runtime["classification"]=="PASS","Pinned current runtime gate blocked")
    def verify_and_compare(path):
        raw=verify_run(path,run,m["policy"])
        return raw,summarize(path,run,raw)
    reg=Registry.create(STATE,baseline(run))
    result=execute_attempt(m,run,reg,dict(authorization=binding,runtime=runtime,source_fmu_sha256=sha(FMU)),
                           real_factory,"AUTHORIZED_SINGLE_G174_WARM45",verify_and_compare,HOME/"finalized")
    write_new(HOME/"EXECUTION_RESULT.json",result)
    return result

if __name__=="__main__":
    parser=argparse.ArgumentParser()
    action=parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--freeze",action="store_true")
    action.add_argument("--verify",action="store_true")
    action.add_argument("--execute",type=Path,metavar="AUTHORIZATION_JSON")
    args=parser.parse_args()
    result=freeze() if args.freeze else verify_frozen() if args.verify else execute(args.execute)
    print(json.dumps(result,indent=2))

