#!/usr/bin/env python3
"""Q-030 (campus C4): engineering quarter — Lanchester B7 (relation 2922283), Engineering
Workshops B9 (221022608) + 13A (221022609), Tizard B13 (66662036), ISVR B15 (160394558),
Cochlear Implant Centre B19 (66662037), B5 (66696203), 236057339, B17 (141677991),
Underwater Tank B8 (141677994) — and the cleared site of the demolished Faraday Tower.

Evidence
  OSM      reference/osm/highfield-campus (Faraday Tower no longer mapped)
  aerial   reference/aerial/highfield-campus/mosaic-z18-8x8-centre-130055-87834.png
           B9: white saw-tooth north-light roof strips; others grey/white flat roofs.
           (The aerial pre-dates the Faraday demolition and still shows the tower.)
  LIDAR    pristine Geocraft (views/q030-survey.png): Lanchester 68/71 over 51; Tizard
           65/68; B5 61; B9 54-56 saw-tooth; ISVR 53-56; B19 48-58 stepping; B17 60-61.
           Faraday: Geocraft brick mass to y89-93 at x6445-6498 z-5690..-5630 outside
           every OSM footprint.
  photos   commons-171521131 (2025, Lanchester: 1960s grey concrete bands, blue-framed
           ribbon windows, stone-clad cantilevered lecture theatre over the road, brick
           base); -171521099 (2025, Engineering Square: white/grey modernist ribbon blocks);
           -13017064 (2008, Faraday Tower, grey concrete tower); -171521042 (2025, "site of
           the former Faraday Tower, recently demolished": fenced sandy cleared ground).

  python3 scripts/build_highfield_engineering.py            # preview + dry-run guards
  SITE_OWNER=... python3 scripts/build_highfield_engineering.py --apply
"""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'scripts'))
from site_kit import apply, preview  # noqa: E402
from campus import N4, Campus, bbox, centre, lidar_parts, lidar_top, pitched_part, way_cells, _shared  # noqa: E402

NAME = 'highfield_engineering'
CONC = dict(wall='light_gray_concrete', glass='light_blue_stained_glass', rows=(1, 2), pier=0, corner_glass=True,
            slab='gray_concrete')
BRICK = dict(wall='bricks', glass='glass', rows=(1, 2), pier=3, corner_glass=True)
SAW = dict(roof_fill='white_concrete', roof_stair='quartz_stairs', roof_ridge='quartz_slab[type=bottom]')

lan, ilan = lidar_parts('2922283', 'b7', **CONC)
tiz, _ = lidar_parts('66662036', 'b13', **CONC)
b5, _ = lidar_parts('66696203', 'b5', **CONC)
_, i9 = lidar_parts('221022608', 'b9tmp', **BRICK)
b9 = [pitched_part('b9', way_cells('221022608'), i9['ground'], smooth=0, **SAW, **BRICK)]
b13a, _ = lidar_parts('221022609', 'b13a', **BRICK)
b15, _ = lidar_parts('160394558', 'b15', **BRICK)
b19, _ = lidar_parts('66662037', 'b19', slab='white_concrete', **BRICK)
b17, _ = lidar_parts('141677991', 'b17', **BRICK)
w339, _ = lidar_parts('236057339', 'w339', **BRICK)
b8, _ = lidar_parts('141677994', 'b8', wall='light_gray_concrete', rows=())
BUILDINGS = [lan, tiz, b5, b9, b13a, b15, b19, b17, w339, b8]
PARTS = [p for b in BUILDINGS for p in b]
WAYS = ('2922283', '66662036', '66696203', '221022608', '221022609', '160394558', '66662037',
        '141677991', '236057339', '141677994')
DOORS = [(None, *centre(max(b, key=lambda p: len(p.cells))), None) for b in BUILDINGS
         if b is not b19 and b is not b17]
DOORS += [(None, 6516, -5702, None), (None, 6378, -5762, None)]   # B19 north side, B17 west (off the trees)
DOORS += [(None, 6401, -5653, None)]                       # Lanchester '7' entrance (photo 171521131)
STAIRS = [(max(b, key=lambda p: len(p.floors)).name, centre(max(b, key=lambda p: len(p.floors))))
          for b in BUILDINGS if max(len(p.floors) for p in b) > 1]


def faraday_cells():
    """Columns of the demolished Faraday Tower: connected tall (>= ground+8) Geocraft mass
    outside every OSM footprint, seeded at the y89+ core."""
    idx, _ = _shared()
    allc = idx.cells()
    tall = {}
    for x in range(6435, 6510):
        for z in range(-5700, -5615):
            if (x, z) not in allc:
                t = lidar_top(x, z)
                if t >= 57:
                    tall[(x, z)] = t
    seed = [q for q, t in tall.items() if t >= 85]
    sx0, sx1 = min(x for x, _ in seed) - 6, max(x for x, _ in seed) + 6
    sz0, sz1 = min(z for _, z in seed) - 6, max(z for _, z in seed) + 6
    comp, stack = set(seed), list(seed)
    while stack:
        x, z = stack.pop()
        for a, b in N4:
            n = (x + a, z + b)
            if n in tall and n not in comp and sx0 <= n[0] <= sx1 and sz0 <= n[1] <= sz1:
                comp.add(n)
                stack.append(n)
    return comp


FARADAY = faraday_cells()
BOX = bbox(PARTS, pad=2)
BOX = (min(BOX[0], min(x for x, _ in FARADAY) - 2), min(BOX[1], min(z for _, z in FARADAY) - 2),
       max(BOX[2], max(x for x, _ in FARADAY) + 2), max(BOX[3], max(z for _, z in FARADAY) + 2))


def faraday_site(c):
    """Clear the tower to the surrounding ground; sandy cleared site (photo 171521042)."""
    ring = {(x + a, z + b) for x, z in FARADAY for a in range(-4, 5) for b in range(-4, 5)} - FARADAY
    gs = sorted(c.terrain(*q) for q in ring if q not in c.idx.cells())
    g = gs[len(gs) // 2]
    for x, z in FARADAY:
        if (x, z) in c.part or (x, z) in c.built:
            continue
        for y in range(g - 3, g):
            c.set(x, y, z, 'stone')
        c.set(x, g, z, 'coarse_dirt')
        for y in range(g + 1, 100):
            c.set(x, y, z, 'air')
    c.faraday_ground = g


EXTRA = faraday_site


def make():
    c = Campus(NAME, PARTS, WAYS, BOX, DOORS, STAIRS, avoid_built=True, step_down_stairs=True, max_fill=2)
    c.p.outside_footprint_ok = None
    return c


def build():
    return make().build(faraday_site)


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--apply', action='store_true')
    a = ap.parse_args()
    c = make()
    plan = c.build(faraday_site)
    print('parts', {pt.name: sum(1 for q in c.part.values() if q is pt) for pt in PARTS})
    print('faraday cells', len(FARADAY), 'ground', c.faraday_ground, 'lanchester', ilan)
    print('stairs', c.stairs_at, 'doors', c.door_cells)
    preview(plan, ROOT / f'verification/site/{NAME}-preview.png', scale=2)
    print(json.dumps(plan.summary())[:300])
    apply(plan, dry=not a.apply)
