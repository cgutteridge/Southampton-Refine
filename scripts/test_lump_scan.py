#!/usr/bin/env python3
"""Unit tests for scripts/lump_scan.py (fake worlds, no Minecraft, no OSM).

  python3 -m unittest scripts/test_lump_scan.py
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import lump_scan as L  # noqa: E402


class FakeWorld:
    """{(x, z): [(y_lo, y_hi, block), ...]} columns; everything else is air."""

    def __init__(self, cols):
        self.cols = cols

    def block(self, x, y, z):
        for lo, hi, b in self.cols.get((x, z), []):
            if lo <= y <= hi:
                return b
        return 'minecraft:air'


def lump_world(x0, z0, w, d, roof=60, ground=55):
    """Pristine: ground + brick walls + carpet roof over a w x d box; plus flat ground around it."""
    cols = {}
    for x in range(x0 - 4, x0 + w + 4):
        for z in range(z0 - 4, z0 + d + 4):
            col = [(40, ground, 'minecraft:stone')]
            if x0 <= x < x0 + w and z0 <= z < z0 + d:
                col = [(40, roof - 1, 'minecraft:bricks'), (roof, roof, 'minecraft:light_gray_carpet')]
            cols[(x, z)] = col
    return cols


class LumpTest(unittest.TestCase):
    def setUp(self):
        self.cols = lump_world(10, 10, 6, 5)
        self.pristine = FakeWorld(self.cols)
        self.box = [(x, z) for x in range(0, 30) for z in range(0, 30)]

    def test_untouched_lump_found(self):
        lumps = L.find_lumps(self.box, FakeWorld(self.cols), self.pristine)
        self.assertEqual(len(lumps), 1)
        lp = lumps[0]
        self.assertEqual(lp['bbox'], [10, 10, 15, 14])
        self.assertEqual(lp['columns'], 30)
        self.assertEqual(lp['roof_y'], [60, 60])
        self.assertEqual(lp['height'], 5)

    def test_ground_recoloured_roof_is_still_a_lump(self):
        live = {k: list(v) for k, v in self.cols.items()}
        for x in range(10, 16):
            for z in range(10, 15):
                live[(x, z)] = [(40, 59, 'minecraft:bricks'), (60, 60, 'minecraft:granite_slab')]
        self.assertEqual(len(L.find_lumps(self.box, FakeWorld(live), self.pristine)), 1)

    def test_cleared_building_is_not_a_lump(self):
        live = {k: list(v) for k, v in self.cols.items()}
        for x in range(10, 16):
            for z in range(10, 15):
                live[(x, z)] = [(40, 55, 'minecraft:stone')]
        self.assertEqual(L.find_lumps(self.box, FakeWorld(live), self.pristine), [])

    def test_feature_columns_subtract(self):
        covered = {(x, z) for x in range(10, 16) for z in range(10, 15)}
        self.assertEqual(L.find_lumps(self.box, FakeWorld(self.cols), self.pristine, covered), [])
        # a build that missed one end leaves a remainder: 6 x 2 = 12 columns
        covered = {(x, z) for x in range(10, 16) for z in range(10, 13)}
        rest = L.find_lumps(self.box, FakeWorld(self.cols), self.pristine, covered)
        self.assertEqual([lp['columns'] for lp in rest], [12])

    def test_slivers_ignored(self):
        cols = lump_world(10, 10, 3, 3)
        self.assertEqual(L.find_lumps(self.box, FakeWorld(cols), FakeWorld(cols)), [])

    def test_exceptions_by_centre(self):
        lumps = L.find_lumps(self.box, FakeWorld(self.cols), self.pristine)
        L.apply_exceptions(lumps, [{'bbox': [0, 0, 5, 5], 'reason': 'x'}])
        self.assertNotIn('exception', lumps[0])
        L.apply_exceptions(lumps, [{'bbox': [9, 9, 16, 16], 'reason': 'ruin kept'}])
        self.assertEqual(lumps[0]['exception'], 'ruin kept')
        self.assertEqual(L.summary(lumps), {'remaining': 0, 'excepted': 1, 'unmapped': 0, 'no_clip': 0})

    def test_two_lumps_separate(self):
        cols = lump_world(2, 2, 5, 5)
        cols.update(lump_world(20, 20, 5, 5))
        lumps = L.find_lumps(self.box, FakeWorld(cols), FakeWorld(cols))
        self.assertEqual(len(lumps), 2)

    def test_lump_features_cluster_skip_taken_and_excepted(self):
        def lp(bbox, osm, **kw):
            return {'bbox': bbox, 'columns': 30, 'osm': osm, **kw}
        lumps = [lp([0, 0, 6, 6], []), lp([10, 0, 16, 6], ['w1']),      # one run (gap 4), one unmapped
                 lp([100, 0, 106, 6], ['w2']),                          # far: its own item, ref taken below
                 lp([200, 0, 206, 6], [], exception='ruin kept')]
        items = L.lump_features(lumps, taken_refs={'w2'})
        self.assertEqual(len(items), 1)
        it = items[0]
        self.assertEqual((it['kind'], it['refs'], it['bbox']), ('lumps', ['w1'], (0, 0, 16, 6)))
        self.assertIn('2 unrefined', it['label'])
        self.assertIn('1 not in OSM', it['label'])
        only_unmapped = L.lump_features([lp([0, 0, 6, 6], [])])
        self.assertEqual(only_unmapped[0]['refs'], ['unmapped'])


if __name__ == '__main__':
    unittest.main()
