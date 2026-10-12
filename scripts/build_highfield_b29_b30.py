#!/usr/bin/env python3
"""Q-025: Highfield campus, B30 Synthetic Chemistry (OSM 66696201) + B29 Graham Hills (225234902).

Evidence
  OSM      reference/osm/highfield-b35 (both outlines axis-aligned in B35's 2:1 frame)
  aerial   reference/aerial/highfield-b35/mosaic-z18-3x3-centre-130056-87836.png
           B30: very light flat roof, two long ranges + plant; B29: a row of ~7 grey
           units stepping along the road (saw-tooth south front, dark gaps between)
  LIDAR    pristine Geocraft: B30 main block top 77 (u -44..2, v -59..-38.5), north and
           south ranges ~72-73, NW corner + NE corner and the road-side strip 54-56;
           B29 top 77 along its whole length, ground 51 west → 48 east
  photos   kartaview-1519868249 (camera 6396,-5526 ESE): silver aluminium cladding,
           ribbon windows, upper floors over a dark glazed one-storey front block, then
           B29's stepped silver bays down the road; kartaview-1519868121 (6322,-5558 ESE):
           B30 beyond B34 as a white/blue-glazed block

Storeys 4 blocks (lab heights). Walls in the (u, v) frame of build_highfield_b35.

  python3 scripts/build_highfield_b29_b30.py            # preview + dry-run guards
  SITE_OWNER=... python3 scripts/build_highfield_b29_b30.py --apply
"""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'scripts'))
from site_kit import apply, preview  # noqa: E402
from campus import Campus, Part  # noqa: E402

NAME = 'highfield_b29_b30'
WAYS = ('66696201', '225234902')
CLAD = dict(wall='light_gray_concrete', glass='light_blue_stained_glass', slab='white_concrete',
            rows=(1, 2), pier=0, corner_glass=True)
F6 = (51, 55, 59, 63, 67, 71)
F7 = (48, 52, 56, 60, 64, 68, 72)

BAYS = [(10.9 + 7 * k + 2, min(10.9 + 7 * k + 7, 60.4), -34.5, -31.0) for k in range(7)]
PARTS = [
    Part('b30_tower', 51, 75, 77, F6, rects=[(-44, 2, -59, -38.5)], **CLAD),
    Part('b30_north', 51, 71, 73, F6[:5], rects=[(-25, 0, -71, -59)], **CLAD),
    Part('b30_south', 51, 71, 73, F6[:5], rects=[(-44, 2, -38.5, -35.5)], **CLAD),
    Part('b30_nw_low', 51, 55, 56, (51,), rects=[(-31.8, -25, -71, -61.4), (-44, -25, -61.4, -59)], **CLAD),
    Part('b30_ne_low', 51, 54, None, (51,), rects=[(2, 12.3, -61.6, -55.2)], **CLAD),
    Part('b30_front', 51, 55, 56, (51,), rects=[(-9.1, 10.9, -35.5, -30.5), (2, 10.9, -40, -35.5)],
         wall='gray_concrete', glass='gray_stained_glass', slab='light_gray_concrete', rows=(1, 2, 3), pier=4),
    Part('b29', 48, 76, 77, F7, rects=[(10.9, 60.4, -43.8, -34.5)], **CLAD),
    Part('b29_bays', 48, 76, 77, F7, rects=BAYS, **{**CLAD, 'pier': 0, 'glass': 'glass'}),
]
STAIRS = [('b30_tower', (6389, -5552)), ('b29', (6434, -5519))]
DOORS = [('b30_front', 6399, -5527, 51), ('b30_north', 6406, -5569, 51),
         ('b29_bays', 6439, -5508, 48), ('b29', 6456, -5507, 48)]


def build():
    return Campus(NAME, PARTS, WAYS, (6345, -5600, 6475, -5500), DOORS, STAIRS).build()


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--apply', action='store_true')
    a = ap.parse_args()
    c = Campus(NAME, PARTS, WAYS, (6345, -5600, 6475, -5500), DOORS, STAIRS)
    plan = c.build()
    print('parts', {pt.name: sum(1 for q in c.part.values() if q is pt) for pt in PARTS})
    print('stairs at', c.stairs_at, 'doors', c.door_cells)
    preview(plan, ROOT / f'verification/site/{NAME}-preview.png', scale=2)
    print(json.dumps(plan.summary())[:600])
    apply(plan, dry=not a.apply)
