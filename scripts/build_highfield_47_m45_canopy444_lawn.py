#!/usr/bin/env python3
"""I-055 (cell 47,-45): w154067444 is a tree on a lawn strip, not a canopy (registered Google aerial).

Removes the y58 deck canopy (deck, posts, floor, stub clearing) built by build_highfield_47_m45_canopies.py
and puts back the ground the ground layer would plan there (grass_block lawn / paving from the z19 aerial + OSM,
LIDAR surface), by running ground_layer.plan_cell with the canopy's columns released, and keeping only the
plan cells inside the box below that differ from the live world. The other canopy (w219899639, deck y54) is
never touched. The tree itself comes from trees_layer afterwards.

  .venv/bin/python scripts/build_highfield_47_m45_canopy444_lawn.py            # dry-run
  SITE_OWNER=... .venv/bin/python scripts/build_highfield_47_m45_canopy444_lawn.py --apply
"""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'scripts'))
from ground_layer import bare, load_masked_positions  # noqa: E402
from site_kit import Plan, World, apply  # noqa: E402

# 'highfield_grounds_' prefix: ground-surface builds are not owners for later ground/trees passes.
NAME = 'highfield_grounds_47_m45_canopy444_lawn'
CELL = (47, -45)
CANOPY = 'highfield_47_m45_canopies'
FLOOR, DECK = 53, 58             # canopy floor / deck y (lawn is one block lower, y52)


def lawn_columns(cols):
    """Columns of the removed canopy that the registered Google aerial shows as lawn / crown (green)."""
    import numpy as np
    from PIL import Image
    import aerial_registered as ar
    reg, A = ar.load(ROOT / 'reference/aerial/highfield-user/googlemaps-music-law-annex-2026-10-15.registration.json')
    im = np.asarray(Image.open(ROOT / 'reference' / reg['image']).convert('RGB')).astype(float) / 255
    r = max(1, int(reg['px_per_block'] / 4))
    out = set()
    for x, z in cols:
        u, v = ar.to_px(A, x + .5, z + .5)
        u, v = int(u), int(v)
        w = im[v - r:v + r + 1, u - r:u + r + 1].reshape(-1, 3).mean(0)
        if w[1] > w[0] + 0.02 and w[1] >= w[2]:
            out.add((x, z))
    return out


def build():
    """Remove every canopy block above the floor; lawn columns (aerial green, not Building 2) become grass_block at y52."""
    w = World()
    planned = json.loads((ROOT / f'verification/site/{CANOPY}-planned.json').read_text())
    pos = [tuple(int(v) for v in k.split(',')) for k in planned]
    pos = [q for q in pos if q[0] >= 6130]
    cols = sorted({(x, z) for x, _y, z in pos})
    p = Plan(NAME)
    masked = load_masked_positions()
    # canopy blocks: the planned non-air blocks that are still there (deck, posts); everything above floor
    for (x, y, z), st in ((q, planned[f'{q[0]},{q[1]},{q[2]}']) for q in pos):
        live = bare(w.block(x, y, z))
        if st != 'minecraft:air' and y > FLOOR and live == bare(st):
            p.set(x, y, z, 'air')
    cand = [c for c in cols if bare(w.block(c[0], FLOOR, c[1])) == 'minecraft:light_gray_concrete'
            and bare(w.block(c[0], FLOOR + 1, c[1])) == 'minecraft:air']
    lawn = {q for q in lawn_columns(cand) if bare(w.block(q[0], FLOOR, q[1])) == 'minecraft:light_gray_concrete'}
    for x, z in sorted(lawn):
        if any((x, y, z) in masked for y in (FLOOR - 1, FLOOR)):
            raise SystemExit(f'masked {x},{z}')
        p.set(x, FLOOR, z, 'air')
        p.set(x, FLOOR - 1, z, 'grass_block')
    p.outside_footprint_ok = 'ground surface only, in the columns of the removed w154067444 canopy'
    return p, lawn, cols


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--apply', action='store_true')
    a = ap.parse_args()
    plan, lawn, cols = build()
    from collections import Counter
    print('cells', len(plan.cells), Counter(plan.cells.values()).most_common(), 'lawn cols', len(lawn))
    for z in range(min(c[1] for c in cols), max(c[1] for c in cols) + 1):
        print(z, ''.join('g' if (x, z) in lawn else ('.' if (x, z) in cols else ' ')
                         for x in range(min(c[0] for c in cols), max(c[0] for c in cols) + 1)))
    apply(plan, dry=not a.apply, modifies=[CANOPY])
