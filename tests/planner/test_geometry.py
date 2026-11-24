"""Numerical invariants of predicted footprints, using synthetic optics only."""
import math
from types import SimpleNamespace
import unittest

from vision_core.models import GateError
from vision_planner.geometry import (footprint_polygon, inscribed_rectangle,
                                     project_point, rotate)


def optics():
    return SimpleNamespace(fx=100.0, fy=100.0, cx=100.0, cy=100.0,
                           usable_image_xywh_px=(0, 0, 200, 200))


class OpticalGeometryTests(unittest.TestCase):
    def test_nadir_rectangle_has_exact_metric_dimensions(self):
        polygon = footprint_polygon((10, 20, 100), (1, 0, 0, 0), optics(), 0)
        self.assertEqual(inscribed_rectangle(polygon), (-90, -80, 200, 200))
        self.assertEqual(project_point((10, 20, 100), (1, 0, 0, 0), (10, 20, 0), optics()), (100, 100))

    def test_plane_height_and_offcentre_intrinsics(self):
        c = optics(); c.cx = 80; c.cy = 60
        polygon = footprint_polygon((0, 0, 100), (1, 0, 0, 0), c, 50)
        self.assertEqual(inscribed_rectangle(polygon), (-40, -70, 100, 100))

    def test_translation_preserves_size(self):
        a = inscribed_rectangle(footprint_polygon((0, 0, 100), (1, 0, 0, 0), optics(), 0))
        b = inscribed_rectangle(footprint_polygon((50, 75, 120), (1, 0, 0, 0), optics(), 20))
        self.assertEqual((b[0]-a[0], b[1]-a[1]), (50, 75))
        self.assertEqual(a[2:], b[2:])

    def test_rotated_footprint_never_claims_bounding_box(self):
        # A 45-degree image roll produces a diamond; its bounding box includes
        # uncovered corners. Every reported rectangle corner must stay inside.
        angle = math.pi/8
        q = (math.cos(angle), math.sin(angle), 0, 0)
        polygon = footprint_polygon((0, 0, 100), q, optics(), 0)
        x, y, width, height = inscribed_rectangle(polygon)
        self.assertAlmostEqual(width, 100*math.sqrt(2))
        self.assertAlmostEqual(height, 100*math.sqrt(2))
        self.assertLess(width, max(v[0] for v in polygon)-min(v[0] for v in polygon))
        self.assert_corners_inside((x, y, width, height), polygon)

    def assert_corners_inside(self, rect, polygon):
        x, y, width, height = rect
        for point in ((x,y),(x+width,y),(x+width,y+height),(x,y+height)):
            for a,b in zip(polygon,polygon[1:]+polygon[:1]):
                self.assertGreaterEqual((b[0]-a[0])*(point[1]-a[1])-(b[1]-a[1])*(point[0]-a[0]), -1e-8)

    def test_oblique_rectangle_is_inside_all_four_half_planes(self):
        # Tilt a down-facing camera 10 degrees around its optical Y axis.
        angle = math.radians(5)
        q = (math.cos(angle), 0, math.sin(angle), 0)
        polygon = footprint_polygon((0, 0, 100), q, optics(), 0)
        self.assert_corners_inside(inscribed_rectangle(polygon), polygon)
        self.assertNotAlmostEqual(polygon[1][1]-polygon[0][1], 0)

    def test_backwards_and_horizon_crossing_views_fail(self):
        for q in ((0,0,0,1), (0,math.sqrt(.5),0,math.sqrt(.5))):
            with self.subTest(q=q), self.assertRaises(GateError):
                footprint_polygon((0,0,100),q,optics(),0)
        with self.assertRaises(GateError):
            project_point((0,0,100),(0,0,0,1),(0,0,0),optics())

    def test_degenerate_and_nonconvex_polygon_fail(self):
        for polygon in (((0,0),(0,0),(1,1),(0,1)), ((0,0),(1,1),(1,0),(0,1)),
                        ((0,0),(2,0),(1,.1),(0,2))):
            with self.subTest(polygon=polygon), self.assertRaises(GateError):
                inscribed_rectangle(polygon)

    def test_nonfinite_and_nonunit_rotations_fail(self):
        for q in ((0,0,0,2),(0,0,math.nan,1),(False,0,0,1)):
            with self.subTest(q=q), self.assertRaises(GateError): rotate(q,(1,2,3))
