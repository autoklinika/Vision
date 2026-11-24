"""Explicitly synthetic browser-test harness, outside production packages.

Creates one real in-memory Workflow before serving; HTTP reads cannot mutate it.
Random credentials are written to a private ignored test file, never to stdout
or a served route. The frontend build contains neither this fixture nor a token.
"""
import argparse
import json
import os
from pathlib import Path
import secrets
import signal

from projection_support import SESSION, memory_fixture
from vision_api.access import ReadGrant
from vision_api.reports import CoreReportProvider
from vision_api.server import make_server


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--auth-file", type=Path, required=True)
    args = parser.parse_args()
    if not 1 <= args.port <= 65535:
        parser.error("invalid port")
    journal, engine = memory_fixture()
    cookie_name, cookie_value = "vision_api02_fixture", secrets.token_urlsafe(32)
    expected = f"{cookie_name}={cookie_value}"

    def authorize(credentials):
        if secrets.compare_digest(credentials.cookie or "", expected):
            return ReadGrant(SESSION, frozenset({"session:read", "events:read"}))
        return None

    def stop(_signal, _frame):
        raise KeyboardInterrupt()

    signal.signal(signal.SIGTERM, stop)
    # This is a test-only fixed filename; refuse existing files/symlinks.
    created = False
    try:
        with args.auth_file.open("x", opener=lambda name, flags: os.open(name, flags, 0o600)) as auth:
            created = True
            json.dump({"cookieName": cookie_name, "cookieValue": cookie_value}, auth)
        with make_server(args.port, provider=CoreReportProvider(engine, source="SYNTHETIC_TEST"), authorizer=authorize) as server:
            print(f"VISION_API02_SYNTHETIC_TEST port={server.server_port}", flush=True)
            try:
                server.serve_forever()
            except KeyboardInterrupt:
                pass
    finally:
        journal.close()
        if created:
            args.auth_file.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
