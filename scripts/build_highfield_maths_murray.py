#!/usr/bin/env python3
"""Q-035 (campus C9): Mathematics B54 (32651040), Murray B58 (33830152), Turner Sims Concert
Hall B52 (30064170), University Health Service B48 (32678442), Mathematical Sciences B56
(93729752), Statistical Science B39 (146986209), 223635325 / 223635326, 226141819, 305968656.

Evidence
  OSM      reference/osm/highfield-campus
  aerial   reference/aerial/highfield-campus/mosaic-z18-8x8-centre-130055-87834.png
  LIDAR    pristine Geocraft (views/q035-survey.png): B54 51 → tower 82-85 + 55 wing;
           B58 54 → 60/66/69; B52 52 → 55-59 faceted roof; B48 50 → 54-60 pitched; B56 60;
           B39 56 → 63.
  photos   commons-114890282 (grey concrete tower with a blank end wall = B54, copper
           Nuffield beyond), -134990247 (2016 B58 Murray: grey concrete, dark ribbon
           windows, glazed entrance), -7578708 (2009 Turner Sims: low hall under a faceted
           grey metal pitched roof with a spire-like flue), -171520741 (2025 view to B100),
           -144943022 (2019: site of the demolished John Hansard Gallery — LIDAR already
           ground there; nothing to clear).
  187918193: small way against the B54 tower (LIDAR to 79) = its core, built with the tower.
  Not built: 219899639 (building=roof), 154067444 (canopy),
  226141861 (no height).

  python3 scripts/build_highfield_maths_murray.py            # preview + dry-run guards
  SITE_OWNER=... python3 scripts/build_highfield_maths_murray.py --apply
"""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'scripts'))
from site_kit import apply, preview  # noqa: E402
from campus import SLATE, XZ, Campus, Part, auto_parts, bbox, centre, lidar_parts, pitched_part, way_cells  # noqa: E402

NAME = 'highfield_maths_murray'
CONC = dict(wall='light_gray_concrete', glass='gray_stained_glass', rows=(1, 2), pier=0, corner_glass=True,
            slab='gray_concrete')
BRICK = dict(wall='bricks', glass='glass', rows=(1, 2), pier=3, corner_glass=True)
SHED = dict(wall='gray_concrete', rows=())

b54, i54 = lidar_parts('32651040', 'b54', **CONC)
# 187918193: small OSM way against the tower, LIDAR up to 79 (stair core) - one with the tower
_t = max(b54, key=lambda p: p.deck)
b54.append(Part('b54_core', _t.base, _t.deck, _t.top, _t.floors, frame=XZ, cells=way_cells('187918193'), **CONC))
b58, _ = lidar_parts('33830152', 'b58', **CONC)
g52 = lidar_parts('30064170', 'tmp')[1]['ground']
b52 = [pitched_part('b52', way_cells('30064170'), g52, eaves=g52 + 3, **SLATE, **BRICK)]
b48, i48 = auto_parts('32678442', 'b48', loose=True, **BRICK)
b56, _ = lidar_parts('93729752', 'b56', **BRICK)
b39, _ = lidar_parts('146986209', 'b39', **BRICK)
small = [lidar_parts(w, f'w{w[-3:]}', min_cells=4, **(BRICK if w.startswith('2236') else SHED))[0]
         for w in ('223635325', '223635326', '226141819', '305968656')]
BUILDINGS = [b54, b58, b52, b48, b56, b39] + small
PARTS = [p for b in BUILDINGS for p in b]
WAYS = ('187918193', '32651040', '33830152', '30064170', '32678442', '93729752', '146986209', '223635325', '223635326',
        '226141819', '305968656')
DOORS = [(None, *centre(max(b, key=lambda p: len(p.cells))), None) for b in BUILDINGS if b not in (b58, b39, small[3])]   # small[3] = rooftop plant (base 62)
DOORS += [(None, 6100, -5836, None), (None, 6072, -5818, None)]   # Murray north forecourt; B39 east (W = brook)
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
    print('b54', i54, 'b48', i48, 'stairs', c.stairs_at)
    preview(plan, ROOT / f'verification/site/{NAME}-preview.png', scale=2)
    print(json.dumps(plan.summary())[:300])
    apply(plan, dry=not a.apply)
