#!/usr/bin/env python3
"""Q-089: Mayfield Road nos. 159-169 (odd) - six detached/staggered two-storey houses,
HOUSE ONLY (layered pass 1 of cell 50,-46; Claude, 15 Oct 2026).

Houses only (HANDOFF-LAYERED-PASSES s1): no lawn, fences, hedges, trees. The build owns each
house box, its roof overhang, door stoops and the Geocraft building raster it replaces.

Evidence
  OSM     ways 177809759..811 (nos 159-169); each footprint ~9x9 m rotated ~30 deg on a
          bend; road lies NNE (Geocraft carriageway), plots run SSW. Fronts face the road.
  LIDAR   pristine Geocraft ground y53 (y54 at 169); light-grey carpet roofs 4-8 above.
  Street  none in the cell sources (hint: Highfield-area 1930s brick houses, brick walls,
          dark tile roofs - same as Broadlands Rd 167-185 Q-087; door sides = hint).
Squared houses: each box 7x7 (x, z) centred on its OSM centroid, front = north (z0).
Separate hip roofs (no shared party walls: the OSM fronts are staggered).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'scripts'))
from site_kit import Plan, World, apply, preview  # noqa: E402

NAME = 'mayfield_rd_159_169'
STREET = 'Mayfield Road'
WALL, FLOOR, ROOF = 'bricks', 'spruce_planks', 'deepslate_tile'
TOP = 18                       # clear this far above the floor


class H:
    def __init__(self, no, x0, x1, z0, z1, b, door):
        self.no, self.x0, self.x1, self.z0, self.z1, self.b = no, x0, x1, z0, z1, b
        self.door = door                # 'W' door near x0, 'E' near x1 (front = north wall z0)

    @property
    def xd(self):
        return self.x0 + 2 if self.door == 'W' else self.x1 - 2

    @property
    def xr(self):                       # rear door column
        return self.xd + 2 if self.door == 'W' else self.xd - 2

    def walls(self):
        return {(x, z) for x in range(self.x0, self.x1 + 1) for z in range(self.z0, self.z1 + 1)
                if x in (self.x0, self.x1) or z in (self.z0, self.z1)}

    def inner(self):
        return [(x, z) for x in range(self.x0 + 1, self.x1) for z in range(self.z0 + 1, self.z1)]


HOUSES = [
    H('159', 6521, 6527, -5850, -5844, 53, 'W'),
    H('161', 6512, 6518, -5854, -5848, 53, 'E'),
    H('163', 6505, 6511, -5857, -5851, 53, 'W'),
    H('165', 6495, 6501, -5861, -5855, 53, 'E'),
    H('167', 6488, 6494, -5864, -5858, 53, 'W'),
    H('169', 6479, 6485, -5868, -5862, 54, 'E'),
]


def pane(axis):
    return 'glass_pane[east=true,west=true]' if axis == 'x' else 'glass_pane[north=true,south=true]'


def stair(mat, facing, half='bottom'):
    return f'{mat}_stairs[facing={facing},half={half}]'


class Build:
    def __init__(self):
        self.p = Plan(NAME)
        self.live = World()

    def set(self, x, y, z, s):
        self.p.set(x, y, z, s)

    def ground_top(self, x, z):
        y = 45
        while self.live.block(x, y + 1, z) not in ('minecraft:air', None):
            y += 1
        return y

    def clear(self):
        """Geocraft building raster (+1 fringe) and every house column go to air above ground."""
        import osm_footprints
        idx = osm_footprints.OSMIndex()
        ours = {h.no for h in HOUSES}
        cols = set()
        for (x, z), i in idx.cells().items():
            n, s = osm_footprints._addr(idx.buildings[i][1])
            if s == STREET and n in ours:
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
        # stair: run south from the front door down column xd; opening over the first two steps
        xd = h.xd
        for i, z in enumerate((h.z0 + 2, h.z0 + 3, h.z0 + 4)):
            self.set(xd, h.b + 1 + i, z, stair('spruce', 'south'))
        for z in (h.z0 + 2, h.z0 + 3):
            self.set(xd, b + 3, z, 'air')

    def pick(self, lo, hi, avoid):
        return [x for x in range(lo, hi + 1) if all(abs(x - a) >= 2 for a in avoid) and (x - lo) % 2 == 0]

    def openings(self, h):
        b, xd, xr = h.b, h.xd, h.xr
        # front (north, z0): door + windows
        for y, p in ((b + 1, 'lower'), (b + 2, 'upper')):
            self.set(xd, y, h.z0, f'spruce_door[facing=north,half={p},hinge=left,open=false]')
        for x in self.pick(h.x0 + 2, h.x1 - 2, [xd]):
            self.set(x, b + 2, h.z0, pane('x'))
        for x in range(h.x0 + 2, h.x1 - 1, 2):
            self.set(x, b + 5, h.z0, pane('x'))
        # rear (south, z1): door + windows
        for y, p in ((b + 1, 'lower'), (b + 2, 'upper')):
            self.set(xr, y, h.z1, f'spruce_door[facing=south,half={p},hinge=right,open=false]')
        for x in self.pick(h.x0 + 2, h.x1 - 2, [xr]):
            self.set(x, b + 2, h.z1, pane('x'))
        for x in range(h.x0 + 2, h.x1 - 1, 2):
            self.set(x, b + 5, h.z1, pane('x'))
        # side walls: one window each floor
        zm = (h.z0 + h.z1) // 2
        for x in (h.x0, h.x1):
            for y in (b + 2, b + 5):
                self.set(x, y, zm, pane('z'))
        # stoops (the lawn outside is the ground pass's; these two cells are ours)
        for x, z in ((xd, h.z0 - 1), (xr, h.z1 + 1)):
            self.set(x, h.b, z, 'smooth_stone')
            for y in range(h.b + 1, h.b + 4):
                self.set(x, y, z, 'air')

    def roof(self):
        heights = {}
        for h in HOUSES:
            rx0, rx1, rz0, rz1 = h.x0 - 1, h.x1 + 1, h.z0 - 1, h.z1 + 1
            for x in range(rx0, rx1 + 1):
                for z in range(rz0, rz1 + 1):
                    d = min(x - rx0, rx1 - x, z - rz0, rz1 - z)
                    y = h.b + 6 + d // 2
                    t = 'bottom' if d % 2 == 0 else 'top'
                    inside = h.x0 <= x <= h.x1 and h.z0 <= z <= h.z1
                    key = (y, 1 if t == 'top' else 0)
                    cur = heights.get((x, z))
                    if cur is None or key > cur[0]:
                        heights[(x, z)] = (key, t, h.b, inside)
        for (x, z), (key, t, b, inside) in heights.items():
            y = key[0]
            if inside:
                for yy in range(b + 6, y):
                    self.set(x, yy, z, WALL)
            self.set(x, y, z, f'{ROOF}_slab[type={t}]')
        # one chimney stack per house, on the west gable, through the roof
        for h in HOUSES:
            x, z = h.x0 + 1, (h.z0 + h.z1) // 2
            ridge = heights[(x, z)][0][0]
            for y in range(h.b + 6, ridge + 3):
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
