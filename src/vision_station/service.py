"""Run the independent Vision station/Core host without an active inspection."""
import argparse
import signal

from .host import CoreHost
from .server import CoreServer
from .inspection import systemd_diagnostics


def main(argv=None, *, composition=None, catalog_dir=None, diagnostics=None, review_authority=None, composition_factory=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--socket", required=True)
    parser.add_argument("--library-root", required=True)
    parser.add_argument("--session-root", help="Existing private 0700 directory; no runtime composition is enabled by this option alone.")
    parser.add_argument("--diagnostics-disabled", action="store_true", help="Explicitly disable service probes in isolated fixtures.")
    parser.add_argument("--readiness-report", help="Explicit private local ROS observer metadata file (diagnostic only).")
    parser.add_argument("--luxonis-directory", help="Private volatile read-only Luxonis observer directory.")
    args = parser.parse_args(argv)
    if args.luxonis_directory and args.diagnostics_disabled:
        parser.error("Luxonis monitor requires an explicit non-fixture diagnostics configuration")
    if args.readiness_report and (args.diagnostics_disabled or diagnostics is not None):
        parser.error("readiness report requires the default diagnostic provider")
    if args.readiness_report:
        diagnostics = lambda: systemd_diagnostics(args.readiness_report)
    def stop(_signal, _frame):
        raise KeyboardInterrupt()
    signal.signal(signal.SIGTERM, stop)
    try:
        server = CoreServer(args.socket, host_factory=lambda: CoreHost(
            args.library_root, session_root=args.session_root, composition=composition,
            catalog_dir=catalog_dir, review_authority=review_authority, composition_factory=composition_factory, luxonis_directory=args.luxonis_directory, diagnostics=(lambda: ()) if args.diagnostics_disabled else diagnostics))
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
