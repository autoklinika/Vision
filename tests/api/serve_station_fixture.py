"""TEST-only station deployment: real separate Core host, temporary accounts/data.

This harness exercises the real production WSGI/static/auth stack, without
attaching to a station or importing any operational command dispatcher.
"""
import argparse
import json
import os
from pathlib import Path
import secrets
import signal
import subprocess
import sys
import tempfile
import time

from vision_api.identity import IdentityStore, provision_account
from vision_api.station import StationApplication, serve_application
from vision_station.client import RemoteStationOwner


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--auth-file", type=Path, required=True)
    args = parser.parse_args()
    created = False
    def stop(_signal, _frame):
        raise KeyboardInterrupt()
    signal.signal(signal.SIGTERM, stop)
    with tempfile.TemporaryDirectory(prefix="vision-station-test-") as directory:
        root = Path(directory)
        username, password = "operator", secrets.token_urlsafe(32)
        accounts = root / "accounts.json"
        provision_account(accounts, username, password)
        owner = RemoteStationOwner(root / "ipc/core.sock")
        core = subprocess.Popen([sys.executable, "-B", "-m", "vision_station.service",
                                 "--socket", str(root / "ipc/core.sock"),
                                 "--library-root", str(root / "library")],
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            deadline = time.monotonic() + 10
            while owner.station_report()["coreConnection"] != "CONNECTED":
                if core.poll() is not None or time.monotonic() >= deadline:
                    raise RuntimeError("test Core process did not become available")
                time.sleep(0.02)
            app = StationApplication(
                identity=IdentityStore(accounts), owner=owner,
                dist_root=Path(__file__).resolve().parents[2] / "webgui/dist",
                origins=[f"http://127.0.0.1:{args.port}"],
            )
            fd = os.open(args.auth_file, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
            created = True
            with os.fdopen(fd, "w") as stream:
                json.dump({"username": username, "password": password}, stream)
            print("VISION_STATION_TEST_FIXTURE_READY", flush=True)
            serve_application(app, port=args.port)
        except KeyboardInterrupt:
            pass
        finally:
            if created:
                args.auth_file.unlink(missing_ok=True)
            core.terminate()
            try:
                core.wait(timeout=5)
            except subprocess.TimeoutExpired:
                core.kill()
                core.wait(timeout=5)


if __name__ == "__main__":
    main()
