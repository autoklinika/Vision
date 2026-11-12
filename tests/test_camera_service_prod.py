"""No-hardware production Camera Service checks."""
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import urlopen
import importlib.util
import json
import threading
import unittest
import numpy as np
import cv2

SCRIPT=Path(__file__).resolve().parents[1]/"scripts/camera/oak/camera_service_prod.py"
import sys
sys.path.insert(0, str(SCRIPT.parent))
spec=importlib.util.spec_from_file_location("camera_service_prod", SCRIPT)
camera=importlib.util.module_from_spec(spec)
spec.loader.exec_module(camera)

class StateTests(unittest.TestCase):
    def test_profiles_and_initial_status(self):
        self.assertEqual(set(camera.PROFILES),{"balanced","detail","near"})
        st=camera.State("balanced")
        self.assertFalse(st.status()["online"])
        self.assertEqual(st.status()["raw_depth_unit"],"millimetres")

    def test_two_frames_and_failure(self):
        st=camera.State("detail")
        st.start("UsbSpeed.SUPER")
        st.publish("rgb",b"jpeg")
        st.publish("depth",b"jpeg2")
        d=np.full((800,1280),np.uint16(900))
        st.publish_depth(d)
        self.assertTrue(st.status()["online"])
        self.assertEqual(st.status()["depth_resolution"],(800,1280))
        self.assertEqual(st.next_frame("rgb",0,timeout=0),(1,b"jpeg"))
        self.assertIsNone(st.next_frame("rgb",1,timeout=0.01))
        copy=st.raw_depth()
        copy[0,0]=100
        self.assertEqual(int(st.raw_depth()[0,0]),900)
        st.fail("X_LINK_ERROR")
        self.assertFalse(st.status()["online"])
        self.assertIsNone(st.next_frame("rgb",0,timeout=0.01))


class ApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.st=camera.State("balanced")
        cls.st.start("UsbSpeed.SUPER")
        cls.st.publish("rgb",b"jpeg-data")
        cls.st.publish("depth",b"depth-jpeg")
        cls.st.publish_depth(np.full((800,1280),np.uint16(1234)))
        cls.st.chip_C=47.3
        cls.server=ThreadingHTTPServer(("127.0.0.1",0),camera.Handler)
        cls.server.state=cls.st
        cls.server.stop_event=threading.Event()
        cls.thread=threading.Thread(target=cls.server.serve_forever,daemon=True)
        cls.thread.start()
        cls.url=f"http://127.0.0.1:{cls.server.server_port}"

    @classmethod
    def tearDownClass(cls):
        cls.server.stop_event.set()
        cls.st.stop()
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=2)

    def test_html_and_api(self):
        with urlopen(self.url+"/",timeout=3) as r:
            self.assertIn(b"Camera Service",r.read())
            self.assertIn("no-store",r.headers["Cache-Control"])
        with urlopen(self.url+"/api/status",timeout=3) as r:
            data=json.load(r)
            self.assertTrue(data["online"])
            self.assertEqual(data["profile"],"balanced")
            self.assertEqual(data["depth_resolution"],[800,1280])

    def test_heartbeat_and_404(self):
        with urlopen(self.url+"/healthz",timeout=3) as r:
            self.assertEqual(r.status,200)
        with self.assertRaises(HTTPError) as ex:
            urlopen(self.url+"/control/robot",timeout=3)
        self.assertEqual(ex.exception.code,404)
        ex.exception.close()

    def test_snapshots(self):
        with urlopen(self.url+"/snapshot/rgb.jpg",timeout=3) as r:
            self.assertEqual(r.read(),b"jpeg-data")
        with urlopen(self.url+"/snapshot/depth-mm.png",timeout=3) as r:
            encoded=np.frombuffer(r.read(),np.uint8)
            restored=cv2.imdecode(encoded,cv2.IMREAD_UNCHANGED)
        self.assertEqual(restored.dtype,np.uint16)
        self.assertEqual(restored.shape,(800,1280))
        self.assertEqual(int(restored[0,0]),1234)

    def test_multi_client_mjpeg(self):
        for k in ("rgb","depth"):
            for _ in range(2):
                with urlopen(self.url+f"/stream/{k}.mjpg",timeout=3) as r:
                    self.assertIn("multipart/x-mixed-replace",r.headers["Content-Type"])
                    self.assertEqual(r.readline(),b"--frame\r\n")
                    self.assertEqual(r.readline(),b"Content-Type: image/jpeg\r\n")
                    size_line=r.readline()
                    self.assertTrue(size_line.startswith(b"Content-Length: "))
                    self.assertEqual(r.readline(),b"\r\n")
                    n=int(size_line.split(b":",1)[1].strip())
                    self.assertIn(r.read(n), (b"jpeg-data",b"depth-jpeg"))

if __name__=="__main__":
    unittest.main()
