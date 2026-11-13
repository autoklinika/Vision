"""Top-face segmentation validation on synthetic scenes; no camera access."""
from pathlib import Path
import sys
import unittest

import numpy as np

DIR=Path(__file__).resolve().parents[1]/"scripts/perception"
sys.path.insert(0,str(DIR))
from top_surface import segment_top_surface


K=np.array([[600.,0,160],[0,600,120],[0,0,1.]])
ROI=(105,65,215,175)
TABLE=(50,15,270,225)


def scene(height_mm=50., kind="disk", dropout=.12, seed=13):
    rng=np.random.default_rng(seed)
    yy,xx=np.mgrid[0:240,0:320]
    h=np.zeros((240,320),dtype=np.float64)
    if kind=="disk":
        dist=np.hypot(xx-160,yy-120)
        h=height_mm*np.clip((35-dist)/9,0,1)
        top=(dist<26)
    elif kind=="box":
        u=np.minimum(xx-115,205-xx)
        v=np.minimum(yy-80,160-yy)
        h=height_mm*np.clip(np.minimum(u,v)/8,0,1)
        top=(u>=8)&(v>=8)
    else:
        raise ValueError(kind)
    z=900.-h+rng.normal(0,.35,size=h.shape)
    depth=np.clip(np.rint(z),0,65535).astype(np.uint16)
    bad=rng.random(size=depth.shape)<dropout
    depth[bad & (h>1)]=0
    return depth,top


class TopSurfaceTests(unittest.TestCase):
    def test_box_plateau_not_sidewalls(self):
        depth,top=scene(101,kind="box")
        out=segment_top_surface(depth,K,ROI,TABLE)
        m=out.metadata
        self.assertEqual(m["validity"],"EXPLORATORY_UNVERIFIED_PROJECTION")
        self.assertLess(abs(m["height_mm"]-101),1.5)
        self.assertTrue(m["top_mask_pixel_count"]>200)
        yy,xx=np.where(out.mask)
        self.assertGreater((top[ROI[1]:ROI[3],ROI[0]:ROI[2]][yy,xx]).mean(),.80)
        self.assertEqual(m["robot_base_frame"],"UNAVAILABLE")
        self.assertFalse(m["metrology_verified"])
        self.assertFalse(m["safety_function"])

    def test_small_circular_cap_with_missing_pixels(self):
        depth,top=scene(34,kind="disk",dropout=.22)
        out=segment_top_surface(depth,K,ROI,TABLE)
        self.assertEqual(out.metadata["validity"],"EXPLORATORY_UNVERIFIED_PROJECTION")
        self.assertLess(abs(out.metadata["height_mm"]-34),1.5)
        self.assertGreater(out.metadata["top_mask_pixel_count"],80)
        selected=out.mask
        self.assertGreater(
            (top[ROI[1]:ROI[3],ROI[0]:ROI[2]]&selected).sum()/selected.sum(),.7)

    def test_unstable_surface_refuses_numeric_height(self):
        depth,top=scene(50,kind="disk",dropout=.20)
        rng=np.random.default_rng(55)
        original=depth[top].astype(np.float32)
        depth[top]=np.clip(
            np.rint(original+rng.normal(0,10,len(original))),
            1,60000).astype(np.uint16)
        out=segment_top_surface(depth,K,ROI,TABLE)
        self.assertEqual(out.metadata["validity"],"NOT_READY")
        self.assertEqual(out.metadata["reason"],"UNSTABLE_TOP_SURFACE")
        self.assertIsNone(out.metadata["height_mm"])
        self.assertIsNotNone(out.metadata["quality"]["candidate_height_mm"])
        self.assertFalse(out.metadata["metrology_verified"])

    def test_no_table_points_fails_closed(self):
        depth,_=scene()
        depth[:,:]=0
        out=segment_top_surface(depth,K,ROI,TABLE)
        self.assertEqual(out.metadata["validity"],"NOT_READY")
        self.assertEqual(out.metadata["reason"],"INSUFFICIENT_TABLE_POINTS")
        self.assertFalse(out.mask.any())

    def test_empty_foreground_fails_closed(self):
        depth=np.full((240,320),900,dtype=np.uint16)
        out=segment_top_surface(depth,K,ROI,TABLE)
        self.assertEqual(out.metadata["validity"],"NOT_READY")
        self.assertEqual(out.metadata["reason"],"INSUFFICIENT_FOREGROUND")
        self.assertFalse(out.mask.any())

    def test_intrinsics_and_roi_weak_contract_refused(self):
        depth,_=scene()
        with self.assertRaises(ValueError):
            segment_top_surface(depth,np.eye(2),ROI,TABLE)
        with self.assertRaises(ValueError):
            segment_top_surface(depth,K,(300,1,400,120),TABLE)
        with self.assertRaises(ValueError):
            segment_top_surface(depth,K,(10.5,1,100,120),TABLE)


if __name__=="__main__":
    unittest.main()
