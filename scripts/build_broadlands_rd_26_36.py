#!/usr/bin/env python3
"""Q-018 (+ redo of Q-016/Q-017): Broadlands Road nos. 26-36, north side — the
whole terrace as one build with scripts/terrace.py (Claude, 11 Oct 2026).

Why one build: Cursor's broadlands_rd_24_26 / _28_30 (+_b) and the 32+34
placeholders were jagged extrusions with flat slab roofs and no bays; they
overlap each other and could not be continued cleanly. This replaces them.

Evidence
  Street  kartaview-1471277657 (camera MC 7071,-5531, looking ENE): red-brick
          two-storey terrace, ground-floor bays with tiled hoods, paired doors
          under white gabled hoods, first-floor window over the bay + small
          one over the door, dark slate roofs, ridge parallel to the street,
          party-wall chimney stacks; nearest house (#32) cream render; tall
          trimmed hedges in front of 30/28.
  Aerial  hampshire-hub z18 mosaic (q018-aerial-annot.png): continuous roofs
          26-36, rear outriggers, pale patio band, long lawns to the rear lane,
          tree crowns mid-plot, small pale roofs (sheds) by the lane.
  OSM     ways 177978895 (26) 867 (28) 885 (30) 846 (32) 855 (34) 916 (36):
          4.8 x 12 m plots rotated 21.8 deg (snapped to 1:3, BROADLANDS_N_SLOPE).
          Houses stay squared: pitch 4/5
          alternating (avg 4.5), fronts stepped to the street line, every
          house centre within ~1.6 of its OSM centroid.
  LIDAR   pristine Geocraft: pavement y28 (west) / y27, gardens rise to y30-31
          at the rear lane; ridge carpets y37-38 (ours: b+10 -> 37/38).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'scripts'))
from site_kit import Plan, World, apply, preview  # noqa: E402
from terrace import BROADLANDS_N_SLOPE, House, Terrace  # noqa: E402

NAME = 'broadlands_rd_26_36'
CFG = json.loads((ROOT / 'config/world.json').read_text())
P = World(CFG['pristine_region_path'])

HOUSES = [  # west -> east
    House('36', 7064, 7068, -5547, 28, 'W', door_block='dark_oak_door', tree=True),
    House('34', 7068, 7073, -5545, 28, 'E', shed=True),
    House('32', 7073, 7077, -5543, 27, 'W', wall='smooth_sandstone', door_block='birch_door', tree=True),
    House('30', 7077, 7082, -5542, 27, 'E', front_boundary='hedge', shed=True),
    House('28', 7082, 7086, -5540, 27, 'W', front_boundary='hedge', door_block='dark_oak_door', tree=True),
    House('26', 7086, 7090, -5538, 27, 'E'),
]


def pav_row(x):
    """Northmost pavement row (pristine polished_diorite)."""
    for z in range(-5552, -5505):
        for y in range(24, 31):
            if 'polished_diorite' in (P.block(x, y, z) or ''):
                return z
    raise SystemExit(f'no pavement at x={x}')


def lane_row(x):
    """Southmost row of the rear lane: first pristine gray_terracotta north of the pavement.

    Searching from a fixed row misses the lane where the 1:3 gardens shear east of
    x7120 (the lane is south of that row) and would instead hit Broadlands Road
    if the search started south of the pavement.
    """
    z0 = pav_row(x) - 1
    for z in range(z0, z0 - 90, -1):
        y = P.ground(x, z, top=45, bottom=20)
        if 'gray_terracotta' in (P.block(x, y, z) or ''):
            return z
    raise SystemExit(f'no lane at x={x}')


def build():
    plan = Plan(NAME)
    t = Terrace(plan, HOUSES, lambda x, z: P.ground(x, z, top=45, bottom=20),
                pav_row, lane_row, (7064, 7090), pristine=P,
                plot_slope=BROADLANDS_N_SLOPE, restore_west=True)
    t.build()
    return plan


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--apply', action='store_true')
    a = ap.parse_args()
    plan = build()
    out = ROOT / f'verification/site/{NAME}-preview.png'
    preview(plan, out, scale=4)
    print(json.dumps(plan.summary())[:600])
    modifies = ('broadlands_facade_revert', 'portswood_x_broadlands_terrace_facade_1', 'portswood_x_broadlands_terrace_facade_1b', 'portswood_x_broadlands_terrace_facade_2', 'portswood_x_broadlands_terrace_facade_2b', 'portswood_x_broadlands_terrace_facade_2c', 'broadlands_rd_24_26', 'broadlands_rd_28_30', 'broadlands_rd_28_30_b', 'broadlands_rd_14_24', 'broadlands_rd_passage_24_26')
    apply(plan, dry=not a.apply, modifies=modifies)
