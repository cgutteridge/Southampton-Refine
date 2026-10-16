#!/usr/bin/env python3
"""Q-087: Broadlands Road nos. 167-185 (odd), west side - five brick semi-detached
pairs, HOUSE ONLY (layered pass 1 of cell 50,-46; Claude, 14 Oct 2026).

Houses only (HANDOFF-LAYERED-PASSES s1): no lawn, fences, hedges, trees. The
build owns each house box, its roof overhang, the two door stoops and the
Geocraft building raster it replaces (cleared down to the ground block).

Evidence
  Street  kartaview-1471276937 (camera MC 6470,-5804, looking SSE along the
          street): plain two-storey red-brick 1930s semis, small white
          casements, dark tile roofs with brick chimney stacks on the party
          line, hedges/fences in front, no bays. Same type for the whole run
          (pairs 177/175..167 are out of shot: `hint`).
  OSM     ways 159868612 (185) 617 (183) 177807799 (181) 788 (179) 804 (175)
          821 (177) 833 (173) 824 (171) 713 (169) 720 (167); houses are
          7 m deep and 7-9 m wide, 185..175 axis-aligned within ~8 deg
          (fronts east), 173..167 turned 29-47 deg on the bend.
  LIDAR   pristine Geocraft: ground y54 (183/185), y53 (173-181), y52
          (167-171); brick carpet roofs 6-7 above ground.
Squared houses: each box 7 deep (x), 7-9 wide (z); aligned pairs share one
x range and a party row; the bend pairs are stepped boxes meeting on a short
party wall.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'scripts'))
from site_kit import Plan, World, apply, preview  # noqa: E402

NAME = 'broadlands_rd_167_185'
WALL, FLOOR, ROOF = 'bricks', 'spruce_planks', 'deepslate_tile'
TOP = 18                       # clear this far above the floor


class H:
    def __init__(self, no, x0, x1, z0, z1, b, door):
        self.no, self.x0, self.x1, self.z0, self.z1, self.b = no, x0, x1, z0, z1, b
        self.door = door                # 'N' door near z0, 'S' near z1
        self.shared = set()             # sides on a party wall: 'N' (z0) / 'S' (z1)

    @property
    def zd(self):
        return self.z0 + 2 if self.door == 'N' else self.z1 - 2

    @property
    def zr(self):                       # rear door row
        return self.zd + 2 if self.door == 'N' else self.zd - 2

    def walls(self):
        return {(x, z) for x in range(self.x0, self.x1 + 1) for z in range(self.z0, self.z1 + 1)
                if x in (self.x0, self.x1) or z in (self.z0, self.z1)}

    def inner(self):
        return [(x, z) for x in range(self.x0 + 1, self.x1) for z in range(self.z0 + 1, self.z1)]


# west -> east is the depth axis (front = east, x1); pairs run north -> south (z up)
HOUSES = [
    H('185', 6446, 6452, -5850, -5842, 54, 'N'), H('183', 6446, 6452, -5842, -5835, 54, 'S'),
    H('181', 6443, 6449, -5832, -5824, 53, 'N'), H('179', 6443, 6449, -5824, -5817, 53, 'S'),
    H('177', 6445, 6451, -5811, -5803, 53, 'N'), H('175', 6445, 6451, -5803, -5796, 53, 'S'),
    H('173', 6450, 6456, -5790, -5783, 53, 'N'), H('171', 6455, 6461, -5783, -5777, 52, 'S'),
    H('169', 6463, 6469, -5772, -5766, 52, 'N'), H('167', 6467, 6473, -5766, -5759, 52, 'S'),
]
PAIRS = [(0, 1), (2, 3), (4, 5), (6, 7), (8, 9)]
ALIGNED = {(0, 1), (2, 3), (4, 5)}
for a, c in PAIRS:
    HOUSES[a].shared.add('S')
    HOUSES[c].shared.add('N')
for a, c in PAIRS:
    if (a, c) not in ALIGNED:               # corner-contact pairs: roofs stay separate hips
        HOUSES[a].shared.clear()
        HOUSES[c].shared.clear()


def pane(axis):
    return 'glass_pane[east=true,west=true]' if axis == 'x' else 'glass_pane[north=true,south=true]'


def stair(mat, facing, half='bottom'):
    return f'{mat}_stairs[facing={facing},half={half}]'


class Build:
    def __init__(self):
        self.p = Plan(NAME)
        self.live = World()
        self.cells = {}

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
        # stair: run west from the front door along row zd; opening over the first two steps
        zd = h.zd
        for i, x in enumerate((h.x1 - 2, h.x1 - 3, h.x1 - 4)):
            self.set(x, h.b + 1 + i, zd, stair('spruce', 'west'))
        for x in (h.x1 - 2, h.x1 - 3):
            self.set(x, b + 3, zd, 'air')

    def pick(self, lo, hi, avoid, parity):
        return [z for z in range(lo, hi + 1) if all(abs(z - a) >= 2 for a in avoid) and (z - lo) % 2 == parity]

    def openings(self, h):
        b, zd, zr = h.b, h.zd, h.zr
        # front (east, x1): door + windows
        for y, p in ((b + 1, 'lower'), (b + 2, 'upper')):
            self.set(h.x1, y, zd, f'spruce_door[facing=east,half={p},hinge=left,open=false]')
        for z in self.pick(h.z0 + 2, h.z1 - 2, [zd], 0):
            self.set(h.x1, b + 2, z, pane('z'))
        for z in range(h.z0 + 2, h.z1 - 1, 2):
            self.set(h.x1, b + 5, z, pane('z'))
        # rear (west, x0): door + windows
        for y, p in ((b + 1, 'lower'), (b + 2, 'upper')):
            self.set(h.x0, y, zr, f'spruce_door[facing=west,half={p},hinge=right,open=false]')
        for z in self.pick(h.z0 + 2, h.z1 - 2, [zr], 0):
            self.set(h.x0, b + 2, z, pane('z'))
        for z in range(h.z0 + 2, h.z1 - 1, 2):
            self.set(h.x0, b + 5, z, pane('z'))
        # outer side walls (not party): one window each floor
        xm = (h.x0 + h.x1) // 2
        for side, z in (('N', h.z0), ('S', h.z1)):
            if side in h.shared:
                continue
            for y in (b + 2, b + 5):
                self.set(xm, y, z, pane('x'))
        # stoops (the lawn outside is the ground pass's; these two cells are ours)
        for x, z in ((h.x1 + 1, zd), (h.x0 - 1, zr)):
            self.set(x, h.b, z, 'smooth_stone')
            for y in range(h.b + 1, h.b + 4):
                self.set(x, y, z, 'air')

    # --- roofs --------------------------------------------------------------
    def roof(self):
        heights = {}
        chim = []
        for h in HOUSES:
            rx0, rx1 = h.x0 - 1, h.x1 + 1
            rz0 = h.z0 if 'N' in h.shared else h.z0 - 1
            rz1 = h.z1 if 'S' in h.shared else h.z1 + 1
            for x in range(rx0, rx1 + 1):
                for z in range(rz0, rz1 + 1):
                    ds = [x - rx0, rx1 - x]
                    if 'N' not in h.shared:
                        ds.append(z - rz0)
                    if 'S' not in h.shared:
                        ds.append(rz1 - z)
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
        top = max(k[0][0] for k in heights.values())
        # one chimney stack per pair, on the party line (corner-contact pairs: the shared corner)
        for a, c in PAIRS:
            ha, hc = HOUSES[a], HOUSES[c]
            z = ha.z1 if (a, c) in ALIGNED else ha.z1
            x = (ha.x0 + ha.x1) // 2 if (a, c) in ALIGNED else max(ha.x0, hc.x0) + 1
            b = ha.b
            ridge = max(k[0][0] for (xx, zz), k in heights.items() if abs(xx - x) <= 3 and abs(zz - z) <= 4)
            for y in range(b + 6, ridge + 3):
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
