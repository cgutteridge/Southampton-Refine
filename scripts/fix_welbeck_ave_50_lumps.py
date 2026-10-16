#!/usr/bin/env python3
"""I-057 cell 50,-42 follow-up to build_welbeck_ave_50_lumps (applied 2026-10-15): the first apply left
(a) Geocraft brick remnants in house fringes (retexed to lawn) and (b) one house whose stoop sat 2 above the
ground in front (door unreachable): door steps down. Both rules are now in the build script itself.
Applies to the LIVE world as it is now; the original plan is read from verification/site/welbeck_ave_50_lumps-planned.json.
"""
import argparse
import json
import sys
from pathlib import Path

from script_env import ROOT  # noqa: E402
import osm_footprints  # noqa: E402
from site_kit import Plan, World, apply, built_cells, preview  # noqa: E402
import build_welbeck_ave_50_lumps as B  # noqa: E402

NAME = 'welbeck_ave_50_lumps_fix'
F = {'north': (0, -1), 'south': (0, 1), 'west': (-1, 0), 'east': (1, 0)}


def build():
    w = World()
    p = Plan(NAME)
    pl = json.loads((ROOT / 'verification/site/welbeck_ave_50_lumps-planned.json').read_text())
    idx = osm_footprints.OSMIndex()
    osm = set(idx.cells())
    owner_cells = {q for q, i in idx.cells().items() if str(idx.buildings[i][1].get('osm_way_id')) in B.WAYS}
    foreign = osm - owner_cells
    others = built_cells(exclude=(B.NAME, NAME, 'highfield_50_m42_ground', 'highfield_50_m42_trees', 'highfield_50_m42_decor',
                                  'highfield_49_m42_ground', 'highfield_51_m42_ground'))
    cols = {(int(k.split(',')[0]), int(k.split(',')[2])) for k in pl}
    nb = 0
    for (x, z) in cols:
        if (x, z) in osm:
            continue
        for y in range(40, 62):
            if (w.block(x, y, z) or '').split('[')[0] == 'minecraft:bricks' and f'{x},{y},{z}' not in pl and (x, y, z) not in others:
                p.set(x, y, z, 'grass_block')
                nb += 1
    ns = 0
    for k, st in pl.items():
        if 'spruce_door' in st and 'half=lower' in st:
            x, y, z = map(int, k.split(','))
            fx, fz = F[st.split('facing=')[1].split(',')[0].split(']')[0]]
            b = y - 1
            fo = B.FACE[(-fx, -fz)]
            old = [(x + fx * k, yy, z + fz * k) for k in range(1, 7) for yy in range(b - 3, b)
                   if (w.block(x + fx * k, yy, z + fz * k) or '') == 'minecraft:smooth_stone']
            for (sx, sy, sz) in old:                      # first fix laid full-block steps: a player cannot walk UP onto those in site_walk
                p.set(sx, sy, sz, f'stone_stairs[facing={fo},half=bottom]')
            if old:
                p.set(x + fx, b, z + fz, f'stone_stairs[facing={fo},half=bottom]')
                ns += len(old)
                continue
            ns += B.door_steps(p.set, lambda cx, cz: next((yy for yy in range(b + 2, 40, -1)
                                                           if (w.block(cx, yy, cz) or 'minecraft:air').split('[')[0] not in
                                                           ('minecraft:air', 'minecraft:cave_air') and 'leaves' not in w.block(cx, yy, cz)
                                                           and '_log' not in w.block(cx, yy, cz) and 'grass[' not in w.block(cx, yy, cz)
                                                           and 'short_grass' not in w.block(cx, yy, cz)), 41),
                               (x + fx, z + fz), (fx, fz), owner_cells | foreign, b)
    print('stray bricks ->grass', nb, 'door steps', ns)
    p.outside_footprint_ok = 'follow-up of build_welbeck_ave_50_lumps: stoop steps on lawn beside the OSM footprints'
    return p


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--apply', action='store_true')
    a = ap.parse_args()
    plan = build()
    preview(plan, ROOT / f'verification/site/{NAME}-preview.png', scale=4)
    apply(plan, dry=not a.apply, modifies=('highfield_50_m42_ground', 'highfield_50_m42_trees', 'highfield_50_m42_decor', B.NAME))
