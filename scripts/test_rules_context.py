#!/usr/bin/env python3
"""Unit tests for rules_context queue classification."""
from __future__ import annotations

import unittest

from rules_context import WorkContext, detect_context, plan_for_item


class RulesContextTests(unittest.TestCase):
    """Detect context from queue text and build reading plans."""

    def _item(self, *lines: str) -> dict:
        return {'id': 'Q-999', 'text': lines[0], 'lines': list(lines)}

    def test_foliage_cell(self) -> None:
        it = self._item(
            'CELL 48,-44 foliage last. build_cell_foliage.py --cell 48,-44; sign all affected parcels',
        )
        ctx, _ = detect_context(it)
        self.assertEqual(ctx, WorkContext.FOLIAGE)
        plan = plan_for_item(it, 'site/cells/48_-44-SOURCES.txt')
        paths = {r.path for r in plan.readings}
        self.assertIn('site/FOLIAGE.txt', paths)
        self.assertNotIn('rules/frontage-and-evidence.md', paths)

    def test_ground_paths(self) -> None:
        it = self._item('CELL 48,-44 path/footway stragglers. build_highfield_q053_paths')
        ctx, _ = detect_context(it)
        self.assertEqual(ctx, WorkContext.GROUND)
        plan = plan_for_item(it)
        paths = {r.path for r in plan.readings}
        self.assertIn('rules/radial-good-enough.md', paths)
        self.assertNotIn('rules/frontage-and-evidence.md', paths)

    def test_terrace(self) -> None:
        it = self._item('TERRACE Broadlands scripts/terrace.py broadlands_rd_14_24')
        ctx, _ = detect_context(it)
        self.assertEqual(ctx, WorkContext.TERRACE)
        plan = plan_for_item(it)
        paths = [r.path for r in plan.readings]
        self.assertIn('rules/terrace-builds.md', paths)

    def test_rules_tag_override(self) -> None:
        it = self._item('RULES: tooling  coverage.py build only')
        ctx, note = detect_context(it)
        self.assertEqual(ctx, WorkContext.TOOLING)
        self.assertIn('RULES:', note)

    def test_property_facade(self) -> None:
        it = self._item('FAÇADE: whole property osm_footprints.py frontage survey')
        ctx, _ = detect_context(it)
        self.assertEqual(ctx, WorkContext.PROPERTY)
        plan = plan_for_item(it)
        paths = {r.path for r in plan.readings}
        self.assertIn('rules/frontage-and-evidence.md', paths)


if __name__ == '__main__':
    unittest.main()
