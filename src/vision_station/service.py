"""Run the independent Vision station/Core host without an active inspection."""
import argparse
import signal

from .host import CoreHost
from .server import CoreServer


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--socket", required=True)
    parser.add_argument("--library-root", required=True)
    args = parser.parse_args()
    def stop(_signal, _frame):
        raise KeyboardInterrupt()
    signal.signal(signal.SIGTERM, stop)
    try:
        server = CoreServer(args.socket, host_factory=lambda: CoreHost(args.library_root))
    except Exception:
        parser.exit(1, "Core station configuration rejected; check private paths and ownership.\n")
    try:
        print("VISION_CORE_SERVICE_STARTED state=NO_ACTIVE_SESSION readiness=UNKNOWN", flush=True)
        server.serve_forever(poll_interval=0.2)
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
