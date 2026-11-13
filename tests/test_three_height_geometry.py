"""Offline synthetic 34/50.4/101mm geometry; no hardware or reference fitting."""
import sys
import unittest
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parents[1]/"scripts/perception"
sys.path.insert(0,str(HERE))
from height_planes import estimate_height_planes
from analyze_three_height_oak import TARGETS, summary

K = np.array([[796.59625,0,634.99469],[0,796.7395,378.50885],[0,0,1.]])
REFS={"beige_box":34.0,"red_cylinder":50.4,"white_red_box":101.0}


def synthetic_scene():
    h,w=800,1280
    y,x=np.mgrid[:h,:w]
    z=np.full((h,w),.84,dtype=np.float32)
    # Two rectangular planar lids with independent sizes.
    z[190:310,490:609] -= .0340
    z[448:610,581:781] -= .1010
    # Cylinder cap and tapered sidewalls (an approximate stereo silhouette).
    rr=np.sqrt((x-460)**2+(y-350)**2)
    fraction=np.clip((38-rr)/10,0,1)
    z -= fraction*.0504
    rng=np.random.default_rng(13)
    z += rng.normal(0,.0006,z.shape).astype(np.float32)
    raw=np.clip(np.rint(z*1000),1,65535).astype(np.uint16)
    raw[rng.random((h,w))<.04]=0
    return raw


class ThreeHeightSyntheticTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.frame=synthetic_scene()

    def test_all_three_geometries_use_same_frame(self):
        for name,ref in REFS.items():
            with self.subTest(name=name):
                region=TARGETS[name]
                result=estimate_height_planes(
                    self.frame,K,region["object_roi_xyxy"],
                    region["table_roi_xyxy"],
                    min_relative_height_mm=18,max_relative_height_mm=150)
                self.assertEqual(result["validity"],
                                 "EXPLORATORY_UNVERIFIED_PROJECTION",
                                 (name,result["reason"]))
                self.assertLess(abs(result["height_mm"]-ref),2.5)
                self.assertEqual(result["coordinate_frame_robot_base"],"UNAVAILABLE")
                self.assertFalse(result["safety_function"])

    def test_bad_roi_returns_not_ready(self):
        r=estimate_height_planes(self.frame,K,(-1,0,40,40),(1,1,90,90))
        self.assertEqual(r["validity"],"NOT_READY")

    def test_aggregate_gate_detects_systematic_bias(self):
        samples=[
            {"validity":"EXPLORATORY_UNVERIFIED_PROJECTION",
             "height_mm":37.,
             "quality":{"top_inlier_count":120,"top_table_normal_angle_deg":3.0,
                        "top_rmse_mm":1.0,"table_rmse_mm":2.0,
                        "object_roi_valid_pct":94.0}}
            for _ in range(25)]
        score=summary(samples,25,34.0)
        self.assertEqual(score["accepted"],25)
        self.assertEqual(score["qa_gate"],"RESEARCH_GATE_FAIL")
        self.assertGreater(score["median_bias_mm"],1)

if __name__=="__main__":
    unittest.main()
