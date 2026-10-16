"""Unit tests for scripts/floaters.py and floater_scan CLI helpers (no Minecraft).

  python3 -m unittest scripts/test_floaters.py
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import coverage as cov  # noqa: E402
import floaters as fl  # noqa: E402
import floater_scan as fs  # noqa: E402


class FakeWorld:
    """Minimal block map for floater heuristics."""

    def __init__(self, blocks: dict[tuple[int, int, int], str]):
        self.blocks = blocks

    def block(self, x: int, y: int, z: int) -> str | None:
        return self.blocks.get((x, y, z))


class TestFloaters(unittest.TestCase):
    """Air stats and downward support checks."""

    def test_is_air_variants(self):
        """Air-like states count as empty."""
        self.assertTrue(fl.is_air('minecraft:air'))
        self.assertTrue(fl.is_air('minecraft:cave_air'))
        self.assertFalse(fl.is_air('minecraft:stone'))

    def test_unsupported_mass_floating_stone(self):
        """Stone with air below within depth is unsupported."""
        w = FakeWorld({(0, 10, 0): 'minecraft:stone'})
        row = fl.unsupported_mass(w.block, 0, 10, 0, 'minecraft:stone', y_min=0, depth=10)
        self.assertIsNotNone(row)
        self.assertEqual(row['kind'], 'unsupported')

    def test_unsupported_mass_on_ground(self):
        """Stone on stone is supported."""
        w = FakeWorld({
            (0, 10, 0): 'minecraft:stone',
            (0, 9, 0): 'minecraft:stone',
        })
        self.assertIsNone(fl.unsupported_mass(w.block, 0, 10, 0, 'minecraft:stone', y_min=0, depth=10))

    def test_unsupported_respects_depth(self):
        """Support just outside depth still counts as floating."""
        w = FakeWorld({
            (0, 10, 0): 'minecraft:stone',
            (0, 8, 0): 'minecraft:stone',
        })
        row = fl.unsupported_mass(w.block, 0, 10, 0, 'minecraft:stone', y_min=0, depth=1)
        self.assertIsNotNone(row)

    def test_scan_box_counts(self):
        """Scan tallies air and non-air cells."""
        w = FakeWorld({
            (0, 5, 0): 'minecraft:stone',
            (0, 6, 0): 'minecraft:air',
        })
        rep = fl.scan_box(w.block, 0, 5, 0, 0, 6, 0, depth=3, attachables=False, structural=False)
        self.assertEqual(rep['counts']['air'], 1)
        self.assertEqual(rep['counts']['non_air'], 1)

    def test_floating_torch(self):
        """Torch with air below is an attachable floater."""
        w = FakeWorld({
            (1, 4, 1): 'minecraft:torch',
            (1, 3, 1): 'minecraft:air',
        })
        rows = fl.cell_glitches(w.block, 1, 4, 1, 'minecraft:torch')
        self.assertTrue(any(r['kind'] == 'floating' for r in rows))

    def test_floating_leaves_orphan_blob(self):
        """Leaf blob with no log is flagged; hedge on brick is not."""
        w = FakeWorld({
            (0, 5, 0): 'minecraft:oak_leaves[persistent=true]',
            (0, 4, 0): 'minecraft:air',
            (2, 5, 0): 'minecraft:oak_leaves[persistent=true]',
            (2, 4, 0): 'minecraft:bricks',
            (4, 5, 0): 'minecraft:oak_leaves[persistent=true]',
            (4, 4, 0): 'minecraft:oak_log',
        })
        orphan = fl.floating_leaves(w.block, 0, 5, 0, 'minecraft:oak_leaves[persistent=true]')
        self.assertIsNotNone(orphan)
        self.assertEqual(orphan['kind'], 'floating_leaves')
        hedge = fl.floating_leaves(w.block, 2, 5, 0, 'minecraft:oak_leaves[persistent=true]')
        self.assertIsNone(hedge)
        tree = fl.floating_leaves(w.block, 4, 5, 0, 'minecraft:oak_leaves[persistent=true]')
        self.assertIsNone(tree)


class TestFloaterScanCli(unittest.TestCase):
    """Cell key → MC bbox wiring."""

    def test_parse_cell(self):
        """Coverage cell keys parse as two integers."""
        self.assertEqual(fs.parse_cell('48,-44'), (48, -44))

    def test_cell_output_stem_negative_tz(self):
        """Negative tz uses m-prefix in default output names."""
        self.assertEqual(fs.cell_output_stem(48, -44), '48_m44')

    def test_cell_matches_coverage_bbox(self):
        """--cell XZ bounds match coverage.cell_bbox."""
        tx, tz = 48, -44
        x0, z0, x1, z1 = cov.cell_bbox(tx, tz, tx, tz)
        self.assertEqual((x0, z0, x1, z1), (6144, -5632, 6271, -5505))


if __name__ == '__main__':
    unittest.main()
