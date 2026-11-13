"""Synthetic plane separation tests. Offline only: no USB, CAN, NN, motors."""
import sys
import unittest
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parents[1] / "scripts/perception"
sys.path.insert(0, str(HERE))
from height_planes import estimate_height_planes, evaluate_reference_gate

K = np.asarray([[796.59625, 0, 634.99469],
                [0, 796.7395, 378.50885],
                [0, 0, 1.]])
OBJECT_BOX=(410,312,510,388)
TABLE_BOX=(280,240,640,495)


def scene(height_mm=50.4, tilt=0., seed=12, dropout=.1, with_object=True):
    """Ray-plane intersections with physically parallel tabletop / top cap.

    Outer cylindrical annulus simulates an oblique sidewall; within ROI top
    has missing stereo points, 0.8 mm noise, and random uncorrelated invalids.
    """
    rng=np.random.default_rng(seed)
    y,x=np.mgrid[:800,:1280]
    r_x=(x-K[0,2])/K[0,0]
    r_y=(y-K[1,2])/K[1,1]
    # plane n·X + d = 0, n oriented toward camera
    n=np.asarray([.03,.08,-.9963])
    n=n/np.linalg.norm(n)
    base_d=.80
    t=-base_d/(n[0]*r_x+n[1]*r_y+n[2])
    center=(460,350)
    radial=np.sqrt((x-center[0])**2+(y-center[1])**2)
    if with_object:
        # Disk radius 29 px, raised sidewall between 29..38 pixels.
        effective_height=height_mm/1000
        fraction=np.clip((38-radial)/9,0,1)
        h=effective_height*fraction
        # Optionally tilt upper plane deliberately beyond gate.
        h += (x-center[0])*tilt/1000*(radial<29)
        t=(base_d-h)/(base_d/np.maximum(t,1e-6))
    t=np.maximum(t,.01)
    t += rng.normal(0,.0008,t.shape)
    depth=np.clip(np.rint(t*1000),0,65535).astype(np.uint16)
    if dropout:
        holes=rng.random(depth.shape)<dropout
        depth[holes]=0
    return depth


class HeightPlanesTests(unittest.TestCase):
    def calc(self, depth, **kw):
        return estimate_height_planes(depth, K, OBJECT_BOX,TABLE_BOX,**kw)

    def test_parallel_planes_with_sidewalls_and_holes(self):
        d=scene(50.4)
        result=self.calc(d)
        self.assertEqual(result["validity"],
                         "EXPLORATORY_UNVERIFIED_PROJECTION",str(result))
        self.assertLess(abs(result["height_mm"]-50.4),2.0)
        self.assertLess(result["quality"]["top_table_normal_angle_deg"],14)
        self.assertEqual(result["coordinate_frame_robot_base"],"UNAVAILABLE")
        self.assertFalse(result["safety_function"])

    def test_nonparallel_cap_fails_closed(self):
        result=self.calc(scene(50.4,tilt=.6))
        self.assertEqual(result["validity"],"NOT_READY")
        self.assertEqual(result["reason"],"TOP_NOT_RELIABLY_PARALLEL")
        self.assertGreater(result["quality"]["top_table_normal_angle_deg"],14)

    def test_no_object_fails_closed(self):
        res=self.calc(scene(with_object=False))
        self.assertEqual(res["validity"],"NOT_READY")
        self.assertIsNone(res["height_mm"])

    def test_missing_depth_fails_closed(self):
        d=np.zeros((800,1280),dtype=np.uint16)
        res=self.calc(d)
        self.assertEqual(res["validity"],"NOT_READY")
        self.assertIsNone(res["height_mm"])

    def test_camera_intrinsics_and_depth_type(self):
        d=scene()
        bad=np.zeros((3,3))
        r=estimate_height_planes(d,bad,OBJECT_BOX,TABLE_BOX)
        self.assertEqual(r["validity"],"NOT_READY")
        self.assertEqual(r["reason"],"INVALID_INTRINSICS_OR_ROI")
        self.assertEqual(self.calc(d.astype(np.float32))["reason"],
                         "DEPTH_U16_REQUIRED")
        self.assertEqual(self.calc(d,top_fraction=.05)["reason"],
                         "INVALID_ESTIMATOR_SETTINGS")

    def test_roi_out_of_bounds(self):
        d=scene()
        r=estimate_height_planes(d,K,(-1,0,4,4),TABLE_BOX)
        self.assertEqual(r["reason"],"INVALID_INTRINSICS_OR_ROI")

    def test_height_change_reflected_without_ground_truth_input(self):
        a=self.calc(scene(35.,seed=20))
        b=self.calc(scene(60.,seed=20))
        self.assertEqual(a["validity"],"EXPLORATORY_UNVERIFIED_PROJECTION")
        self.assertEqual(b["validity"],"EXPLORATORY_UNVERIFIED_PROJECTION")
        self.assertGreater(b["height_mm"]-a["height_mm"],18.)

    def test_gate_refuses_biased_IR_measurement(self):
        stats={"attempted":31,"usable":31,"height_mm_median":47.136,
               "height_mm_sample_std":1.163,
               "height_mm_p05":45.413,"height_mm_p95":48.829}
        gate=evaluate_reference_gate(stats,50.4)
        self.assertFalse(gate["research_target_pass"])
        self.assertIn("SYSTEMATIC_BIAS_TOO_LARGE",gate["reasons"])
        self.assertFalse(gate["metrology_certified"])
        self.assertFalse(gate["robot_ready"])

    def test_gate_pass_still_requires_real_calibration(self):
        stats={"attempted":50,"usable":49,"height_mm_median":50.6,
               "height_mm_sample_std":.4,
               "height_mm_p05":49.9,"height_mm_p95":51.1}
        gate=evaluate_reference_gate(stats,50.4)
        self.assertTrue(gate["research_target_pass"])
        self.assertEqual(gate["status"],"RESEARCH_GATE_PASS_ONLY")
        self.assertFalse(gate["metrology_certified"])
        self.assertFalse(gate["robot_ready"])

    def test_gate_rejects_invalid_reference_or_sparse_data(self):
        with self.assertRaises(ValueError):
            evaluate_reference_gate({},0)
        bad=evaluate_reference_gate({"attempted":50,"usable":4},50.4)
        self.assertFalse(bad["research_target_pass"])
        self.assertIn("INSUFFICIENT_FRAMES",bad["reasons"])

if __name__=="__main__":
    unittest.main()
