"""Unit tests for google_aerial tile maths and sheet."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import google_aerial as ga  # noqa: E402


class TestTiles(unittest.TestCase):
    def test_tile_float_matches_known_oakdene_tiles(self):
        # looked up by hand 2026-10-16: lat 50.931839, lon -1.395051
        for zoom, xy in ((18, (130056, 87838)), (19, (260112, 175677)), (20, (520224, 351354))):
            fx, fy = ga.tile_float(50.931839, -1.395051, zoom)
            self.assertEqual((int(fx), int(fy)), xy)

    def test_url_is_a_plain_tile(self):
        self.assertEqual(ga.tile_url(260112, 175677, 19), 'https://mt1.google.com/vt/lyrs=s&x=260112&y=175677&z=19')

    def test_cell_at_z19_is_a_handful_of_tiles(self):
        tx0, ty0, tx1, ty1 = ga.tile_range((6272, -5376, 6399, -5249), 19)
        self.assertIn(tx1 - tx0 + 1, (3, 4))
        self.assertIn(ty1 - ty0 + 1, (3, 4))

    def test_too_many_tiles_is_refused(self):
        with self.assertRaises(ValueError):
            ga.tile_range((6272, -5376, 6399, -5249), 21)


class TestGrid(unittest.TestCase):
    def test_lines_every_ten_blocks_inside_the_box(self):
        lines = ga.grid_lines((6354, -5302, 6404, -5252))
        xs = [ln['value'] for ln in lines if ln['axis'] == 'x']
        zs = [ln['value'] for ln in lines if ln['axis'] == 'z']
        self.assertEqual(xs, [6360, 6370, 6380, 6390, 6400])
        self.assertEqual(zs, [-5300, -5290, -5280, -5270, -5260])

    def test_sheet_has_every_tile_and_the_outline(self):
        page = ga.sheet_html((6354, -5302, 6404, -5252), 20, 't')
        tx0, ty0, tx1, ty1 = ga.tile_range((6354, -5302, 6404, -5252), 20)
        self.assertEqual(page.count('<img '), (tx1 - tx0 + 1) * (ty1 - ty0 + 1))
        self.assertIn('x6370', page)
        self.assertIn('<polygon', page)


if __name__ == '__main__':
    unittest.main()
