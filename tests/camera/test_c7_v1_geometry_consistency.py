"""Synthetic image-registration accuracy check, requires the isolated camera venv (OpenCV SIFT)."""
import importlib.util
import unittest
from pathlib import Path
import cv2
import numpy as np

ROOT=Path(__file__).resolve().parents[2]
P=ROOT/"scripts/lab/c7_v1_geometry_consistency_audit.py"
spec=importlib.util.spec_from_file_location("c7_v1_geometry_consistency_audit",str(P))
lib=importlib.util.module_from_spec(spec)
spec.loader.exec_module(lib)

class CameraGeometryConsistencySynthetic(unittest.TestCase):
    @staticmethod
    def textured_scene():
        # Deterministic static features on mounting-plate ROI, not user data.
        a=np.zeros((1080,1920,3),dtype=np.uint8)
        rng=np.random.default_rng(20261120)
        for _ in range(420):
            x=int(rng.integers(258,526));y=int(rng.integers(220,632))
            cv2.circle(a,(x,y),int(rng.integers(1,4)),
                       tuple(int(v) for v in rng.integers(90,255,size=3)),-1)
        return a

    def test_known_one_point_eight_percent_zoom_recovered(self):
        image=self.textured_scene()
        factor=1.018
        # An affine zoom around an arbitrary static image center.
        center=np.array([400.,430.],float)
        dx=(1-factor)*center
        warp=np.array([[factor,0,dx[0]],[0,factor,dx[1]]],dtype=np.float32)
        transformed=cv2.warpAffine(image,warp,(1920,1080))
        result=lib.affine_align(image,transformed)
        self.assertGreaterEqual(result["inliers"],20)
        self.assertAlmostEqual(result["scale_change_pct"],1.8,delta=.22)
        self.assertLess(abs(result["rotation_deg"]),0.3)

    def test_exact_static_image_has_unit_scale(self):
        a=self.textured_scene()
        result=lib.affine_align(a,a.copy())
        self.assertGreaterEqual(result["inliers"],30)
        self.assertAlmostEqual(result["scale_ratio"],1.0,delta=.00001)
        self.assertLess(result["inlier_rmse_px"],.01)

if __name__=="__main__":unittest.main()
