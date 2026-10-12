#!/usr/bin/env python3
"""Unit tests for tpo_fetch helpers (no network)."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'scripts'))
import tpo_fetch  # noqa: E402


class TpoFetchTest(unittest.TestCase):
    def test_parse_wkt_point(self):
        self.assertEqual(tpo_fetch.parse_wkt_point('POINT (-1.4 50.94)'), (-1.4, 50.94))
        self.assertIsNone(tpo_fetch.parse_wkt_point(''))

    def test_craft_for_species(self):
        self.assertEqual(tpo_fetch.craft_for_species('Beech'), 'oak')
        self.assertEqual(tpo_fetch.craft_for_species('Blue cedar'), 'spruce')
        self.assertIsNone(tpo_fetch.craft_for_species(''))

    def test_trees_in_bbox_from_index(self):
        import json
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as tmp:
            idx = Path(tmp) / 'idx.jsonl'
            rows = [
                {'lon': -1.40, 'lat': 50.94, 'reference': 'in'},
                {'lon': -1.50, 'lat': 50.94, 'reference': 'out'},
            ]
            idx.write_text('\n'.join(json.dumps(r) for r in rows) + '\n')
            bbox = (-1.405, 50.935, -1.395, 50.945)
            got = tpo_fetch.trees_in_bbox_from_index(bbox, idx)
            self.assertEqual([g['reference'] for g in got], ['in'])


if __name__ == '__main__':
    unittest.main()
