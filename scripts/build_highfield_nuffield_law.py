#!/usr/bin/env python3
"""Q-032 (campus C6): B2 (226000420), Law B4 (93729747), Nuffield Theatre B6 (30063860),
The Annex 2A (33830587), Interchange Kiosk 115 (141612508), Centenary Building B100
(702200481), 93742827, 1024630088.

Evidence
  OSM      reference/osm/highfield-campus
  aerial   reference/aerial/highfield-campus/mosaic-z18-8x8-centre-130055-87834.png (pre-dates
           Centenary: car park + old B58a there); B2 white roof, Law/Nuffield dark flat roofs.
  LIDAR    pristine Geocraft (views/q032-survey.png): B2 52 → 56/68-71; Law 54 → 68/72;
           Nuffield 54 → 59 base, 65-68 fly tower; Annex 59-60; Centenary 56 → 74-76 / 87-89.
  photos   commons-144943043 (2019, Centenary: white ribbed cladding, punched windows, dark
           brick ground floor), -126269265 / -114890264 (Nuffield: verdigris copper-clad
           blocks over brick base and a pool), -148052260 (2020 view from B100: white
           concrete ribbon-window blocks, copper theatre, low brick ranges), -113513296
           (bus interchange: timber canopy, brick kiosk).
  Not built: 1482280003 / 1482280004 / 236241511 (no LIDAR height, no photo), 154067444
  (canopy).

  python3 scripts/build_highfield_nuffield_law.py            # preview + dry-run guards
  SITE_OWNER=... python3 scripts/build_highfield_nuffield_law.py --apply
"""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'scripts'))
from site_kit import apply, preview  # noqa: E402
from campus import Campus, bbox, centre, lidar_parts  # noqa: E402

NAME = 'highfield_nuffield_law'
BRICK = dict(wall='bricks', glass='glass', rows=(1, 2), pier=3, corner_glass=True)
CONC = dict(wall='white_concrete', glass='gray_stained_glass', rows=(1, 2), pier=0, corner_glass=True)
RIBBED = dict(wall='white_concrete', glass='black_stained_glass', rows=(1, 2), pier=2, corner_glass=False,
              band_block='nether_bricks')
COPPER = dict(wall='weathered_copper', glass='glass', rows=(), pier=0)

b2, _ = lidar_parts('226000420', 'b2', **CONC)
b4, _ = lidar_parts('93729747', 'b4', **CONC)
nuf, inuf = lidar_parts('30063860', 'b6', **BRICK)
nuf = [p if p.deck < 63 else type(p)(p.name, p.base, p.deck, p.top, p.floors, frame=p.frame, cells=p.cells,
                                     **COPPER) for p in nuf]
annex, _ = lidar_parts('33830587', 'b2a', **BRICK)
kiosk, _ = lidar_parts('141612508', 'k115', min_cells=4, **BRICK)
g100 = lidar_parts('702200481', 'tmp')[1]['ground']
b100, _ = lidar_parts('702200481', 'b100', band=(g100 + 1, g100 + 2), **RIBBED)
w827, _ = lidar_parts('93742827', 'w827', min_cells=4, **BRICK)
w088, _ = lidar_parts('1024630088', 'w088', **BRICK)
BUILDINGS = [b2, b4, nuf, annex, kiosk, b100, w827, w088]
PARTS = [p for b in BUILDINGS for p in b]
WAYS = ('226000420', '93729747', '30063860', '33830587', '141612508', '702200481', '93742827', '1024630088')
DOORS = [(None, *centre(max(b, key=lambda p: len(p.cells))), None) for b in BUILDINGS if b is not w088]
DOORS += [(None, 6208, -5838, None)]                       # w088 west side (east faces a Geocraft wall)
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
    print('nuffield', inuf, 'stairs', c.stairs_at, 'doors', c.door_cells)
    preview(plan, ROOT / f'verification/site/{NAME}-preview.png', scale=2)
    print(json.dumps(plan.summary())[:300])
    apply(plan, dry=not a.apply)
