"""site_kit.owned_in (persistent ownership index) must agree with the full built_cells merge."""
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import site_kit

AIR, STONE, DIRT = 'minecraft:air', 'minecraft:stone', 'minecraft:coarse_dirt'


class OwnedInTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.out = self.tmp / 'out'
        self.out.mkdir()
        patches = [mock.patch.object(site_kit, 'OUT', self.out),
                   mock.patch.object(site_kit, 'OWNERS_DB', self.tmp / 'owners.sqlite'),
                   mock.patch.object(site_kit, 'CELLS_CACHE', self.tmp / 'cache')]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)
        self.t = 1_700_000_000

    def write(self, name, cells):
        f = self.out / f'{name}-cells.json'
        f.write_text(json.dumps({f'{x},{y},{z}': s for (x, y, z), s in cells.items()}))
        self.t += 10
        os.utime(f, (self.t, self.t))

    def check(self, cells, exclude=()):
        full = site_kit.built_cells(exclude=exclude)
        want = {q: full[q] for q in cells if q in full}
        self.assertEqual(site_kit.owned_in(cells, exclude), want)
        return want

    def test_later_build_wins_and_air_cancels(self):
        self.write('a', {(0, 0, 0): STONE, (1, 0, 0): STONE, (2, 0, 0): STONE})
        self.write('b', {(0, 0, 0): DIRT, (1, 0, 0): AIR, (3, 0, 0): AIR})
        got = self.check([(0, 0, 0), (1, 0, 0), (2, 0, 0), (3, 0, 0)])
        self.assertEqual(got[(0, 0, 0)], ('b', DIRT))
        self.assertNotIn((1, 0, 0), got)

    def test_exclude_reveals_earlier_build(self):
        self.write('a', {(0, 0, 0): STONE})
        self.write('b', {(0, 0, 0): DIRT})
        self.assertEqual(self.check([(0, 0, 0)], exclude={'b'})[(0, 0, 0)], ('a', STONE))

    def test_new_and_resaved_files_are_picked_up(self):
        self.write('a', {(0, 0, 0): STONE})
        self.check([(0, 0, 0)])
        self.write('b', {(0, 0, 0): DIRT})
        self.assertEqual(self.check([(0, 0, 0)])[(0, 0, 0)], ('b', DIRT))
        self.write('a', {(0, 0, 0): STONE, (5, 0, 0): STONE})     # re-saved: now newest, wins over b
        self.assertEqual(self.check([(0, 0, 0), (5, 0, 0)])[(0, 0, 0)], ('a', STONE))

    def test_removed_file_forces_rebuild(self):
        self.write('a', {(0, 0, 0): STONE})
        self.write('b', {(0, 0, 0): DIRT})
        self.check([(0, 0, 0)])
        (self.out / 'b-cells.json').unlink()
        self.assertEqual(self.check([(0, 0, 0)])[(0, 0, 0)], ('a', STONE))


if __name__ == '__main__':
    unittest.main()
