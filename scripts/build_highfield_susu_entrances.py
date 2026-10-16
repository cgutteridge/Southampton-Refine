#!/usr/bin/env python3
"""B42 Students' Union entrances from the university portal register (user, 2026-10-16).

Positions are reference/portals (scripts/portals.py cell 48,-44); photos (look-only) give the form: a glazed door in a white
surround (42-A has a fascia sign above), a glazed shopfront (42-B, 42-C), steps with a handrail beside the Cafe door (42-D).
42-A "Concourse entrance" sits under the OSM canopy (way 391790374), a roofed recess in the NE face.

Simple rule for each portal: the nearest straight stretch of B42 wall is the door, at the height of the ground outside, with a
jamb and glass flank each side and a lintel. Only B42's own cells change: no landings, no ground, no plants (other passes).

  python3 scripts/build_highfield_susu_entrances.py            # dry run + printout
  SITE_OWNER=... python3 scripts/build_highfield_susu_entrances.py --apply
"""
import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'scripts'))
from site_kit import Plan, World, apply, preview  # noqa: E402
from campus import way_cells  # noqa: E402
from entrances import door, entrances  # noqa: E402

NAME = 'highfield_susu_entrances'
FLOORS = (48, 51, 54)                 # B42 storey floors (slab y)
WALL, GLASS = 'white_concrete', 'glass'
FACE = {(1, 0): 'east', (-1, 0): 'west', (0, 1): 'south', (0, -1): 'north'}
MODIFIES = ('highfield_susu_west', 'highfield_susu_west-lower', 'highfield_susu_west-greeblies', 'highfield_susu_west-canopyfix',
            'highfield_susu_west-holes', 'highfield_susu_west-trenchfix', 'highfield_q050_opens', 'highfield_q051_ur',
            'highfield_q054_micro', 'highfield_q054_micro-canopy-removed', 'highfield_48_m44_ground', 'highfield_grounds_sc',
            'highfield_susu_west-followups-reset', 'highfield_susu_west-membrane-spill')

w = World()
b42 = way_cells('33830305')
# 800 px portal photos: black steel frames and glass at the Union fronts (42-A, B, C), a brick-lined open passage at the Cafe (42-D)
STYLE = {'42-A': ('iron_door', 'black_concrete'), '42-B': ('iron_door', 'black_concrete'), '42-C': ('iron_door', 'black_concrete'),
         '42-D': (None, 'bricks')}


def build(world=None):
    """@param world: object with .block(x, y, z) (default the live world); the rebuild passes the new plan over the world"""
    w = world or globals()['w']
    p, notes = Plan(NAME), []
    entrances(p, w, b42, {'42-B': (6204, -5564), '42-C': (6224, -5555), '42-D': (6180, -5575)}, notes, double={'42-B'}, flat={'42-B'}, style=STYLE, check_walls=False)
    # 42-A: the concourse entrance under the canopy: carve the roofed recess (x6190-6194, z-5568..-5565) inside the building,
    # floor level with the plaza (55), door in the back wall at z-5564, the building roof (60) overhead as the canopy
    notes.append('42-A')
    for x in range(6190, 6195):
        for z in range(-5568, -5564):
            for y in range(56, 60):
                p.set(x, y, z, 'minecraft:air')
            p.set(x, 55, z, 'minecraft:polished_granite')       # recess floor level with the plaza outside
    door(p, w, 6191, -5564, 0, -1, notes, width='double', y0=56, frame='black_concrete')       # 42-A: glazed metal double doors under "The Union" fascia
    p.cells.update({(x, 60, z): 'minecraft:light_gray_concrete' for x in range(6190, 6195) for z in range(-5568, -5564)})
    return p, notes


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--apply', action='store_true')
    a = ap.parse_args()
    plan, notes = build()
    print('\n'.join(notes))
    preview(plan, ROOT / f'verification/site/{NAME}-preview.png', scale=2)
    apply(plan, dry=not a.apply, modifies=MODIFIES)
