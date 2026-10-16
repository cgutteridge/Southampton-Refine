"""Each fast path must give exactly what the slow code it replaced gave (no Minecraft, no world writes)."""
import math
import random
import unittest

import coverage
import lump_scan
import osm_footprints as osm
import pass_mask as pm


class TestFootprintRaster(unittest.TestCase):
    def test_inside_grid_matches_inside(self):
        rnd = random.Random(11)
        for _ in range(30):
            cx, cz = rnd.uniform(-40, 40), rnd.uniform(-40, 40)
            n = rnd.randint(3, 10)
            outer = [(cx + rnd.uniform(3, 20) * math.cos(2 * math.pi * i / n),
                      cz + rnd.uniform(3, 20) * math.sin(2 * math.pi * i / n)) for i in range(n)]
            hole = [(cx + 1.2 * math.cos(2 * math.pi * i / 4), cz + 1.2 * math.sin(2 * math.pi * i / 4)) for i in range(4)]
            rings = [outer, hole] if rnd.random() < .5 else [outer]
            xs, zs = [p[0] for p in outer], [p[1] for p in outer]
            import numpy as np
            gx, gz = np.meshgrid(np.arange(math.floor(min(xs)), math.ceil(max(xs)) + 1),
                                 np.arange(math.floor(min(zs)), math.ceil(max(zs)) + 1), indexing='ij')
            fast = osm._inside_grid(gx + .5, gz + .5, rings)
            for x, z, h in zip(gx.ravel().tolist(), gz.ravel().tolist(), fast.ravel().tolist()):
                self.assertEqual(h, osm._inside(x + .5, z + .5, rings))


class TestPassMaskDecode(unittest.TestCase):
    def reference(self, palette, runs, bbox):
        placements, cursor = {}, 0
        for pos in pm._scan_order(bbox):
            while runs[cursor][1] == 0:
                cursor += 1
            value, _ = runs[cursor]
            runs[cursor][1] -= 1
            if value != 0:
                placements[pos] = palette[value]
        return placements

    def test_matches_reference_and_consumes_runs(self):
        rnd = random.Random(5)
        for _ in range(60):
            bbox = [rnd.randint(-5, 5), rnd.randint(40, 50), rnd.randint(-5, 5), 0, 0, 0]
            bbox[3], bbox[4], bbox[5] = bbox[0] + rnd.randint(0, 6), bbox[1] + rnd.randint(0, 5), bbox[2] + rnd.randint(0, 6)
            vol = (bbox[3] - bbox[0] + 1) * (bbox[4] - bbox[1] + 1) * (bbox[5] - bbox[2] + 1)
            palette = ['minecraft:air', 'minecraft:stone', 'minecraft:oak_log', 'minecraft:grass_block']
            runs, left = [], vol
            while left:
                n = min(left, rnd.randint(1, 9))
                runs.append([rnd.randint(0, 3), n])
                left -= n
            a, b = pm._runs_copy(runs), pm._runs_copy(runs)
            want = self.reference(palette, a, bbox)
            got = pm.decode_runs(palette, b, bbox)
            self.assertEqual(got, want)
            self.assertEqual(list(got), list(want))
            self.assertEqual(a, b)

    def test_runs_that_end_early_raise(self):
        with self.assertRaises(IndexError):
            pm.decode_runs(['minecraft:air'], [[0, 2]], [0, 0, 0, 1, 1, 1])


class TestSurfaceSectionSkip(unittest.TestCase):
    class W:
        """A world where only y 60..64 and 70 hold blocks; uniform_air mimics site_kit.World sections."""
        def __init__(self, fast):
            if fast:
                self.uniform_air = self._uniform

        def block(self, x, y, z):
            if 60 <= y <= 64:
                return 'minecraft:grass_block' if y == 64 else 'minecraft:stone'
            if y == 70:
                return 'minecraft:oak_leaves[persistent=true]'
            return 'minecraft:air' if y > 0 else None

        def _uniform(self, x, y, z, airs):
            sec = y >> 4
            return not any(60 <= yy <= 64 or yy == 70 for yy in range(sec * 16, sec * 16 + 16))

    def test_skipping_sections_gives_the_same_surface(self):
        for top in (140, 70, 64, 63, 16, 15, 1):
            self.assertEqual(lump_scan.surface(self.W(True), 3, 4, top), lump_scan.surface(self.W(False), 3, 4, top))
        self.assertEqual(lump_scan.surface(self.W(True), 3, 4), (64, 'minecraft:grass_block'))
        self.assertEqual(lump_scan.surface(self.W(True), 3, 4, 20), (0, ''))


class TestTouchedMemo(unittest.TestCase):
    def test_memo_follows_file_changes_and_hands_out_copies(self):
        import json
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as d:
            old_out, old_cache = coverage.OUT, coverage.TOUCH_CACHE
            coverage.OUT, coverage.TOUCH_CACHE = Path(d), Path(d) / 'cache.json'
            try:
                f = Path(d) / 'demo_build-cells.json'
                f.write_text(json.dumps({'1,50,2': 'minecraft:stone'}))
                first = coverage.touched_by_build()
                self.assertEqual(first['demo_build'], {(1, 2)})
                first['demo_build'].add((9, 9))                              # a caller scribbling on its copy
                self.assertEqual(coverage.touched_by_build()['demo_build'], {(1, 2)})
                f.write_text(json.dumps({'1,50,2': 'minecraft:stone', '3,50,4': 'minecraft:stone'}))
                self.assertEqual(coverage.touched_by_build()['demo_build'], {(1, 2), (3, 4)})   # changed file, fresh answer
            finally:
                coverage.OUT, coverage.TOUCH_CACHE = old_out, old_cache
                coverage._TOUCHED_MEMO.clear()


if __name__ == '__main__':
    unittest.main()
