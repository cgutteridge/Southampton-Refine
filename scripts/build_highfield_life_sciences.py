#!/usr/bin/env python3
"""Q-031 (campus C5): Life Sciences B85 (relation 3176751), B32 (35683388), High Voltage
Laboratory B20 (93729744), 293165048, Nightingale B67 (30063996).

Evidence
  OSM      reference/osm/highfield-campus
  aerial   reference/aerial/highfield-campus/mosaic-z18-8x8-centre-130055-87834.png
           grey/white flat roofs with plant; B85 glazed roof-lights.
  LIDAR    pristine Geocraft (views/q031-survey.png): ground 55; B85 72-78; B32 70-73;
           B67 70-73; B20 52 → 61-62.
  photos   commons-123638288 / -171521163 (B85: silver-grey vertical cladding, glazed corner
           stair, wide steps; B32 behind: white with ribbon glazing), -5578930 (2007, B32 W
           face: full blue glass curtain wall), -123638253 / -113513366 (B67 Nightingale:
           white render, dark ribbon windows, brick plinth). B20 / 293165048: no photos.

  python3 scripts/build_highfield_life_sciences.py            # preview + dry-run guards
  SITE_OWNER=... python3 scripts/build_highfield_life_sciences.py --apply
"""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'scripts'))
from site_kit import apply, preview  # noqa: E402
from campus import Campus, bbox, centre, lidar_parts  # noqa: E402

NAME = 'highfield_life_sciences'
BRICK = dict(wall='bricks', glass='glass', rows=(1, 2), pier=3, corner_glass=True)
CLAD = dict(wall='light_gray_concrete', glass='gray_stained_glass', rows=(1, 2), pier=2, corner_glass=True,
            slab='light_gray_concrete')
CURTAIN = dict(wall='gray_concrete', glass='light_blue_stained_glass', rows=(1, 2), pier=0, corner_glass=True)
RENDER = dict(wall='white_concrete', glass='gray_stained_glass', rows=(1, 2), pier=0, corner_glass=True,
              band_block='bricks')

b85, i85 = lidar_parts('3176751', 'b85', **CLAD)
b32, _ = lidar_parts('35683388', 'b32', **CURTAIN)
g67 = lidar_parts('30063996', 'tmp')[1]['ground']
b67, _ = lidar_parts('30063996', 'b67', band=(g67 + 1, g67 + 2), **RENDER)   # brick plinth storey
b20, _ = lidar_parts('93729744', 'b20', **BRICK)
w048, _ = lidar_parts('293165048', 'w048', min_cells=4, **BRICK)
BUILDINGS = [b85, b32, b67, b20, w048]
PARTS = [p for b in BUILDINGS for p in b]
WAYS = ('3176751', '35683388', '30063996', '93729744', '293165048')
DOORS = [(None, 6318, -5800, None), (None, 6290, -5790, None), (None, 6240, -5800, None),
         (None, 6340, -5855, None), (None, 6313, -5790, None)]
STAIRS = [(max(b, key=lambda p: len(p.floors)).name, centre(max(b, key=lambda p: len(p.floors))))
          for b in BUILDINGS if max(len(p.floors) for p in b) > 1]
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
    print('b85', i85, 'stairs', c.stairs_at, 'doors', c.door_cells)
    preview(plan, ROOT / f'verification/site/{NAME}-preview.png', scale=2)
    print(json.dumps(plan.summary())[:300])
    apply(plan, dry=not a.apply)
