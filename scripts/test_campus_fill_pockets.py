"""Unit tests for campus._fill_pockets (LIDAR-noise holes inside a building footprint; no Minecraft).

  python3 -m unittest scripts/test_campus_fill_pockets.py
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import campus  # noqa: E402


def square(x0, z0, n):
    return {(x, z) for x in range(x0, x0 + n) for z in range(z0, z0 + n)}


class TestFillPockets(unittest.TestCase):
    def test_speckle_is_filled_with_nearest_band(self):
        cells = square(0, 0, 12)
        holes = {(3, 3), (6, 7), (8, 2), (9, 9)}          # single-cell LIDAR noise
        solid = cells - holes
        band = {q: 55 for q in solid}
        filled = campus._fill_pockets(cells, solid, band, 5)
        self.assertEqual(set(filled), holes)
        self.assertEqual(set(filled.values()), {55})

    def test_real_courtyard_is_kept(self):
        cells = square(0, 0, 20)
        court = square(6, 6, 8)                           # 8x8 clear square holds a 5x5
        solid = cells - court
        band = {q: 66 for q in solid}
        self.assertEqual(campus._fill_pockets(cells, solid, band, 5), {})

    def test_thin_open_strip_is_filled(self):
        cells = square(0, 0, 14)
        strip = {(x, 6) for x in range(2, 12)}            # 1 wide: no 5x5
        solid = cells - strip
        band = {q: 54 for q in solid}
        self.assertEqual(set(campus._fill_pockets(cells, solid, band, 5)), strip)


if __name__ == '__main__':
    unittest.main()
