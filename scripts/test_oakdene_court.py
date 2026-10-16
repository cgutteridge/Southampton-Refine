import unittest

from oakdene_court import diagonal_chains, pair_slots, runs, single_slots


class PairSlotsTest(unittest.TestCase):
    def test_runs_too_short_for_a_pair_have_none(self):
        self.assertEqual([pair_slots(n) for n in (0, 1)], [[], []])

    def test_the_8_cell_front_is_WW_BB_WW(self):
        self.assertEqual(pair_slots(8), [(0, 1), (3, 4), (6, 7)])          # middle pair is the balcony on the entrance face

    def test_pairs_have_one_cell_piers_and_stay_inside_the_run(self):
        for n in range(2, 40):
            slots = pair_slots(n)
            self.assertTrue(slots)
            self.assertGreaterEqual(slots[0][0], 0)
            self.assertLessEqual(slots[-1][1], n - 1)
            for a, b in zip(slots, slots[1:]):
                self.assertEqual(b[0] - a[1], 2)

    def test_group_is_centred(self):
        self.assertEqual(pair_slots(4), [(1, 2)])


class RunsTest(unittest.TestCase):
    def test_runs_split_on_gaps_and_on_wall_line_jogs(self):
        cells = [(5, 0), (5, 1), (5, 2), (5, 4), (6, 5)]        # d = W: wall lines are x, runs go along z
        found = sorted(sorted(r) for r in runs(cells, 'W'))
        self.assertEqual(found, [[(5, 0), (5, 1), (5, 2)], [(5, 4)], [(6, 5)]])


class DiagonalChainsTest(unittest.TestCase):
    def test_a_staircase_is_one_chain_and_a_lone_corner_is_none(self):
        stairs = [(0, 0), (1, 1), (2, 2), (3, 3)]
        self.assertEqual(diagonal_chains(stairs + [(10, 10)]), [stairs])

    def test_both_diagonal_directions(self):
        up = [(0, 3), (1, 2), (2, 1)]
        down = [(5, 0), (6, 1)]
        self.assertEqual(sorted(diagonal_chains(up + down)), sorted([up, down]))


class SingleSlotsTest(unittest.TestCase):
    def test_one_window_every_third_cell_centred(self):
        self.assertEqual(single_slots(8), [0, 3, 6])
        self.assertEqual(single_slots(2), [0])

    def test_never_more_than_a_third_of_the_cells_plus_one(self):
        for n in range(2, 30):
            slots = single_slots(n)
            self.assertLessEqual(len(slots), (n + 2) // 3)
            self.assertGreaterEqual(min(slots), 0)
            self.assertLessEqual(max(slots), n - 1)


if __name__ == '__main__':
    unittest.main()
