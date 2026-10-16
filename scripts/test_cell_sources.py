"""Unit tests for cell_sources helpers."""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'scripts'))

import cell_sources as cs  # noqa: E402
from ground_sources import cell_coverage  # noqa: E402


class TestCellSources(unittest.TestCase):
    """Path and parse helpers."""

    def test_parse_cell(self):
        self.assertEqual(cs.parse_cell('48,-44'), (48, -44))
        self.assertEqual(cs.parse_cell(' -1 , 2 '), (-1, 2))

    def test_sources_path(self):
        p = cs.sources_path(48, -44)
        self.assertEqual(p.name, '48_-44-SOURCES.txt')
        self.assertEqual(p.parent.name, 'cells')


class TestAttempts(unittest.TestCase):
    """Attempt ledger blocks blind repeats."""

    def setUp(self):
        self._orig = cs.CELLS
        self._tmp = tempfile.TemporaryDirectory()
        cs.CELLS = Path(self._tmp.name)

    def tearDown(self):
        cs.CELLS = self._orig
        self._tmp.cleanup()

    def test_repeat_needs_reason(self):
        cs.record_attempt(1, 2, 'rightmove', 'none', 'no exteriors')
        with self.assertRaises(SystemExit):
            cs.record_attempt(1, 2, 'rightmove', 'none', 'again')
        row = cs.record_attempt(1, 2, 'rightmove', 'found', 'new postcode', 'different postcode')
        self.assertEqual(row['retry_reason'], 'different postcode')
        self.assertEqual(len(cs.load_attempts(1, 2)), 2)

    def test_status_tried(self):
        cs.record_attempt(1, 2, 'streetview', 'none', 'no coverage')
        self.assertEqual(cs.source_status(1, 2)['streetview']['state'], 'tried')


class TestCellCoverage(unittest.TestCase):
    """An aerial counts for a cell only if it shows most of it, not just a clipped edge."""

    def test_clipped_edge_is_not_coverage(self):
        # B35 mosaic reaches z-5346; cell 49,-42 spans z-5376..-5249 (30 of 128 rows)
        b35 = {'bbox_mc': [6246, -5637, 6538, -5346]}
        self.assertAlmostEqual(cell_coverage(b35, 49, -42), 31 / 128, places=3)
        self.assertLess(cell_coverage(b35, 49, -42), cs.MIN_AERIAL_COVERAGE)

    def test_mosaic_over_the_cell_is_full_coverage(self):
        welbeck = {'bbox_mc': [6151, -5444, 6443, -5153]}
        self.assertEqual(cell_coverage(welbeck, 49, -42), 1.0)

    def test_no_bbox_or_disjoint_is_zero(self):
        self.assertEqual(cell_coverage({}, 49, -42), 0.0)
        self.assertEqual(cell_coverage({'bbox_mc': [0, 0, 10, 10]}, 49, -42), 0.0)


if __name__ == '__main__':
    unittest.main()
