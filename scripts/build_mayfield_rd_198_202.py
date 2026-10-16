#!/usr/bin/env python3
"""Q-090: Mayfield Road nos. 198, 200, 202 (even) - three detached two-storey houses,
HOUSE ONLY (layered pass 1 of cell 50,-46; Claude, 15 Oct 2026).

Houses only (HANDOFF-LAYERED-PASSES s1): no lawn, fences, hedges, trees. The build owns each
house box, its roof overhang, door stoops and the Geocraft building raster it replaces.

Evidence
  OSM     ways 177910475/480/485 (nos 198/200/202); each footprint ~8x9 cells rotated ~35 deg;
          road lies SSE (pavement polished_diorite from x6506,z-5877), plots run NNW. Fronts face south.
  LIDAR   pristine Geocraft ground y53; light-grey carpet roofs 4-9 above.
  Street  none in the cell sources (hint: same 1930s brick houses with dark tile roofs as
          Mayfield Rd 159-169 Q-089 / Broadlands Rd 167-185 Q-087; door sides = hint).
Squared houses: each box 7x7 (x, z) centred on its OSM centroid, front = SOUTH wall (z1).
Separate hip roofs (staggered fronts, no party walls).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'scripts'))
from site_kit import Plan, World, apply, preview  # noqa: E402

NAME = 'mayfield_rd_198_202'
STREET = 'Mayfield Road'
WALL, FLOOR, ROOF = 'bricks', 'spruce_planks', 'deepslate_tile'
TOP = 18                       # clear this far above the floor


class H:
    def __init__(self, no, x0, x1, z0, z1, b, door):
        self.no, self.x0, self.x1, self.z0, self.z1, self.b = no, x0, x1, z0, z1, b
        self.door = door                # 'W' door near x0, 'E' near x1 (front = south wall z1)

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
    H('198', 6523, 6529, -5884, -5878, 53, 'E'),
    H('200', 6514, 6520, -5888, -5882, 53, 'W'),
    H('202', 6506, 6512, -5890, -5884, 53, 'E'),
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
        # stair: run north from the front (south) door down column xd; opening over the first two steps
        xd = h.xd
        for i, z in enumerate((h.z1 - 2, h.z1 - 3, h.z1 - 4)):
            self.set(xd, h.b + 1 + i, z, stair('spruce', 'north'))
        for z in (h.z1 - 2, h.z1 - 3):
            self.set(xd, b + 3, z, 'air')

    def pick(self, lo, hi, avoid):
        return [x for x in range(lo, hi + 1) if all(abs(x - a) >= 2 for a in avoid) and (x - lo) % 2 == 0]

    def openings(self, h):
        b, xd, xr = h.b, h.xd, h.xr
        # front (south, z1): door + windows
        for y, p in ((b + 1, 'lower'), (b + 2, 'upper')):
            self.set(xd, y, h.z1, f'spruce_door[facing=south,half={p},hinge=left,open=false]')
        for x in self.pick(h.x0 + 2, h.x1 - 2, [xd]):
            self.set(x, b + 2, h.z1, pane('x'))
        for x in range(h.x0 + 2, h.x1 - 1, 2):
            self.set(x, b + 5, h.z1, pane('x'))
        # rear (north, z0): door + windows
        for y, p in ((b + 1, 'lower'), (b + 2, 'upper')):
            self.set(xr, y, h.z0, f'spruce_door[facing=north,half={p},hinge=right,open=false]')
        for x in self.pick(h.x0 + 2, h.x1 - 2, [xr]):
            self.set(x, b + 2, h.z0, pane('x'))
        for x in range(h.x0 + 2, h.x1 - 1, 2):
            self.set(x, b + 5, h.z0, pane('x'))
        # side walls: one window each floor
        zm = (h.z0 + h.z1) // 2
        for x in (h.x0, h.x1):
            for y in (b + 2, b + 5):
                self.set(x, y, zm, pane('z'))
        # stoops (the lawn outside is the ground pass's; these two cells are ours)
        for x, z in ((xd, h.z1 + 1), (xr, h.z0 - 1)):
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
