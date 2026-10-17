import unittest

import lidar_heightmap as L


class FakeWorld:
    def __init__(self, blocks):
        self.blocks = blocks

    def block(self, x, y, z):
        return self.blocks.get((x, y, z))


def col(blocks, x=0, z=0):
    return L.column(FakeWorld({(x, y, z): b for y, b in blocks.items()}), x, z, top=80)


class ColumnTest(unittest.TestCase):
    def test_plain_ground_ignores_grass_tufts(self):
        self.assertEqual(col({40: 'minecraft:stone', 41: 'minecraft:short_grass'}), (40, 40, 0, L.GROUND))

    def test_flowers_and_tall_plants_are_not_lidar_height(self):
        for plant in ('minecraft:dandelion', 'minecraft:blue_orchid', 'minecraft:oxeye_daisy', 'minecraft:tall_grass[half=upper]',
                      'minecraft:lilac[half=lower]', 'minecraft:fern', 'minecraft:oak_sign[rotation=3]'):
            with self.subTest(plant=plant):
                self.assertEqual(col({40: 'minecraft:grass_block', 41: plant}), (40, 40, 0, L.GROUND))

    def test_carpet_is_ignored_for_height_and_marks_a_roof(self):
        self.assertEqual(col({40: 'minecraft:stone', 48: 'minecraft:bricks', 49: 'minecraft:light_gray_carpet'}),
                         (48, 48, 49, L.ROOF))

    def test_leaves_and_logs_count_as_height_but_are_not_ground(self):
        h, base, roof, kind = col({40: 'minecraft:grass_block', 41: 'minecraft:oak_log', 42: 'minecraft:oak_log',
                                   43: 'minecraft:oak_leaves[distance=1]'})
        self.assertEqual((h, base, roof, kind), (43, 40, 0, L.TREE))

    def test_crown_over_a_roof_is_flagged(self):
        h, base, roof, kind = col({40: 'minecraft:stone', 48: 'minecraft:bricks', 49: 'minecraft:light_gray_carpet',
                                   51: 'minecraft:oak_leaves'})
        self.assertEqual((h, roof, kind), (51, 49, L.TREE_OVER_ROOF))

    def test_empty_column(self):
        self.assertEqual(col({}), (0, 0, 0, L.GROUND))


class LumpTest(unittest.TestCase):
    def test_two_buildings_with_storeys_and_roof_shape(self):
        import numpy as np
        n = 128
        hm = {'cell': (0, 0), 'x0': 0, 'z0': 0, 'h': np.zeros((n, n), 'int16'), 'base': np.full((n, n), 40, 'int16'),
              'roof': np.zeros((n, n), 'int16'), 'kind': np.zeros((n, n), 'uint8')}
        for x in range(10, 20):                    # pitched: ridge along x at z=15
            for z in range(10, 21):
                hm['roof'][x, z] = 46 - abs(z - 15) // 2 + 4
                hm['kind'][x, z] = L.ROOF
        for x in range(60, 70):                    # flat
            for z in range(60, 70):
                hm['roof'][x, z] = 47
                hm['kind'][x, z] = L.ROOF
        hm['roof'][5, 5] = 47                      # a 1-column sliver is ignored
        items = L.lumps(hm)
        self.assertEqual(len(items), 2)
        pitched, flat = items
        self.assertEqual((pitched['roof'], pitched['ridge_axis'], pitched['ground_y']), ('pitched', 'x', 40))
        self.assertEqual((flat['roof'], flat['ridge_axis'], flat['storeys']), ('flat', None, 1))

    def blank_map(self):
        import numpy as np
        n = 128
        return {'cell': (0, 0), 'x0': 0, 'z0': 0, 'h': np.zeros((n, n), 'int16'), 'base': np.full((n, n), 40, 'int16'),
                'roof': np.zeros((n, n), 'int16'), 'kind': np.zeros((n, n), 'uint8')}

    def test_narrow_pitched_house_stays_pitched(self):
        """A 3-wide gable's interior is only its ridge strip (spread 0): too narrow to judge by, so the whole footprint is used."""
        hm = self.blank_map()
        for x in range(10, 22):
            for z in range(10, 13):
                hm['roof'][x, z] = 50 if z == 11 else 47
                hm['kind'][x, z] = L.ROOF
        (lump,) = L.lumps(hm)
        self.assertEqual((lump['roof'], lump['ridge_axis']), ('pitched', 'x'))

    def test_flat_roof_with_blurred_rim_is_flat(self):
        """Lidar reads the rim of any building 3-6 low (Oakdene Court); only the interior says flat or pitched."""
        hm = self.blank_map()
        for x in range(10, 24):
            for z in range(10, 20):
                rim = x in (10, 23) or z in (10, 19)
                hm['roof'][x, z] = 48 if rim else 57
                hm['kind'][x, z] = L.ROOF
        (lump,) = L.lumps(hm)
        self.assertEqual((lump['roof'], lump['ridge_axis'], lump['ridge_y']), ('flat', None, 57))


class AuditTest(unittest.TestCase):
    def maps(self):
        import numpy as np
        n = 128
        mk = lambda: {'cell': (0, 0), 'x0': 0, 'z0': 0, 'h': np.full((n, n), 40, 'int16'), 'base': np.full((n, n), 40, 'int16'),
                      'roof': np.zeros((n, n), 'int16'), 'kind': np.zeros((n, n), 'uint8')}
        pri, live = mk(), mk()
        for x in range(10, 20):
            for z in range(10, 20):
                pri['roof'][x, z] = 50
                pri['h'][x, z] = 49
                pri['kind'][x, z] = L.ROOF
                live['h'][x, z] = 50 if x < 15 else 44          # half the house matches, half is 6 too low
        pri['kind'][100, 100] = L.TREE
        live['kind'][101, 101] = L.TREE
        return live, pri

    def test_audit_counts_matches_lumps_and_trees(self):
        import lidar_audit as A
        live, pri = self.maps()
        res = A.audit(live, pri, tol=1)
        self.assertEqual((res['tree_missing'], res['tree_extra']), (1, 1))
        (lump,) = res['lumps']
        self.assertEqual((lump['within'], lump['lowest'], lump['highest'], lump['lidar_ridge']), (0.5, -6, 0, 50))
        self.assertEqual(res['worst'][0][2:], [44, 50])
        self.assertIn('LIDAR AUDIT', A.format_audit((0, 0), res, 1))

    def test_grid_diff_crosses_cell_edges_and_filters(self):
        """Maps.top_at + grid_diff: one column per side of a cell edge, |d| filter."""
        import numpy as np
        import lidar_audit as A

        def hm(cell, x0, z0, roof_at, h=40):
            n = 128
            out = {'cell': cell, 'x0': x0, 'z0': z0, 'h': np.full((n, n), h, 'int16'),
                   'base': np.full((n, n), h, 'int16'), 'roof': np.zeros((n, n), 'int16'),
                   'kind': np.zeros((n, n), 'uint8')}
            for (x, z), y in roof_at.items():
                out['roof'][x - x0, z - z0] = y
                out['kind'][x - x0, z - z0] = L.ROOF
            return out

        # cell (0,-1) ends at z=-1; cell (0,0) starts at z=0
        pri = L.Maps(use_cache=False)
        live = L.Maps(use_cache=False)
        pri._hm[(0, -1)] = hm((0, -1), 0, -128, {(5, -1): 58})
        pri._hm[(0, 0)] = hm((0, 0), 0, 0, {(5, 0): 60})
        live._hm[(0, -1)] = hm((0, -1), 0, -128, {}, h=60)   # live top = h when no carpet
        live._hm[(0, 0)] = hm((0, 0), 0, 0, {}, h=60)
        self.assertEqual(pri.top_at(5, -1), 58)
        self.assertEqual(pri.top_at(5, 0), 60)
        rows = A.grid_diff(live, pri, 5, -1, 5, 0, min_abs=2)
        self.assertEqual(rows, [(5, -1, 60, 58, 2)])          # only the south column is off by 2
        text = A.format_grid((5, -1, 5, 0), rows, 2)
        self.assertIn('LIVE-MINUS-LIDAR', text)
        self.assertIn('+2', text)


class ResetToBaseTest(unittest.TestCase):
    def test_restores_from_base_not_air_when_followup_cleared(self):
        """Follow-up air over a base roof must put the roof back, not leave a hole."""
        import tempfile
        from pathlib import Path
        import site_kit

        with tempfile.TemporaryDirectory() as d:
            out = Path(d)
            old = site_kit.OUT
            site_kit.OUT = out
            try:
                (out / 'feat-cells.json').write_text(
                    '{"10,50,20": "minecraft:light_gray_concrete", "10,51,20": "minecraft:smooth_stone_slab[type=bottom]"}')
                (out / 'feat-lower-cells.json').write_text(
                    '{"10,50,20": "minecraft:air", "10,51,20": "minecraft:air", "11,50,20": "minecraft:stone"}')
                plan = site_kit.reset_to_base('feat', ['feat-lower'])
                self.assertEqual(plan.name, 'feat-reset')
                self.assertEqual(plan.cells[(10, 50, 20)], 'minecraft:light_gray_concrete')
                self.assertEqual(plan.cells[(10, 51, 20)], 'minecraft:smooth_stone_slab[type=bottom]')
                self.assertEqual(plan.cells[(11, 50, 20)], 'minecraft:air')  # not in base → air
            finally:
                site_kit.OUT = old


if __name__ == '__main__':
    unittest.main()
