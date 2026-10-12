#!/usr/bin/env python3
"""Q-037: rest of the demolished Faraday complex — Geocraft brick/carpet masses round the
already-cleared Faraday Tower core (highfield_engineering) that no OSM footprint covers.

Evidence
  photos   commons-171521042 (David Martin, 2025, "Site of the former Faraday Tower, recently
           demolished": heras-fenced sandy cleared ground, engineering buildings beyond);
           commons-13017064 (2008: tower + lower brick/concrete Faraday ranges).
  OSM      2025 extract maps nothing here (University Road houses to the E are mapped and
           are excluded with a 3-block margin).
  aerial   mosaic-z18-8x8-centre-130055-87834.png pre-dates the demolition (shows the blocks).
  LIDAR    pristine Geocraft masses 52-58 over ground 48-50 at x6455-6535 z-5690..-5625.
Cleared to the pristine terrain per column with a coarse_dirt surface (sandy site).

  python3 scripts/build_highfield_faraday_site.py
  SITE_OWNER=... python3 scripts/build_highfield_faraday_site.py --apply
"""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'scripts'))
from site_kit import apply, preview  # noqa: E402
from campus import Campus, _shared  # noqa: E402

NAME = 'highfield_faraday_site'
BOX = (6455, -5690, 6535, -5625)
EXTRA = None


def site_cells(c):
    idx, _ = _shared()
    out = set()
    for x in range(BOX[0], BOX[2] + 1):
        for z in range(BOX[1], BOX[3] + 1):
            if (x, z) in c.built or idx.near_footprint(x, z, 3):
                continue
            t = c.terrain(x, z)
            col = [c.w.block(x, y, z) or '' for y in range(t + 1, t + 20)]
            if any(k in b for b in col for k in ('bricks', 'carpet', 'concrete', 'glass', 'stone_brick')):
                out.add((x, z))
    return out


def make():
    return Campus(NAME, [], (), BOX)


def build():
    c = make()
    c.site = site_cells(c)
    for x, z in c.site:
        t = c.terrain(x, z)
        c.set(x, t, z, 'coarse_dirt')
        for y in range(t + 1, 100):
            b = c.w.block(x, y, z) or 'minecraft:air'
            if 'leaves' in b or '_log' in b:
                continue
            c.set(x, y, z, 'air')
    return c.p


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--apply', action='store_true')
    a = ap.parse_args()
    plan = build()
    print('site columns', len({(x, z) for x, _y, z in plan.cells}))
    preview(plan, ROOT / f'verification/site/{NAME}-preview.png', scale=3)
    print(json.dumps(plan.summary())[:300])
    apply(plan, dry=not a.apply)
