#!/usr/bin/env python3
"""Unit tests for scripts/tree_review.py (synthetic height maps, no Minecraft).

  python3 -m unittest scripts/test_tree_review.py
"""
import sys
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import lidar_heightmap as L  # noqa: E402
import tree_review as T  # noqa: E402


def hmap(trees, x0=0, z0=0, ground=55):
    """128x128 height map with a cone-topped tree at each (i, j, height): kind TREE, h = ground + height."""
    n = 128
    h = np.full((n, n), ground, dtype=np.int16)
    base = np.full((n, n), ground, dtype=np.int16)
    kind = np.zeros((n, n), dtype=np.uint8)
    for i, j, ht in trees:
        for di in range(-2, 3):
            for dj in range(-2, 3):
                d = max(abs(di), abs(dj))
                h[i + di, j + dj] = ground + max(1, ht - d)
                kind[i + di, j + dj] = L.TREE
    return {'x0': x0, 'z0': z0, 'h': h, 'base': base, 'roof': np.zeros((n, n), dtype=np.int16), 'kind': kind}


class ReviewTest(unittest.TestCase):
    def verdicts(self, live, pri):
        return sorted((r['verdict'], tuple(r['centre'])) for r in T.review_cell(hmap(live), hmap(pri)))

    def test_matching_crowns_are_ok(self):
        self.assertEqual(self.verdicts([(20, 20, 10)], [(21, 20, 11)]), [('ok', (21, 20))])

    def test_lidar_crown_without_live_is_missing_with_distance(self):
        rows = T.review_cell(hmap([]), hmap([(40, 40, 12)]))
        self.assertEqual([(r['verdict'], r['live_leaf_dist']) for r in rows], [('MISSING', None)])

    def test_live_crown_without_lidar_is_invented(self):
        self.assertEqual(self.verdicts([(60, 60, 12)], []), [('INVENTED', (60, 60))])

    def test_height_difference_is_low_or_high(self):
        self.assertEqual(self.verdicts([(20, 20, 4)], [(20, 20, 12)])[0][0], 'LOW')
        self.assertEqual(self.verdicts([(20, 20, 16)], [(20, 20, 8)])[0][0], 'HIGH')

    def test_shrubs_below_min_peak_are_ignored(self):
        self.assertEqual(self.verdicts([], [(30, 30, 2)]), [])

    def test_marks_skip_ok_and_cover_a_patch(self):
        rows = [{'centre': [10, 10], 'verdict': 'ok'}, {'centre': [20, 20], 'verdict': 'MISSING'}]
        m = T.marks(rows)
        self.assertEqual(len(m), 9)
        self.assertTrue(all(c == '#ff0000' for _x, _z, c in m))

    def test_zone_cells(self):
        self.assertEqual(T.cells_for_zone(6150, -5787, 6349, -5583), [(48, -46), (49, -46), (48, -45), (49, -45), (48, -44), (49, -44)])


if __name__ == '__main__':
    unittest.main()
