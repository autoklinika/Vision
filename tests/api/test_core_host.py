"""Actual private Core process/IPC tests. Inspection fixtures are synthetic only."""
import io
import json
import os
from pathlib import Path
import socket
import stat
import struct
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from vision_api.access import Credentials, CursorRejected, ReportUnavailable
from vision_api.identity import IdentityStore, provision_account
from vision_api.station import StationApplication
from vision_api.station_owner import NoActiveSession
from vision_station.client import RemoteStationOwner
from vision_station.host import CoreHost
from vision_station.protocol import (EXCHANGE_TIMEOUT, PROTOCOL, REQUEST_LIMIT, RESPONSE_LIMIT,
                                     check_peer, receive, send, validate_station_report)
from vision_station.server import CoreServer

REPO = Path(__file__).resolve().parents[2]


class CoreHostTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="vc-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.path = self.root / "ipc/core.sock"
        self.library = self.root / "library"
        self.owner = RemoteStationOwner(self.path)

    def run_host(self, host=None):
        host = host or CoreHost(self.library)
        server = CoreServer(self.path, host)
        thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.01})
        thread.start()
        def stop():
            server.shutdown()
            thread.join(3)
            server.server_close()
        self.addCleanup(stop)
        return host, server

    def child(self):
        environment = os.environ.copy()
        environment["PYTHONPATH"] = str(REPO / "src")
        process = subprocess.Popen([sys.executable, "-B", "-m", "vision_station.service",
                                    "--socket", str(self.path), "--library-root", str(self.library)],
                                   env=environment, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        def stop():
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5)
        self.addCleanup(stop)
        deadline = time.monotonic() + 5
        while self.owner.station_report()["coreConnection"] != "CONNECTED":
            if process.poll() is not None or time.monotonic() >= deadline:
                self.fail("Core child failed to start")
            time.sleep(0.01)
        return process

    def exchange(self, request):
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
            connection.connect(str(self.path))
            deadline = time.monotonic() + EXCHANGE_TIMEOUT
            send(connection, request, limit=REQUEST_LIMIT, deadline=deadline)
            return receive(connection, limit=RESPONSE_LIMIT, deadline=deadline)

    def test_idle_host_does_not_construct_workflow_or_journal(self):
        with patch("vision_core.workflow.Workflow.__init__", side_effect=AssertionError("unexpected workflow")), \
             patch("vision_core.journal.Journal.__init__", side_effect=AssertionError("unexpected journal")):
            host, _server = self.run_host()
            report = self.owner.station_report()
            self.assertTrue(validate_station_report(report))
            self.assertEqual(report["coreConnection"], "CONNECTED")
            self.assertEqual(report["state"], "NO_ACTIVE_SESSION")
            self.assertEqual(report["coreReadiness"], "UNKNOWN")
            self.assertIsNone(report["sessionId"])
            self.assertIsNone(report["sessionViewId"])
            self.assertIsNone(host._runtime)
            with self.assertRaises(NoActiveSession):
                self.owner.session_report()
            self.assertFalse(list(self.root.rglob("*.sqlite")))

    def test_proxy_constructs_no_store_or_socket_directory(self):
        first = self.owner.station_report()
        second = self.owner.station_report()
        self.assertEqual(first["coreConnection"], "NOT_CONNECTED")
        self.assertEqual(first["instanceId"], second["instanceId"])
        self.assertFalse(self.path.parent.exists())
        self.assertFalse(self.library.exists())
        with self.assertRaises(ReportUnavailable):
            self.owner.library_reader.library_report(Credentials())
        with self.assertRaises(ReportUnavailable):
            self.owner.session_report()

    def test_real_library_reads_and_invalid_cursor(self):
        self.run_host()
        report = self.owner.library_reader.library_report(Credentials())
        self.assertEqual(report["source"], "STATION")
        self.assertEqual(len(report["entries"]), 1)
        entry = report["entries"][0]
        detail = self.owner.library_reader.entry_report(Credentials(), entry_id=entry["entryId"],
                                                        view=report["viewId"])
        self.assertEqual(detail["entry"]["entryId"], entry["entryId"])
        with self.assertRaises(CursorRejected):
            self.owner.library_reader.entry_report(Credentials(), entry_id=entry["entryId"], view="0" * 64)

    def test_socket_and_lock_are_private(self):
        self.run_host()
        for path in (self.path, self.path.with_name("core.sock.lock")):
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
            self.assertEqual(path.stat().st_uid, os.getuid())
        self.assertEqual(stat.S_IMODE(self.path.parent.stat().st_mode), 0o700)

    def test_duplicate_host_cannot_replace_active_socket(self):
        host, _server = self.run_host()
        inode = self.path.stat().st_ino
        before = self.owner.station_report()["instanceId"]
        with self.assertRaises(BlockingIOError):
            CoreServer(self.path, host)
        with self.assertRaises(BlockingIOError):
            CoreServer(self.path, host_factory=lambda: self.fail("duplicate owner initialized"))
        self.assertEqual(self.path.stat().st_ino, inode)
        self.assertEqual(self.owner.station_report()["instanceId"], before)

    def test_unsafe_parent_and_symlink_rejected(self):
        self.path.parent.mkdir(mode=0o755)
        # The station launcher uses umask 077; establish the intentionally
        # unsafe test mode explicitly rather than relying on mkdir's request.
        self.path.parent.chmod(0o755)
        with self.assertRaises(ValueError):
            CoreServer(self.path, CoreHost(self.library))
        self.assertEqual(self.owner.station_report()["coreConnection"], "NOT_CONNECTED")
        self.path.parent.chmod(0o700)
        self.path.symlink_to(self.root / "missing")
        with self.assertRaises(ValueError):
            CoreServer(self.path, CoreHost(self.library))

    def test_unmanaged_regular_file_is_not_removed(self):
        self.path.parent.mkdir(mode=0o700)
        self.path.write_bytes(b"do not delete")
        self.path.chmod(0o600)
        with self.assertRaises(ValueError):
            CoreServer(self.path, CoreHost(self.library))
        self.assertEqual(self.path.read_bytes(), b"do not delete")

    def test_peer_identity_is_checked(self):
        class Peer:
            def getsockopt(self, *_args):
                return struct.pack("3i", os.getpid(), os.getuid() + 1, os.getgid())
        with self.assertRaises(ValueError):
            check_peer(Peer())

    def test_write_operations_and_extra_fields_are_denied(self):
        host, _server = self.run_host()
        for operation in ("start", "attach", "bind_core", "stop", "approve", "shutdown"):
            result = self.exchange({"schema": PROTOCOL, "operation": operation, "query": {}})
            self.assertEqual(result, {"schema": PROTOCOL, "error": "BAD_REQUEST"})
        result = self.exchange({"schema": PROTOCOL, "operation": "station", "query": {"runtime": "x"}})
        self.assertEqual(result["error"], "BAD_REQUEST")
        self.assertIsNone(host._runtime)
        self.assertEqual(self.owner.station_report()["state"], "NO_ACTIVE_SESSION")

    def test_oversized_and_duplicate_frames_are_denied(self):
        self.run_host()
        raw = b'{"schema":"vision.station.ipc.v1","operation":"station","operation":"start","query":{}}'
        for data in (struct.pack("!I", REQUEST_LIMIT + 1), struct.pack("!I", len(raw)) + raw):
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
                connection.connect(str(self.path))
                connection.sendall(data)
                result = receive(connection, limit=RESPONSE_LIMIT,
                                 deadline=time.monotonic() + EXCHANGE_TIMEOUT)
                self.assertEqual(result["error"], "BAD_REQUEST")
        self.assertEqual(self.owner.station_report()["coreConnection"], "CONNECTED")

    def test_malformed_report_cannot_claim_connection(self):
        host, _server = self.run_host()
        with patch.object(host, "station_report", return_value={"coreConnection": "CONNECTED"}):
            self.assertEqual(self.owner.station_report()["coreConnection"], "NOT_CONNECTED")
        with patch.object(host, "station_report", side_effect=RuntimeError("private/path/password")):
            result = self.exchange({"schema": PROTOCOL, "operation": "station", "query": {}})
            self.assertEqual(result, {"schema": PROTOCOL, "error": "REPORT_UNAVAILABLE"})

    def test_worker_saturation_is_bounded_and_recovers(self):
        _host, server = self.run_host()
        connections = []
        try:
            for _ in range(4):
                connection = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                connection.connect(str(self.path))
                connection.sendall(b"\x00")  # Incomplete frame occupies one worker.
                connections.append(connection)
            deadline = time.monotonic() + 1
            while server._slots._value != 0 and time.monotonic() < deadline:
                time.sleep(0.01)
            self.assertEqual(server._slots._value, 0)
            started = time.monotonic()
            self.assertEqual(self.owner.station_report()["coreConnection"], "NOT_CONNECTED")
            self.assertLess(time.monotonic() - started, 1)
        finally:
            for connection in connections:
                connection.close()
        deadline = time.monotonic() + 1
        while self.owner.station_report()["coreConnection"] != "CONNECTED":
            if time.monotonic() >= deadline:
                self.fail("worker slots did not recover")
            time.sleep(0.01)

    def test_partial_frame_expires_under_aggregate_deadline(self):
        self.run_host()
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
            connection.connect(str(self.path))
            connection.settimeout(EXCHANGE_TIMEOUT + 1)
            connection.sendall(struct.pack("!I", 100) + b"{")
            started = time.monotonic()
            self.assertEqual(connection.recv(1), b"")
            self.assertLess(time.monotonic() - started, EXCHANGE_TIMEOUT + 0.75)

    def test_independent_process_survives_api_recreation_and_crash_recovers(self):
        core = self.child()
        before = self.owner.station_report()
        library = self.owner.library_reader.library_report(Credentials())
        # Replacing API-side client lifetimes cannot replace the Core instance.
        for _ in range(3):
            api_owner = RemoteStationOwner(self.path)
            self.assertEqual(api_owner.station_report()["instanceId"], before["instanceId"])
        self.assertIsNone(core.poll())
        core.kill()
        core.wait(timeout=5)
        self.assertTrue(self.path.exists())  # Simulate unclean exit/stale socket.
        self.assertEqual(self.owner.station_report()["coreConnection"], "NOT_CONNECTED")
        with self.assertRaises(ReportUnavailable):
            self.owner.library_reader.library_report(Credentials())
        restarted = self.child()
        self.assertNotEqual(restarted.pid, core.pid)
        self.assertNotEqual(self.owner.station_report()["instanceId"], before["instanceId"])
        self.assertEqual(self.owner.library_reader.library_report(Credentials())["viewId"], library["viewId"])

    def test_authenticated_wsgi_restart_reads_same_core_process(self):
        core = self.child()
        instance = self.owner.station_report()["instanceId"]
        accounts = self.root / "accounts.json"
        provision_account(accounts, "operator", "synthetic-test-password")
        identity = IdentityStore(accounts)
        token, _report = identity.login("operator", "synthetic-test-password", "test")
        dist = self.root / "dist"
        (dist / "assets").mkdir(parents=True)
        (dist / "index.html").write_text('<meta name="vision-deployment" content="station">')
        (dist / "THIRD_PARTY_NOTICES.txt").write_text("test fixture")
        for _ in range(2):
            application = StationApplication(identity=identity, owner=RemoteStationOwner(self.path),
                                             dist_root=dist, origins=["http://127.0.0.1:18490"])
            response = []
            environment = {"REQUEST_METHOD": "GET", "PATH_INFO": "/api/v1/station",
                           "QUERY_STRING": "", "HTTP_HOST": "127.0.0.1:18490",
                           "HTTP_COOKIE": "vision_session=" + token,
                           "wsgi.input": io.BytesIO(b"")}
            raw = b"".join(application(environment, lambda status, headers: response.append(status)))
            self.assertEqual(response, ["200 OK"])
            self.assertEqual(json.loads(raw)["instanceId"], instance)
        self.assertIsNone(core.poll())

    def test_trusted_real_runtime_binding_is_read_only_and_cleanup_is_versioned(self):
        # Reuse the established synthetic fixture to instantiate the ACTUAL
        # coordinator with approved test-only releases and real Workflow.
        sys.path.insert(0, str(REPO / "tests/core"))
        self.addCleanup(lambda: sys.path.remove(str(REPO / "tests/core")))
        import test_vision_runtime_v1 as fixture
        case = fixture.RuntimeTests()
        self.addCleanup(case.doCleanups)
        case.setUp()
        host, _server = self.run_host()
        runtime = case.coordinator
        before = runtime.engine.journal.replay(runtime.engine.context.session_id)
        first = host.attach_runtime(runtime)
        report = self.owner.station_report()
        self.assertEqual(report["state"], "SESSION_ACTIVE")
        self.assertEqual(report["sessionViewId"], first)
        session = self.owner.session_report()
        self.assertTrue(all(stage["state"] == "PENDING" for stage in session["stages"]))
        events = self.owner.events_report(view=first, after=0, through=session["journalSequence"])
        self.assertEqual(events["events"], [])
        another_proxy = RemoteStationOwner(self.path)
        again = another_proxy.session_report()
        self.assertEqual(again["viewId"], session["viewId"])
        self.assertEqual(again["stages"], session["stages"])
        self.assertEqual(again["journalSequence"], session["journalSequence"])
        self.assertEqual(runtime.engine.journal.replay(runtime.engine.context.session_id), before)
        second = host.attach_runtime(runtime)
        self.assertNotEqual(first, second)
        self.assertFalse(host.clear_runtime(first))
        self.assertTrue(host.clear_runtime(second))
        self.assertEqual(self.owner.station_report()["coreConnection"], "CONNECTED")
        self.assertEqual(self.owner.station_report()["state"], "NO_ACTIVE_SESSION")
        with self.assertRaises(NoActiveSession):
            self.owner.session_report()
        with self.assertRaises(ValueError):
            host.attach_runtime(runtime.engine)


if __name__ == "__main__":
    unittest.main()
