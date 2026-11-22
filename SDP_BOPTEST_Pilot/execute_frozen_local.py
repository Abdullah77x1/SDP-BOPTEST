"""Exactly one A and one B using unchanged experiment logic and transport adapter v1."""
import functools
import hashlib
import json
from client import utc
from compat_v1.transport import Client
from experiment import ROOT, run_arm, compare, write_json


def main():
    plan_digest = hashlib.sha256((ROOT/"plan.json").read_bytes()).hexdigest()
    assert plan_digest == "65bd76278f2273e83283150ed2690074a75007cc7fe931f3bb9700a202bb49ce"
    preflight = json.loads((ROOT/"evidence"/"verified_local_preflight_v2"/"compatibility.json").read_text())
    assert preflight["classification"] == "COMPATIBLE" and preflight["cleanup"] == "STOPPED_OR_NOT_DEPLOYED"
    directory = ROOT/"evidence"/"local_matched_AB"
    directory.mkdir(parents=True, exist_ok=True)
    with (directory/"CAMPAIGN_STARTED.json").open("x", encoding="utf-8") as stream:
        json.dump({"utc": utc(), "plan_sha256": plan_digest, "endpoint": "http://127.0.0.1:80",
                   "attempt_budget": {"A": 1, "B": 1}, "transport": "compat_v1",
                   "transport_sha256": hashlib.sha256((ROOT/"compat_v1"/"transport.py").read_bytes()).hexdigest(),
                   "transport_timeout_seconds": 120,
                   "protocol_changes": "None: transport routing and stop-ACK parsing only; original scripts unchanged"}, stream, indent=2)
    factory = functools.partial(Client, timeout=120, read_retries=1)
    run_arm("baseline", directory/"A", "http://127.0.0.1:80", client_factory=factory)
    print("A complete; exactly one B attempt next", flush=True)
    run_arm("intervention", directory/"B", "http://127.0.0.1:80", client_factory=factory)
    result = compare(directory)
    print(json.dumps(result, indent=2), flush=True)


if __name__ == "__main__":
    main()
