#!/usr/bin/env python3
"""Broadlands Road nos. 2-12, north side (terrace C) — whole properties with
scripts/terrace.py (Claude, 11 Oct 2026, Q-019).

Evidence
  Aerial  hampshire-hub z18 mosaic (q019-aerial-2-12-annot.png): one continuous
          roof run 12..2, a narrow dark gap between #14 (red roof) and #12, and
          the terrace ends at #2 against the lane that runs NE from Broadlands
          Rd to Portswood Rd (Geocraft gray_terracotta x7143-7166). #12..#4 dark
          slate; #2 red clay tiles. Lawns + dark tree crowns mid-plot, pale
          outbuilding roof at the back of #12, gardens on the 1:3 plot stair to the
          diagonal rear lane. East of #2 the converging lanes leave a gore (aerial
          q041-aerial-gardens.png); that wedge is #2's garden.
  OSM     ways 177978907 (12) 864 (10) 915 (8) 877 (6) 873 (4) 883 (2);
          party walls squared to 7122/26/30/35/39/44/48 — each house centre
          within 0.6 of its OSM centroid. 1-wide gravel passage at x7121.
  Street  kartaview-1471277737 (GPS 7134,-5505) actually looks ESE past the end
          of the terrace (buff brick wall + trees beyond the lane), so the
          fronts are unseen: typology, door sides and front boundaries are a
          hint from 14-36 (pairs continue the 14-24 rhythm: 14W | 12E,10W ...).
  LIDAR   pavement y24-25, gardens rising north; Geocraft carpets y34-36.
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
from terrace import BROADLANDS_N_SLOPE, House, Terrace, passage_xs  # noqa: E402
from build_broadlands_rd_14_24 import HOUSES as HOUSES_14  # noqa: E402
from build_broadlands_rd_26_36 import P  # noqa: E402

NAME = 'broadlands_rd_2_12'
WAYS = {'12': '177978907', '10': '177978864', '8': '177978915',
        '6': '177978877', '4': '177978873', '2': '177978883'}
X0, X1 = 7122, 7148
PAV_END = 7140          # last column with pristine pavement; the Geocraft lane mouth sits east of it


def front_row(no, xc):
    """Row of the OSM front edge (the two southmost vertices) at column centre xc."""
    rings = next(r for r, p in OSMIndex().buildings if p.get('osm_way_id') == WAYS[no])[0][:-1]
    (x0, z0), (x1, z1) = sorted(rings, key=lambda v: -v[1])[:2]
    return math.floor(z0 + (z1 - z0) * (xc - x0) / (x1 - x0))


def _pav(x):
    """(northmost pristine pavement row, its Y) at column x (pavement dips to y23 here)."""
    for z in range(-5530, -5500):
        y = P.ground(x, z, top=45, bottom=15)
        if 'polished_diorite' in (P.block(x, y, z) or ''):
            return z, y
    raise SystemExit(f'no pavement at x={x}')


def pav_row(x):
    """Northmost pavement row. East of PAV_END Geocraft put the NE lane's mouth ~4
    blocks west of where the aerial shows it, so continue the pavement line (0.4/col)."""
    if x <= PAV_END:
        return _pav(x)[0]
    return round(_pav(PAV_END)[0] + (x - PAV_END) * 0.4)


def lane_row(x):
    """Southmost row of the diagonal rear lane behind the gardens (pristine gray_terracotta)."""
    for z in range(-5540, -5590, -1):
        if 'gray_terracotta' in P.block(x, P.ground(x, z, top=45, bottom=20), z):
            return z
    raise SystemExit(f'no lane at x={x}')


def pav_y(x):
    """Pristine pavement level at column x: the house floor and front garden sit at it."""
    return _pav(min(x, PAV_END))[1]


SPEC = [  # no, pw, pe, door, extras (west -> east)
    ('12', 7122, 7126, 'E', dict(front_boundary='hedge', shed=True)),
    ('10', 7126, 7130, 'W', dict(door_block='dark_oak_door', tree=True)),
    ('8', 7130, 7135, 'E', dict(front_boundary='hedge', tree=True)),
    ('6', 7135, 7139, 'W', dict(door_block='birch_door')),
    ('4', 7139, 7144, 'E', dict(tree=True)),
    ('2', 7144, 7148, 'W', dict(roof='granite', door_block='dark_oak_door')),
]

HOUSES = [House(no, pw, pe, front_row(no, (pw + pe) / 2), pav_y((pw + pe) // 2), door, **kw)
          for no, pw, pe, door, kw in SPEC]


def _street(x, z):
    """Rear lane and the NE lane to Portswood (gray), or the Broadlands pavement."""
    y = P.ground(x, z, top=45, bottom=15)
    b = P.block(x, y, z) or ''
    return 'gray_terracotta' in b or 'polished_diorite' in b


def build():
    plan = Plan(NAME)
    t = Terrace(plan, HOUSES, lambda x, z: P.ground(x, z, top=45, bottom=20),
                pav_row, lane_row, (X0, X1), plot_slope=BROADLANDS_N_SLOPE,
                gore='E', gore_reach=18, street=_street)
    t.build()
    # Squared #2 stops at x7148; the OSM plot still owns the east corner
    # (parcel was 8 columns of Geocraft carpet). Yard, not more house wall.
    h2 = HOUSES[-1]
    rz = h2.f - 11
    for x in range(h2.pe + 1, h2.pe + 4):
        for z in range(rz - 1, rz + 5):
            if (x, z) in t.plots or _street(x, z):
                continue
            t._lay(h2, x, z)
    # side passage after #14: gravel alley between the two plot lines, from the
    # pavement to the rear lane, rising with #12's lawn
    h14, h12 = HOUSES_14[-1], HOUSES[0]
    gap = {}
    for z in range(-5510, -5580, -1):
        for x in passage_xs(z, h14.pe, h14.f - 11, h12.pw, h12.f - 11, BROADLANDS_N_SLOPE):
            try:
                if lane_row(x) < z < pav_row(x):
                    gap.setdefault(x, []).append(z)
            except SystemExit:
                continue
    for x, zs in gap.items():
        zl = lane_row(x)
        lane_y = P.ground(x, zl, top=45, bottom=20)
        prev = None
        for z in sorted(zs, reverse=True):
            y = min(t.surface_y(h12, h12.inner[0], z), lane_y - 1)
            for yy in range(y - 3, y):
                plan.set(x, yy, z, 'dirt')
            plan.set(x, y, z, 'gravel')
            for yy in range(y + 1, y + 17):
                plan.set(x, yy, z, 'air')
            if prev is not None and y == prev + 1:
                plan.set(x, y, z, 'stone_brick_stairs[facing=north,half=bottom]')
            prev = y
        if (zl + 1) in zs:
            plan.set(x, lane_y, zl + 1, 'stone_brick_stairs[facing=north,half=bottom]')
    # pavement edge continued in front of #4/#2 where the misplaced lane mouth was
    for x in range(PAV_END + 1, X1 + 1):
        plan.set(x, pav_y(x), pav_row(x), 'polished_diorite')
    return plan


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--apply', action='store_true')
    a = ap.parse_args()
    for h in HOUSES:
        print(h.no, h.pw, h.pe, 'front', h.f, 'b', h.b, 'pav', pav_row((h.pw + h.pe) // 2),
              'lane', lane_row((h.pw + h.pe) // 2))
    plan = build()
    preview(plan, ROOT / f'verification/site/{NAME}-preview.png', scale=4)
    print(json.dumps(plan.summary())[:300])
    apply(plan, dry=not a.apply, modifies=())
