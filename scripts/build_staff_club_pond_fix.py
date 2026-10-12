#!/usr/bin/env python3
"""Staff Club B38 courtyard pond: level the water surface and clean the plaza rim.

Geocraft left the east shelf of the pond one block low (water at y54, air at y55)
while the west side is full to y55 — it reads broken from the white paving. This
plan fills those cells and replaces stone/granite coping beside polished diorite
with matching plaza blocks.

  python3 scripts/build_staff_club_pond_fix.py
  SITE_OWNER=... python3 scripts/build_staff_club_pond_fix.py --apply
"""
import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'scripts'))

from site_kit import Plan, World, apply, bid, preview  # noqa: E402

NAME = 'staff_club_pond_fix'
POND_X = range(6216, 6228)
POND_Z = range(-5694, -5682)
RIM_PAD = range(6214, 6230), range(-5696, -5680)
PLAZA = ('polished_diorite', 'white_concrete', 'polished_granite', 'smooth_stone')
RIM = ('stone', 'granite', 'cobblestone')


def _is_water(w: World, x: int, y: int, z: int) -> bool:
    b = w.block(x, y, z) or ''
    return bid(b) == 'minecraft:water'


def _is_plaza(w: World, x: int, z: int, y: int = 55) -> bool:
    b = w.block(x, y, z) or ''
    return any(p in b for p in PLAZA)


def _is_rim_block(w: World, x: int, y: int, z: int) -> bool:
    b = bid(w.block(x, y, z) or 'minecraft:air')
    return any(b.endswith(r) for r in RIM)


def build_plan() -> Plan:
    """Build the pond levelling and rim plan from the live world.

    @returns: kit Plan ready for preview/apply
    """
    w = World()
    p = Plan(NAME)
    for x in POND_X:
        for z in POND_Z:
            if _is_water(w, x, 54, z) and bid(w.block(x, 55, z) or 'minecraft:air') == 'minecraft:air':
                p.set(x, 55, z, 'water[level=0]')
    rx, rz = RIM_PAD
    for x in rx:
        for z in rz:
            if not _is_rim_block(w, x, 55, z):
                continue
            touches_plaza = any(_is_plaza(w, x + dx, z + dz) for dx, dz in
                                ((1, 0), (-1, 0), (0, 1), (0, -1)))
            touches_water = any(_is_water(w, x + dx, y, z + dz)
                                for dx, dz in ((1, 0), (-1, 0), (0, 1), (0, -1))
                                for y in (54, 55))
            if touches_plaza and touches_water:
                p.set(x, 55, z, 'polished_diorite')
                if _is_rim_block(w, x, 54, z) and not _is_water(w, x, 54, z):
                    p.set(x, 54, z, 'polished_diorite')
    return p


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--apply', action='store_true')
    args = ap.parse_args()
    plan = build_plan()
    print(f'{NAME}: {len(plan.cells)} cells')
    preview(plan, ROOT / f'verification/site/{NAME}-preview.png', scale=2)
    apply(plan, dry=not args.apply)
