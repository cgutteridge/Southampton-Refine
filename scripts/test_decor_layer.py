"""Unit tests for decor_layer.join_pieces (no Minecraft, no world writes)."""
import unittest

import decor_layer as dl

B = 'brick_wall'


def world(grid0, grid1):
    """Live blocks from two ASCII layers (y=0 and y=1), rows along z, columns along x."""
    live = {}
    for y, grid in ((0, grid0), (1, grid1)):
        for z, row in enumerate(grid):
            for x, ch in enumerate(row):
                live[(x, y, z)] = {'G': 'minecraft:grass_block', 'B': f'minecraft:{B}',
                                   'F': 'minecraft:poppy', '_': 'minecraft:air'}[ch]
    return live


class TestJoinPieces(unittest.TestCase):
    """Joins of same-type walls and fences."""

    def setUp(self):
        self.live = world(['GGGBB', 'GB___'], ['GFB__', 'B____'])
        self.get = lambda p: self.live.get(p, 'minecraft:air')
        self.can = lambda p: p[1] in (0, 1) and 0 <= p[0] <= 4 and 0 <= p[2] <= 1 and \
            dl.is_air(self.get(p))

    def pieces(self):
        return {p: B for p, b in self.live.items() if b == f'minecraft:{B}'}

    def test_example_joins_everything_with_one_block_per_join(self):
        """Pass 1 adds two stacked blocks, pass 2 exactly one of the two diagonal spots."""
        found = {p: B for p, b in self.pieces().items() if p[1] == 0}
        found[(2, 1, 0)] = B
        found[(0, 1, 1)] = B
        added = dl.join_pieces(found, self.get, self.can)
        self.assertEqual(set(added), {(3, 1, 0), (1, 1, 1), (1, 1, 0)})

    def test_prefers_supported_candidate(self):
        """(2,1,1) floats over air, (1,1,0) sits on grass: the grass one wins."""
        added = dl.join_pieces({(2, 1, 0): B, (1, 1, 1): B}, self.get, self.can)
        self.assertEqual(added, {(1, 1, 0): B})

    def test_diagonal_only_is_disjoint_and_other_type_not_joined(self):
        """A different block type between two walls is not bridged."""
        found = {(0, 1, 0): B, (2, 1, 0): 'iron_bars'}
        self.assertEqual(dl.join_pieces(found, self.get, self.can), {})

    def test_cannot_replace_grass(self):
        """Only air and flowers may be replaced."""
        live = world(['GGG'], ['B_B'])
        live[(1, 1, 0)] = 'minecraft:stone'
        found = {(0, 1, 0): B, (2, 1, 0): B}
        self.assertEqual(dl.join_pieces(found, lambda p: live.get(p, 'minecraft:air'),
                                        lambda p: dl.is_air(live.get(p, 'minecraft:air'))), {})


if __name__ == '__main__':
    unittest.main()
