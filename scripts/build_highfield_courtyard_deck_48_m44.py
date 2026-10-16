#!/usr/bin/env python3
"""Q-180 (cell 48,-44): timber courtyard terrace with picnic tables, west side of the Students' Union (B42)
wing, between the grass/woodland garden and the building (Google z20 sheet at 6168,-5546).

Evidence
  GOOGLE  quad of decking at ground level, corners read off the 10-block grid:
          (6165.2,-5554.7) (6177.5,-5550.0) (6170.2,-5536.4) (6160.8,-5541.8); the west third is pale beige,
          the rest brown weathered timber; seven dark picnic tables.
  LIVE    the quad is light_gray_concrete at y48 (surface type wrong, level right).
  Not evidenced: plank material -> birch (pale) and spruce (brown) planks; tables as 2 x 2 dark slabs.

  python3 scripts/build_highfield_courtyard_deck_48_m44.py            # preview + dry run
  SITE_OWNER=... python3 scripts/build_highfield_courtyard_deck_48_m44.py --apply
"""
import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'scripts'))
from site_kit import Plan, World, apply, preview  # noqa: E402
from campus import inside  # noqa: E402

NAME = 'highfield_courtyard_deck_48_m44'
QUAD = [(6165.2, -5554.7), (6177.5, -5550.0), (6170.2, -5536.4), (6160.8, -5541.8)]
LINE = ((6170.6, -5552.7), (6165.9, -5539.4))   # pale / brown boundary
TABLES = [(6167.8, -5551.3), (6166.4, -5548.3), (6164.9, -5545.2), (6163.6, -5542.3),
          (6171.1, -5549.6), (6168.8, -5545.7)]
Y = 48
PALE, BROWN, TABLE = 'birch_planks', 'spruce_planks', 'polished_deepslate_slab[type=bottom]'
OLD = ('light_gray_concrete', 'gray_concrete', 'grass_block')


def pale(x, z):
    (x0, z0), (x1, z1) = LINE
    return (x - x0) * (z1 - z0) - (z - z0) * (x1 - x0) < 0


def build():
    w = World()
    p = Plan(NAME)
    skipped = []
    for x in range(6159, 6180):
        for z in range(-5557, -5535):
            if not inside(x + .5, z + .5, QUAD):
                continue
            b = (w.block(x, Y, z) or '').replace('minecraft:', '').split('[')[0]
            above = (w.block(x, Y + 1, z) or 'air').replace('minecraft:', '')
            if b not in OLD or above not in ('air', 'cave_air', ''):
                skipped.append((x, z, b, above))
                continue
            p.set(x, Y, z, PALE if pale(x + .5, z + .5) else BROWN)
    for tx, tz in TABLES:
        for dx in (0, 1):
            for dz in (0, 1):
                q = (int(tx) + dx, Y + 1, int(tz) - 1 + dz)
                if (q[0], Y, q[2]) in p.cells:
                    p.set(*q, TABLE)
    return p, skipped


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--apply', action='store_true')
    a = ap.parse_args()
    plan, skipped = build()
    print('cells', len(plan.cells), 'skipped', len(skipped), skipped[:8])
    preview(plan, ROOT / f'verification/site/{NAME}-preview.png', scale=8)
    apply(plan, dry=not a.apply, modifies=('highfield_48_m44_ground', 'highfield_grounds_sc',
                                        'highfield_q050_opens', 'highfield_48_m44_foliage'))
