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
import portals  # noqa: E402
from site_kit import Plan, World, apply, preview  # noqa: E402
from campus import way_cells  # noqa: E402

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


def top(x, z):
    """Highest solid, non-foliage block of a column (y)."""
    for y in range(75, 45, -1):
        b = (w.block(x, y, z) or 'minecraft:air').split('[')[0][10:]
        if b not in ('air', 'cave_air') and 'leaves' not in b and 'log' not in b and 'trapdoor' not in b:
            return y
    return 48


def wall_cell(px, pz, n=2):
    """Nearest straight stretch of B42 wall to the portal: a cell whose 2n+1 neighbours along the wall are all wall with open
    air outside the same way, so the door faces out of the wall and its frame runs along it (a stepped diagonal wall has no
    such stretch except on its flat steps). Returns (x, z, dx, dz)."""
    best = None
    for (x, z) in b42:
        for dx, dz in FACE:
            ax, az = abs(dz), abs(dx)
            run = [(x + k * ax, z + k * az) for k in range(-n, n + 1)]
            if all(c in b42 and (c[0] + dx, c[1] + dz) not in b42 for c in run):
                d = (x - px) ** 2 + (z - pz) ** 2
                if best is None or d < best[0]:
                    best = (d, x, z, dx, dz)
    if best is None:
        return wall_cell(px, pz, n - 1) if n > 1 else None
    return best[1:]


def door(p, x, z, dx, dz, notes, y0=None):
    """A framed double-glazed door at wall cell (x, z) facing (dx, dz): door at the height of the ground outside (so the
    entrance is level with what is there; ground and steps belong to the ground pass and are never touched), a glass flank
    and a white jamb each side, a lintel, and a threshold block inside. Only B42's own cells change."""
    face = FACE[(dx, dz)]
    y0 = y0 or top(x + dx, z + dz) + 1
    ax, az = abs(dz), abs(dx)                        # along the wall
    p.set(x, y0, z, f'minecraft:dark_oak_door[facing={face},half=lower,hinge=left,open=false]')
    p.set(x, y0 + 1, z, f'minecraft:dark_oak_door[facing={face},half=upper,hinge=left,open=false]')
    for s in (-1, 1):
        for k, blk in ((1, GLASS), (2, WALL)):
            for yy in (y0, y0 + 1):
                p.set(x + s * ax * k, yy, z + s * az * k, blk)
    for k in (-2, -1, 0, 1, 2):
        p.set(x + k * ax, y0 + 2, z + k * az, WALL)
    p.set(x - dx, y0 - 1, z - dz, 'minecraft:smooth_stone')       # floor inside, level with the door
    for yy in (y0, y0 + 1):
        p.set(x - dx, yy, z - dz, 'minecraft:air')
    notes.append(f'door at {x},{y0},{z} facing {face}, ground outside {y0 - 1}')


def build():
    p, notes = Plan(NAME), []
    for pid, (px, pz) in {'42-B': (6204, -5564), '42-C': (6224, -5555), '42-D': (6180, -5575)}.items():
        x, z, dx, dz = wall_cell(px, pz)
        notes.append(f'{pid}: portal {px},{pz}, wall cell {x},{z} outward {FACE[(dx, dz)]}, {abs(x - px) + abs(z - pz)} blocks from the portal')
        notes.append(pid)
        door(p, x, z, dx, dz, notes)
    # 42-A: the concourse entrance under the canopy: carve the roofed recess (x6190-6194, z-5568..-5565) inside the building,
    # floor level with the plaza (55), door in the back wall at z-5564, the building roof (60) overhead as the canopy
    notes.append('42-A')
    for x in range(6190, 6195):
        for z in range(-5568, -5564):
            for y in range(56, 60):
                p.set(x, y, z, 'minecraft:air')
            p.set(x, 55, z, 'minecraft:polished_granite')       # recess floor level with the plaza outside
    door(p, 6192, -5564, 0, -1, notes, y0=56)
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
