"""Synthetic and actual loopback tests; no Vision hardware or private data."""
import http.client
import json
from pathlib import Path
import threading
import unittest
from unittest.mock import patch

from vision_api.server import make_server, MAX_RESPONSE_BYTES
from vision_api.status import boot_status, validate_boot_status

ROOT = Path(__file__).resolve().parents[2]
CONTRACT = ROOT / "contracts" / "vision-api" / "v1"
FIXTURES = json.loads((CONTRACT / "status-fixtures.json").read_text())


class ContractTests(unittest.TestCase):
    def test_shared_fixtures(self):
        self.assertTrue(validate_boot_status(FIXTURES["valid"]))
        for case in FIXTURES["invalid"]:
            with self.subTest(case=case["name"]):
                self.assertFalse(validate_boot_status(case["value"]))

    def test_schema_and_generated_report(self):
        schema = json.loads((CONTRACT / "status.schema.json").read_text())
        status = boot_status()
        self.assertEqual(set(schema["required"]), set(status))
        self.assertFalse(schema["additionalProperties"])
        for key, prop in schema["properties"].items():
            if "const" in prop:
                self.assertEqual(status[key], prop["const"])
        self.assertTrue(validate_boot_status(status))


class HTTPTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = make_server(0)
        cls.worker = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.worker.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.worker.join(timeout=3)

    def request(self, method="GET", path="/api/v1/status", headers=None):
        with_connection = http.client.HTTPConnection("127.0.0.1", self.server.server_port, timeout=4)
        try:
            with_connection.request(method, path, headers=headers or {})
            response = with_connection.getresponse()
            raw = response.read(MAX_RESPONSE_BYTES + 1)
            self.assertLessEqual(len(raw), MAX_RESPONSE_BYTES)
            self.assertEqual(response.getheader("Cache-Control"), "no-store")
            self.assertEqual(response.getheader("Content-Type"), "application/json; charset=utf-8")
            self.assertIsNone(response.getheader("Access-Control-Allow-Origin"))
            self.assertIsNone(response.getheader("Location"))
            return response.status, json.loads(raw) if raw else None, response.getheader("Allow")
        finally:
            with_connection.close()

    def error(self, expected, reason, *args, **kwargs):
        status, value, allow = self.request(*args, **kwargs)
        self.assertEqual(status, expected)
        self.assertEqual(value, {"schema": "vision.api.error.v1", "code": reason})
        self.assertEqual(allow, "GET" if expected == 405 else None)

    def test_real_http_response(self):
        status, value, _ = self.request()
        self.assertEqual(self.server.server_address[0], "127.0.0.1")
        self.assertEqual(status, 200)
        self.assertTrue(validate_boot_status(value))

    def test_exact_path_only(self):
        for target in ("/", "/api/v2/status", "/api/v1/status?x=1", "//api/v1/status", "/api/v1/status/", "/etc/passwd"):
            with self.subTest(target=target):
                self.error(404, "NOT_FOUND", path=target)

    def test_methods_never_dispatch(self):
        for method in ("POST", "PUT", "PATCH", "DELETE", "OPTIONS", "TRACE", "CONNECT", "CUSTOM"):
            with self.subTest(method=method):
                self.error(405, "METHOD_NOT_ALLOWED", method=method)
        status, value, allow = self.request("HEAD")
        self.assertEqual((status, value, allow), (405, None, "GET"))

    def test_host_origin_and_body_rejected(self):
        self.error(403, "HOST_REJECTED", headers={"Host": "untrusted.test"})
        self.error(403, "ORIGIN_REJECTED", headers={"Origin": "https://untrusted.test"})
        self.error(403, "ORIGIN_REJECTED", headers={"Sec-Fetch-Site": "cross-site"})
        self.error(400, "BAD_REQUEST", headers={"Content-Length": "1"})
        self.error(400, "BAD_REQUEST", headers={"Transfer-Encoding": "chunked"})
        status, value, _ = self.request(headers={"Origin": f"http://127.0.0.1:{self.server.server_port}"})
        self.assertEqual(status, 200)
        self.assertTrue(validate_boot_status(value))

    def test_provider_errors_sanitized(self):
        with patch("vision_api.server.boot_status", side_effect=RuntimeError("private detail")):
            self.error(500, "INTERNAL_ERROR")
        with patch("vision_api.server.boot_status", return_value={"bad": "private detail"}):
            self.error(500, "INTERNAL_ERROR")


if __name__ == "__main__":
    unittest.main()
