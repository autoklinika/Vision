"""Deployment boundary: real authentication, static allowlist and owner lifecycle."""
from io import BytesIO
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from projection_support import memory_fixture
from vision_api.access import Credentials, CursorRejected
from vision_api.identity import IdentityStore, provision_account
from vision_api.station import StationApplication, STATION_MARKER, _load_static, _origins
from vision_api.station_owner import NoActiveSession, StationOwner
from vision_modules.ecu_library_backend import ECULibraryService


class StationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.dist = self.root / "dist"
        (self.dist / "assets").mkdir(parents=True)
        (self.dist / "index.html").write_bytes(b"<!doctype html>" + STATION_MARKER)
        (self.dist / "THIRD_PARTY_NOTICES.txt").write_text("Test notices")
        (self.dist / "assets" / "app-test.js").write_text("/* test asset */")
        (self.dist / ".env").write_text("MUST_NOT_SERVE")
        (self.dist / "assets" / "app.js.map").write_text("MUST_NOT_SERVE")
        self.accounts = self.root / "accounts.json"
        self.password = "test-only-station-password-2026"
        provision_account(self.accounts, "operator", self.password)
        self.identity = IdentityStore(self.accounts)
        self.owner = StationOwner(ECULibraryService(self.root / "library"))
        self.app = StationApplication(identity=self.identity, owner=self.owner, dist_root=self.dist,
                                      origins=["http://127.0.0.1:18490", "https://station.example"])

    def request(self, target, *, method="GET", value=None, raw=None, cookie=None, headers=None, host="127.0.0.1:18490"):
        path, _, query = target.partition("?")
        env = {"REQUEST_METHOD": method, "PATH_INFO": path, "QUERY_STRING": query,
               "REQUEST_URI": target, "HTTP_HOST": host, "wsgi.input": BytesIO(b"")}
        if cookie:
            env["HTTP_COOKIE"] = cookie
        if value is not None or raw is not None:
            body = raw if raw is not None else json.dumps(value).encode()
            env.update({"wsgi.input": BytesIO(body), "CONTENT_TYPE": "application/json", "CONTENT_LENGTH": str(len(body))})
        if headers:
            env.update(headers)
        response = {}
        def start(status, response_headers):
            response["status"] = int(status.split()[0])
            response["headers"] = dict(response_headers)
        response["body"] = b"".join(self.app(env, start))
        if response["headers"]["Content-Type"].startswith("application/json"):
            response["json"] = json.loads(response["body"] or b"null")
        return response

    def login(self, *, host="127.0.0.1:18490"):
        result = self.request("/api/v1/auth/login", method="POST", host=host,
                              value={"username": "operator", "password": self.password},
                              headers={"HTTP_ORIGIN": self.app.origins[host], "HTTP_X_VISION_CLIENT": "webgui"})
        self.assertEqual(result["status"], 200)
        return result, result["headers"]["Set-Cookie"].split(";")[0]

    def test_login_session_logout_and_cookie_scope(self):
        result, cookie = self.login(host="station.example")
        attributes = result["headers"]["Set-Cookie"].split("; ")[1:]
        self.assertEqual(set(attributes), {"Path=/", "HttpOnly", "SameSite=Strict", "Max-Age=28800", "Secure"})
        report = result["json"]
        self.assertEqual(set(report), {"schema", "authenticated", "username", "role", "expiresAt"})
        self.assertEqual(report["role"], "reader")
        self.assertFalse(self.password.encode() in result["body"])
        self.assertEqual(self.request("/api/v1/auth/session", cookie=cookie)["status"], 200)
        out = self.request("/api/v1/auth/logout", method="POST", value={}, cookie=cookie,
                           host="station.example", headers={"HTTP_ORIGIN": "https://station.example", "HTTP_X_VISION_CLIENT": "webgui"})
        self.assertEqual(out["status"], 200)
        self.assertTrue("Max-Age=0" in out["headers"]["Set-Cookie"])
        self.assertTrue("; Secure" in out["headers"]["Set-Cookie"])
        self.assertEqual(self.request("/api/v1/auth/session", cookie=cookie)["status"], 401)
        self.assertEqual(self.request("/api/v1/library", cookie=cookie)["status"], 401)

    def test_loopback_login_cookie_usable_in_secure_local_context(self):
        result, cookie = self.login()
        self.assertFalse("; Secure" in result["headers"]["Set-Cookie"])
        self.assertEqual(self.request("/api/v1/library", cookie=cookie)["status"], 200)

    def test_anonymous_reads_never_touch_owners(self):
        with patch.object(self.owner, "station_report", side_effect=AssertionError("owner reached")), \
             patch.object(self.owner, "session_report", side_effect=AssertionError("owner reached")), \
             patch.object(self.owner.library_reader, "library_report", side_effect=AssertionError("owner reached")):
            for path in ("/api/v1/station", "/api/v1/session", "/api/v1/library",
                         "/api/v1/events?view=" + "a" * 32 + "&after=0&through=0",
                         "/api/v1/library/entries/" + "a" * 32 + "?view=" + "a" * 64):
                with self.subTest(path=path):
                    self.assertEqual(self.request(path)["status"], 401)

    def test_real_idle_report_and_library_do_not_construct_workflow(self):
        _, cookie = self.login()
        with patch("vision_core.workflow.Workflow.__init__", side_effect=AssertionError("constructed Core")):
            station = self.request("/api/v1/station", cookie=cookie)["json"]
            self.assertEqual(station["state"], "NO_ACTIVE_SESSION")
            self.assertEqual(station["coreConnection"], "NOT_CONNECTED")
            self.assertEqual(station["coreReadiness"], "UNKNOWN")
            self.assertIsNone(station["sessionId"])
            self.assertIsNone(station["sessionViewId"])
            idle = self.request("/api/v1/session", cookie=cookie)
            self.assertEqual(idle["status"], 409)
            self.assertEqual(idle["json"]["code"], "NO_ACTIVE_SESSION")
            library = self.request("/api/v1/library", cookie=cookie)["json"]
            self.assertEqual(library["source"], "STATION")
            self.assertTrue(all(e["kind"] == "CATALOG_RECORD" for e in library["entries"]))
            self.assertTrue(all(e["readiness"] == "NOT_READY" for e in library["entries"]))

    def test_same_backend_two_clients_browser_logout_cannot_change_owner(self):
        _, first = self.login()
        _, second = self.login()
        a = self.request("/api/v1/station", cookie=first)["json"]
        b = self.request("/api/v1/station", cookie=second)["json"]
        self.assertEqual(a["instanceId"], b["instanceId"])
        self.request("/api/v1/auth/logout", method="POST", value={}, cookie=first,
                     headers={"HTTP_ORIGIN": "http://127.0.0.1:18490", "HTTP_X_VISION_CLIENT": "webgui"})
        self.assertEqual(self.request("/api/v1/station", cookie=second)["json"]["instanceId"], a["instanceId"])

    def test_account_reset_revokes_access_without_server_restart(self):
        _, cookie = self.login()
        provision_account(self.accounts, "operator", "test-only-replacement-password", replace=True)
        self.assertEqual(self.request("/api/v1/library", cookie=cookie)["status"], 401)

    def test_unavailable_identity_store_reports_service_failure_without_details(self):
        _, cookie = self.login()
        self.accounts.write_text("corrupt private content")
        response = self.request("/api/v1/library", cookie=cookie)
        self.assertEqual(response["status"], 503)
        self.assertEqual(response["json"], {"schema": "vision.api.error.v1", "code": "REPORT_UNAVAILABLE"})

    def test_origin_host_csrf_and_header_ambiguity_fail_closed(self):
        _, cookie = self.login()
        for host, headers in (("evil.example", {}), ("127.0.0.1:18490", {"HTTP_ORIGIN": "https://evil.example"}),
                              ("127.0.0.1:18490", {"HTTP_SEC_FETCH_SITE": "cross-site"}),
                              ("127.0.0.1:18490, evil.example", {}),
                              ("station.example", {"HTTP_ORIGIN": "http://127.0.0.1:18490"})):
            self.assertEqual(self.request("/api/v1/library", host=host, headers=headers, cookie=cookie)["status"], 403)
        # Spoofed forwarding headers never change the explicit origin policy.
        self.assertEqual(self.request("/api/v1/library", host="evil.example", cookie=cookie,
                                      headers={"HTTP_X_FORWARDED_HOST": "station.example", "HTTP_X_FORWARDED_PROTO": "https"})["status"], 403)
        for headers in ({}, {"HTTP_ORIGIN": "http://127.0.0.1:18490"}, {"HTTP_X_VISION_CLIENT": "webgui"}):
            self.assertEqual(self.request("/api/v1/auth/logout", method="POST", value={}, cookie=cookie, headers=headers)["status"], 403)
        self.assertEqual(self.request("/api/v1/library", cookie=cookie + ", " + cookie)["status"], 401)
        self.assertEqual(self.request("/api/v1/library", cookie=cookie + "; " + cookie)["status"], 401)

    def test_closed_bounded_login_json_and_no_operational_routes(self):
        headers = {"HTTP_ORIGIN": "http://127.0.0.1:18490", "HTTP_X_VISION_CLIENT": "webgui"}
        bad = [b"[]", b"null", b'{"username":"operator","username":"other","password":"x"}',
               b'{"username":"operator","password":"x","admin":true}', b"x" * 8193, b"\xff"]
        for raw in bad:
            self.assertEqual(self.request("/api/v1/auth/login", method="POST", raw=raw, headers=headers)["status"], 400)
        _, cookie = self.login()
        for path in ("/api/v1/session", "/api/v1/station/bind", "/api/v1/restart", "/api/v1/library"):
            self.assertEqual(self.request(path, method="POST", value={}, cookie=cookie, headers=headers)["status"], 405)

    def test_static_root_is_allowlisted_not_repository_or_storage(self):
        for path in ("/", "/index.html", "/assets/app-test.js", "/THIRD_PARTY_NOTICES.txt"):
            response = self.request(path)
            self.assertEqual(response["status"], 200)
            self.assertEqual(response["headers"]["Cache-Control"], "no-store")
            self.assertEqual(response["headers"]["X-Frame-Options"], "DENY")
        self.assertEqual(self.request("/", method="HEAD")["body"], b"")
        for path in ("/.env", "/accounts.json", "/.station-test-auth.json", "/assets/app.js.map",
                     "/src/main.tsx", "/@fs/etc/passwd", "/../accounts.json", "/%2e%2e/accounts.json"):
            self.assertEqual(self.request(path)["status"], 404)
        self.assertEqual(self.request("/api/v1/library?unexpected=1")["status"], 404)

    def test_static_build_marker_symlinks_and_origin_configuration(self):
        (self.dist / "index.html").write_text("demo must not be deployed")
        with self.assertRaises(ValueError):
            _load_static(self.dist)
        (self.dist / "index.html").unlink()
        (self.dist / "index.html").symlink_to(self.accounts)
        with self.assertRaises(ValueError):
            _load_static(self.dist)
        for origins in (["http://192.0.2.1:18490"], ["https://station.example/path"],
                        ["https://user@station.example"], ["https://station.example", "http://station.example"]):
            with self.assertRaises(ValueError):
                _origins(origins)

    def test_owner_binding_cutover_and_retired_cleanup(self):
        journal, engine = memory_fixture(acknowledgements=2)
        self.addCleanup(journal.close)
        first = self.owner.bind_core(engine)
        report = self.owner.session_report()
        self.assertEqual(report["viewId"], first)
        self.assertEqual(report["source"], "STATION")
        self.assertEqual(self.owner.station_report()["state"], "SESSION_ACTIVE")
        second = self.owner.bind_core(engine)
        self.assertNotEqual(first, second)
        self.assertFalse(self.owner.clear_core(first))
        with self.assertRaises(CursorRejected):
            self.owner.events_report(view=first, after=0, through=report["journalSequence"])
        self.assertTrue(self.owner.clear_core(second))
        with self.assertRaises(NoActiveSession):
            self.owner.session_report()
        # Browser operations above never start/stop/replay this engine.

    def test_cutover_during_read_cannot_publish_retired_snapshot(self):
        journal, engine = memory_fixture(acknowledgements=2)
        self.addCleanup(journal.close)
        self.owner.bind_core(engine)
        original = engine.read_snapshot
        def cutover():
            value = original()
            self.owner.bind_core(engine)
            return value
        with patch.object(engine, "read_snapshot", side_effect=cutover):
            with self.assertRaises(CursorRejected):
                self.owner.session_report()


if __name__ == "__main__":
    unittest.main()
