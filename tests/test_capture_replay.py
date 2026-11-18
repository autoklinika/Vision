"""Offline-only regression tests. Synthetic depth, no hardware or recordings."""
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts" / "replay"))
from check_capture import inspect_capture


class CaptureTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.depth = np.full((4, 8, 12), 750, dtype=np.uint16)
        self.k = np.array([[796.596, 0, 635], [0, 796.739, 378.5], [0, 0, 1]], dtype=float)
        self.times = np.array([100, 200, 300, 400], dtype=np.int64)
        self.manifest = {
            "schema_version": "vision.capture-baseline.v1",
            "session_id": "SYNTHETIC-TEST-ONLY",
            "capture": {"format": "npz-raw16-v1", "file": "synthetic.npz"},
            "expected": {"frames": 4, "depth_hw": [8, 12], "depth_dtype": "uint16",
                         "declared_optical_frame": "stereo_left_rectified_optical",
                         "K": [796.596, 796.739, 635, 378.5], "K_tolerance_px": 0.2},
            "quality": {"valid_depth_mm": [250, 2000], "min_valid_fraction": 0.95},
        }
        self.write_capture()

    def tearDown(self):
        self.tmp.cleanup()

    def write_capture(self):
        p = self.root / "synthetic.npz"
        np.savez_compressed(p, depth_mm=self.depth, K=self.k, device_timestamp_ns=self.times)
        self.manifest["capture"]["sha256"] = hashlib.sha256(p.read_bytes()).hexdigest()
        (self.root / "manifest.json").write_text(json.dumps(self.manifest))

    def check(self):
        return inspect_capture(self.root / "manifest.json", self.root)

    def test_good_frozen_capture(self):
        self.assertEqual(self.check()["status"], "PASS")

    def test_detect_resolution_regression(self):
        self.depth = self.depth[:, ::2, ::2]
        self.write_capture()
        self.assertIn("FRAME_COUNT_OR_RESOLUTION_REGRESSION", self.check()["errors"])

    def test_detect_hash_mutation(self):
        with (self.root / "synthetic.npz").open("ab") as f:
            f.write(b"tampered")
        self.assertIn("CAPTURE_HASH_MISMATCH", self.check()["errors"])

    def test_detect_calibration_regression(self):
        self.k[0, 0] += 15
        self.write_capture()
        self.assertIn("INTRINSICS_REGRESSION", self.check()["errors"])

    def test_detect_timestamp_regression(self):
        self.times[2] = 100
        self.write_capture()
        self.assertIn("TIMESTAMPS_NONMONOTONIC", self.check()["errors"])

    def test_detect_invalid_depth(self):
        self.depth.fill(0)
        self.write_capture()
        self.assertIn("DEPTH_COVERAGE_BELOW_BASELINE", self.check()["errors"])

    def test_refuse_absolute_path(self):
        self.manifest["capture"]["file"] = str(self.root / "synthetic.npz")
        (self.root / "manifest.json").write_text(json.dumps(self.manifest))
        self.assertIn("CAPTURE_PATH_UNSAFE_OR_INVALID", self.check()["errors"])

    def test_refuse_parent_traversal(self):
        self.manifest["capture"]["file"] = "../synthetic.npz"
        (self.root / "manifest.json").write_text(json.dumps(self.manifest))
        self.assertIn("CAPTURE_PATH_UNSAFE_OR_INVALID", self.check()["errors"])

    def test_missing_calibration_fails_closed(self):
        p = self.root / "synthetic.npz"
        np.savez_compressed(p, depth_mm=self.depth)
        self.manifest["capture"]["sha256"] = hashlib.sha256(p.read_bytes()).hexdigest()
        (self.root / "manifest.json").write_text(json.dumps(self.manifest))
        self.assertIn("REQUIRED_ARRAYS_MISSING", self.check()["errors"])


if __name__ == "__main__":
    unittest.main()
