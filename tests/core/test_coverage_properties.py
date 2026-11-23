"""Deterministic geometric consistency tests against integer-cell reference."""
import random
import unittest
from vision_core.repeatability import _areas, MAX_FOOTPRINTS


def raster(rectangles):
    tiles=set()
    for x1,y1,x2,y2 in rectangles:
        tiles.update((x,y) for x in range(x1,x2) for y in range(y1,y2))
    return tiles


class CoverageProperties(unittest.TestCase):
    def test_rectangle_unions_match_independent_integer_raster(self):
        rng=random.Random(20261123)
        for case in range(120):
            regions=[]
            captures=[]
            for group, total in ((regions,rng.randrange(1,8)), (captures,rng.randrange(1,8))):
                for _ in range(total):
                    x1=rng.randrange(-5,8)
                    y1=rng.randrange(-5,8)
                    x2=x1+rng.randrange(1,6)
                    y2=y1+rng.randrange(1,6)
                    group.append((x1,y1,x2,y2))
            denominator,intersection=_areas(regions,captures)
            expected=raster(regions)
            observed=raster(captures)
            with self.subTest(case=case):
                self.assertEqual(denominator,len(expected))
                self.assertEqual(intersection,len(expected & observed))
                self.assertLessEqual(intersection,denominator)

    def test_coverage_rejects_excess_footprints_before_processing(self):
        from vision_core import GateError
        good=[(0,0,5,5)]
        oversized=[(i,0,i+1,1) for i in range(MAX_FOOTPRINTS+1)]
        with self.assertRaises(GateError):
            _areas(good,oversized)
