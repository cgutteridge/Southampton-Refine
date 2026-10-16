#!/usr/bin/env python3
"""The Stag's (Union bar), 40-B, at the south end of the West Building: a low white pavilion (user, 2026-10-16).

Evidence
  photo    portal 40-B (reference/portals, 800 px): white rendered single-storey box with a thin dark-teal flat roof edge and a
           glazed double door in a pale frame, two brick steps up to it, low white balustrade walls either side (added: 4 long, 2 high).
  Google   z20 at 6197,-5583: a narrow flat roof against the foot of the tiled range, south-east face.
  lidar    pristine roof at 59-60 at x6191-6199, z-5582..-5584 (the pavilion roof), ground 55.
The old build had only B40's brick wall running past (and a narrow door in it): that door stays as the inner door.

  python3 scripts/build_highfield_stags.py            # dry run
  SITE_OWNER=... python3 scripts/build_highfield_stags.py --apply
"""
import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'scripts'))
from site_kit import Plan, World, apply, preview  # noqa: E402
from entrances import door  # noqa: E402

NAME = 'highfield_stags'
X0, X1, Z0, Z1 = 6191, 6202, -5584, -5581      # footprint (x, z inclusive); the front faces south (z -5581)
GROUND, WALLH = 55, 4                           # ground block y, wall height: y56..59, roof at 60
w = World()


def build():
    p, notes = Plan(NAME), []
    p.outside_footprint_ok = 'Stags pavilion is unmapped in OSM: portal photo 40-B, Google z20 at 6197,-5583, lidar roof 59-60'
    for x in range(X0, X1 + 1):
        for z in range(Z0, Z1 + 1):
            edge = x in (X0, X1) or z in (Z0, Z1)
            p.set(x, GROUND, z, 'minecraft:smooth_stone')                                  # floor
            for y in range(GROUND + 1, GROUND + 1 + WALLH):
                p.set(x, y, z, 'minecraft:white_concrete' if edge else 'minecraft:air')
            p.set(x, GROUND + 1 + WALLH, z, 'minecraft:dark_prismarine' if edge else 'minecraft:light_gray_concrete')   # flat roof, teal edge
    door(p, w, 6197, Z1, 0, 1, notes, width='double', y0=GROUND + 1, leaf='iron_door', frame='white_concrete')
    for x in range(6196, 6199):                                                             # two brick steps in front of the door
        p.set(x, GROUND, Z1 + 1, 'minecraft:stone_brick_stairs[facing=north,half=bottom]')
    for x0, x1 in ((X0 - 4, X0 - 1), (X1 + 1, X1 + 4)):                                      # low white balustrade walls either side
        for x in range(x0, x1 + 1):
            for y in (GROUND + 1, GROUND + 2):
                p.set(x, y, Z1, 'minecraft:white_concrete')
    return p, notes


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--apply', action='store_true')
    a = ap.parse_args()
    plan, notes = build()
    print('\n'.join(notes))
    preview(plan, ROOT / f'verification/site/{NAME}-preview.png', scale=2)
    from site_kit import built_cells
    mod = tuple(sorted({b for b, _s in built_cells(within=plan.cells).values()} - {NAME}))
    print('changes cells of', mod)
    apply(plan, dry=not a.apply, modifies=mod + ('highfield_q061_stragglers', 'highfield_grounds_sc', 'highfield_library_b34_b18', 'highfield_susu_west',
                                              'highfield_q051_ur', 'highfield_entrances_48_m44', 'highfield_48_m44_ground',
                                              'highfield_48_m44_foliage', 'highfield_q050_opens'))
