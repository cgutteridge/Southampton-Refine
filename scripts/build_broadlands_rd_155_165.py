#!/usr/bin/env python3
"""Q-093: Broadlands Road nos. 155-165 (odd), south side - three brick semi-detached
pairs (165/163, 161/159, 157/155), HOUSE ONLY (layered pass 1 of cell 50,-45; Claude,
15 Oct 2026).

Houses only (HANDOFF-LAYERED-PASSES s1): no lawn, fences, hedges, trees. The build owns
each house box, its roof overhang, the door stoops and the Geocraft building raster it
replaces (cleared down to the ground block).

Evidence
  Aerial  campus z18 8x8 mosaic (z19 absent here): three dark-roofed semi pairs in a row
          turned ~22 deg from the x axis (row runs ESE), fronts on the NNW side facing the
          wide Broadlands Road carriageway, ~2 m passages between the pairs, gardens
          behind (south). Ridge runs along each pair.
  OSM     ways 177807745 (165) 732 (163) 757 (161) 774 (159) 800 (157) 764 (155);
          each house ~8.6 x 6.8 m.
  Street  none for this stretch: same 1930s red-brick semi type as 167-185
          (kartaview-1471276937), `hint` for walls/roof/windows/door sides.
  LIDAR   pristine Geocraft: ground y50 (165-159), y49 (157-155); carpet roofs 7-9 above.
Squared: each pair is one aligned run of two 9-wide, 8-deep boxes on a shared party wall;
pairs step south along the row (the real 22 deg turn), meeting corner to corner.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'scripts'))
from site_kit import Plan, World, apply, preview  # noqa: E402

NAME = 'broadlands_rd_155_165'
WALL, FLOOR, ROOF = 'bricks', 'spruce_planks', 'deepslate_tile'
TOP = 18                       # clear this far above the floor


class H:
    def __init__(self, no, x0, x1, z0, z1, b, door, ovw=1, ove=1):
        self.no, self.x0, self.x1, self.z0, self.z1, self.b = no, x0, x1, z0, z1, b
        self.door = door                # 'W' door near x0, 'E' near x1
        self.ovw, self.ove = ovw, ove   # gable-end overhang west / east
        self.shared = set()             # sides on a party wall: 'W' (x0) / 'E' (x1)

    @property
    def xd(self):
        return self.x0 + 2 if self.door == 'W' else self.x1 - 2

    @property
    def xr(self):                       # rear door column
        return self.xd + 2 if self.door == 'W' else self.xd - 2

    def walls(self):
        return {(x, z) for x in range(self.x0, self.x1 + 1) for z in range(self.z0, self.z1 + 1)
                if z in (self.z0, self.z1) or x in (self.x0, self.x1)}

    def inner(self):
        return [(x, z) for x in range(self.x0 + 1, self.x1) for z in range(self.z0 + 1, self.z1)]


# front = north (z0); pairs run west -> east and step south with the road
HOUSES = [
    H('165', 6480, 6488, -5755, -5748, 50, 'W', ove=1), H('163', 6488, 6496, -5755, -5748, 50, 'E', ovw=1, ove=0),
    H('161', 6498, 6506, -5749, -5742, 50, 'W', ovw=0), H('159', 6506, 6514, -5749, -5742, 50, 'E', ove=0),
    H('157', 6515, 6523, -5741, -5734, 49, 'W', ovw=0), H('155', 6523, 6532, -5741, -5734, 49, 'E'),
]
PAIRS = [(0, 1), (2, 3), (4, 5)]
for a, c in PAIRS:
    HOUSES[a].shared.add('E')
    HOUSES[c].shared.add('W')


def pane(axis):
    return 'glass_pane[east=true,west=true]' if axis == 'x' else 'glass_pane[north=true,south=true]'


def stair(mat, facing, half='bottom'):
    return f'{mat}_stairs[facing={facing},half={half}]'


class Build:
    def __init__(self):
        self.p = Plan(NAME)
        self.p.outside_footprint_ok = ('22-deg rotated semi row squared to the axes: box corners 1-2 blocks past the '
                                       'OSM rectangles (aerial campus z18 8x8 mosaic; OSM ways 177807745..764)')
        self.live = World()

    def set(self, x, y, z, s):
        self.p.set(x, y, z, s)

    def ground_top(self, x, z):
        y = 45
        while self.live.block(x, y + 1, z) not in ('minecraft:air', None):
            y += 1
        return y

    # --- clearing -----------------------------------------------------------
    def clear(self):
        """Geocraft building raster (+1 fringe) and every house column go to air above ground."""
        import osm_footprints
        idx = osm_footprints.OSMIndex()
        ours = {h.no for h in HOUSES}
        cols = set()
        for (x, z), i in idx.cells().items():
            n, s = osm_footprints._addr(idx.buildings[i][1])
            if s == 'Broadlands Road' and n in ours:
                cols.update((x + dx, z + dz) for dx in (-1, 0, 1) for dz in (-1, 0, 1))
        for h in HOUSES:
            cols.update((x, z) for x in range(h.x0 - 2, h.x1 + 3) for z in range(h.z0 - 2, h.z1 + 3))
        self.cols = cols
        bmin = {}
        for h in HOUSES:
            for x in range(h.x0 - 2, h.x1 + 3):
                for z in range(h.z0 - 2, h.z1 + 3):
                    bmin[(x, z)] = min(bmin.get((x, z), 99), h.b)
        for x, z in cols:
            b = bmin.get((x, z)) or min(HOUSES, key=lambda h: abs(x - (h.x0 + h.x1) / 2) + abs(z - (h.z0 + h.z1) / 2)).b
            g = self.ground_top(x, z)
            for y in range(min(g, b) + 1, max(g, b + TOP) + 1):
                if self.live.block(x, y, z) not in ('minecraft:air', None):
                    self.set(x, y, z, 'air')

    # --- one house ----------------------------------------------------------
    def shell(self, h):
        b = h.b
        for x, z in h.walls():
            for y in range(b - 4, b):
                self.set(x, y, z, 'stone')
            for y in range(b, b + 6):
                self.set(x, y, z, WALL)
        for x, z in h.inner():
            for y in range(b - 4, b):
                self.set(x, y, z, 'stone')
            self.set(x, b, z, FLOOR)
            for y in range(b + 1, b + 6):
                self.set(x, y, z, 'air')
            self.set(x, b + 3, z, FLOOR)
        # stair: run south from the front door along column xd; opening over the first two steps
        xd = h.xd
        for i, z in enumerate((h.z0 + 2, h.z0 + 3, h.z0 + 4)):
            self.set(xd, h.b + 1 + i, z, stair('spruce', 'south'))
        for z in (h.z0 + 2, h.z0 + 3):
            self.set(xd, b + 3, z, 'air')

    def pick(self, lo, hi, avoid, parity):
        return [x for x in range(lo, hi + 1) if all(abs(x - a) >= 2 for a in avoid) and (x - lo) % 2 == parity]

    def openings(self, h):
        b, xd, xr = h.b, h.xd, h.xr
        # front (north, z0): door + windows
        for y, p in ((b + 1, 'lower'), (b + 2, 'upper')):
            self.set(xd, y, h.z0, f'spruce_door[facing=north,half={p},hinge=left,open=false]')
        for x in self.pick(h.x0 + 2, h.x1 - 2, [xd], 0):
            self.set(x, b + 2, h.z0, pane('x'))
        for x in range(h.x0 + 2, h.x1 - 1, 2):
            self.set(x, b + 5, h.z0, pane('x'))
        # rear (south, z1): door + windows
        for y, p in ((b + 1, 'lower'), (b + 2, 'upper')):
            self.set(xr, y, h.z1, f'spruce_door[facing=south,half={p},hinge=right,open=false]')
        for x in self.pick(h.x0 + 2, h.x1 - 2, [xr], 0):
            self.set(x, b + 2, h.z1, pane('x'))
        for x in range(h.x0 + 2, h.x1 - 1, 2):
            self.set(x, b + 5, h.z1, pane('x'))
        # outer side walls (not party): one window each floor
        zm = (h.z0 + h.z1) // 2
        for side, x in (('W', h.x0), ('E', h.x1)):
            if side in h.shared:
                continue
            for y in (b + 2, b + 5):
                self.set(x, y, zm, pane('z'))
        # stoops (the lawn outside is the ground pass's; these two cells are ours)
        for x, z in ((xd, h.z0 - 1), (xr, h.z1 + 1)):
            self.set(x, h.b, z, 'smooth_stone')
            for y in range(h.b + 1, h.b + 4):
                self.set(x, y, z, 'air')

    # --- roofs --------------------------------------------------------------
    def roof(self):
        heights = {}
        for h in HOUSES:
            rz0, rz1 = h.z0 - 1, h.z1 + 1
            rx0 = h.x0 if 'W' in h.shared else h.x0 - h.ovw
            rx1 = h.x1 if 'E' in h.shared else h.x1 + h.ove
            for x in range(rx0, rx1 + 1):
                for z in range(rz0, rz1 + 1):
                    ds = [z - rz0, rz1 - z]
                    if 'W' not in h.shared:
                        ds.append(x - rx0)
                    if 'E' not in h.shared:
                        ds.append(rx1 - x)
                    d = min(ds)
                    y = h.b + 6 + d // 2
                    t = 'bottom' if d % 2 == 0 else 'top'
                    inside = h.x0 <= x <= h.x1 and h.z0 <= z <= h.z1
                    cur = heights.get((x, z))
                    key = (y, 1 if t == 'top' else 0)
                    if cur is None or key > cur[0]:
                        heights[(x, z)] = (key, t, h.b, inside)
        for (x, z), (key, t, b, inside) in heights.items():
            y = key[0]
            if inside:
                for yy in range(b + 6, y):
                    self.set(x, yy, z, WALL)
            self.set(x, y, z, f'{ROOF}_slab[type={t}]')
        # one chimney stack per pair, on the party wall at mid-depth
        for a, c in PAIRS:
            ha = HOUSES[a]
            x, z = ha.x1, (ha.z0 + ha.z1) // 2
            ridge = max(k[0][0] for (xx, zz), k in heights.items() if abs(xx - x) <= 3 and abs(zz - z) <= 4)
            for y in range(ha.b + 6, ridge + 3):
                self.set(x, y, z, WALL)

    def build(self):
        self.clear()
        for h in HOUSES:
            self.shell(h)
            self.openings(h)
        self.roof()
        import osm_footprints                       # drop eave-overhang corners that stray past the OSM margin
        for q, v in osm_footprints.guard(self.p.cells)['outside'].items():
            if 'slab' in v[0]:
                del self.p.cells[q]
        return self.p


def build():
    return Build().build()


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--apply', action='store_true')
    a = ap.parse_args()
    plan = build()
    out = ROOT / f'verification/site/{NAME}-preview.png'
    preview(plan, out, scale=4)
    print(json.dumps(plan.summary())[:600])
    apply(plan, dry=not a.apply)
