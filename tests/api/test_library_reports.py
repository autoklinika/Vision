"""Protected API-03 contracts, authority separation and actual backend reads."""
from copy import deepcopy
from dataclasses import replace
import http.client
import json
from pathlib import Path
import secrets
import tempfile
import threading
import unittest
from unittest.mock import patch

from library_support import LIBRARY_ID, PROFILE_ID, library_fixture
from test_library_projection import files
from vision_api.access import (AccessDenied, Credentials, LibraryReadGrant,
                               ReadGrant, ReportUnavailable)
from vision_api.library_reports import (LibraryReadService, LibraryReportProvider,
    validate_library_report, validate_library_entry_report, validate_library_history_report)
from vision_api.reports import MAX_PROTECTED_BYTES
from vision_api.server import make_server

CONTRACTS = Path(__file__).resolve().parents[2] / "contracts/vision-api/v1"


class LibraryContractTests(unittest.TestCase):
    def test_shared_fixtures_closed_schemas_and_unknown_fields(self):
        fixtures = json.loads((CONTRACTS / "library-fixtures.json").read_text())
        for name, schema_name, validator in (
            ("library", "library", validate_library_report),
            ("catalogEntry", "library-entry", validate_library_entry_report),
            ("profileEntry", "library-entry", validate_library_entry_report),
            ("history", "library-history", validate_library_history_report),
        ):
            with self.subTest(name=name):
                value = fixtures[name]
                schema = json.loads((CONTRACTS / f"{schema_name}.schema.json").read_text())
                self.assertTrue(validator(value))
                self.assertEqual(set(schema["required"]), set(value))
                self.assertFalse(schema["additionalProperties"])
                self.assertFalse(validator({**value, "private": "never publish"}))
                self.assertFalse(validator({**value, "capturedAt": "2026-02-30T00:00:00Z"}))
                self.assertFalse(validator({**value, "source": "LIVE"}))
                self.assertFalse(validator({**value, "viewId": "a" * 32}))
                for bad in (None, True, [], "invalid"):
                    self.assertFalse(validator(bad))

    def test_page_and_entry_semantics_are_not_only_shape_checks(self):
        good = json.loads((CONTRACTS / "library-fixtures.json").read_text())["library"]
        for key, value in (("after", True), ("after", 1), ("nextAfter", 0), ("totalCount", 513), ("totalCount", 1)):
            self.assertFalse(validate_library_report({**good, key: value}))
        for change in ({"readiness": "PASS"}, {"kind": "SPECIMEN"}, {"status": "APPROVED"},
                       {"etag": None}, {"reasonCode": "CATALOG_ONLY"}, {"displayName": "secret\npath"}):
            value = deepcopy(good)
            draft = next(e for e in value["entries"] if e["kind"] == "REFERENCE_DRAFT")
            draft.update(change)
            self.assertFalse(validate_library_report(value))
        duplicate = deepcopy(good); duplicate["entries"][1] = duplicate["entries"][0]
        self.assertFalse(validate_library_report(duplicate))

    def test_detail_and_history_cannot_claim_readiness_or_expose_payload(self):
        fixtures = json.loads((CONTRACTS / "library-fixtures.json").read_text())
        good = fixtures["profileEntry"]
        invalid = []
        for key, replacement in (("sections", []), ("historyCount", 0), ("historyCount", True)):
            value = deepcopy(good); value["profile"][key] = replacement; invalid.append(value)
        value = deepcopy(good); value["profile"]["sections"][0]["status"] = "VERIFIED"; invalid.append(value)
        value = deepcopy(good); value["profile"]["sections"][0]["raw"] = {"path": "/private"}; invalid.append(value)
        value = deepcopy(good); value["profile"]["workflows"][0]["stateId"] = "unknown"; invalid.append(value)
        value = deepcopy(good); value["catalog"] = fixtures["catalogEntry"]["catalog"]; invalid.append(value)
        for value in invalid:
            self.assertFalse(validate_library_entry_report(value))
        value = deepcopy(fixtures["history"]); value["items"][-1]["etag"] = '"' + "0" * 64 + '"'
        self.assertFalse(validate_library_history_report(value))
        value = deepcopy(fixtures["history"]); value["items"][0]["profile"] = {"private": True}
        self.assertFalse(validate_library_history_report(value))


class LibraryHTTPTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.service = library_fixture(Path(self.temp.name) / "library")
        self.provider = LibraryReportProvider(self.service, library_id=LIBRARY_ID, source="SYNTHETIC_TEST")
        self.token = secrets.token_hex(24)
        self.grant = LibraryReadGrant(LIBRARY_ID, frozenset({"library:read"}))
        self.server = make_server(0, library_provider=self.provider, library_authorizer=self.authorize)
        self.worker = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.worker.start()

    def tearDown(self):
        self.server.shutdown(); self.server.server_close(); self.worker.join(timeout=3)
        self.temp.cleanup()

    def authorize(self, credentials):
        return self.grant if credentials.authorization == f"Bearer {self.token}" else None

    def request(self, path="/api/v1/library", *, authenticated=True, headers=None, method="GET"):
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

    @staticmethod
    def detail_path(report, entry):
        return f"/api/v1/library/entries/{entry['entryId']}?view={report['viewId']}"

    @staticmethod
    def history_path(report, entry, after=0):
        return f"/api/v1/library/entries/{entry['entryId']}/history?view={report['viewId']}&after={after}"

    def test_catalog_draft_detail_history_share_view_without_mutation(self):
        before = files(self.service.store.root)
        with (patch.object(self.service, "validate_profile", side_effect=AssertionError("operational validation")),
              patch.object(self.service.store, "transaction", side_effect=AssertionError("write"))):
            status, report = self.request()
            self.assertEqual(status, 200); self.assertTrue(validate_library_report(report))
            self.assertEqual(report["totalCount"], 2)
            for entry in report["entries"]:
                status, detail = self.request(self.detail_path(report, entry))
                self.assertEqual(status, 200); self.assertTrue(validate_library_entry_report(detail))
                self.assertEqual(detail["entry"], entry)
                self.assertEqual(detail["viewId"], report["viewId"])
                self.assertEqual(entry["readiness"], "NOT_READY")
                if entry["kind"] == "REFERENCE_DRAFT":
                    self.assertEqual(len(detail["profile"]["sections"]), 15)
                    self.assertEqual(detail["profile"]["historyCount"], 2)
                    status, history = self.request(self.history_path(report, entry))
                    self.assertEqual(status, 200); self.assertTrue(validate_library_history_report(history))
                    self.assertEqual(history["etag"], entry["etag"])
                    self.assertEqual(history["items"][-1]["etag"], entry["etag"])
                else:
                    self.assertEqual(detail["catalog"]["fieldNoteCount"], 2)
                    self.assertFalse(detail["catalog"]["fieldNotesVerified"])
                    self.assertEqual(self.request(self.history_path(report, entry))[0], 409)
        self.assertEqual(files(self.service.store.root), before)

    def test_unauthorized_or_wrong_scope_never_invokes_provider(self):
        with patch.object(self.provider, "library_report", side_effect=AssertionError("must not read")) as read:
            self.assertEqual(self.request(authenticated=False)[0], 401)
            self.assertEqual(self.request(authenticated=False, headers={"X-User": "admin", "X-Authorized": "true"})[0], 401)
            for grant in (True, "admin", ReadGrant("session", {"session:read"}), LibraryReadGrant("other", {"library:read"})):
                self.grant = grant
                self.assertEqual(self.request()[0], 401)
            read.assert_not_called()
        self.assertEqual(self.request("/api/v1/status", authenticated=False)[0], 200)
        self.assertEqual(self.request("/api/v1/session")[0], 401)

    def test_authorization_is_separate_and_precedes_cursor_reads(self):
        _, report = self.request()
        entry = report["entries"][-1]
        self.grant = ReadGrant(LIBRARY_ID, {"session:read", "events:read"})
        with patch.object(self.provider._model, "capture", side_effect=AssertionError("must not capture")) as read:
            for path in (self.detail_path(report, entry), self.history_path(report, entry), f"/api/v1/library?view={report['viewId']}&after=0"):
                self.assertEqual(self.request(path)[0], 401)
            read.assert_not_called()
        for authorize in (None, lambda _: True):
            with self.assertRaises(AccessDenied):
                LibraryReadService(provider=self.provider, authorizer=authorize).library_report(Credentials())
        def broken(_):
            raise RuntimeError("private auth message")
        with self.assertRaises(AccessDenied):
            LibraryReadService(provider=self.provider, authorizer=broken).library_report(Credentials())
        with self.assertRaises(ReportUnavailable):
            LibraryReadService(authorizer=lambda _: LibraryReadGrant(LIBRARY_ID, {"library:read"})).library_report(Credentials())

    def test_changed_or_reverted_generation_rejects_previous_view(self):
        _, first = self.request()
        entry = next(e for e in first["entries"] if e["kind"] == "REFERENCE_DRAFT")
        original = self.service.get_draft(PROFILE_ID)
        changed = deepcopy(original["profile"]); changed["identity"]["aliases"] = ["private-alias-not-on-wire"]
        update = self.service.update_draft(PROFILE_ID, changed, original["etag"])
        for path in (self.detail_path(first, entry), self.history_path(first, entry), f"/api/v1/library?view={first['viewId']}&after=0"):
            self.assertEqual(self.request(path), (409, {"schema": "vision.api.error.v1", "code": "CURSOR_REJECTED"}))
        self.service.update_draft(PROFILE_ID, original["profile"], update["etag"])
        _, final = self.request()
        self.assertNotEqual(first["viewId"], final["viewId"])
        self.assertEqual(self.request(self.detail_path(first, entry))[0], 409)
        self.assertNotIn("private-alias", json.dumps(final))

    def test_real_catalog_and_history_pages_are_bounded_and_exact(self):
        record = self.service.catalog.list_records()[0]
        for n in range(51):
            self.service.catalog.register(replace(record, family=f"Family_{n:03}", profile_id=f"catalog_{n:03}"))
        draft = self.service.get_draft(PROFILE_ID)
        for _ in range(49):
            draft = self.service.update_draft(PROFILE_ID, draft["profile"], draft["etag"])
        status, first = self.request()
        self.assertEqual(status, 200); self.assertEqual(len(first["entries"]), 50)
        self.assertEqual(first["nextAfter"], 50)
        status, second = self.request(f"/api/v1/library?view={first['viewId']}&after=50")
        self.assertEqual(status, 200); self.assertEqual(second["nextAfter"], None)
        entries = first["entries"] + second["entries"]
        self.assertEqual(len(entries), first["totalCount"])
        self.assertEqual(len({e["entryId"] for e in entries}), len(entries))
        entry = next(e for e in entries if e["kind"] == "REFERENCE_DRAFT")
        status, history = self.request(self.history_path(first, entry))
        self.assertEqual(status, 200); self.assertEqual(len(history["items"]), 50)
        status, last = self.request(self.history_path(first, entry, 50))
        self.assertEqual(status, 200); self.assertEqual(len(last["items"]), 1)
        self.assertEqual(last["items"][-1]["etag"], entry["etag"])
        self.assertEqual(last["nextAfter"], None)
        for after in (1, 51, 100, 9999):
            self.assertEqual(self.request(self.history_path(first, entry, after))[0], 409)

    def test_corruption_and_provider_failure_publish_no_partial_or_private_data(self):
        with patch.object(self.provider._model, "capture", side_effect=RuntimeError("/private/library-root")):
            self.assertEqual(self.request(), (503, {"schema": "vision.api.error.v1", "code": "REPORT_UNAVAILABLE"}))
        oldest = self.service.store.read_snapshot()[0].history[0].snapshot_id
        (self.service.store.root / "history" / f"{PROFILE_ID}--{oldest}.json").unlink()
        before = files(self.service.store.root)
        self.assertEqual(self.request(), (503, {"schema": "vision.api.error.v1", "code": "REPORT_UNAVAILABLE"}))
        self.assertEqual(files(self.service.store.root), before)

    def test_exact_routes_origins_methods_and_noncreating_default_server(self):
        _, report = self.request()
        entry = report["entries"][-1]
        path = self.detail_path(report, entry)
        history = self.history_path(report, entry)
        for wrong in ("//api/v1/library", "/api/v1/library/", "/api/v1/library?after=0", path + "&debug=1",
                      path.replace("?view=", "?token="), history + "&after=0", history.replace("after=0", "after=00"),
                      f"/api/v1/library?after=0&view={report['viewId']}"):
            self.assertEqual(self.request(wrong)[0], 404)
        for method in ("POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"):
            self.assertEqual(self.request(path, method=method)[0], 405)
        self.assertEqual(self.request(path, headers={"Origin": "https://attacker.invalid"})[0], 403)
        self.assertEqual(self.request(path, headers={"Sec-Fetch-Site": "cross-site"})[0], 403)
        self.assertEqual(self.request(path, headers={"Authorization": "x" * 1025})[0], 400)
        with patch("vision_modules.ecu_library_backend.service.DraftStore", side_effect=AssertionError("no constructor")):
            with make_server(0) as default:
                with self.assertRaises(AccessDenied):
                    default.library_read_service.library_report(Credentials())

    def test_oversize_serialization_fails_before_headers_or_partial_body(self):
        _, report = self.request()
        report["entries"][0]["displayName"] = "x" * MAX_PROTECTED_BYTES
        with patch.object(self.provider, "library_report", return_value=report):
            self.assertEqual(self.request(), (503, {"schema": "vision.api.error.v1", "code": "REPORT_UNAVAILABLE"}))


if __name__ == "__main__":
    unittest.main()
