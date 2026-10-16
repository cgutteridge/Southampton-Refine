"""Unit tests for scripts/cell_marker.py (no Minecraft)."""
import tempfile
import unittest
from pathlib import Path

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

    def test_wool_hazard_tape_alternate(self):
        """Colours alternate every block along the closed ring."""
        self.assertEqual(cm.wool_along_perimeter(0), 'black_wool')
        self.assertEqual(cm.wool_along_perimeter(1), 'yellow_wool')
        self.assertEqual(cm.wool_along_perimeter(2), 'black_wool')
        ring = cm.perimeter_columns(48, -44)
        self.assertEqual(len({cm.wool_along_perimeter(i) for i in range(len(ring))}), 2)

    def test_is_air(self):
        """Only air variants are replaceable."""
        self.assertTrue(cm.is_air('minecraft:air'))
        self.assertFalse(cm.is_air('minecraft:stone'))

    def test_marker_y_band_legacy_bumps(self):
        """Legacy teardown scans HEIGHT_ABOVE through +LEGACY_BUMP_MAX."""
        ys = list(cm.marker_y_band(60))
        self.assertEqual(ys[0], 60 + cm.HEIGHT_ABOVE)
        self.assertEqual(len(ys), cm.LEGACY_BUMP_MAX + 1)

    def test_clear_positions_sweeps_orphan_corner_wool(self):
        """Perimeter wool outside the registry (legacy Y) is still cleared."""
        tx, tz = 48, -44
        x0, z0, _, _ = cm.cell_bounds(tx, tz)
        base = 60
        y_ring = base + cm.HEIGHT_ABOVE
        y_legacy = y_ring + 2
        corner = (x0, y_legacy, z0)
        registry = {f'{x0},{y_ring},{z0}': 'black_wool'}

        class StubWorld:
            def ground(self, x, z):
                return base

            def block(self, x, y, z):
                if (x, y, z) == corner:
                    return 'minecraft:yellow_wool'
                key = f'{x},{y},{z}'
                return 'minecraft:black_wool' if key in registry else 'minecraft:air'

        found = cm._clear_positions(tx, tz, StubWorld(), registry)
        self.assertIn(corner, found)
        self.assertIn((x0, y_ring, z0), found)


class TestFocusFile(unittest.TestCase):
    """CURRENT-CELL.json guards (temp dirs, no Minecraft)."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        tmp = Path(self._tmp.name)
        self._old = (cm.CURRENT_FILE, cm.OUT)
        cm.CURRENT_FILE = tmp / 'CURRENT-CELL.json'
        cm.OUT = tmp
        self.out = tmp

    def tearDown(self):
        cm.CURRENT_FILE, cm.OUT = self._old
        self._tmp.cleanup()

    def test_no_file_means_no_focus(self):
        self.assertIsNone(cm.read_current())

    def test_write_and_release(self):
        cm.write_current((48, -46))
        self.assertEqual(cm.read_current(), (48, -46))
        cm.write_current(None)
        self.assertIsNone(cm.read_current())

    def test_raise_refused_when_other_cell_holds_focus(self):
        cm.write_current((48, -45))
        self.assertIn('--clear 48,-45', cm.check_can_raise((48, -46)))
        self.assertIsNone(cm.check_can_raise((48, -45)))

    def test_raise_refused_with_stray_registry(self):
        (self.out / 'cell_marker_47_m44-cells.json').write_text('{}')
        self.assertEqual(cm.registered_cells(), [(47, -44)])
        self.assertIn('47,-44', cm.check_can_raise((49, -45)))
        self.assertIsNone(cm.check_can_raise((47, -44)))

    def test_registry_parse_positive_tz(self):
        (self.out / 'cell_marker_3_5-cells.json').write_text('{}')
        self.assertEqual(cm.registered_cells(), [(3, 5)])

    def test_clear_of_stray_refused_without_flag(self):
        cm.write_current((48, -46))
        self.assertEqual(cm.cmd_clear(47, -44, True), 2)


if __name__ == '__main__':
    unittest.main()
