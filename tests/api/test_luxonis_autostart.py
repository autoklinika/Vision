"""Offline supervisor policy tests; no ROS, USB or real process commands."""
import importlib.util
from pathlib import Path
import tempfile
from types import SimpleNamespace as NS
import unittest

MODULE = Path(__file__).resolve().parents[2] / "scripts/deploy/vision_luxonis_supervisor.py"
spec = importlib.util.spec_from_file_location("luxonis_supervisor", MODULE)
s = importlib.util.module_from_spec(spec)
spec.loader.exec_module(s)


class CameraSupervisorTests(unittest.TestCase):
    def test_independent_deadlines_and_startup_grace(self):
        w = s.StreamWatch(100)
        self.assertFalse(w.expired(159.9))
        self.assertTrue(w.expired(160))
        w.seen("rgb", 159, 1)
        w.seen("depth", 159, 1)
        self.assertFalse(w.expired(160))
        w.seen("rgb", 190, 2)
        w.seen("depth", 190, 1)  # repeated frame must not renew liveness
        self.assertTrue(w.expired(190))
        w.seen("depth", 190, 2)
        self.assertFalse(w.expired(190))

    def test_passive_usb_inventory_and_reenumeration(self):
        with tempfile.TemporaryDirectory() as path:
            root = Path(path)
            self.assertIsNone(s.camera_count(root))
            (root/"usb1").mkdir()
            self.assertEqual(s.camera_count(root), 0)
            entry = root/"1-1"
            entry.mkdir()
            (entry/"idVendor").write_text("03e7")
            for product in ("2485", "f63b", "f63c"):
                (entry/"idProduct").write_text(product)
                self.assertEqual(s.camera_count(root), 1)
            (entry/"idProduct").unlink()
            self.assertEqual(s.camera_count(root), 0)

    def test_frame_layout_not_depth_scene_content(self):
        header = NS(stamp=NS(sec=100,nanosec=0))
        depth = NS(header=header,width=2,height=2,step=4,encoding="16UC1",data=bytes(8))
        self.assertTrue(s.valid_frame(depth,"depth"))
        self.assertFalse(s.valid_frame(depth,"rgb"))
        depth.data = bytes(7)
        self.assertFalse(s.valid_frame(depth,"depth"))

    def test_unit_scope(self):
        unit = MODULE.with_name("vision-luxonis.service").read_text()
        for text in ("Restart=always", "RestartSec=15", "WantedBy=default.target",
                     "Environment=ROS_DOMAIN_ID=186", "Environment=ROS_LOCALHOST_ONLY=1",
                     "KillMode=mixed", "ExecStartPre=/usr/bin/mountpoint -q /srv/vision-data"):
            self.assertIn(text, unit)
        self.assertNotIn("Requires=vision-nero", unit)
        self.assertNotIn("Wants=vision-nero", unit)
