"""Unit tests for the trees pass dense-cover fill (no Minecraft, no world writes)."""
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

import numpy as np

import trees_layer as tl

CELL = (900, 900)          # no ground-cells file exists for it, so ground_cols is None


def cover(frac_left=1.0, frac_right=0.0):
    """128x128 cover grid: left half one value, right half another."""
    g = np.zeros((128, 128))
    g[:64], g[64:] = frac_left, frac_right
    return g


class FakeWorld:
    def block(self, x, y, z):
        return 'minecraft:air'


class TestCoverPixels(unittest.TestCase):
    def test_wood_is_cover_roof_and_lawn_are_not(self):
        from PIL import Image
        img = np.zeros((40, 120, 3), np.uint8)
        img[:, :40] = (94, 83, 58)        # brown-olive shaded wood (g < r) that the crown test rejects
        img[:, 40:80] = (150, 70, 50)     # red roof
        img[:, 80:] = (185, 175, 170)     # bright, unsaturated paving
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / 'm.png'
            Image.fromarray(img).save(p)
            m = tl.cover_pixels(p)
        self.assertGreater(m[:, :40][10:30, 10:30].mean(), 0.95)
        self.assertEqual(m[:, 40:][10:30, 10:100].mean(), 0)


class TestFillDense(unittest.TestCase):
    def test_dense_patch_gets_proportionally_many_crowns(self):
        n_full = len(tl.fill_dense(cover(1.0, 0.0), []))
        n_mid = len(tl.fill_dense(cover(0.75, 0.0), []))
        area = 64 * 128
        self.assertGreater(n_full, 0.5 * area / tl.FILL_SPACING ** 2)     # about one per spacing² cell
        self.assertLess(n_mid, 0.75 * n_full)                              # fewer at lower cover
        self.assertGreater(n_mid, 0.2 * n_full)
        self.assertTrue(all(i < 70 for i, _j, _r in tl.fill_dense(cover(1.0, 0.0), [])))

    def test_sparse_patch_unchanged(self):
        self.assertEqual(tl.fill_dense(cover(tl.COVER_MIN - 0.05, 0.3), []), [])

    def test_existing_crowns_are_not_overlapped(self):
        crowns = [(i, j, 6.0) for i in range(5, 128, 10) for j in range(5, 128, 10)]
        for i, j, _r in tl.fill_dense(cover(1.0, 1.0), crowns):
            self.assertTrue(all((i - ci) ** 2 + (j - cj) ** 2 > (cr * 0.75) ** 2 for ci, cj, cr in crowns))

    def test_deterministic(self):
        self.assertEqual(tl.fill_dense(cover(), [], seed=3), tl.fill_dense(cover(), [], seed=3))


class TestPlanCellKeepsRules(unittest.TestCase):
    """Fill crowns go through plan_cell's footprint / surface rules like any other crown."""

    def run_plan(self, footprint_x, hard_x):
        x0, z0 = CELL[0] * 128, CELL[1] * 128
        fp = {(x0 + i, z0 + j) for i in range(*footprint_x) for j in range(128)}

        def surface(world, x, z):
            return (60, 'stone') if x - x0 in range(*hard_x) else (60, 'grass_block')

        osm = types.ModuleType('osm_footprints')
        osm.OSMIndex = lambda: types.SimpleNamespace(cells=lambda: fp)
        plan = types.SimpleNamespace(set=lambda *a: None)
        with mock.patch.object(tl, 'canopy_grid', lambda c: np.zeros((128, 128))), \
                mock.patch.object(tl, 'cover_grid', lambda c: cover(1.0, 1.0)), \
                mock.patch.object(tl, 'surface_y', surface), \
                mock.patch.object(tl, 'built_cells', lambda exclude=None: []), \
                mock.patch.object(tl, 'load_masked_positions', lambda: {}), \
                mock.patch.dict(sys.modules, {'osm_footprints': osm}):
            return tl.plan_cell(CELL, plan, FakeWorld())[1]

    def test_footprint_and_hard_surface_columns_are_not_rooted(self):
        x0 = CELL[0] * 128
        rep = self.run_plan((10, 30), (60, 80))
        self.assertGreater(len(rep['trees']), 100)
        for x, _z, _r, _k in rep['trees']:
            self.assertNotIn(x - x0, range(10, 30))
            self.assertNotIn(x - x0, range(60, 80))
        why = {w for *_p, w in rep['skipped']}
        self.assertIn('feature zone', why)
        self.assertIn('surface stone', why)


class TestOverhang(unittest.TestCase):
    """One rule: a tree belongs to the cell its trunk is in; the crown may overhang neighbour air."""

    def plan(self, world, masked=None, crown=(127, 64, 5.0)):
        x0, z0 = CELL[0] * 128, CELL[1] * 128
        osm = types.ModuleType('osm_footprints')
        osm.OSMIndex = lambda: types.SimpleNamespace(cells=lambda: set())
        sets = {}
        plan = types.SimpleNamespace(set=lambda x, y, z, b: sets.__setitem__((x, y, z), b))
        with mock.patch.object(tl, 'canopy_grid', lambda c: np.zeros((128, 128))), \
                mock.patch.object(tl, 'find_crowns', lambda g: [crown]), \
                mock.patch.object(tl, 'cover_grid', lambda c: np.zeros((128, 128))), \
                mock.patch.object(tl, 'surface_y', lambda w, x, z: (60, 'grass_block')), \
                mock.patch.object(tl, 'built_cells', lambda exclude=None: []), \
                mock.patch.object(tl, 'load_masked_positions', lambda: masked or {}), \
                mock.patch.dict(sys.modules, {'osm_footprints': osm}):
            placed, rep = tl.plan_cell(CELL, plan, world)
        return placed, rep, sets, x0 + 128, z0

    def test_overhang_into_neighbour_air_is_kept_and_planned(self):
        placed, rep, sets, edge, _z = self.plan(FakeWorld())
        outside = [p for p in placed if p[0] >= edge]
        self.assertGreater(len(outside), 0)
        self.assertEqual(rep['overhang'], len(outside))
        self.assertEqual(sets, placed)                       # the plan writes the same blocks the mask will record
        self.assertTrue(all('leaves' in b for p, b in placed.items() if p[0] >= edge))

    def test_trunk_is_in_the_cell(self):
        placed, _rep, _s, edge, z0 = self.plan(FakeWorld())
        logs = [p for p, b in placed.items() if 'log' in b]
        self.assertTrue(logs)
        self.assertTrue(all(p[0] < edge and z0 <= p[2] < z0 + 128 for p in logs))

    def test_neighbour_blocks_and_masks_are_not_overwritten(self):
        edge = CELL[0] * 128 + 128
        solid = {(x, y, z) for x in range(edge, edge + 3) for y in range(60, 75) for z in range(CELL[1] * 128 + 56, CELL[1] * 128 + 72)}

        class W:
            def block(self, x, y, z):
                return 'minecraft:stone' if (x, y, z) in solid else 'minecraft:air'
        owned = {(edge + 3, 63, CELL[1] * 128 + 64): 'trees 901,900'}
        placed, _rep, _s, _e, _z = self.plan(W(), masked=owned)
        self.assertFalse(set(placed) & solid)
        self.assertNotIn((edge + 3, 63, CELL[1] * 128 + 64), placed)

    def test_trunk_blocked_outside_cell_never_moves_the_trunk(self):
        # a crown rooted at the edge column still roots in-cell; nothing is planted rooted outside
        placed, rep, *_ = self.plan(FakeWorld(), crown=(127, 0, 3.0))
        self.assertEqual([(x, z) for x, z, *_ in rep['trees']], [(CELL[0] * 128 + 127, CELL[1] * 128)])
        self.assertTrue(all(p[0] < CELL[0] * 128 + 128 for p, b in placed.items() if 'log' in b))

    def test_leaf_merges_into_neighbour_tree_leaf_but_never_its_trunk(self):
        edge = CELL[0] * 128 + 128
        z = CELL[1] * 128 + 64
        leaf = {(edge + 1, y, z) for y in range(60, 75)}
        log = {(edge + 2, y, z) for y in range(60, 75)}
        owned = {p: 'trees 901,900' for p in leaf | log}

        class W:
            def block(self, x, y, zz):
                return 'minecraft:oak_leaves' if (x, y, zz) in leaf else 'minecraft:oak_log' if (x, y, zz) in log else 'minecraft:air'
        placed, *_ = self.plan(W(), masked=owned)
        self.assertTrue(set(placed) & leaf)
        self.assertFalse(set(placed) & log)

    def test_may_plant_rule(self):
        air, leaf, log = 'minecraft:air', 'minecraft:oak_leaves', 'minecraft:oak_log'
        self.assertTrue(tl.may_plant(air, leaf, None))
        self.assertFalse(tl.may_plant(leaf, leaf, None))                    # unowned leaf (Geocraft) stays
        self.assertTrue(tl.may_plant(leaf, leaf, 'trees 1,1'))
        self.assertFalse(tl.may_plant(leaf, log, 'trees 1,1'))
        self.assertFalse(tl.may_plant(leaf, leaf, 'decor 1,1'))
        self.assertFalse(tl.may_plant(log, leaf, 'trees 1,1'))

    def test_deterministic(self):
        a = self.plan(FakeWorld())[0]
        self.assertEqual(a, self.plan(FakeWorld())[0])


class TestExtraCrowns(unittest.TestCase):
    """reference/trees-extra-crowns.json: a tree the mosaic cannot show, planted through the normal rules."""

    def run_plan(self, in_footprint, surface):
        import json
        x0, z0 = CELL[0] * 128, CELL[1] * 128
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / 'extra.json'
            f.write_text(json.dumps({f'{CELL[0]},{CELL[1]}': [{'x': x0 + 60, 'z': z0 + 60, 'r': 3.4}]}))
            osm = types.ModuleType('osm_footprints')
            fp = {(x0 + 60, z0 + 60)} if in_footprint else set()
            osm.OSMIndex = lambda: types.SimpleNamespace(cells=lambda: fp)
            plan = types.SimpleNamespace(set=lambda *a: None)
            with mock.patch.object(tl, 'EXTRA_CROWNS', f), \
                    mock.patch.object(tl, 'canopy_grid', lambda c: np.zeros((128, 128))), \
                    mock.patch.object(tl, 'cover_grid', lambda c: np.zeros((128, 128))), \
                    mock.patch.object(tl, 'surface_y', lambda w, x, z: (60, surface)), \
                    mock.patch.object(tl, 'built_cells', lambda exclude=None: []), \
                    mock.patch.object(tl, 'load_masked_positions', lambda: {}), \
                    mock.patch.dict(sys.modules, {'osm_footprints': osm}):
                return tl.plan_cell(CELL, plan, FakeWorld())

    def test_extra_crown_is_planted_even_in_an_osm_footprint(self):
        placed, rep = self.run_plan(True, 'grass_block')
        self.assertEqual(len(rep['trees']), 1)
        self.assertTrue(any('log' in b for b in placed.values()))

    def test_extra_crown_still_needs_lawn(self):
        placed, rep = self.run_plan(True, 'light_gray_concrete')
        self.assertEqual(rep['trees'], [])
        self.assertEqual(placed, {})


if __name__ == '__main__':
    unittest.main()
