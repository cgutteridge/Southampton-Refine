"""Block reference: colour grouping, nearest-colour lookup, model rendering (needs the extracted assets)."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import block_reference as br  # noqa: E402

HAVE = (br.ASSETS / 'blockstates' / 'stone_bricks.json').exists()


class TestGroups(unittest.TestCase):
    def test_hue_groups(self):
        self.assertEqual(br.hue_group((200, 30, 30)), 'red')
        self.assertEqual(br.hue_group((120, 120, 120)), 'grey-mid')
        self.assertEqual(br.hue_group((20, 20, 22)), 'grey-black')
        self.assertEqual(br.hue_group((60, 160, 60)), 'green')


@unittest.skipUnless(HAVE, 'run block_reference.py extract first')
class TestRender(unittest.TestCase):
    def test_full_block_has_four_views_with_pixels(self):
        views = br.block_views('stone_bricks')
        self.assertEqual(len(views), 4)
        self.assertGreater(len(set(views[2].convert('RGB').getdata())), 10)

    def test_connecting_block_changes_with_neighbours(self):
        alone = br.faces_of('glass_pane')
        joined = br.faces_of('glass_pane', {'north': 'true', 'south': 'true'})
        self.assertGreater(len(joined), len(alone))

    def test_average_colour_is_reasonable(self):
        r, g, b = br.average_colour('white_concrete')
        self.assertGreater(min(r, g, b), 200)


if __name__ == '__main__':
    unittest.main()
