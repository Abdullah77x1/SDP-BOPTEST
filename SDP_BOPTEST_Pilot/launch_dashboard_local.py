"""Reusable local dashboard launcher; each session gets a fresh evidence directory."""
import datetime
import functools
from compat_v1.transport import Client
from dashboard import Controller, make_server
from experiment import ROOT


def main():
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%S_%fZ")
    directory = ROOT/"evidence"/"dashboard_sessions"/stamp
    controller = Controller("http://127.0.0.1:80", directory,
                            client_factory=functools.partial(Client, timeout=120))
    server = make_server(controller, 8765)
    print("Live simulated building dashboard: http://127.0.0.1:8765", flush=True)
    print(f"Session evidence: {directory}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        controller.close()


if __name__ == "__main__":
    main()
