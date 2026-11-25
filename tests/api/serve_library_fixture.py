"""Explicit synthetic integration harness using the actual ECU library backend.

All writes happen during fixture construction before HTTP starts. No fixture
route, token option, asset endpoint or write route is added to production code.
"""
import argparse
import json
import os
from pathlib import Path
import secrets
import signal
import tempfile

from library_support import LIBRARY_ID, library_fixture
from vision_api.access import LibraryReadGrant
from vision_api.library_reports import LibraryReportProvider
from vision_api.server import make_server


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--auth-file", type=Path, required=True)
    args = parser.parse_args()
    if not 1 <= args.port <= 65535:
        parser.error("invalid port")
    cookie_name, cookie_value = "vision_api03_test", secrets.token_urlsafe(32)
    expected = f"{cookie_name}={cookie_value}"

    def authorize(credentials):
        if secrets.compare_digest(credentials.cookie or "", expected):
            return LibraryReadGrant(LIBRARY_ID, frozenset({"library:read"}))
        return None

    def stop(_signal, _frame):
        raise KeyboardInterrupt()

    signal.signal(signal.SIGTERM, stop)
    created = False
    try:
        with tempfile.TemporaryDirectory(prefix="vision-api03-synthetic-") as directory:
            service = library_fixture(Path(directory) / "library")
            provider = LibraryReportProvider(service, library_id=LIBRARY_ID, source="SYNTHETIC_TEST")
            with open(args.auth_file, "x", opener=lambda name, flags: os.open(name, flags, 0o600)) as auth:
                created = True
                json.dump({"cookieName": cookie_name, "cookieValue": cookie_value}, auth)
            with make_server(args.port, library_provider=provider, library_authorizer=authorize) as server:
                print(f"VISION_API03_SYNTHETIC_TEST port={server.server_port}", flush=True)
                try:
                    server.serve_forever()
                except KeyboardInterrupt:
                    pass
    finally:
        if created:
            args.auth_file.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
