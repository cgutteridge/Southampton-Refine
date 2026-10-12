#!/usr/bin/env python3
"""Broadlands Road nos. 14-24, north side (terrace A) — whole properties with
scripts/terrace.py (Claude, 11 Oct 2026). Replaces Cursor's broadlands_rd_20_22
and the #24 half of broadlands_rd_24_26 (jagged extrusions, flat slab roofs).

Evidence
  Aerial  hampshire-hub z18 mosaic: one continuous roof run 24..14, ~1.4 m
          passage between #24 and #26 (terrace B), gap after #14 before 12..2.
          Rear outriggers, patio bands, lawns on the 1:3 plot stair to the rear lane.
  OSM     ways 177978849 (24) 886 (22) 869 (20) 859 (18) 912 (16) 876 (14);
          party walls squared to 7092/97/102/106/111/115/120 — each house
          centre within 0.6 of its OSM centroid.
  Street  same typology as 26-36 (kartaview-1471277657, hint for this end:
          the camera looks along these fronts but they are small in frame).
          Door sides are a hint (pairs continue the 26-36 rhythm).
  LIDAR   pavement y26, gardens y27-29; ridge carpets y36-37 (ours b+10=37).
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'scripts'))
from osm_footprints import OSMIndex  # noqa: E402
from site_kit import Plan, apply, preview  # noqa: E402
from terrace import BROADLANDS_N_SLOPE, House, Terrace  # noqa: E402
from build_broadlands_rd_26_36 import P, pav_row, lane_row  # noqa: E402

NAME = 'broadlands_rd_14_24'
WAYS = {'24': '177978849', '22': '177978886', '20': '177978869',
        '18': '177978859', '16': '177978912', '14': '177978876'}


def front_row(no, xc):
    """Row of the OSM front edge (the two southmost vertices) at column centre xc."""
    rings = next(r for r, p in OSMIndex().buildings if p.get('osm_way_id') == WAYS[no])[0][:-1]
    (x0, z0), (x1, z1) = sorted(rings, key=lambda v: -v[1])[:2]
    return math.floor(z0 + (z1 - z0) * (xc - x0) / (x1 - x0))


SPEC = [  # no, pw, pe, door, extras (west -> east)
    ('24', 7092, 7097, 'E', dict(tree=True)),
    ('22', 7097, 7102, 'W', dict(door_block='dark_oak_door', shed=True)),
    ('20', 7102, 7106, 'E', dict(front_boundary='hedge')),
    ('18', 7106, 7111, 'W', dict(door_block='birch_door', tree=True)),
    ('16', 7111, 7115, 'E', dict(shed=True)),
    ('14', 7115, 7120, 'W', dict(front_boundary='hedge', door_block='dark_oak_door', tree=True)),
]
def pav_y(x):
    """Pristine pavement level at column x: the house floor and front garden sit at it."""
    z = pav_row(x)
    return max(y for y in range(22, 31) if 'polished_diorite' in (P.block(x, y, z) or ''))


HOUSES = [House(no, pw, pe, front_row(no, (pw + pe) / 2), pav_y((pw + pe) // 2), door, **kw)
          for no, pw, pe, door, kw in SPEC]


def build():
    plan = Plan(NAME)
    Terrace(plan, HOUSES, lambda x, z: P.ground(x, z, top=45, bottom=20),
            pav_row, lane_row, (7092, 7120), plot_slope=BROADLANDS_N_SLOPE).build()
    return plan


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--apply', action='store_true')
    a = ap.parse_args()
    for h in HOUSES:
        print(h.no, h.pw, h.pe, 'front', h.f, 'b', h.b)
    plan = build()
    preview(plan, ROOT / f'verification/site/{NAME}-preview.png', scale=4)
    print(json.dumps(plan.summary())[:300])
    modifies = ('broadlands_rd_20_22', 'broadlands_rd_24_26', 'broadlands_rd_28_30', 'broadlands_rd_28_30_b', 'broadlands_facade_revert',
                'portswood_x_broadlands_terrace_facade_1', 'portswood_x_broadlands_terrace_facade_1b',
                'portswood_x_broadlands_terrace_facade_2', 'portswood_x_broadlands_terrace_facade_2b',
                'portswood_x_broadlands_terrace_facade_2c', 'broadlands_rd_2_12',
                'broadlands_rd_passage_24_26')
    apply(plan, dry=not a.apply, modifies=modifies)
