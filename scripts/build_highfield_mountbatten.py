#!/usr/bin/env python3
"""Q-033 (campus C7): Mountbatten B53 (relation 2967245), Zepler B59 (27743656), Gower B60
(30064096), B1 (35683386), B16 (35683387), small blocks 249342647, 862836598, 1002066983,
guardhouse 1026518808.

Evidence
  OSM      reference/osm/highfield-campus
  aerial   reference/aerial/highfield-campus/mosaic-z18-8x8-centre-130055-87834.png
           white/grey flat roofs with plant; Gower a long curved strip on Salisbury Rd.
  LIDAR    pristine Geocraft (views/q033-survey.png): B53 58 → 69/76-77; B59 57 → 71;
           B60 57 → 62/69; B1 55 → 63; B16 55 → 64/67.
  photos   commons-8457501 (B53/B59: white with horizontal louvres, green panels),
           -123638194 (New Zepler on Salisbury Rd: white render, punched dark windows),
           -154577598 (2021 Gower: white blocks, full-height glazed stair tower),
           -104745586 (Salisbury Rd: white/grey ranges with green-accented glazing).
  Not built: 224489179 / 391790378 (no LIDAR height).

  python3 scripts/build_highfield_mountbatten.py            # preview + dry-run guards
  SITE_OWNER=... python3 scripts/build_highfield_mountbatten.py --apply
"""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'scripts'))
from site_kit import apply, preview  # noqa: E402
from campus import Campus, bbox, centre, lidar_parts  # noqa: E402

NAME = 'highfield_mountbatten'
WHITE = dict(wall='white_concrete', glass='gray_stained_glass', rows=(1, 2), pier=2, corner_glass=True)
LOUVRE = dict(wall='white_concrete', glass='light_gray_stained_glass', rows=(1, 2), pier=0, corner_glass=True)
BRICK = dict(wall='bricks', glass='glass', rows=(1, 2), pier=3, corner_glass=True)
SHED = dict(wall='gray_concrete', rows=())

b53, i53 = lidar_parts('2967245', 'b53', **LOUVRE)
b59, _ = lidar_parts('27743656', 'b59', **WHITE)
b60, _ = lidar_parts('30064096', 'b60', **WHITE)
b1, _ = lidar_parts('35683386', 'b1', **WHITE)
b16, _ = lidar_parts('35683387', 'b16', **LOUVRE)
sm = []
for w in ('249342647', '862836598', '1002066983', '1026518808'):
    sm.append(lidar_parts(w, f'w{w[-3:]}', min_cells=4, **SHED)[0])
BUILDINGS = [b53, b59, b60, b1, b16] + sm
PARTS = [p for b in BUILDINGS for p in b]
WAYS = ('2967245', '27743656', '30064096', '35683386', '35683387', '249342647', '862836598', '1002066983',
        '1026518808')
DOORS = [(None, *centre(max(b, key=lambda p: len(p.cells))), None) for b in BUILDINGS]
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
    print('b53', i53, 'stairs', c.stairs_at, 'doors', c.door_cells)
    preview(plan, ROOT / f'verification/site/{NAME}-preview.png', scale=2)
    print(json.dumps(plan.summary())[:300])
    apply(plan, dry=not a.apply)
