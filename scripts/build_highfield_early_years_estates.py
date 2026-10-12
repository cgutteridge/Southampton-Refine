#!/usr/bin/env python3
"""Q-025: Highfield campus low blocks south/east of B35 — Early Years (OSM 146985468),
Estates (146985466) and the shed east of the bike shed (159865642).

Evidence
  OSM      reference/osm/highfield-b35
  aerial   reference/aerial/highfield-b35/mosaic-z18-3x3-centre-130056-87836.png
           Early Years and Estates: grey flat roofs; shed: dark flat roof
  LIDAR    pristine Geocraft: Early Years top 59 over u -32..-21 only (OSM's east fringe
           to u -18 is ground), ground 52 → two storeys; Estates top 52-53, ground 47-48 →
           one tall storey; shed top 52 on ground 48
  photos   none of Early Years / Estates elevations (hint: brick, like B35 and B37);
           kartaview-1519868329 (6447,-5494 ESE) shows a sage-green metal shed by the
           bike shelters (registration ~5 m; taken as 159865642)

  python3 scripts/build_highfield_early_years_estates.py            # preview + dry-run
  SITE_OWNER=... python3 scripts/build_highfield_early_years_estates.py --apply
"""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'scripts'))
from site_kit import apply, preview  # noqa: E402
from campus import Campus, Part, XZ  # noqa: E402

NAME = 'highfield_early_years_estates'
WAYS = ('146985468', '146985466', '159865642')
BRICK = dict(wall='bricks', glass='glass', rows=(1, 2), pier=3)
SHED = [(6447.3, -5493.8), (6444.5, -5487.8), (6435.3, -5492.0), (6438.1, -5498.1)]
PARTS = [
    Part('early_years', 52, 58, 59, (52, 55), rects=[(-32.5, -21, 26, 63.2)], **BRICK),
    Part('estates', 48, 52, 53, (48,), rects=[(6381, 6401, -5462, -5443), (6390, 6398, -5443, -5420)],
         frame=XZ, **BRICK),
    Part('shed', 48, 51, None, (48,), polys=[SHED], frame=XZ, wall='green_terracotta',
         slab='gray_concrete', rows=()),
]
DOORS = [('early_years', 6346, -5469, 52), ('early_years', 6338, -5479, 52),
         ('estates', 6392, -5463, 48), ('estates', 6398, -5432, 48), ('shed', 6441, -5496, 48)]
BOX = (6320, -5500, 6450, -5415)


def make():
    return Campus(NAME, PARTS, WAYS, BOX, DOORS, ('early_years', (6341, -5472)))


def build():
    return make().build()


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--apply', action='store_true')
    a = ap.parse_args()
    c = make()
    plan = c.build()
    print('parts', {pt.name: sum(1 for q in c.part.values() if q is pt) for pt in PARTS})
    print('stair at', c.stair_at, 'doors', c.door_cells)
    preview(plan, ROOT / f'verification/site/{NAME}-preview.png', scale=3)
    print(json.dumps(plan.summary())[:500])
    apply(plan, dry=not a.apply)
