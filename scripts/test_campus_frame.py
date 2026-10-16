"""Unit tests for campus.BuildingFrame (footprint frame, rects/lines, faces, flat-tread entrance; no Minecraft).

  python3 -m unittest scripts/test_campus_frame.py
"""
import math
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import campus  # noqa: E402

BF = campus.BuildingFrame


def box(x0, z0, w, d):
    return {(x, z) for x in range(x0, x0 + w) for z in range(z0, z0 + d)}


def slanted(length, width, deg):
    """Cells whose centres lie in a length x width rectangle rotated `deg` from +x toward +z, about the origin."""
    ux, uz = math.cos(math.radians(deg)), math.sin(math.radians(deg))
    out = set()
    for x in range(-60, 60):
        for z in range(-60, 60):
            a, s = (x + .5) * ux + (z + .5) * uz, -(x + .5) * uz + (z + .5) * ux
            if abs(a) <= length / 2 and abs(s) <= width / 2:
                out.add((x, z))
    return out


class TestFit(unittest.TestCase):
    def test_axis_aligned_boxes(self):
        f = BF(box(10, 20, 30, 8))
        self.assertAlmostEqual(f.c0, 25.0)
        self.assertAlmostEqual(f.c1, 24.0)
        self.assertAlmostEqual(f.angle, 0, places=6)
        g = BF(box(10, 20, 8, 30))                      # long axis along z: points south
        self.assertAlmostEqual(g.angle, 90, places=6)

    def test_rotated_rectangle_angle(self):
        f = BF(slanted(36, 12, 24))
        self.assertAlmostEqual(f.angle, 24, delta=1.0)
        self.assertGreater(f.ux, 0)

    def test_axis_sense_is_canonical(self):
        f = BF(slanted(36, 12, 155))                    # same line as -25 deg: the east-pointing sense is chosen
        self.assertGreater(f.ux, 0)
        self.assertAlmostEqual(f.angle, -25, delta=1.0)

    def test_override_pins_the_fit(self):
        f = BF(box(0, 0, 10, 4), centre=(5.5, 2.5), axis=(-1, 0))
        self.assertEqual((f.c0, f.c1), (5.5, 2.5))
        self.assertEqual((f.ux, f.uz), (1, 0))


class TestCoordinates(unittest.TestCase):
    def test_frame_and_world_round_trip(self):
        f = BF(slanted(36, 12, 24))
        for q in [(0, 0), (7, -3), (-12, 5)]:
            a, s = f.frame(*q)
            x, z = f.world_xz(a, s)
            self.assertAlmostEqual(x, q[0] + .5)
            self.assertAlmostEqual(z, q[1] + .5)

    def test_across_is_along_turned_toward_plus_z_side(self):
        f = BF(box(0, 0, 20, 6))
        self.assertAlmostEqual(f.frame(15, 0)[0], 5.5)           # east of centre (10, 3): along +
        self.assertAlmostEqual(f.frame(10, 5)[1], 2.5)           # south of centre: across +

    def test_rect_and_line_are_integer_world_points(self):
        f = BF(box(0, 0, 20, 6))                                 # centre (10, 3), axes aligned
        self.assertEqual(f.rect(-2, 4, -1, 1), [(8, 2), (14, 2), (14, 4), (8, 4)])
        self.assertEqual(f.line((-3, 0), (3, 2)), [(7, 3), (13, 5)])
        self.assertEqual(f.point(0, 0), (10, 3))


class TestFaces(unittest.TestCase):
    def test_nearest_side_of_default_extent(self):
        f = BF(box(0, 0, 20, 6))
        self.assertEqual(f.face_of(0, 3), 'a0')
        self.assertEqual(f.face_of(19, 3), 'a1')
        self.assertEqual(f.face_of(10, 0), 's0')
        self.assertEqual(f.face_of(10, 5), 's1')

    def test_set_back_rectangle(self):
        f = BF(box(0, 0, 20, 6))
        self.assertEqual(f.face_of(5, 3, a0=4.0), 'a0')          # a wall line moved in: x=5 is nearer it than the north/south sides


class TestEntrance(unittest.TestCase):
    def setUp(self):
        self.cells = box(0, 0, 20, 12)
        self.f = BF(self.cells)

    def test_picks_flat_pair_nearest_portal_on_face(self):
        pair = self.f.entrance_cells(self.cells, (-1.5, 8.0), 'a0')
        self.assertEqual(pair, [(0, 7), (0, 8)])

    def test_pair_runs_along_the_exposed_side(self):
        pair = self.f.entrance_cells(self.cells, (9.0, -1.5), 's0')          # north face: the pair runs along x
        self.assertEqual({q[1] for q in pair}, {0})
        self.assertEqual(abs(pair[0][0] - pair[1][0]), 1)
        self.assertEqual(self.f.jambs([(8, 0), (9, 0)]), [(7, 0), (10, 0)])

    def test_corners_are_never_treads(self):
        pair = self.f.entrance_cells(self.cells, (-5.0, -5.0), 'a0')          # portal off the north-west corner
        self.assertNotIn((0, 0), pair)
        self.assertEqual(pair, [(0, 1), (0, 2)])

    def test_jambs_either_end(self):
        self.assertEqual(self.f.jambs([(0, 7), (0, 8)]), [(0, 6), (0, 9)])
        self.assertEqual(self.f.jambs([(0, 8), (0, 7)]), [(0, 6), (0, 9)])

    def test_no_flat_run_raises(self):
        with self.assertRaises(ValueError):
            BF({(0, 0), (1, 0)}).entrance_cells({(0, 0), (1, 0)}, (0, 0), 'a0')


if __name__ == '__main__':
    unittest.main()
