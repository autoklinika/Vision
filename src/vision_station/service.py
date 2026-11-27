"""Run the independent Vision station/Core host without an active inspection."""
import argparse
import signal

from .host import CoreHost
from .server import CoreServer
from .inspection import systemd_diagnostics
from .luxonis_ir import IRController
from .nero_clear_coordinator import RosClearTransport
from .client import RemoteStationOwner
from .nero_manual_transport import ManualTransport


def main(argv=None, *, composition=None, catalog_dir=None, diagnostics=None, review_authority=None, composition_factory=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--socket", required=True)
    parser.add_argument("--library-root", required=True)
    parser.add_argument("--session-root", help="Existing private 0700 directory; no runtime composition is enabled by this option alone.")
    parser.add_argument("--diagnostics-disabled", action="store_true", help="Explicitly disable service probes in isolated fixtures.")
    parser.add_argument("--readiness-report", help="Explicit private local ROS observer metadata file (diagnostic only).")
    parser.add_argument("--nero-manual-socket", help="Explicit sole-owner manual maintenance socket; excludes inspections and clear.")
    parser.add_argument("--nero-directory", help="Private volatile read-only NERO observer directory.")
    parser.add_argument("--nero-clear-overlay", help="Explicit generated ROS interface overlay on NVMe; no default.")
    parser.add_argument("--nero-clear-ros-directory", help="Existing private NVMe ROS log directory.")
    parser.add_argument("--nero-clear-idle-socket", help="Independent production idle interlock socket.")
    parser.add_argument("--nero-history-directory", help="Explicit existing private NVMe directory for NERO fault history.")
    parser.add_argument("--luxonis-directory", help="Private volatile read-only Luxonis observer directory.")
    parser.add_argument("--luxonis-ir-control", action="store_true", help="Explicitly enable standalone camera IR control.")
    parser.add_argument("--luxonis-ir-idle-socket", help="Optional separate Core read-only idle interlock (required in DEV).")
    args = parser.parse_args(argv)
    if args.luxonis_ir_control and (not args.luxonis_directory or args.diagnostics_disabled):
        parser.error("IR control requires the configured Luxonis observer")
    if args.luxonis_ir_idle_socket and not args.luxonis_ir_control:
        parser.error("IR idle interlock requires explicit IR control")
    clear_options=(args.nero_clear_overlay,args.nero_clear_ros_directory,args.nero_clear_idle_socket)
    if any(clear_options) and (not all(clear_options) or not args.nero_history_directory):
        parser.error("NERO clear requires all explicit overlay, ROS directory, idle socket and history options")
    if args.nero_manual_socket and (any(clear_options) or composition is not None or composition_factory is not None or not args.nero_directory):
        parser.error("exclusive manual maintenance requires NERO observer, no inspection composition or clear")
    if args.nero_history_directory and not args.nero_directory:
        parser.error("NERO history requires the observer")
    if args.nero_directory and args.diagnostics_disabled:
        parser.error("NERO monitor requires explicit non-fixture diagnostics configuration")
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
            catalog_dir=catalog_dir, review_authority=review_authority, composition_factory=composition_factory, nero_directory=args.nero_directory, nero_history_directory=args.nero_history_directory, nero_manual_transport=ManualTransport(args.nero_manual_socket) if args.nero_manual_socket else None, nero_clear_transport=RosClearTransport(args.nero_clear_overlay,args.nero_clear_ros_directory) if args.nero_clear_overlay else None, nero_clear_interlock=RemoteStationOwner(args.nero_clear_idle_socket).station_report if args.nero_clear_idle_socket else None, luxonis_directory=args.luxonis_directory, luxonis_ir=IRController() if args.luxonis_ir_control else None, luxonis_ir_interlock=RemoteStationOwner(args.luxonis_ir_idle_socket).station_report if args.luxonis_ir_idle_socket else None, diagnostics=(lambda: ()) if args.diagnostics_disabled else diagnostics))
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
