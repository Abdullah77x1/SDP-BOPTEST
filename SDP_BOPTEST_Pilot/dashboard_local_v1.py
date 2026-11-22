"""Launch the unchanged dashboard/controller with the v1 transport adapter."""
import functools
import os
from compat_v1.transport import Client
from dashboard import Controller, make_server
from experiment import ROOT, write_json


def main():
    directory = ROOT/"evidence"/"local_live_dashboard"
    directory.mkdir(parents=True, exist_ok=True)
    with (directory/"DASHBOARD_STARTED.txt").open("x", encoding="utf-8") as stream:
        stream.write(str(os.getpid()))
    controller = Controller("http://127.0.0.1:80", directory,
                            client_factory=functools.partial(Client, timeout=120))
    server = make_server(controller, 8765)
    print("Live BOPTEST dashboard: http://127.0.0.1:8765", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        controller.close()


if __name__ == "__main__":
    main()
