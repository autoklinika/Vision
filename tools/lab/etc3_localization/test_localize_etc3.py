import unittest
import numpy as np
import cv2
import localize_etc3_rgbd as m

class LocalizationTests(unittest.TestCase):
    def setUp(self): self.K=np.array([[1000.,0,100],[0,1000.,100],[0,0,1]])
    def test_deprojection(self): np.testing.assert_allclose(m.deproject(110,120,1000,self.K),[10,20,1000])
    def test_warp_translation(self): np.testing.assert_allclose(m.warp([[1,2]],np.array([[1.,0,3],[0,1,4]])),[[4,6]])
    def test_warp_rotation(self): np.testing.assert_allclose(m.warp([[1,0]],np.array([[0.,-1,0],[1,0,0]])),[[0,1]])
    def test_depth_outlier(self): self.assertEqual(m.robust_keep([750,751,750,752,749,751,750,841]).tolist(),[True]*7+[False])
    def test_invalid_depth(self): self.assertEqual(m.robust_keep([0,750,751,750,750,9999]).tolist(),[False,True,True,True,True,False])
    def test_insufficient_depth_fails_closed(self): self.assertFalse(m.robust_keep([750,0,0,0]).any())
    def test_patch_valid_median(self): self.assertEqual(m.patch_depth(np.full((30,30),750,np.uint16),[15,15]),750)
    def test_patch_insufficient_fails(self): self.assertIsNone(m.patch_depth(np.zeros((30,30),np.uint16),[15,15]))
    def test_plane_with_outliers(self):
        rng=np.random.default_rng(1); xy=rng.uniform(-100,100,(3000,2)); z=800+.02*xy[:,0]+rng.normal(0,.5,3000); p=np.column_stack([xy,z]); p[:300,2]+=40
        plane=m.fit_plane(p); self.assertIsNotNone(plane); self.assertGreater(plane['inlier_fraction'],.85); self.assertLess(plane['rms_mm'],1); self.assertLess(plane['holdout_p95_mm'],45)
    def test_plane_too_few(self): self.assertIsNone(m.fit_plane(np.zeros((100,3))))
    def test_plane_degenerate(self): self.assertIsNone(m.fit_plane(np.zeros((3000,3))))
    def test_blank_affine_fails(self): self.assertIsNone(m.affine_match(np.zeros((1080,1920),np.uint8),np.zeros((1080,1920),np.uint8)))
    def test_segmentation_empty_fails(self):
        d=np.zeros((200,200),np.uint16); plane={'normal':[0,0,-1],'d_mm':800}; seg,h=m.segment(d,self.K,plane,np.array([[20,20],[180,20],[180,180],[20,180]]),[100,100],12); self.assertIsNone(seg); self.assertIsNone(h)
    def test_segment_measured_height(self):
        d=np.full((200,200),800,np.uint16); d[50:150,50:150]=780; plane={'normal':[0,0,-1],'d_mm':800}; seg,h=m.segment(d,self.K,plane,np.array([[20,20],[180,20],[180,180],[20,180]]),[100,100],12); self.assertIsNotNone(seg); self.assertAlmostEqual(seg['height_median_mm'],20); self.assertEqual(seg['status'],'PROVISIONAL_INCOMPLETE_OR_OCCLUDED')
if __name__=='__main__': unittest.main()
