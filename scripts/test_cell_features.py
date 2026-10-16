"""Unit tests for cell_features and handoff ring order."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'scripts'))

import cell_features as cf  # noqa: E402
import site_handoff as sh  # noqa: E402


class TestCellFeatures(unittest.TestCase):
    def test_layer_builds_are_not_features(self):
        for n in ('highfield_49_m43_ground', 'highfield_48_m44_trees_undo',
                  'highfield_grounds_mc', 'cell_marker_48_m44', 'highfield_48_m45_foliage'):
            self.assertFalse(cf.is_feature_build(n), n)
        for n in ('highfield_b35', 'highfield_engineering', 'chamberlain_rd_8_58'):
            self.assertTrue(cf.is_feature_build(n), n)

    def test_split_runs_joins_neighbours_only(self):
        a = {'bbox': (0, 0, 8, 8)}
        b = {'bbox': (14, 0, 22, 8)}
        c = {'bbox': (100, 0, 108, 8)}
        runs = cf._split_runs([a, b, c])
        self.assertEqual(sorted(len(g) for g in runs), [1, 2])

    def test_ring_order(self):
        self.assertEqual(sh.ring_cells(1), [(48, -45), (49, -45), (49, -44), (49, -43),
                                            (48, -43), (47, -43), (47, -44), (47, -45)])
        self.assertEqual(len(set(sh.ring_cells(2))), 16)


if __name__ == '__main__':
    unittest.main()
