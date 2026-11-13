"""Integration without camera: optical metadata and diagnostic ROI endpoint."""
from http.server import ThreadingHTTPServer
from urllib.error import HTTPError
from urllib.request import urlopen
from pathlib import Path
import importlib.util
import json
import sys
import threading
import unittest

import cv2
import depthai as dai
import numpy as np

OAK = Path(__file__).resolve().parents[1] / "scripts/camera/oak"
sys.path.insert(0, str(OAK))
spec = importlib.util.spec_from_file_location("camera_service_optics_test",
                                              OAK / "camera_service_prod.py")
camera = importlib.util.module_from_spec(spec)
spec.loader.exec_module(camera)


class FakeFrame:
    def __init__(self, transformation):
        self.transform = transformation
    def getTransformation(self):
        return self.transform


class OpticalServiceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.state = camera.State("balanced")
        cls.state.start("UsbSpeed.SUPER")
        arr = np.full((480, 640, 3), 100, dtype=np.uint8)
        ok, jpeg = cv2.imencode(".jpg", arr)
        assert ok
        cls.state.publish("rgb", jpeg.tobytes())
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), camera.Handler)
        cls.server.state = cls.state
        cls.server.stop_event = threading.Event()
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.url = "http://127.0.0.1:" + str(cls.server.server_port)

    @classmethod
    def tearDownClass(cls):
        cls.server.stop_event.set()
        cls.state.stop()
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=2)

    def test_01_valid_output_transform_is_provisional(self):
        k = [[500.,0,320],[0,500,240],[0,0,1.]]
        fake = FakeFrame(dai.ImgTransformation(640,480,k))
        self.state.record_optics("depth", fake, 640,480)
        cal = self.state.calibration
        self.assertEqual(cal["depth_projection_status"],
                         "FRAME_TRANSFORM_REPORTED_UNVERIFIED")
        self.assertTrue(self.state.optics_captured["depth"])
        self.assertEqual(cal["intrinsics"]["stereo_left_rectified_optical"]["K"], k)
        with urlopen(self.url + "/api/status", timeout=3) as r:
            status = json.load(r)
        self.assertEqual(status["depth_projection_status"],
                         "FRAME_TRANSFORM_REPORTED_UNVERIFIED")

    def test_02_valid_digital_zoom_is_bounded(self):
        with urlopen(self.url +
                "/snapshot/rgb-roi.jpg?x=0.25&y=0.25&w=0.5&h=0.5", timeout=3) as r:
            payload = r.read()
        image = cv2.imdecode(np.frombuffer(payload, dtype=np.uint8),
                             cv2.IMREAD_COLOR)
        self.assertEqual(image.shape,(240,320,3))
        with self.assertRaises(HTTPError) as bad:
            urlopen(self.url +
                "/snapshot/rgb-roi.jpg?x=0.8&y=0.2&w=0.5&h=0.5", timeout=3)
        self.assertEqual(bad.exception.code,400)
        bad.exception.close()

    def test_03_missing_roi_and_synthetic_loss(self):
        with self.assertRaises(HTTPError) as bad:
            urlopen(self.url + "/snapshot/rgb-roi.jpg", timeout=3)
        self.assertEqual(bad.exception.code,400)
        bad.exception.close()
        self.state.fail("simulated USB disconnect")
        self.assertFalse(self.state.status()["online"])
        with self.assertRaises(HTTPError) as bad2:
            urlopen(self.url +
                "/snapshot/rgb-roi.jpg?x=0.1&y=0.1&w=0.5&h=0.5", timeout=3)
        self.assertEqual(bad2.exception.code, 503)
        bad2.exception.close()


if __name__ == "__main__":
    unittest.main()
