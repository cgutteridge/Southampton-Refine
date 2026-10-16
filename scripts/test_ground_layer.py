"""Unit tests for scripts/ground_layer.py helpers (no Minecraft, no world writes)."""
import unittest
from collections import Counter

import ground_layer as gl


class TestGroundLayer(unittest.TestCase):
    """Naming, air rules and cell containment."""

    def test_plan_name_negative_tz(self):
        """Negative tz encodes as m prefix, matching cell_marker naming."""
        self.assertEqual(gl.plan_name(48, -44), 'highfield_48_m44_ground')

    def test_plan_name_positive_tz(self):
        """Non-negative tz stays numeric."""
        self.assertEqual(gl.plan_name(48, 3), 'highfield_48_3_ground')

    def test_flowers_and_stems_are_air(self):
        """§10: flowers and grass stems count as air for the ground step."""
        self.assertTrue(gl.is_air('minecraft:short_grass'))
        self.assertTrue(gl.is_air('minecraft:poppy[half=lower]'))
        self.assertFalse(gl.is_air('minecraft:grass_block'))

    def test_bare_strips_state(self):
        """World block states compare against plan ids without properties."""
        self.assertEqual(gl.bare('minecraft:oak_log[axis=y]'), 'minecraft:oak_log')

    def test_cell_contains_edges(self):
        """Cell 48,-44 includes its first and last column and excludes the next."""
        self.assertTrue(gl.cell_contains((48, -44), 6144, -5632))
        self.assertTrue(gl.cell_contains((48, -44), 6271, -5505))
        self.assertFalse(gl.cell_contains((48, -44), 6272, -5505))


class TestGroundSources(unittest.TestCase):
    """Evidence rules: widths from tags, colour classes, speckle filter."""

    def test_road_width_from_lanes_and_cycle_lanes(self):
        import ground_sources as gs
        self.assertEqual(gs.road_width({'highway': 'unclassified', 'lanes': '2'}), 6.0)
        self.assertEqual(gs.road_width({'highway': 'unclassified', 'lanes': '2', 'cycleway:both': 'lane',
                                        'cycleway:width': '1.25'}), 8.5)
        self.assertEqual(gs.road_width({'highway': 'service', 'service': 'driveway'}), 3.0)
        self.assertEqual(gs.road_width({'highway': 'service', 'width': '4.5 m'}), 4.5)

    def test_aerial_classes(self):
        import ground_sources as gs
        self.assertEqual(gs.aerial_class((0.64, 0.60, 0.54)), 'lawn')      # khaki, sun-bleached grass
        self.assertEqual(gs.aerial_class((0.84, 0.76, 0.69)), 'brick')     # pink-orange block paving
        self.assertEqual(gs.aerial_class((0.85, 0.85, 0.85)), 'light')     # neutral paving
        self.assertEqual(gs.aerial_class((0.44, 0.39, 0.27)), 'shade')     # dark, saturated: canopy

    def test_majority_removes_a_speck(self):
        import ground_sources as gs
        grid = {(x, z): 'lawn' for x in range(5) for z in range(5)}
        grid[(2, 2)] = 'brick'
        self.assertEqual(gs.majority(grid, {(2, 2)})[(2, 2)], 'lawn')

    def test_poly_and_line_cells(self):
        import ground_sources as gs
        square = [[(0, 0), (4, 0), (4, 4), (0, 4)]]
        self.assertEqual(len(gs.poly_cells([square])), 16)
        self.assertIn((2, 0), gs.line_cells([(0.5, 0.5), (4.5, 0.5)], 0.6))


class TestAerialNoData(unittest.TestCase):
    """I-042/I-057: blank (black) mosaic pixels must not be read as dark paving."""

    def test_black_pixels_are_dropped_not_classed_dark(self):
        import tempfile
        from pathlib import Path
        import numpy as np
        from PIL import Image
        import ground_sources as gs
        im = np.full((40, 40, 3), 120, dtype=np.uint8)
        im[:, :20] = 0                                    # left half: no data
        with tempfile.TemporaryDirectory() as d:
            png = Path(d) / 'm.png'
            Image.fromarray(im).save(png)
            old_m, old_px = gs.MOSAIC, gs.mosaic_px
            gs.MOSAIC = png
            gs.mosaic_px = lambda pts: {p: (p[0], 20) for p in pts}
            try:
                out = gs.aerial_rgb((0, 0), margin=0)
            finally:
                gs.MOSAIC, gs.mosaic_px = old_m, old_px
        self.assertNotIn((10, 0), out)
        self.assertIn((30, 0), out)


class TestGroundDecisions(unittest.TestCase):
    """Classification and levelling on small synthetic evidence."""

    class Osm:
        def __init__(self, kind=None, pri=None, road=(), marks=()):
            self.kind, self.pri, self.road, self.marks = kind or {}, pri or {}, set(road), set(marks)
            self.feat = {}
            self.hedge = self.wall = self.fence = set()

    def test_osm_surface_beats_aerial_and_shade_takes_neighbours(self):
        cell = (48, -44)
        x0, z0 = 6144, -5632
        live = {(x0 + i, z0 + j): (50, 'stone') for i in range(6) for j in range(6)}
        osm = self.Osm({(x0, z0): 'tarmac'}, {(x0, z0): 90})
        lawn, shade = (0.64, 0.60, 0.54), (0.44, 0.39, 0.27)
        rgb = {(x0 + i, z0 + j): lawn for i in range(-4, 9) for j in range(-4, 4)}
        rgb[(x0 + 2, z0 + 2)] = shade
        kind, _ = gl.classify(cell, live, osm, rgb)
        self.assertEqual(kind[(x0, z0)], 'tarmac')
        self.assertEqual(kind[(x0 + 1, z0)], 'grass')
        self.assertEqual(kind[(x0 + 2, z0 + 2)], 'grass')                      # shade takes the lawn around it

    def test_registered_aerial_lawn_beats_mapped_plaza_but_mosaic_lawn_does_not(self):
        import ground_sources as gs
        cell = (47, -45)
        x0, z0 = 6130, -5740
        cols = [(x0 + i, z0 + j) for i in range(8) for j in range(8)]
        live = {q: (50, 'stone') for q in cols}
        osm = self.Osm({q: 'paving' for q in cols}, {q: gs.PRI['pedestrian'] for q in cols})
        sharp = {q: gs.RegRGB((0.35, 0.45, 0.35)) for q in cols}          # registered user aerial: green
        kind, how = gl.classify(cell, live, osm, sharp)
        self.assertTrue(all(kind[q] == 'grass' for q in cols))
        self.assertGreater(how['registered aerial lawn inside mapped plaza'], 0)
        blurry = {q: (0.64, 0.60, 0.54) for q in cols}                    # mosaic lawn colour: plaza stays paved
        kind, _ = gl.classify(cell, live, osm, blurry)
        self.assertTrue(all(kind[q] == 'paving' for q in cols))

    def test_poly_cells_matches_the_per_column_reference(self):
        """The numpy even-odd fill must equal the old pure-Python scan, column for column."""
        import math
        import random
        import ground_sources as gs

        def reference(rings_list):
            out = set()
            for rings in rings_list:
                o = rings[0]
                for x in range(math.floor(min(p[0] for p in o)), math.ceil(max(p[0] for p in o)) + 1):
                    for z in range(math.floor(min(p[1] for p in o)), math.ceil(max(p[1] for p in o)) + 1):
                        c = (x + .5, z + .5)
                        if gs.inside(*c, o) and not any(gs.inside(*c, h) for h in rings[1:]):
                            out.add((x, z))
            return out

        rnd = random.Random(7)
        shapes = []
        for _ in range(40):
            cx, cz = rnd.uniform(-50, 50), rnd.uniform(-50, 50)
            n = rnd.randint(3, 12)
            ring = [(cx + rnd.uniform(3, 25) * math.cos(2 * math.pi * i / n),
                     cz + rnd.uniform(3, 25) * math.sin(2 * math.pi * i / n)) for i in range(n)]
            hole = [(cx + 1.5 * math.cos(2 * math.pi * i / 5), cz + 1.5 * math.sin(2 * math.pi * i / 5)) for i in range(5)]
            shapes.append([ring, hole] if rnd.random() < .4 else [ring])
        shapes.append([[(0, 0), (10, 0), (10, 0.5), (0, 0.5)]])                 # thin sliver, horizontal edges
        shapes.append([[(0.5, 0.5), (8.5, 0.5), (8.5, 8.5), (0.5, 8.5)]])       # edges exactly on column centres
        shapes.append([[(1, 1), (2, 2), (3, 3)]])                               # degenerate
        for s in shapes:
            self.assertEqual(gs.poly_cells([s]), reference([s]))
        self.assertEqual(gs.poly_cells(shapes), reference(shapes))

    def test_only_isolated_hard_spikes_are_levelled(self):
        live = {(x, z): (50, 'x') for x in range(5) for z in range(5)}
        live[(2, 2)] = (51, 'x')
        kind = {q: 'paving' for q in live}
        self.assertEqual(gl.level_spikes(live, kind, set())[(2, 2)], 50)
        kind[(2, 2)] = 'grass'
        self.assertEqual(gl.level_spikes(live, kind, set())[(2, 2)], 51)

    def test_path_is_carried_straight_across_shade(self):
        # a 3-wide brick path along x with a 9-long shaded gap; lawn above and below
        kind = {(x, z): 'brick' for x in list(range(0, 8)) + list(range(17, 25)) for z in (10, 11, 12)}
        kind.update({(x, z): 'grass' for x in range(0, 25) for z in list(range(4, 10)) + list(range(13, 19))})
        gap = {(x, z) for x in range(8, 17) for z in range(4, 19)}
        out = gl.bridge_paths(kind, gap)
        self.assertTrue(all(out.get((x, 11)) == 'brick' for x in range(8, 17)))
        self.assertNotIn((12, 5), out)                                     # lawn either side is not path

    def test_unrelated_paths_are_not_joined(self):
        kind = {(x, z): 'paving' for x in range(0, 6) for z in (0, 1)}
        kind.update({(x, z): 'paving' for x in range(0, 6) for z in (20, 21)})
        gap = {(x, z) for x in range(0, 6) for z in range(2, 20)}           # ends face sideways, not each other
        self.assertEqual(gl.bridge_paths(kind, gap), {})

    def test_noise_pass_removes_specks_but_keeps_long_thin_paths(self):
        kind = {(x, z): 'grass' for x in range(30) for z in range(30)}
        kind.update({(x, 15): 'paving' for x in range(30)})               # a 1-wide path, 30 long
        kind[(5, 5)] = 'brick'                                             # a single stray block
        kind.update({(10, 25): 'brick', (11, 25): 'brick'})                # a stray pair
        out = gl.denoise(kind, set(), Counter())
        self.assertEqual(out[(5, 5)], 'grass')
        self.assertEqual(out[(10, 25)], 'grass')
        self.assertEqual(out[(20, 15)], 'paving')

    def test_ignored_builds_forget_old_passes_but_not_neighbours(self):
        ign = gl.ignored_builds((48, -44))
        self.assertIn('highfield_q051_ur', ign)
        self.assertIn('highfield_48_m44_trees', ign)
        self.assertNotIn('highfield_48_m45_trees', ign)


if __name__ == '__main__':
    unittest.main()


class TestRegisteredAerial(unittest.TestCase):
    """Registered user aerials (Google 3D render) as a higher-priority colour source (I-042/I-057)."""

    def test_registered_green_is_lawn_but_same_colour_as_mosaic_is_not(self):
        import ground_sources as gs
        green = (0.35, 0.49, 0.38)                                   # Google lawn beside Building 2
        self.assertEqual(gs.aerial_class(gs.RegRGB(green)), 'lawn')
        self.assertNotEqual(gs.aerial_class(green), 'lawn')          # mosaic thresholds untouched (hue > 110)
        self.assertEqual(gs.aerial_class((0.64, 0.60, 0.54)), 'lawn')
        self.assertEqual(gs.aerial_class((0.84, 0.76, 0.69)), 'brick')

    def test_registered_paving_roof_and_brick(self):
        import ground_sources as gs
        R = gs.RegRGB
        self.assertEqual(gs.aerial_class(R((0.85, 0.81, 0.77))), 'light')    # cream promenade (hue 28, s 0.10)
        self.assertEqual(gs.aerial_class(R((0.93, 0.95, 0.96))), 'light')    # white roof / neutral paving
        self.assertEqual(gs.aerial_class(R((0.79, 0.56, 0.55))), 'brick')    # salmon block paving
        self.assertEqual(gs.aerial_class(R((0.72, 0.64, 0.66))), 'brick')    # pale pink block paving
        self.assertEqual(gs.aerial_class(R((0.44, 0.49, 0.61))), 'shade')    # leaning blue roof: ground unseen
        self.assertEqual(gs.aerial_class(R((0.1, 0.1, 0.1))), 'dark')

    def test_registered_rgb_skips_outside_edge_and_black(self):
        import numpy as np
        import ground_sources as gs
        im = np.zeros((200, 200, 3)) + (0.35, 0.49, 0.38)
        im[:, 100:] = 0                                              # black no-data half
        src = {'name': 't', 'A': np.array([[2.0, 0, 0], [0, 2.0, 0]]), 'im': im, 'ppb': 2.0}
        out = gs.registered_rgb([(30, 50), (1, 50), (30, 1), (60, 50), (80, 50)], [src])
        self.assertEqual(set(out), {(30, 50)})                       # (1,50),(30,1) near the edge; (60,50),(80,50) black
        self.assertEqual(gs.aerial_class(out[(30, 50)]), 'lawn')

    def test_registered_wins_over_mosaic_and_glob_finds_registrations(self):
        import ground_sources as gs
        self.assertTrue(any('googlemaps-music-law-annex' in s['name'] for s in gs.registered_aerials()))
        reg = gs.registered_rgb([(6136, -5715)])
        self.assertIsInstance(reg[(6136, -5715)], gs.RegRGB)
