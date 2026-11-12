"""Synthetic-only perception geometry and validity tests, no DepthAI or NERO."""
from pathlib import Path
import sys
import unittest

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts/perception"))
from perception_engine import (deproject_depth, fit_plane, find_objects,
                               scene_change, observe_scene, FRAME)


def metadata(verified=True):
    return {
        "schema_version": "camera.frame_bundle.v1",
        "bundle_id": "test:1",
        "session_id": "test",
        "sync_state": "SYNCED",
        "capture_age_ms": 12,
        "rgb": {"frame_id": 10},
        "depth": {"frame_id": 12, "resolution": [160, 120],
                  "coordinate_frame": FRAME},
        "calibration": {"intrinsics": {
            "stereo_left_rectified_optical" if verified
                else "stereo_left_raw_optical": {
                "resolution": [160, 120],
                "K": [[150, 0, 80], [0, 150, 60], [0, 0, 1]],
            }
        }}
    }


class GeometryTests(unittest.TestCase):
    def setUp(self):
        self.depth = np.full((120, 160), 1000, dtype=np.uint16)
        self.k = np.asarray([[150, 0, 80], [0, 150, 60], [0, 0, 1]],
                            dtype=np.float64)

    def test_metric_projection_and_zero_invalid(self):
        self.depth[60, 80] = 750
        self.depth[0, 0] = 0
        pts, uv, fraction = deproject_depth(self.depth, self.k, stride=1)
        self.assertAlmostEqual(fraction, 1 - 1/19200)
        found = np.where((uv[:, 0] == 80) & (uv[:, 1] == 60))[0][0]
        np.testing.assert_allclose(pts[found], [0, 0, .75], rtol=1e-8)
        self.assertEqual(len(pts), 19199)

    def test_ransac_plane(self):
        pts, _, _ = deproject_depth(self.depth, self.k, stride=4)
        plane = fit_plane(pts)
        self.assertIsNotNone(plane)
        self.assertAlmostEqual(abs(plane["normal"][2]), 1.0, places=4)
        self.assertAlmostEqual(plane["inlier_fraction"], 1.0, places=3)
        self.assertLess(plane["residual_rmse_m"], .001)

    def test_unknown_object_and_change(self):
        previous = self.depth.copy()
        self.depth[30:85, 45:105] = 850
        observation = observe_scene(metadata(), self.depth, previous)
        self.assertEqual(observation["schema_version"],
                         "perception.scene_observation.v1")
        self.assertEqual(observation["validity"], "CAMERA_FRAME_ONLY")
        self.assertEqual(observation["robot_base_frame"]["status"], "UNAVAILABLE")
        self.assertGreaterEqual(len(observation["objects"]), 1)
        obj = observation["objects"][0]
        self.assertEqual(obj["class"], "unknown_object")
        self.assertEqual(obj["candidate_ecu"], "UNCONFIRMED")
        self.assertAlmostEqual(obj["position_camera_m"][2], .85, places=2)
        self.assertGreater(observation["change"]["changed_fraction"], .1)
        self.assertFalse(observation["safety_function"])

    def test_raw_intrinsics_are_experimental(self):
        observation = observe_scene(metadata(verified=False), self.depth)
        self.assertEqual(observation["validity"],
                         "EXPLORATORY_UNVERIFIED_PROJECTION")
        self.assertIn("RECTIFIED_DEPTH_INTRINSICS_NOT_VERIFIED",
                      observation["reasons"])

    def test_unsynced_or_stale_data_rejected(self):
        unsynced = metadata()
        unsynced["sync_state"] = "NOT_READY"
        self.assertEqual(observe_scene(unsynced, self.depth)["validity"],
                         "NOT_READY")
        stale = metadata()
        stale["capture_age_ms"] = 999
        self.assertEqual(observe_scene(stale, self.depth)["validity"],
                         "NOT_READY")
        self.assertIn("STALE_FRAME_BUNDLE",
                      observe_scene(stale, self.depth)["reasons"])
        self.assertNotEqual(observe_scene(stale, self.depth, replay=True)
                            ["validity"], "NOT_READY")

    def test_missing_optics_blocks_xyz(self):
        no_cal = metadata()
        no_cal["calibration"] = {"state": "UNAVAILABLE"}
        out = observe_scene(no_cal, self.depth)
        self.assertEqual(out["validity"], "NOT_READY")
        self.assertEqual(out["objects"], [])

    def test_sensor_bad_type_rejected(self):
        x = self.depth.astype(np.float32)
        self.assertEqual(observe_scene(metadata(), x)["validity"], "NOT_READY")
        with self.assertRaises(ValueError):
            deproject_depth(x, self.k)

    def test_missing_scene_baseline_not_assumed_safe(self):
        self.assertEqual(scene_change(self.depth, None)["state"],
                         "BASELINE_UNAVAILABLE")
        self.assertEqual(fit_plane(np.zeros((2, 3))), None)


if __name__ == "__main__":
    unittest.main()
