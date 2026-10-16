#!/usr/bin/env python3
"""Entrances of the other 48,-44 buildings from the portal register (user, 2026-10-16): the rule is in scripts/entrances.py.

  18-A Jubilee Sports Complex "Main" (way 93729745)   38-D Staff Club "Prayer Room" (relation 2139045)
  40-A West Building "Main", 40-B "Stags" (way 34391673)
(18-A is in scripts/build_highfield_jubilee.py, 40-B in scripts/build_highfield_stags.py, 42-x in
scripts/build_highfield_susu_entrances.py / build_highfield_susu_b42.py, 57-A in scripts/build_highfield_su_retail.py.)

  python3 scripts/build_highfield_entrances_48_m44.py            # dry run + printout
  SITE_OWNER=... python3 scripts/build_highfield_entrances_48_m44.py --apply
"""
import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'scripts'))
import portals  # noqa: E402
from site_kit import Plan, World, apply, built_cells, preview  # noqa: E402
from campus import way_cells  # noqa: E402
from entrances import door, entrances  # noqa: E402

NAME = 'highfield_entrances_48_m44'
WAYS = ('93729745', '2139045', '34391673')      # Jubilee, Staff Club, West Building: a portal belongs to the nearest footprint, not
                                                # to its university building number (38-D, the Prayer Room, stands at the West Building)
DOUBLE = {'18-A', '40-A'}                       # the Main entrances
# 800 px photos: Jubilee = glazed lobby in a grey metal frame; Us. (40-A) = brick opening with dark wooden doors; Stags = white
# render with glazed doors; Prayer Room has no photo (brick building, wooden door)
STYLE = {'18-A': ('iron_door', 'gray_concrete'), '40-A': ('dark_oak_door', 'bricks'), '40-B': ('iron_door', 'white_concrete'),
         '38-D': ('dark_oak_door', 'bricks')}


def build():
    w = World()
    plan, notes = Plan(NAME), []
    footprints = {way: way_cells(way) for way in WAYS}
    for p in portals.in_cell(48, -44):
        if p['id'] in ('18-A', '40-B') or p['building'] in ('42', '57'):
            continue                                    # their own scripts (Jubilee, Stags pavilion, B42, retail)
        near = {way: min((x - p['x']) ** 2 + (z - p['z']) ** 2 for x, z in c) for way, c in footprints.items()}
        way = min(near, key=near.get)
        notes.append(f"{p['id']} -> footprint {way} ({near[way] ** 0.5:.0f} blocks)")
        if p['id'] == '40-A':          # fixed: its flush wall (5 cells out to the plane) is already in the world from the first apply
            door(plan, w, 6207, -5605, 1, 0, notes, width='double', y0=56, leaf='dark_oak_door', frame='bricks', fascia=True)
            continue
        entrances(plan, w, footprints[way], {p['id']: (p['x'], p['z'])}, notes, double=DOUBLE, flat=DOUBLE, style=STYLE)
    return plan, notes


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--apply', action='store_true')
    a = ap.parse_args()
    plan, notes = build()
    print('\n'.join(notes))
    mod = tuple(sorted({b for b, _s in built_cells(within=plan.cells).values()} - {NAME}))
    print('changes cells of', mod)
    preview(plan, ROOT / f'verification/site/{NAME}-preview.png', scale=2)
    apply(plan, dry=not a.apply, modifies=mod)
