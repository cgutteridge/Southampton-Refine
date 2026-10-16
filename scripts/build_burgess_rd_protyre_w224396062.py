#!/usr/bin/env python3
"""Q-144: Protyre Autocare, 170-176 Burgess Road, OSM w224396062 (building=industrial, shop=car_repair, SO16 3HH;
~366 cells, L-shaped; NOT campus, a commercial garage; layered pass 1 of cell 50,-47; 15 Oct 2026).

Evidence: OSM footprint + tags only (no height/levels). Read as a single-storey light-grey workshop with a flat
roof (5 blocks); roof/wall colours are hints (z18 aerial blurry). Entrance door on the north wall
(Burgess Road side, road at z-5990), glazing on every 3rd wall cell. Floor from natural stone surface outside the footprint
(y56). Old Geocraft carpet blobs/walls inside the footprint and a 2-cell margin are cleared. House/building only: no garden.

  python3 scripts/build_burgess_rd_protyre_w224396062.py
  SITE_OWNER=... python3 scripts/build_burgess_rd_protyre_w224396062.py --apply
"""
import argparse
import collections
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'scripts'))
from site_kit import Plan, World, apply, preview  # noqa: E402
import osm_footprints  # noqa: E402

NAME = 'burgess_rd_protyre_w224396062'
WAY = '224396062'
N4 = ((1, 0), (-1, 0), (0, 1), (0, -1))
H = 5  # wall blocks above floor
OLD = ('light_gray_carpet', 'bricks', 'stone', 'granite', 'gray_carpet')


def nm(b):
    return (b or 'minecraft:air').split('[')[0].replace('minecraft:', '')


def build():
    idx = osm_footprints.OSMIndex()
    w = World()
    own = {c for c, i in idx.cells().items() if str(idx.buildings[i][1].get('osm_way_id')) == WAY}

    def surf(x, z):
        for y in range(80, 40, -1):
            if nm(w.block(x, y, z)) in ('stone', 'grass_block', 'dirt', 'granite'):
                return y
    ys = [surf(x + dx, z + dz) for x, z in own for dx in (-4, 4) for dz in (-4, 4)
          if (x + dx, z + dz) not in own]
    ys = [y for y in ys if y]
    fy = collections.Counter(ys).most_common(1)[0][0]
    print('ref surface counts', collections.Counter(ys).most_common(4), '-> floor y', fy)
    walls = {c for c in own if any((c[0] + dx, c[1] + dz) not in own for dx, dz in N4)}
    margin = {(x + dx, z + dz) for x, z in own for dx in range(-2, 3) for dz in range(-2, 3)} - own
    p = Plan(NAME)
    for x, z in margin:  # old carpet/walls spill outside the footprint
        for y in range(fy + 1, fy + 14):
            if nm(w.block(x, y, z)) in ('light_gray_carpet', 'bricks', 'gray_carpet', 'stone_bricks', 'smooth_stone', 'smooth_stone_slab'):
                p.set(x, y, z, 'air')
        if nm(w.block(x, fy, z)) in ('light_gray_carpet', 'bricks', 'air'):
            p.set(x, fy, z, 'stone')
    for x, z in own:
        for y in range(fy - 3, fy):
            p.set(x, y, z, 'stone')
        p.set(x, fy, z, 'spruce_planks')
        for y in range(fy + 1, fy + 16):
            p.set(x, y, z, 'air')
        wall = (x, z) in walls
        for y in range(fy + 1, fy + H + 1):
            p.set(x, y, z, 'light_gray_concrete' if wall else 'air')
        p.set(x, fy + H + 1, z, 'smooth_stone_slab[type=bottom,waterlogged=false]' if wall
              else 'smooth_stone')
        if not wall and (x % 5 == 0 and z % 5 == 0):
            p.set(x, fy + H, z, 'sea_lantern')
    # entrance: north wall cell nearest the centre x of the north arm (Burgess Road side)
    north = sorted((c for c in walls if (c[0], c[1] - 1) not in own and (c[0], c[1] + 1) in own),
                   key=lambda c: (c[1], abs(c[0] - 6496)))
    door = north[0]
    print('door', door)
    for dx in (0, 1):
        c = (door[0] + dx, door[1])
        if c not in walls:
            continue
        for half, y in (('lower', fy + 1), ('upper', fy + 2)):
            p.set(c[0], y, c[1], f'spruce_door[facing=north,half={half},hinge={"left" if dx == 0 else "right"},open=false]')
        for y in (fy + 3, fy + 4):
            p.set(c[0], y, c[1], 'glass_pane[east=true,west=true]')
        p.set(c[0], fy, c[1] - 1, 'stone_bricks')
    for x, z in sorted(walls):
        if (x, z) in ((door[0], door[1]), (door[0] + 1, door[1])):
            continue
        if (x + z) % 3 == 0:
            ax = ((x, z + 1) not in own) or ((x, z - 1) not in own)
            if ax:
                for y in (fy + 2, fy + 3):
                    p.set(x, y, z, 'glass_pane[east=true,west=true]')
            else:
                for y in (fy + 2, fy + 3):
                    p.set(x, y, z, 'glass_pane[north=true,south=true]')
    return p, own, fy


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--apply', action='store_true')
    a = ap.parse_args()
    plan, own, fy = build()
    print('cells', len(own), 'floor y', fy)
    preview(plan, ROOT / f'verification/site/{NAME}-preview.png', scale=6)
    apply(plan, dry=not a.apply, modifies=[])
