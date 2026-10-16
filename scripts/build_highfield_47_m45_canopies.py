#!/usr/bin/env python3
"""I-055 / I-057 (cell 47,-45): the two covered walkways Geocraft had rasterised into solid lumps.

OSM building=roof ways (layer=1, no walls):
  219899639  University Service Road West, diagonal walkway bbox 6050,-5708..6059,-5691 (deck y54, floor y50)
  154067444  unnamed street, bbox 6136,-5747..6141,-5739 (deck y58, floor from natural ground); this is the
             'junk mass' of I-055 (user stood on it at 6139,58,-5741): a canopy, not a tree.
Same method as build_highfield_physics_canopies.py (I-058): open flat canopy deck gray_concrete at the
LIDAR deck height, paved floor from natural ground outside the lump, concrete posts every 3rd open-edge
cell, lump spill columns (Geocraft carpet+brick outside the OSM line whose LIDAR top is at deck height)
decked too, other spill paved. Cells of the lump that LIDAR shows well above the deck (stub of the
neighbouring tower) are cleared to canopy, not left as a pillar. Cells owned by other builds are never touched.
No plain dirt.

  python3 scripts/build_highfield_47_m45_canopies.py            # dry-run guards + preview
  SITE_OWNER=... python3 scripts/build_highfield_47_m45_canopies.py --apply
"""
import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'scripts'))
from site_kit import Plan, World, apply, preview, built_cells  # noqa: E402
from campus import way_cells, lidar_top, N4  # noqa: E402

NAME = 'highfield_47_m45_canopies'
WAYS = {'219899639': 54, '154067444': 58}      # way -> deck y (LIDAR)
PAVE = 'light_gray_concrete'
ROOF = 'gray_concrete'
POST = 'light_gray_concrete'
AIR = ('air', 'cave_air', 'void_air', 'light')
LUMP = ('light_gray_carpet', 'bricks')
SOFT = ('leaves', '_log', 'fence', 'wall', 'hedge', 'bush', 'grass', 'fern', 'flower', 'tulip', 'poppy',
        'dandelion', 'azalea', 'bamboo', 'lantern', 'torch', 'chain', 'bars')
GROUND = ('light_gray_concrete', 'stone', 'grass_block', 'gravel', 'black_wool', 'gray_concrete',
          'coarse_dirt', 'dirt', 'smooth_stone', 'black_concrete', 'granite')


def nm(b):
    return (b or 'air').split('[')[0].replace('minecraft:', '')


def build():
    w = World()
    built = {(x, z) for x, _y, z in built_cells(exclude=(NAME,))}
    p = Plan(NAME)
    info = {}

    def surf(x, z, hi):
        for y in range(hi, 40, -1):
            b = nm(w.block(x, y, z))
            if b not in AIR and not any(s in b for s in ('leaves', '_log', 'grass', 'fern')) \
                    and b not in LUMP and b != 'iron_bars':
                return y
        return None
    for way, DECK in WAYS.items():
        fp = {q for q in way_cells(way) if q not in built}
        xs, zs = [q[0] for q in fp], [q[1] for q in fp]
        box = (min(xs) - 2, min(zs) - 2, max(xs) + 2, max(zs) + 2)
        top = {q: lidar_top(*q) for q in fp}
        spill = {(x, z) for x in range(box[0], box[2] + 1) for z in range(box[1], box[3] + 1)
                 if (x, z) not in fp and (x, z) not in built
                 and nm(w.block(x, DECK, z)) in LUMP + ('air',)
                 and any(nm(w.block(x, y, z)) in LUMP for y in range(DECK - 3, DECK + 1))
                 and nm(w.block(x, DECK + 1, z)) in AIR}
        lump = fp | spill
        ring = []
        for x in range(box[0] - 2, box[2] + 3):
            for z in range(box[1] - 2, box[3] + 3):
                if (x, z) in lump or nm(w.block(x, DECK, z)) in LUMP:
                    continue
                s = surf(x, z, DECK - 2)
                if s is not None and nm(w.block(x, s, z)) in GROUND and nm(w.block(x, s + 1, z)) in AIR + ('short_grass',):
                    ring.append(s)
        floor = sorted(ring)[len(ring) // 2]
        deck = set(fp)
        for q in spill:
            t = lidar_top(*q)
            if abs(t - DECK) <= 1:
                deck.add(q)
        clear_to = max(list(top.values()) + [DECK]) + 3
        stub = {q for q in fp if top[q] > DECK + 1}

        def open_side(q):
            return any((q[0] + dx, q[1] + dz) not in deck for dx, dz in N4)
        npost = 0
        for q in sorted(lump):
            x, z = q
            g = surf(x, z, clear_to) or floor
            for y in range(min(g, floor) + 1, clear_to + 1):
                if nm(w.block(x, y, z)) not in AIR or y > floor:
                    p.set(x, y, z, 'air')
            for y in range(g + 1, floor):
                p.set(x, y, z, 'stone')
            p.set(x, floor, z, PAVE)
            if q in deck:
                if open_side(q) and (x + z) % 3 == 0:
                    for y in range(floor + 1, DECK):
                        p.set(x, y, z, POST)
                    npost += 1
                p.set(x, DECK, z, ROOF)
        near = {(x + a, z + b) for x, z in lump for a in range(-2, 3) for b in range(-2, 3)} - lump - built
        removed = 0
        for x, z in near:
            for y in range(floor + 1, DECK + 3):
                if nm(w.block(x, y, z)) not in AIR and any(s in nm(w.block(x, y, z)) for s in SOFT):
                    p.set(x, y, z, 'air')
                    removed += 1
        info[way] = dict(fp=len(fp), spill=len(spill), deck=len(deck), stub=sorted(stub), floor=floor,
                         ring_n=len(ring), posts=npost, near_soft_removed=removed, built_skipped=len(way_cells(way)) - len(fp))
    p.outside_footprint_ok = 'OSM building=roof canopies (ways 219899639 / 154067444): deck on the OSM footprint; spill is the Geocraft lump width'
    return p, info


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--apply', action='store_true')
    a = ap.parse_args()
    plan, info = build()
    for k, v in info.items():
        print(k, v)
    preview(plan, ROOT / f'verification/site/{NAME}-preview.png', scale=6)
    apply(plan, dry=not a.apply, modifies=[])
