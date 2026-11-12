"""Offline smoke tests: no DepthAI import, no camera, no robot hardware."""
import importlib.util
import json
from http.server import ThreadingHTTPServer
from pathlib import Path
import threading
import unittest
from urllib.error import HTTPError
from urllib.request import urlopen


SCRIPT = Path(__file__).resolve().parents[1] / "scripts/camera/oak/browser_preview.py"
SPEC = importlib.util.spec_from_file_location("oak_browser_preview", SCRIPT)
mod = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(mod)


class PreviewStateTests(unittest.TestCase):
    def test_status_requires_both_fresh_streams(self):
        state = mod.PreviewState()
        self.assertFalse(state.status()["online"])
        state.start("UsbSpeed.HIGH")
        state.publish("rgb", b"jpeg-rgb")
        self.assertFalse(state.status()["online"])
        state.publish("depth", b"jpeg-depth", valid_pct=65.3)
        self.assertTrue(state.status()["online"])
        self.assertEqual(state.status()["depth_valid_pct"], 65.3)
        self.assertEqual(state.next_frame("rgb", 0, timeout=0), (1, b"jpeg-rgb"))
        state.fail("X_LINK_ERROR")
        self.assertFalse(state.status()["online"])
        self.assertIsNone(state.next_frame("rgb", 1, timeout=0))
        self.assertEqual(state.status()["error"], "X_LINK_ERROR")

    def test_rejects_empty_or_unknown_stream(self):
        state = mod.PreviewState()
        with self.assertRaises(ValueError):
            state.publish("rgb", b"")
        with self.assertRaises(ValueError):
            state.publish("thermal", b"image")


class PreviewHTTPTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.state = mod.PreviewState()
        cls.state.fail("CAMERA_BUSY")
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), mod.PreviewHandler)
        cls.server.state = cls.state
        cls.server.stop_event = threading.Event()
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.base = f"http://127.0.0.1:{cls.server.server_port}"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=2)

    def test_html_status_and_security_headers(self):
        with urlopen(self.base + "/", timeout=3) as response:
            html = response.read().decode("utf-8")
            self.assertIn("OAK-D Pro AF", html)
            self.assertIn("no-store", response.headers["Cache-Control"])
            self.assertIn("default-src 'none'", response.headers["Content-Security-Policy"])
        with urlopen(self.base + "/api/status", timeout=3) as response:
            data = json.load(response)
        self.assertEqual(data["error"], "CAMERA_BUSY")
        self.assertFalse(data["online"])

    def test_absent_camera_does_not_fake_mjpeg(self):
        with self.assertRaises(HTTPError) as ex:
            urlopen(self.base + "/stream/rgb.mjpg", timeout=3)
        self.assertEqual(ex.exception.code, 503)

    def test_unknown_endpoint(self):
        with self.assertRaises(HTTPError) as ex:
            urlopen(self.base + "/control/robot", timeout=3)
        self.assertEqual(ex.exception.code, 404)


if __name__ == "__main__":
    unittest.main()
