#!/usr/bin/env python3
"""Unit tests for terrace plot slopes (no world / OSM access).

  python3 -m unittest scripts/test_terrace.py
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from terrace import BROADLANDS_N_SLOPE, House, Terrace, line_x, passage_xs, snap_slope  # noqa: E402


def _terrace(houses, slope=(0, -1)):
    return Terrace(None, houses, None, lambda x: -5520, lambda x: -5580,
                   (houses[0].pw, houses[-1].pe), plot_slope=slope)


class SlopeTest(unittest.TestCase):
    def test_snap_broadlands_is_one_in_three(self):
        # OSM long edge, about 22° east of north.
        self.assertEqual(snap_slope(4.5, -11.1), (1, -3))
        self.assertEqual(BROADLANDS_N_SLOPE, (1, -3))

    def test_snap_axes_and_diagonals(self):
        self.assertEqual(snap_slope(0, -10), (0, -1))
        self.assertEqual(snap_slope(10, -10), (1, -1))
        self.assertEqual(snap_slope(10, -1), (1, 0))
        self.assertEqual(snap_slope(-1, -4), (-1, -4))

    def test_line_steps_in_runs_of_three(self):
        # depth 0,1,2 stay; 3,4,5 step once; 6 steps twice.
        self.assertEqual([line_x(100, -50, z, (1, -3)) for z in range(-50, -57, -1)],
                         [100, 100, 100, 101, 101, 101, 102])
        self.assertEqual(line_x(100, -50, -40, (1, -3)), 100)  # street side of the anchor

    def test_axis_aligned_span_matches_the_squared_house(self):
        houses = [House('a', 0, 4, -10, 28, 'W'), House('b', 4, 9, -8, 28, 'E')]
        t = _terrace(houses)
        self.assertEqual(list(t.span(houses[0], -30)), list(range(0, 4)))
        self.assertEqual(list(t.span(houses[1], -30)), list(range(4, 10)))

    def test_shared_line_does_not_overlap_or_gap(self):
        houses = [House(str(i), 5 * i, 5 * i + 5, -20 - i, 28, 'W') for i in range(4)]
        t = _terrace(houses, (1, -3))
        for z in range(-25, -60, -1):
            cols = []
            for h in houses:
                cols.extend(t.span(h, z))
            self.assertEqual(len(cols), len(set(cols)))
            self.assertEqual(sorted(cols), list(range(min(cols), max(cols) + 1)))

    def test_stepped_fences_join_edge_to_edge(self):
        # Fence posts only connect N/S/E/W, so each step needs an overlapping post.
        houses = [House(str(i), 5 * i, 5 * i + 5, -20 - i, 28, 'W') for i in range(3)]
        t = _terrace(houses, (1, -3))
        for h in houses:
            lines = [lambda z, h=h: t._bound_x(h, z, 'W')]
            if h is houses[-1]:
                lines.append(lambda z, h=h: t._bound_x(h, z, 'E'))
            for line in lines:
                cells = {(x, z) for z in range(-35, -60, -1) for x in range(-5, 40)
                         if t._on_fence_line(h, x, z) and abs(x - line(z)) <= 1}
                for z in range(-36, -59, -1):
                    a, b = (line(z), z), (line(z - 1), z - 1)
                    self.assertIn(a, cells)
                    joined = (a[0], b[1]) in cells or (b[0], a[1]) in cells or a[0] == b[0]
                    self.assertTrue(joined, (h.no, a, b))
                for x, z in cells:
                    self.assertIn(x, t.span(h, z))

    def test_broadlands_passages_stay_open(self):
        # Surveyed fronts / party columns (26-36, 14-24, 2-12).
        h26 = House('26', 7086, 7090, -5538, 27, 'E')
        h24 = House('24', 7092, 7097, -5535, 26, 'E')
        h14 = House('14', 7115, 7120, -5526, 26, 'W')
        h12 = House('12', 7122, 7126, -5523, 25, 'E')
        for z in range(-5530, -5590, -1):
            g1 = list(passage_xs(z, h26.pe, h26.f - 11, h24.pw, h24.f - 11, (1, -3)))
            g2 = list(passage_xs(z, h14.pe, h14.f - 11, h12.pw, h12.f - 11, (1, -3)))
            self.assertGreaterEqual(len(g1), 1, z)
            self.assertGreaterEqual(len(g2), 1, z)
            self.assertLessEqual(len(g1), 4, z)
            self.assertLessEqual(len(g2), 4, z)


if __name__ == '__main__':
    unittest.main()
