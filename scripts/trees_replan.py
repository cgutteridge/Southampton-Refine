#!/usr/bin/env python3
"""Dry plan of the trees pass for a cell that already has trees: its own old trees mask is treated as undone. Writes nothing to the world.

trees_layer.py's dry run plans against the live world, where the cell's own old trees block every column, so it cannot preview a
redo. This plans as if scripts/mask_undo.py had run (the old crowns' blocks are air, their mask positions are not owned), prints the
counts and skips, and writes the plan JSON that scripts/google_window.py plan draws over Google.

  python3 scripts/trees_replan.py --cell 48,-44 --out plan.json
"""
from __future__ import annotations

import argparse
import json
from collections import Counter

import trees_layer as tl
from cellmath import parse_cell
from ground_layer import load_masked_positions
from pass_mask import mask_path, mask_placements, read_mask
from site_kit import Plan, World


def replan(cell: tuple[int, int]):
    own = set(mask_placements(read_mask(mask_path('trees', cell)))) if mask_path('trees', cell).exists() else set()

    class Undone(World):
        def block(self, x, y, z):
            return 'minecraft:air' if (x, y, z) in own else super().block(x, y, z)

    real = tl.load_masked_positions
    tl.load_masked_positions = lambda: {p: o for p, o in load_masked_positions().items() if p not in own}
    try:
        placed, rep = tl.plan_cell(cell, Plan('replan'), Undone())
    finally:
        tl.load_masked_positions = real
    return own, placed, rep


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--cell', required=True)
    ap.add_argument('--out', help='write the plan JSON here')
    a = ap.parse_args(argv)
    cell = parse_cell(a.cell)
    own, placed, rep = replan(cell)
    print(f'old mask {len(own)} blocks -> planned {len(placed)} blocks, {len(rep["trees"])} crowns, skipped {len(rep["skipped"])}')
    print(dict(Counter(w.split(' of ')[0] if ' of ' not in w else 'voxels blocked' for *_x, w in rep['skipped'])))
    for s in rep['skipped']:
        print('  skipped', s)
    if a.out:
        json.dump({'trees': rep['trees'], 'skipped': rep['skipped']}, open(a.out, 'w'))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
