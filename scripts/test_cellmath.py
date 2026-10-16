import unittest

import cellmath as C


class CellMathTest(unittest.TestCase):
    def test_parse_cell(self):
        self.assertEqual(C.parse_cell(' 48 , -44'), (48, -44))
        for bad in ('48', '1,2,3', 'a,b', ''):
            with self.assertRaises(SystemExit):
                C.parse_cell(bad)

    def test_cell_of_and_bounds_round_trip(self):
        self.assertEqual(C.cell_of(6152, -5592), (48, -44))
        self.assertEqual(C.cell_of(-1, -1), (-1, -1))
        x0, z0, x1, z1 = C.bounds((48, -44))
        self.assertEqual((x0, z0, x1, z1), (6144, -5632, 6271, -5505))
        self.assertEqual(C.cell_of(x1, z1), (48, -44))
        self.assertEqual(C.bounds((48, -44), 8), (6136, -5640, 6279, -5497))

    def test_ring_order_is_north_centre_then_clockwise(self):
        ring = C.ring_cells(1)
        self.assertEqual(ring[0], (48, -45))                    # north centre of the ring
        self.assertEqual(ring[1], (49, -45))                    # then clockwise (east)
        self.assertEqual(len(ring), 8)
        self.assertEqual(len(set(ring)), 8)
        self.assertTrue(all(C.ring_distance(c) == 1 for c in ring))
        self.assertEqual(len(C.ring_cells(3)), 24)
        self.assertEqual(C.ring_cells(0), [C.ORIGIN_CELL])


if __name__ == '__main__':
    unittest.main()
