#!/usr/bin/env python3
"""Unit tests for geo.py helpers (no gdal / Minecraft required).

  python3 -m unittest scripts/test_geo.py
"""
from __future__ import annotations

import math
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import geo  # noqa: E402
from terrace import BROADLANDS_N_SLOPE  # noqa: E402


class ConvertMcTest(unittest.TestCase):
    def test_mc_osgb_roundtrip(self):
        rec = geo.coord_triple_from_mc(5652, -2492)
        self.assertTrue(rec['in_bounds'])
        self.assertEqual(rec['mc']['x'], 5652)
        e, n = rec['osgb']['easting'], rec['osgb']['northing']
        back = geo.coord_triple_from_osgb(e, n)
        self.assertEqual(back['mc']['x'], 5652)
        self.assertEqual(back['mc']['z'], -2492)


class SlopeTest(unittest.TestCase):
    def test_bearing_broadlands(self):
        rec = geo.slope_from_bearing(22)
        self.assertEqual(tuple(rec['slope'].values()), BROADLANDS_N_SLOPE)

    def test_points_rear_to_front(self):
        rec = geo.slope_from_points(7100, -5500, 7103, -5509)
        self.assertEqual((rec['slope']['dx'], rec['slope']['dz']), (1, -3))

    def test_pitch_near_forty_five(self):
        rec = geo.pitch_deg_to_slope(40)
        self.assertLess(rec['delta_deg'], 6)


class ViewTest(unittest.TestCase):
    def test_north_look(self):
        rec = geo.view_from_heading(100.0, 70.0, -200.0, 0.0, distance=10.0)
        self.assertAlmostEqual(rec['look'][0], 100.0)
        self.assertAlmostEqual(rec['look'][2], -210.0)

    def test_east_look(self):
        rec = geo.view_from_heading(0.0, 64.0, 0.0, 90.0, distance=10.0)
        self.assertAlmostEqual(rec['look'][0], 10.0, places=5)
        self.assertAlmostEqual(rec['look'][2], 0.0, places=5)


class SurveyTest(unittest.TestCase):
    def test_terrace_bbox_contains_centre(self):
        rec = geo.survey_bbox(7097, -5521, 'terrace')
        x0, z0, x1, z1 = geo.parse_bbox(rec['bbox_mc'])
        self.assertLessEqual(x0, 7097)
        self.assertGreaterEqual(x1, 7097)
        self.assertLessEqual(z0, -5521)
        self.assertGreaterEqual(z1, -5521)


class DoorFacingTest(unittest.TestCase):
    def test_toward_south(self):
        self.assertEqual(geo.door_facing_toward(0, 5), 'south')


if __name__ == '__main__':
    unittest.main()
