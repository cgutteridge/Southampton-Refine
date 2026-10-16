#!/usr/bin/env python3
"""Q-034 (campus C8): Physics & Astronomy B5 (relation 3006924) + B46 (relation 3006921),
Shackleton B44 (relation 3300438), Psychology 44A (30446953), sheds 226247416 / 226247418 /
226247420.

Evidence
  OSM      reference/osm/highfield-campus
  aerial   reference/aerial/highfield-campus/mosaic-z18-8x8-centre-130055-87834.png
           dark grey flat roofs with plant; Shackleton a courtyard square.
  LIDAR    pristine Geocraft (views/q034-survey.png): B5 53 → 66-72; B44 52 → 65-69 round
           the courtyard (54-56 low wings); 44A 51 → 56; sheds 53-54.
  photos   commons-14474802 (Shackleton: 1960s grey concrete bands, blue-framed ribbon
           windows, 4 storeys), -171520763 (2025: grey ribbon blocks beyond the gardens),
           -171520794 / -13527539 (gardens and stream W of the buildings).
  Not built: building=roof canopies 147603916, 154417140, 226117630; 220434721 and
  148212337 (no LIDAR height).

  python3 scripts/build_highfield_shackleton_physics.py            # preview + dry-run guards
  SITE_OWNER=... python3 scripts/build_highfield_shackleton_physics.py --apply
"""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'scripts'))
from site_kit import apply, preview  # noqa: E402
from campus import Campus, bbox, centre, lidar_parts  # noqa: E402

NAME = 'highfield_shackleton_physics'
CONC = dict(wall='light_gray_concrete', glass='light_blue_stained_glass', rows=(1, 2), pier=0, corner_glass=True,
            slab='gray_concrete')
BRICK = dict(wall='bricks', glass='glass', rows=(1, 2), pier=3, corner_glass=True)
SHED = dict(wall='gray_concrete', rows=())

b5, i5 = lidar_parts('3006924', 'b5p', **CONC)
b46, i46 = lidar_parts('3006921', 'b46', **CONC)
# photo (ground floor): red-brown brick piers + dark glazing under pale upper cladding
GROUND = dict(wall='bricks', glass='gray_stained_glass', pier=3)
b44, i44 = lidar_parts('3300438', 'b44', fill_pockets=7, ground=GROUND, **CONC)
b44a, _ = lidar_parts('30446953', 'b44a', **BRICK)
sheds = [lidar_parts(w, f's{w[-3:]}', min_cells=4, **SHED)[0] for w in ('226247416', '226247418', '226247420')]
BUILDINGS = [b5, b46, b44, b44a] + sheds
PARTS = [p for b in BUILDINGS for p in b]
WAYS = ('3006924', '3006921', '3300438', '30446953', '226247416', '226247418', '226247420')
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
    print('info', i5, i46, i44)
    print('stairs', c.stairs_at, 'doors', c.door_cells)
    preview(plan, ROOT / f'verification/site/{NAME}-preview.png', scale=2)
    print(json.dumps(plan.summary())[:300])
    apply(plan, dry=not a.apply)
