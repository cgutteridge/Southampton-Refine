#!/usr/bin/env python3
"""Q-147: Mr Wang Hot Pot, 180 Burgess Road, OSM w148590577 (amenity=restaurant, cuisine=asian, building=yes;
layered pass 1 of cell 50,-47; 15 Oct 2026).

Evidence: OSM footprint + tags only (no height/levels; z18 aerial blurry, roof colour hint only). Read as a single-storey
restaurant in a shop terrace: brick walls, flat slab roof, shopfront glazing + door on the north (Burgess Road pavement,
z<=-5991). Floor y54 from natural stone surface outside the footprint. Old Geocraft light_gray carpet stacks inside the
footprint (to y58-62) are cleared; other OSM buildings' cells (west/east) left alone. Building only: no garden.
"""
import argparse
import collections
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'scripts'))
from site_kit import Plan, World, apply, preview  # noqa: E402
import osm_footprints  # noqa: E402

NAME = 'burgess_rd_180_w148590577'
WAY = '148590577'
N4 = ((1, 0), (-1, 0), (0, 1), (0, -1))
H = 4  # wall blocks above floor
OLD = ('light_gray_carpet', 'bricks', 'stone', 'granite', 'gray_carpet')


def nm(b):
    return (b or 'minecraft:air').split('[')[0].replace('minecraft:', '')


def build():
    idx = osm_footprints.OSMIndex()
    w = World()
    cells = idx.cells()
    own = {c for c, i in cells.items() if str(idx.buildings[i][1].get('osm_way_id')) == WAY}
    others = set(cells) - own

    def surf(x, z):
        for y in range(80, 40, -1):
            if nm(w.block(x, y, z)) in ('stone', 'grass_block', 'dirt', 'granite'):
                return y
    ys = [surf(x + dx, z + dz) for x, z in own for dx in (-4, 4) for dz in (-4, 4)
          if (x + dx, z + dz) not in cells]
    ys = [y for y in ys if y]
    fy = collections.Counter(ys).most_common(1)[0][0]
    print('ref surface counts', collections.Counter(ys).most_common(4), '-> floor y', fy)
    walls = {c for c in own if any((c[0] + dx, c[1] + dz) not in own for dx, dz in N4)}
    margin = {(x + dx, z + dz) for x, z in own for dx in range(-1, 2) for dz in range(-1, 2)} - own - others
    p = Plan(NAME)
    for x, z in margin:
        for y in range(fy + 1, fy + 14):
            if nm(w.block(x, y, z)) in ('lime_carpet', 'light_gray_carpet', 'gray_carpet', 'bricks'):
                p.set(x, y, z, 'air')
        if nm(w.block(x, fy, z)) in ('lime_carpet', 'light_gray_carpet', 'bricks', 'air'):
            p.set(x, fy, z, 'stone')
    for x, z in own:
        for y in range(fy - 3, fy):
            p.set(x, y, z, 'stone')
        p.set(x, fy, z, 'spruce_planks')
        for y in range(fy + 1, fy + 16):
            p.set(x, y, z, 'air')
        wall = (x, z) in walls
        for y in range(fy + 1, fy + H + 1):
            p.set(x, y, z, 'bricks' if wall else 'air')
        p.set(x, fy + H + 1, z, 'stone_brick_slab[type=bottom,waterlogged=false]' if wall else 'stone_bricks')
        if not wall and (x % 3 == 0 and z % 3 == 0):
            p.set(x, fy + H, z, 'sea_lantern')
    # road (north) side: wall cells with no building cell to the north
    north = sorted(c for c in walls if (c[0], c[1] - 1) not in cells and c[1] <= min(z for _, z in own) + 3)
    print('north wall cells', north)
    door = min(north, key=lambda c: abs(c[0] - (min(x for x, _ in north) + max(x for x, _ in north)) // 2))
    print('door', door)
    for half, y in (('lower', fy + 1), ('upper', fy + 2)):
        p.set(door[0], y, door[1], f'spruce_door[facing=north,half={half},hinge=left,open=false]')
    p.set(door[0], fy + 3, door[1], 'glass_pane[east=true,west=true]')
    p.set(door[0], fy, door[1] - 1, 'stone_bricks')
    for x, z in north:  # shopfront glazing
        if abs(x - door[0]) >= 1 and x not in (min(c[0] for c in north), max(c[0] for c in north)):
            for y in (fy + 2, fy + 3):
                p.set(x, y, z, 'glass_pane[east=true,west=true]')
    return p, own, fy


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--apply', action='store_true')
    a = ap.parse_args()
    plan, own, fy = build()
    print('cells', len(own), 'floor y', fy)
    preview(plan, ROOT / f'verification/site/{NAME}-preview.png', scale=6)
    apply(plan, dry=not a.apply, modifies=[])
