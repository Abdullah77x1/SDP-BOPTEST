"""Stage 4D dashboard; no simulator is deployed until an explicit Connect command."""
import argparse
import functools
import hashlib
import json
from pathlib import Path
from compat_v1.transport import Client
from dashboard import make_server
from experiment import ROOT
from stage4d.loop import AutonomousController


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--output", type=Path, default=ROOT/"stage4d"/"evidence"/"authorized_demo")
    args = parser.parse_args()
    frozen = json.loads((ROOT/"stage4d"/"FROZEN_MANIFEST.json").read_text())
    for path, digest in frozen["files"].items():
        if hashlib.sha256((ROOT/path).read_bytes()).hexdigest() != digest:
            raise RuntimeError("Frozen Stage 4D dependency changed: "+path)
    protocol = json.loads((ROOT/"stage4d"/"protocol.json").read_text())
    controller = AutonomousController("http://127.0.0.1:80", args.output,
        functools.partial(Client, timeout=120), protocol)
    server = make_server(controller, args.port, html_path=ROOT/"stage4d"/"index.html")
    print(f"Stage 4D dashboard: http://127.0.0.1:{server.server_port}", flush=True)
    print("One fresh instance, maximum 180 advances; no Stage 4C A/B execution.", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        controller.close()


if __name__ == "__main__":
    main()
