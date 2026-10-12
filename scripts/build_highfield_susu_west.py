#!/usr/bin/env python3
"""Q-029 (campus C3): Students' Union B42 (OSM 33830305) + Compactor Store 42a (294963447),
West Building & Staff Social Centre B40 (34391673), Staff Club B38 (relation 2139045),
Blue Room (456577218).

Evidence
  OSM      reference/osm/highfield-campus
  aerial   reference/aerial/highfield-campus/mosaic-z18-8x8-centre-130055-87834.png
           B40: red-brown pitched tile roofs (campus.tiled) on the two long ranges, dark
           flat roofs on the north link; B38: white flat roofs round courtyards; B42: grey
           flat roofs with plant, stepping down the slope to the west.
  LIDAR    pristine Geocraft (survey views/q029-survey.png): B40 ground 54, ridges 63-67;
           B38 ground 55, tops 59-61; B42 ground 48 (W) .. 54, tops 53/57-58/60/62.
  photos   commons-114892434 / -123638152 / -113513149 / -7578485 (B40, the 1930s former
           Union: brown-red brick, red tile roofs, tall gabled ends with stone-framed tall
           windows, ivy); commons-24864637 (SUSU 2013 entrance: white panels + glass
           shopfront). B38 / B42 main ranges: no photo (brick as hint).
  Not built: 391790374 (small canopy, no evidence of walls).

  python3 scripts/build_highfield_susu_west.py            # preview + dry-run guards
  SITE_OWNER=... python3 scripts/build_highfield_susu_west.py --apply
"""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'scripts'))
from site_kit import apply, preview  # noqa: E402
from campus import Campus, auto_parts, bbox, centre, lidar_parts  # noqa: E402

NAME = 'highfield_susu_west'
BRICK = dict(wall='bricks', glass='glass', rows=(1, 2), pier=3, corner_glass=True)
WHITE = dict(wall='white_concrete', glass='glass', rows=(1, 2), pier=4, corner_glass=True)

b40, i40 = auto_parts('34391673', 'b40', loose=True, **BRICK)
b38, i38 = lidar_parts('2139045', 'b38', slab='white_concrete', **BRICK)
blue, _ = lidar_parts('456577218', 'blue', slab='white_concrete', **BRICK)
b42, i42 = lidar_parts('33830305', 'b42', **BRICK)
cmp_, _ = lidar_parts('294963447', 'b42a', min_cells=4, wall='gray_concrete', rows=())
PARTS = b40 + b38 + blue + b42 + cmp_
WAYS = ('34391673', '2139045', '456577218', '33830305', '294963447')
DOORS = [(None, 6200, -5600, None), (None, 6176, -5632, None), (None, 6205, -5660, None),
         (None, 6196, -5655, None), (None, 6203, -5569, None), (None, 6160, -5530, None),
         (None, 6205, -5516, None)]
STAIRS = [(p.name, centre(p)) for p in (b40[-1], b38[0], b42[0])]
BOX = bbox(PARTS, pad=2)
EXTRA = None


def make():
    return Campus(NAME, PARTS, WAYS, BOX, DOORS, STAIRS, avoid_built=True, step_down_stairs=True, max_fill=2)


def build():
    return make().build()


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--apply', action='store_true')
    a = ap.parse_args()
    c = make()
    plan = c.build()
    print('parts', {pt.name: sum(1 for q in c.part.values() if q is pt) for pt in PARTS})
    print('info', i40, i38, i42)
    print('stairs', c.stairs_at, 'doors', c.door_cells)
    preview(plan, ROOT / f'verification/site/{NAME}-preview.png', scale=2)
    print(json.dumps(plan.summary())[:300])
    apply(plan, dry=not a.apply)
