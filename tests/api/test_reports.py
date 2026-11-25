"""Protected API integration against real synthetic Core; no hardware."""
from copy import deepcopy
import http.client
import json
from pathlib import Path
import secrets
import threading
import unittest
from unittest.mock import patch

from projection_support import SESSION, memory_fixture
from vision_api.access import AccessDenied, Credentials, ReadGrant, ReportUnavailable
from vision_api.reports import (CoreReportProvider, MAX_PROTECTED_BYTES, SessionReadService,
                                validate_events_report, validate_session_report)
from vision_api.server import make_server

CONTRACTS = Path(__file__).resolve().parents[2] / "contracts/vision-api/v1"


class ReportContractTests(unittest.TestCase):
    def test_shared_fixtures_and_closed_schema_keys(self):
        fixtures = json.loads((CONTRACTS / "session-fixtures.json").read_text())
        for name, validator in (("session", validate_session_report), ("events", validate_events_report)):
            schema = json.loads((CONTRACTS / f"{name}.schema.json").read_text())
            value = fixtures[name]
            self.assertTrue(validator(value))
            self.assertEqual(set(schema["required"]), set(value))
            self.assertFalse(schema["additionalProperties"])
            self.assertFalse(validator({**value, "private": "never export"}))
            self.assertFalse(validator({**value, "capturedAt": "2026-02-30T00:00:00Z"}))
            self.assertFalse(validator({**value, "source": "LIVE"}))
            self.assertFalse(validator(None))

    def test_stage_semantics_and_hostile_types(self):
        good = json.loads((CONTRACTS / "session-fixtures.json").read_text())["session"]
        for replacement in (True, -1, 2**53, 1.5):
            self.assertFalse(validate_session_report({**good, "journalSequence": replacement}))
        variants = []
        duplicate = deepcopy(good); duplicate["stages"][-1] = duplicate["stages"][0]; variants.append(duplicate)
        missing = deepcopy(good); missing["stages"][-1]["id"] = "extra"; variants.append(missing)
        invalid = deepcopy(good); invalid["stages"][0]["state"] = "ACK"; variants.append(invalid)
        success = deepcopy(good); success["stages"][0]["historicalSuccess"] = False; variants.append(success)
        raw = deepcopy(good); raw["stages"][1]["lastAckSequence"] = 100; variants.append(raw)
        variants.append({**good, "invalidated": True})
        for value in variants:
            self.assertFalse(validate_session_report(value))

    def test_page_sequence_cursor_and_private_payload_rejected(self):
        good = json.loads((CONTRACTS / "session-fixtures.json").read_text())["events"]
        for field, value in (("throughSequence", 100), ("afterSequence", 8), ("nextAfterSequence", 7)):
            self.assertFalse(validate_events_report({**good, field: value}))
        bad = deepcopy(good); bad["events"][1]["sequence"] = 7
        self.assertFalse(validate_events_report(bad))
        bad = deepcopy(good); bad["events"][1]["state"] = "SUCCEEDED"
        self.assertFalse(validate_events_report(bad))
        bad = deepcopy(good); bad["events"][0]["data"] = {"path": "/private"}
        self.assertFalse(validate_events_report(bad))


class ProtectedAPITests(unittest.TestCase):
    def setUp(self):
        self.journal, self.engine = memory_fixture()
        self.provider = CoreReportProvider(self.engine, source="SYNTHETIC_TEST")
        self.token = secrets.token_hex(24)
        self.grant = ReadGrant(SESSION, frozenset({"session:read", "events:read"}))
        self.server = make_server(0, provider=self.provider, authorizer=self.authorize)
        self.worker = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.worker.start()

    def tearDown(self):
        self.server.shutdown(); self.server.server_close(); self.worker.join(timeout=3)
        self.journal.close()

    def authorize(self, credentials):
        return self.grant if credentials.authorization == f"Bearer {self.token}" else None

    def request(self, path="/api/v1/session", *, authenticated=True, headers=None, method="GET"):
        request_headers = {"Authorization": f"Bearer {self.token}"} if authenticated else {}
        request_headers.update(headers or {})
        connection = http.client.HTTPConnection("127.0.0.1", self.server.server_port, timeout=4)
        try:
            connection.request(method, path, headers=request_headers)
            response = connection.getresponse()
            raw = response.read(MAX_PROTECTED_BYTES + 1)
            self.assertLessEqual(len(raw), MAX_PROTECTED_BYTES)
            self.assertEqual(response.getheader("Cache-Control"), "no-store")
            self.assertEqual(response.getheader("X-Content-Type-Options"), "nosniff")
            self.assertIsNone(response.getheader("Access-Control-Allow-Origin"))
            self.assertIsNone(response.getheader("Location"))
            return response.status, json.loads(raw) if raw else None
        finally:
            connection.close()

    def events_path(self, report, *, after=0, through=None, view=None):
        return f"/api/v1/events?view={view or report['viewId']}&after={after}&through={report['journalSequence'] if through is None else through}"

    def test_authorized_session_and_pages_are_consistent_read_only(self):
        before = self.journal.db.total_changes
        history = self.journal.replay(SESSION)
        states = dict(self.engine.states)
        status, report = self.request()
        self.assertEqual(status, 200); self.assertTrue(validate_session_report(report))
        self.assertEqual(report["source"], "SYNTHETIC_TEST")
        self.assertEqual(report["stages"][0]["state"], "SUCCEEDED")
        self.assertTrue(report["stages"][0]["historicalSuccess"])
        self.assertEqual(report["stages"][1]["state"], "RUNNING")
        self.assertIsNotNone(report["stages"][1]["lastAckSequence"])
        collected, after = [], 0
        while True:
            status, page = self.request(self.events_path(report, after=after))
            self.assertEqual(status, 200); self.assertTrue(validate_events_report(page))
            self.assertEqual(page["viewId"], report["viewId"])
            collected.extend(page["events"])
            if page["nextAfterSequence"] is None:
                break
            after = page["nextAfterSequence"]
        self.assertEqual([event["sequence"] for event in collected], [event.sequence for event in history])
        self.assertEqual(self.journal.db.total_changes, before)
        self.assertEqual(self.journal.replay(SESSION), history)
        self.assertEqual(dict(self.engine.states), states)
        self.assertNotIn("synthetic-reference", json.dumps(report) + json.dumps(collected))

    def test_denied_auth_never_reads_provider_and_public_status_stays_public(self):
        with patch.object(self.provider, "session_report", side_effect=AssertionError("provider must not run")) as read:
            status, value = self.request(authenticated=False)
            self.assertEqual((status, value["code"]), (401, "ACCESS_DENIED"))
            status, value = self.request(authenticated=False, headers={"X-User": "admin", "X-Authorized": "true"})
            self.assertEqual(status, 401); read.assert_not_called()
        status, value = self.request("/api/v1/status", authenticated=False)
        self.assertEqual(status, 200)
        self.assertEqual(value["coreReadiness"], "UNKNOWN")
        self.assertNotIn("sessionId", value)

    def test_defaultdeny_scope_mismatch_truthy_and_authorizer_exception(self):
        credentials = Credentials()
        authorizers = [None, lambda _: False, lambda _: True, lambda _: "admin",
                       lambda _: ReadGrant("other", frozenset({"session:read"})),
                       lambda _: ReadGrant(SESSION, frozenset({"events:read"}))]
        def broken(_):
            raise RuntimeError("private authorization failure")
        authorizers.append(broken)
        with patch.object(self.provider, "session_report") as read:
            for authorize in authorizers:
                with self.assertRaises(AccessDenied):
                    SessionReadService(provider=self.provider, authorizer=authorize).session_report(credentials)
            read.assert_not_called()
        with self.assertRaises(ReportUnavailable):
            SessionReadService(authorizer=lambda _: self.grant).session_report(credentials)

    def test_events_require_separate_scope_and_provider_binding(self):
        _, report = self.request()
        self.grant = ReadGrant(SESSION, frozenset({"session:read"}))
        with patch.object(self.provider, "events_report") as read:
            self.assertEqual(self.request(self.events_path(report))[0], 401)
            read.assert_not_called()
        self.grant = ReadGrant(SESSION, frozenset({"session:read", "events:read"}))
        self.assertEqual(self.request(self.events_path(report, view="0" * 32))[0], 409)
        self.assertEqual(self.request(self.events_path(report, after=report["journalSequence"] + 1))[0], 409)
        self.assertEqual(self.request(self.events_path(report, through=2**53))[0], 409)

    def test_historical_page_pin_does_not_follow_later_events(self):
        _, report = self.request()
        self.engine.ack("S02", "synthetic-req-S02")
        before = self.journal.db.total_changes
        status, page = self.request(self.events_path(report, after=report["journalSequence"] - 1))
        self.assertEqual(status, 200)
        self.assertEqual(page["events"][-1]["sequence"], report["journalSequence"])
        self.assertIsNone(page["nextAfterSequence"])
        self.assertEqual(self.journal.db.total_changes, before)

    def test_redaction_unknown_events_and_invalidation_history(self):
        self.journal.append(SESSION, "private-stage", "private-request", "private-kind", {"token": "private-secret", "path": "/secret/file", "raw": "x" * 300000})
        _, report = self.request()
        status, page = self.request(self.events_path(report, after=report["journalSequence"] - 1))
        self.assertEqual(status, 200)
        self.assertEqual(page["events"][0]["kind"], "OTHER")
        self.assertIsNone(page["events"][0]["stageId"])
        self.assertNotIn("private", json.dumps(page))
        self.engine.invalidate("private reason")
        status, report = self.request()
        self.assertEqual(status, 200); self.assertTrue(report["invalidated"])
        self.assertTrue(all(s["state"] == "BLOCKED" for s in report["stages"]))
        self.assertTrue(report["stages"][0]["historicalSuccess"])
        self.assertNotIn("private reason", json.dumps(report))

    def test_unavailable_and_exception_do_not_publish_partial_reports(self):
        with patch.object(self.engine, "read_snapshot", side_effect=RuntimeError("private local path")):
            self.assertEqual(self.request(), (503, {"schema": "vision.api.error.v1", "code": "REPORT_UNAVAILABLE"}))
        with patch.object(self.engine, "read_snapshot", return_value=None):
            self.assertEqual(self.request()[0], 503)
        self.engine._journal_uncertain = True
        self.assertEqual(self.request()[0], 503)

    def test_route_origin_and_method_boundaries(self):
        _, report = self.request()
        route = self.events_path(report)
        for path in ("//api/v1/session", "/api/v1/session?token=anything", "/api/v1/session/", route + "&after=0", route.replace("after=0", "after=00"), route + "&debug=1"):
            self.assertEqual(self.request(path)[0], 404)
        self.assertEqual(self.request(headers={"Origin": "https://attacker.invalid"})[0], 403)
        self.assertEqual(self.request(headers={"Sec-Fetch-Site": "cross-site"})[0], 403)
        self.assertEqual(self.request(headers={"Cookie": "x" * 4097})[0], 400)
        for method in ("POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"):
            self.assertEqual(self.request(method=method)[0], 405)


if __name__ == "__main__":
    unittest.main()
