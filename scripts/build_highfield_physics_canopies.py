#!/usr/bin/env python3
"""I-058 (cell 47,-44): the two open covered entrances of the Physics & Astronomy buildings,
OSM building=roof ways 147603916 (E side of B5, bbox 6032,-5580..6040,-5569) and 154417140
(S side of Shackleton B44, bbox 6079,-5542..6089,-5531), both layer=1.

Evidence
  OSM      two 'building=roof' multipolygons (canopy, no walls) beside relations 3006924 / 3300438
           (build_highfield_shackleton_physics.py deliberately left them out: "Not built").
  LIDAR    flat deck at 58 over both (pristine carpet roof 58 on a hollow bricks shell, Geocraft
           lump); cells that rise to 61-66 along the building side are the building's own wall
           (OSM outlines overlap it) and are built as wall continuing the main build's style.
  aerial   mosaic-z18-8x8-centre-130055-87834: pale paved forecourt under a light flat canopy at
           both; no walls. User (I-058): covered entrances, stood at 6038,58,-5573 / 6084,.. .
  Not evidenced: post / ceiling detail -> concrete posts every 3rd edge cell, flat deck in the
  main build's gray_concrete, paving light_gray_concrete (same as the forecourt ground).

  python3 scripts/build_highfield_physics_canopies.py            # preview + dry-run guards
  SITE_OWNER=... python3 scripts/build_highfield_physics_canopies.py --apply
"""
import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'scripts'))
from site_kit import Plan, World, apply, preview, built_cells  # noqa: E402
from campus import way_cells, lidar_top, N4  # noqa: E402
from osm_footprints import PRISTINE  # noqa: E402

NAME = 'highfield_physics_canopies'
WAYS = ('147603916', '154417140')
DECK = 58
PAVE = 'light_gray_concrete'
WALL = 'light_gray_concrete'
ROOF = 'gray_concrete'
POST = 'light_gray_concrete'
AIR = ('air', 'cave_air', 'void_air', 'light')
LUMP = ('light_gray_carpet', 'bricks')
SOFT = ('leaves', '_log', 'fence', 'wall', 'hedge', 'bush', 'grass', 'fern', 'flower', 'tulip', 'poppy',
        'dandelion', 'azalea', 'bamboo', 'lantern', 'torch', 'chain', 'bars')


def nm(b):
    return (b or 'air').split('[')[0].replace('minecraft:', '')


def build():
    w = World()
    built = {(x, z) for x, _y, z in built_cells(exclude=(NAME,))}
    p = Plan(NAME)
    info = {}
    for way in WAYS:
        fp = way_cells(way)
        xs, zs = [q[0] for q in fp], [q[1] for q in fp]
        box = (min(xs) - 1, min(zs) - 1, max(xs) + 1, max(zs) + 1)
        top = {q: lidar_top(*q) for q in fp}

        def surf(x, z):
            for y in range(70, 40, -1):
                b = nm(w.block(x, y, z))
                if b not in AIR and not any(s in b for s in ('leaves', '_log', 'grass', 'fern')) \
                        and b not in LUMP and b != 'iron_bars':
                    return y
            return None
        # spill: lump columns outside the OSM line (carpet roof + shell the scan counts)
        spill = {(x, z) for x in range(box[0], box[2] + 1) for z in range(box[1], box[3] + 1)
                 if (x, z) not in fp and (x, z) not in built and nm(w.block(x, DECK, z)) in LUMP + ('air',)
                 and any(nm(w.block(x, y, z)) in LUMP for y in range(56, 59))}
        # floor: natural ground just outside the lump (median, lump-free, not another build's tall stuff)
        ring = []
        for x in range(box[0] - 2, box[2] + 3):
            for z in range(box[1] - 2, box[3] + 3):
                if (x, z) in fp or (x, z) in spill:
                    continue
                if nm(w.block(x, DECK, z)) in LUMP:
                    continue
                s = surf(x, z)
                if s is not None and s <= 56 and nm(w.block(x, s, z)) in ('light_gray_concrete', 'stone', 'grass_block',
                                                                        'dirt', 'gravel', 'black_wool', 'gray_concrete'):
                    ring.append(s)
        floor = sorted(ring)[len(ring) // 2]
        tall = {q for q in fp if top[q] > DECK + 1}
        canopy = fp - tall
        clear_to = max(list(top.values()) + [DECK]) + 3

        def has_open_side(q):
            return any((q[0] + dx, q[1] + dz) not in fp or (q[0] + dx, q[1] + dz) in spill for dx, dz in N4) and \
                any((q[0] + dx, q[1] + dz) not in tall for dx, dz in N4)
        for q in sorted(fp | spill):
            x, z = q
            g = surf(x, z) or floor
            for y in range(min(g, floor) + 1, clear_to + 1):          # clear lump / old stuff
                if nm(w.block(x, y, z)) not in AIR or y > floor:
                    p.set(x, y, z, 'air')
            for y in range(g + 1, floor):
                p.set(x, y, z, 'stone')
            p.set(x, floor, z, PAVE)
            if q in tall:
                for y in range(floor + 1, top[q]):
                    p.set(x, y, z, WALL)
                p.set(x, top[q], z, ROOF)
            elif q in canopy:
                if has_open_side(q) and (x + z) % 3 == 0:
                    for y in range(floor + 1, DECK):
                        p.set(x, y, z, POST)
                p.set(x, DECK, z, ROOF)
        # old decor / trees within 2 columns of the volume (re-done by the later passes)
        near = {(x + a, z + b) for x, z in fp | spill for a in range(-2, 3) for b in range(-2, 3)} - fp - spill
        removed = 0
        for x, z in near:
            if (x, z) in built and False:
                continue
            for y in range(floor + 1, DECK + 3):
                if any(s in nm(w.block(x, y, z)) for s in SOFT) and nm(w.block(x, y, z)) not in AIR:
                    p.set(x, y, z, 'air')
                    removed += 1
        info[way] = dict(fp=len(fp), tall=len(tall), spill=len(spill), floor=floor, ring_n=len(ring),
                         near_soft_removed=removed)
    p.outside_footprint_ok = 'OSM building=roof canopies (way 147603916 / 154417140): the deck lies on the OSM footprint; ' \
                             'spill columns are pavement only'
    return p, info


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--apply', action='store_true')
    a = ap.parse_args()
    plan, info = build()
    print(info)
    preview(plan, ROOT / f'verification/site/{NAME}-preview.png', scale=6)
    apply(plan, dry=not a.apply, modifies=[])
