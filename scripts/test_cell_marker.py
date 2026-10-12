"""Unit tests for scripts/cell_marker.py (no Minecraft)."""
import unittest

import cell_marker as cm


class TestCellMarker(unittest.TestCase):
    """Perimeter and naming helpers."""

    def test_marker_name_negative_tz(self):
        """Negative tz encodes as m prefix."""
        self.assertEqual(cm.marker_name(48, -44), 'cell_marker_48_m44')

    def test_marker_name_positive_tz(self):
        """Non-negative tz stays numeric."""
        self.assertEqual(cm.marker_name(48, 3), 'cell_marker_48_3')

    def test_perimeter_count(self):
        """A 128 edge cell ring has 4*128 - 4 columns (corners once)."""
        cols = cm.perimeter_columns(48, -44)
        self.assertEqual(len(cols), 508)
        x0, z0, x1, z1 = 48 * 128, -44 * 128, 49 * 128 - 1, -43 * 128 - 1
        for x, z in cols:
            on_edge = x in (x0, x1) or z in (z0, z1)
            self.assertTrue(on_edge, (x, z))

    def test_perimeter_corners(self):
        """All four corners of the cell appear on the ring."""
        cols = set(cm.perimeter_columns(48, -44))
        x0, z0, x1, z1 = 48 * 128, -44 * 128, 49 * 128 - 1, -43 * 128 - 1
        for corner in ((x0, z0), (x1, z0), (x1, z1), (x0, z1)):
            self.assertIn(corner, cols)


if __name__ == '__main__':
    unittest.main()
