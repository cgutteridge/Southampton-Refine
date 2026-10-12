#!/usr/bin/env python3
"""Unit tests for the roof ridge-jog lint (no world / OSM access).

  python3 -m unittest scripts/test_roof_lint.py
"""
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from roof_lint import OUT, ridge_jogs  # noqa: E402

T = 'minecraft:deepslate_tile'


def gable(cells, ridge_x, z0, z1, y=50, half=4, cap=f'{T}s'):
    """A ridge-on-x gable over rows z0..z1: stairs rising to a full-block ridge at ridge_x."""
    for z in range(z0, z1 + 1):
        cells[(ridge_x, y, z)] = cap
        for d in range(1, half + 1):
            cells[(ridge_x - d, y - d, z)] = f'{T}_stairs[facing=east,half=bottom]'
            cells[(ridge_x + d, y - d, z)] = f'{T}_stairs[facing=west,half=bottom]'
    return cells


class RidgeJogTest(unittest.TestCase):
    def test_straight_gable_is_clean(self):
        self.assertEqual(ridge_jogs(gable({}, 10, 0, 8)), [])

    def test_stepped_segments_jog(self):
        # broadlands_rd_56_62: one pair squared as segments whose ridge moves 2 east
        cells = gable(gable({}, 10, 0, 4), 12, 5, 9)
        jogs = ridge_jogs(cells)
        self.assertEqual(len(jogs), 1)
        self.assertEqual((jogs[0]['axis'], jogs[0]['shift']), ('x', -2))

    def test_party_wall_stagger_is_allowed(self):
        # terrace houses may stagger at a 2-wide brick parapet across the ridge
        cells = gable({}, 10, 0, 4)
        for d in (0, 1):
            cells[(10 + d, 50, 5)] = 'minecraft:bricks'
        for d in range(1, 5):
            cells[(10 - d, 50 - d, 5)] = f'{T}_stairs[facing=east,half=bottom]'
            cells[(11 + d, 50 - d, 5)] = f'{T}_stairs[facing=west,half=bottom]'
        gable(cells, 12, 6, 9)
        self.assertEqual(ridge_jogs(cells), [])

    def test_chimney_does_not_hide_a_jog(self):
        cells = gable(gable({}, 10, 0, 4), 12, 5, 9)
        cells[(10, 51, 4)] = 'minecraft:bricks'
        self.assertEqual(len(ridge_jogs(cells)), 1)

    def test_ridge_along_x_is_checked_too(self):
        cells = {}
        for x, rz in ((0, 10), (1, 10), (2, 13), (3, 13)):
            cells[(x, 50, rz)] = f'{T}s'
            for d in range(1, 5):
                cells[(x, 50 - d, rz - d)] = f'{T}_stairs[facing=south,half=bottom]'
                cells[(x, 50 - d, rz + d)] = f'{T}_stairs[facing=north,half=bottom]'
        self.assertEqual([j['axis'] for j in ridge_jogs(cells)], ['z'])


class RecordedBuildsTest(unittest.TestCase):
    """Regression: every committed verification/site/*-cells.json stays jog-free."""

    def test_all_recorded_build_cells_have_no_ridge_jogs(self):
        bad = []
        for f in sorted(OUT.glob('*-cells.json')):
            name = f.name[: -len('-cells.json')]
            raw = json.loads(f.read_text())
            cells = {tuple(int(v) for v in k.split(',')): s for k, s in raw.items()}
            jogs = ridge_jogs(cells)
            if jogs:
                bad.append(f'{name} ({len(jogs)} jog(s))')
        self.assertEqual(bad, [], 'ridge jogs in recorded builds: ' + ', '.join(bad))


if __name__ == '__main__':
    unittest.main()
