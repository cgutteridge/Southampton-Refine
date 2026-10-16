"""Tests for cross-zone report helpers."""
from __future__ import annotations

import unittest

from cross_zone import expanded_cell_bbox, neighbor_cells, parcels_on_cell_edge


class TestCrossZone(unittest.TestCase):
    def test_neighbor_cells(self):
        nb = neighbor_cells(48, -44, chebyshev=1)
        self.assertIn((48, -44), nb)
        self.assertIn((49, -44), nb)

    def test_expanded_bbox(self):
        x0, z0, x1, z1 = expanded_cell_bbox(48, -44, 8)
        base = expanded_cell_bbox(48, -44, 0)
        self.assertEqual(x0, base[0] - 8)
        self.assertEqual(x1, base[2] + 8)


if __name__ == '__main__':
    unittest.main()
