import unittest

from oakdene_court import runs, window_slots


class WindowSlotsTest(unittest.TestCase):
    def test_short_runs_have_no_windows(self):
        self.assertEqual([window_slots(n) for n in (0, 1, 2)], [[], [], []])

    def test_three_cells_get_one_centred_pane(self):
        self.assertEqual(window_slots(3), [1])

    def test_pairs_are_centred_with_a_solid_flank_each_end(self):
        self.assertEqual(window_slots(4), [1, 2])
        self.assertEqual(window_slots(8), [1, 2, 5, 6])
        for n in range(3, 40):
            slots = window_slots(n)
            self.assertGreaterEqual(min(slots), 1)
            self.assertLessEqual(max(slots), n - 2)


class RunsTest(unittest.TestCase):
    def test_runs_split_on_gaps_and_on_wall_line_jogs(self):
        cells = [(5, 0), (5, 1), (5, 2), (5, 4), (6, 5)]        # d = W: wall lines are x, runs go along z
        found = sorted(sorted(r) for r in runs(cells, 'W'))
        self.assertEqual(found, [[(5, 0), (5, 1), (5, 2)], [(5, 4)], [(6, 5)]])


if __name__ == '__main__':
    unittest.main()
