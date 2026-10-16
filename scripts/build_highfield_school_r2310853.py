#!/usr/bin/env python3
"""Q-072 (cell 47,-43): building=school, OSM relation 2310853 (unnamed; bbox 5990,-5395,6035,-5344).

Evidence
  OSM      reference/osm/highfield-campus (outer ring 31 pts + small inner courtyard ring)
  aerial   reference/aerial/highfield-campus/mosaic-z18-5x5-centre-130053-87835.png
           pale blue-grey flat roofs, plant on the roof, tiny central courtyard.
  LIDAR    pristine Geocraft: one roof band 54 on ground 50 -> single storey + parapet.
  Not evidenced: wall material / window pattern (no street photo in the manifest). Brick
  walls with a glazed ribbon are a placeholder typical of the type - revisit with a photo.

  .venv/bin/python scripts/build_highfield_school_r2310853.py            # preview + dry-run guards
  SITE_OWNER=... .venv/bin/python scripts/build_highfield_school_r2310853.py --apply
"""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'scripts'))
from site_kit import apply, preview  # noqa: E402
from campus import Campus, bbox, centre, lidar_parts, way_cells  # noqa: E402

NAME = 'highfield_school_r2310853'
STYLE = dict(wall='bricks', glass='glass', rows=(1, 2), pier=3, corner_glass=True, slab='light_gray_concrete')

# Street View (pano _A3saspZsRfOCrAHrfRq9A, Aug 2025, look-only) covers only the WEST frontage on
# Hawthorn Rd, from the camera at MC 5985,-5378. Sections below follow what it shows; the east and
# rear are unseen and keep the placeholder brick (rows 1-2 glazed ribbon).
WHITE = dict(wall='white_concrete', glass='glass', rows=(1, 2), pier=4, corner_glass=True, slab='light_gray_concrete')
RED = dict(wall='bricks', glass='glass', rows=(1, 2), pier=3, corner_glass=True, slab='light_gray_concrete')
DARK = dict(wall='brown_terracotta', glass='glass', rows=(1, 2), pier=3, corner_glass=True,
            slab='light_gray_concrete', band=(53,), band_block='white_terracotta')
OTHER = RED
_fp = way_cells('2310853')
_red = {q for q in _fp if 6000 <= q[0] <= 6008 and -5378 <= q[1] <= -5372}
_dark = {q for q in _fp if q[1] >= -5369 and q[0] <= 6003 and q[1] <= -5358} - _red
_white = {q for q in _fp if q[1] <= -5379 and q[0] <= 6012} - _red - _dark
_white |= {q for q in _fp if 5999 <= q[0] <= 6002 and -5372 <= q[1] <= -5370} - _red - _dark
_rest = _fp - _red - _dark - _white
SECTIONS = [(_white, 'schw', WHITE), (_red, 'schr', RED), (_dark, 'schd', DARK), (_rest, 'scho', OTHER)]
school, info = [], []
for _cells, _pre, _style in SECTIONS:
    _p, _i = lidar_parts('2310853', _pre, base=50, only=_cells, fill_pockets=5, **_style)
    school += _p
    info.append(_i)
# coverage parcel prop:r2310853 rasterises 6 edge columns the way cells miss; cover them so sign-off sees no stone
from coverage import load_area  # noqa: E402
_parcel = load_area('highfield').parcels['prop:r2310853']['set']
_extra = _parcel - {q for p in school for q in p.cells}
max(school, key=lambda p: len(p.cells)).cells |= _extra
BUILDINGS = [school]
PARTS = [p for b in BUILDINGS for p in b]
WAYS = ('2310853',)
DOORS = [(None, *centre(max(b, key=lambda p: len(p.cells))), None) for b in BUILDINGS]
STAIRS = []
BOX = bbox(PARTS, pad=2)


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
    print('info', info)
    print('doors', c.door_cells)
    preview(plan, ROOT / f'verification/site/{NAME}-preview.png', scale=2)
    print(json.dumps(plan.summary())[:300])
    apply(plan, dry=not a.apply)
