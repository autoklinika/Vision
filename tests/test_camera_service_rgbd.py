"""Offline public API tests of coherent RGB-D bundles (no physical device)."""
from http.server import ThreadingHTTPServer
from urllib.error import HTTPError
from urllib.request import urlopen
from pathlib import Path
import importlib.util
import json
import sys
import threading
import time
import unittest
import numpy as np

DIR = Path(__file__).resolve().parents[1] / "scripts/camera/oak"
sys.path.insert(0, str(DIR))
spec = importlib.util.spec_from_file_location("camera_service_rgbd_test",
                                               DIR / "camera_service_prod.py")
camera = importlib.util.module_from_spec(spec)
spec.loader.exec_module(camera)
from camera_sync import decode_replay_npz


class RgbdApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.st = camera.State("balanced")
        cls.st.start("UsbSpeed.SUPER")
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), camera.Handler)
        cls.server.state = cls.st
        cls.server.stop_event = threading.Event()
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.url = "http://127.0.0.1:" + str(cls.server.server_port)

    @classmethod
    def tearDownClass(cls):
        cls.server.stop_event.set()
        cls.st.stop()
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=2)

    def test_01_not_ready_when_no_pair(self):
        with self.assertRaises(HTTPError) as c:
            urlopen(self.url + "/api/frame-bundle/latest", timeout=2)
        self.assertEqual(c.exception.code, 503)
        c.exception.close()

    def test_02_bundle_metadata_and_lossless_snapshot(self):
        raw = np.full((4, 6), 1400, dtype=np.uint16)
        raw[0, 0] = 0
        jpeg = b"\xff\xd8synthetic\xff\xd9"
        self.st.publish("rgb", jpeg)
        self.st.publish_depth(raw)
        now = time.monotonic_ns()
        self.st.ingest_packet("rgb", jpeg, 10, 2_000_000_000,
                              6, 4, now)
        self.st.ingest_packet("depth", raw, 20, 2_003_000_000,
                              6, 4, now)
        with urlopen(self.url + "/api/frame-bundle/latest", timeout=3) as r:
            meta = json.load(r)
            self.assertEqual(meta["schema_version"], "camera.frame_bundle.v1")
            self.assertEqual(meta["pairing_delta_ms"], 3)
            self.assertEqual(meta["sync_state"], "SYNCED")
            self.assertIsNone(meta["extrinsics_id"])
            self.assertEqual(meta["transform_status"]["table"], "UNAVAILABLE")
        with urlopen(self.url + "/snapshot/frame-bundle.npz", timeout=3) as r:
            archive = r.read()
        restored_meta, restored_jpeg, restored_depth = decode_replay_npz(archive)
        self.assertEqual(meta["bundle_id"], restored_meta["bundle_id"])
        self.assertEqual(restored_jpeg, jpeg)
        np.testing.assert_array_equal(restored_depth, raw)
        self.assertEqual(self.st.status()["rgbd_sync"]["paired_count"], 1)

    def test_03_usb_failure_invalidates_output(self):
        self.st.fail("simulated USB loss")
        with self.assertRaises(HTTPError) as c:
            urlopen(self.url + "/snapshot/frame-bundle.npz", timeout=3)
        self.assertEqual(c.exception.code, 503)
        c.exception.close()
        self.assertFalse(self.st.status()["online"])


if __name__ == "__main__":
    unittest.main()
