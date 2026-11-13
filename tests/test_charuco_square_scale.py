"""Offline checks for measured 29.5mm ChArUco square-size input."""
import sys
import unittest
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts/perception"))
from verify_charuco_scale import verify, BOARD_SQUARES, SQUARE_MM


class CharucoScaleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        ar=cv2.aruco
        d=ar.getPredefinedDictionary(ar.DICT_5X5_50)
        board=ar.CharucoBoard(BOARD_SQUARES,SQUARE_MM/1000,
                              .5*SQUARE_MM/1000,d)
        mono=board.generateImage((500,700),marginSize=20)
        cls.img=cv2.cvtColor(mono,cv2.COLOR_GRAY2BGR)
        cls.K=np.asarray([[900.,0,250.],[0,900.,350.],[0,0,1.]])

    def test_measured_square_propagates_to_nominal_dimensions(self):
        result=verify(self.img,self.K,29.5)
        self.assertEqual(result["board_outer_nominal_mm"],[147.5,206.5])
        self.assertGreaterEqual(result["charuco_corners_detected"],20)
        self.assertLess(result["homography_rms_px"],.8)
        self.assertFalse(result["metric_accuracy_certified"])
        self.assertEqual(result["depth_registration"],
                         "NOT_COMPUTED_NO_CROSS_CAMERA_EXTRINSICS")

    def test_missing_image_and_nonphysical_square_size(self):
        for square in (0,-1,float("nan")):
            with self.assertRaises(ValueError):
                verify(self.img,self.K,square)
        with self.assertRaises(ValueError):
            verify(None,self.K,29.5)

    def test_blank_image_never_creates_metric_pose(self):
        blank=np.ones_like(self.img)*255
        result=verify(blank,self.K,29.5)
        self.assertEqual(result["status"],"NOT_READY_INSUFFICIENT_CORNERS")
        self.assertFalse(result["metric_accuracy_certified"])

if __name__=="__main__":
    unittest.main()
