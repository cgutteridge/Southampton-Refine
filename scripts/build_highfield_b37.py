#!/usr/bin/env python3
"""Q-025: Highfield campus, B37 George Thomas (OSM 146985469).

Evidence
  OSM      reference/osm/highfield-b35 (north block axis-aligned in B35's 2:1 frame; the south
           wing is a triangle whose long SW face runs ~1:2 in MC)
  aerial   reference/aerial/highfield-b35/mosaic-z18-3x3-centre-130056-87836.png
           north block dark grey flat roof with rows of solar panels along its south half;
           triangular wing a tan/brown flat roof with plant
  LIDAR    pristine Geocraft: top 65 over the whole footprint (67-68 central rooflight,
           ignored), ground 54 west / 53 east
  photos   kartaview-1519868121 (6322,-5558 ESE): north face, dark red-brown brick, four
           rows of regular windows, flat roof, recessed ground floor with cycle racks;
           kartaview-1471281353 (6283,-5514 NNW): west face brick; kartaview-1471281241
           (6308,-5462 NNW): long SW face red brick, gridded windows, glazed stair tower at
           the far (NW) end

4 storeys x 3 blocks from 54 (roof 66, coping 67 — 1-2 over LIDAR to keep 3-block storeys).

  python3 scripts/build_highfield_b37.py            # preview + dry-run guards
  SITE_OWNER=... python3 scripts/build_highfield_b37.py --apply
"""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'scripts'))
from site_kit import apply, preview  # noqa: E402
from campus import Campus, Part  # noqa: E402

NAME = 'highfield_b37'
WAYS = ('146985469',)
BRICK = dict(wall='bricks', glass='glass', rows=(1, 2), pier=3, corner_glass=True)
F4 = (54, 57, 60, 63)
WING = [(-58.8, 11), (-58.8, 14.4), (-49.5, 14.4), (-49.5, 50.5), (-59.2, 45.1), (-94, 19.5),
        (-92.6, 19.5), (-92.6, 16), (-96, 16), (-96, 12.6), (-93, 12.6), (-93, 11)]
PARTS = [
    Part('b37_north', 54, 66, 67, F4, rects=[(-106, -54.5, -11.5, 9), (-105.5, -58.8, 9, 11)],
         slab='gray_concrete', **BRICK),
    Part('b37_wing', 54, 66, 67, F4, polys=[WING], slab='smooth_sandstone', **BRICK),
]
DOORS = [('b37_north', 6319, -5546, 54), ('b37_north', 6290, -5547, 54), ('b37_wing', 6321, -5482, 54)]
BOX = (6280, -5565, 6350, -5470)


def solar(c):
    """Rows of panels on the north block's south half (aerial)."""
    from campus import UV
    for (x, z), pt in c.part.items():
        if pt.name != 'b37_north':
            continue
        u, v = UV(x, z)
        if 1 <= v < 9 and -100 <= u < -60 and int(v) % 2 == 0 and \
                all(c.part.get((x + a, z + b)) is pt for a in (-1, 0, 1) for b in (-1, 0, 1)):
            c.set(x, pt.deck + 1, z, 'daylight_detector[inverted=false,power=0]')


def make():
    return Campus(NAME, PARTS, WAYS, BOX, DOORS, ('b37_north', (6313, -5536)))


def build():
    return make().build(solar)


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--apply', action='store_true')
    a = ap.parse_args()
    c = make()
    plan = c.build(solar)
    print('parts', {pt.name: sum(1 for q in c.part.values() if q is pt) for pt in PARTS})
    print('stair at', c.stair_at, 'doors', c.door_cells)
    preview(plan, ROOT / f'verification/site/{NAME}-preview.png', scale=2)
    print(json.dumps(plan.summary())[:500])
    apply(plan, dry=not a.apply)
