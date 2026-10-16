#!/usr/bin/env python3
"""Q-099: Ripstone Gardens nos. 54-58 (even, north side) - HOUSE ONLY
(layered pass 1 of cell 50,-44; Claude, 15 Oct 2026).

Houses only (HANDOFF-LAYERED-PASSES s1): no lawn, fences, hedges, trees. The build
owns each house's cells (OSM raster), its roof overhang over unowned cells, the
door stoops and the Geocraft building raster it replaces.

Evidence
  OSM     ways 177758962, 177759011, 177759017 (nos. 54, 56, 58; addr:street Ripstone
          Gardens). Odd numbers face them across the road to the south, so every
          front is to the S.
  Aerial  highfield-campus z18 mosaics: form from OSM footprints (three small
          houses in a row, turned to the grid); roofs pitched with ridges along the
          depth (`hint`: 1930s-60s estate houses, dark tile, as 41-49).
  Street  none held for Ripstone Gardens; brick/dark tile/two-storey is a `hint`.
  LIDAR   ground from the pristine Geocraft world around each house.
Footprints are the OSM raster itself (the turn cannot be squared without leaving
the plot); walls are 8-connected so the shell is airtight.
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'scripts'))
import osm_footprints  # noqa: E402
from site_kit import Plan, World, apply, preview  # noqa: E402

NAME = 'ripstone_gardens_54_58'
WALL, FLOOR, ROOF = 'bricks', 'spruce_planks', 'deepslate_tile'
TOP = 18
WANT = {'54', '56', '58'}

# group -> (house numbers, roof mode, door facing or None=auto south, rear door)
GROUPS = [
    dict(nos=['58', '56', '54'], mode='each', front='S'),
]
DIRS = {'N': (0, -1), 'S': (0, 1), 'W': (-1, 0), 'E': (1, 0)}
OPP = {'N': 'S', 'S': 'N', 'W': 'E', 'E': 'W'}
N8 = [(dx, dz) for dx in (-1, 0, 1) for dz in (-1, 0, 1) if dx or dz]


def pane(axis):
    return 'glass_pane[east=true,west=true]' if axis == 'x' else 'glass_pane[north=true,south=true]'


def stair(mat, facing, half='bottom'):
    return f'{mat}_stairs[facing={facing},half={half}]'


class House:
    def __init__(self, no, cells, group):
        self.no, self.cells, self.group = no, cells, group
        self.front = group['front']


class Build:
    def __init__(self):
        self.p = Plan(NAME)
        self.live = World()
        idx = osm_footprints.OSMIndex()
        by_no = {}
        for (x, z), i in idx.cells().items():
            n, s = osm_footprints._addr(idx.buildings[i][1])
            if s == 'Ripstone Gardens' and n in WANT:
                by_no.setdefault(n, set()).add((x, z))
        self.idx = idx
        self.houses = []
        for g in GROUPS:
            for no in g['nos']:
                self.houses.append(House(no, by_no[no], g))
        self.owner = {}
        for k, h in enumerate(self.houses):
            for c in h.cells:
                self.owner[c] = k
        self.by_no_all = by_no

    def set(self, x, y, z, s):
        self.p.set(x, y, z, s)

    def ground_top(self, x, z):
        y = 45
        while self.live.block(x, y + 1, z) not in ('minecraft:air', None):
            y += 1
        return y

    def floor_y(self, h):
        ring = set()
        for (x, z) in h.cells:
            for dx in range(-3, 4):
                for dz in range(-3, 4):
                    c = (x + dx, z + dz)
                    if c not in self.owner and c not in self.by_no_all_cells:
                        ring.add(c)
        ys = [self.ground_top(x, z) for x, z in ring]
        return int(statistics.median(ys))

    def clear(self):
        cols = set()
        for (x, z) in self.owner:
            cols.update((x + dx, z + dz) for dx in (-2, -1, 0, 1, 2) for dz in (-2, -1, 0, 1, 2))
        # Geocraft raster of these numbers (+1 fringe) is already inside the above
        self.cols = cols
        bcol = {}
        for h in self.houses:
            for (x, z) in h.cells:
                for dx in range(-2, 3):
                    for dz in range(-2, 3):
                        c = (x + dx, z + dz)
                        bcol[c] = min(bcol.get(c, 99), h.b)
        for x, z in cols:
            b = bcol[(x, z)]
            g = self.ground_top(x, z)
            for y in range(min(g, b) + 1, max(g, b + TOP) + 1):
                if self.live.block(x, y, z) not in ('minecraft:air', None):
                    self.set(x, y, z, 'air')

    def exposed(self, c, d):
        dx, dz = DIRS[d]
        return (c[0] + dx, c[1] + dz) not in self.owner

    def shell(self, k, h):
        b = h.b
        own = h.cells
        h.walls = set()
        for c in own:
            for dx, dz in N8:
                n = (c[0] + dx, c[1] + dz)
                ko = self.owner.get(n)
                if ko is None or (ko != k and k < ko):
                    h.walls.add(c)
                    break
        h.inner = own - h.walls
        for x, z in own:
            for y in range(b - 4, b):
                self.set(x, y, z, 'stone')
        for x, z in h.walls:
            for y in range(b, b + 6):
                self.set(x, y, z, WALL)
        for x, z in h.inner:
            self.set(x, b, z, FLOOR)
            for y in range(b + 1, b + 6):
                self.set(x, y, z, 'air')
            self.set(x, b + 3, z, FLOOR)

    def doors(self, k, h, taken):
        b = h.b
        f = h.front
        r = OPP[f]
        fx, fz = DIRS[f]
        # front door cell: wall cell exposed to the front, nearest the middle of the
        # front-most run of the house (per unit for the block group)
        units = [h]
        cand = [c for c in h.walls if self.exposed(c, f) and (c[0] - fx, c[1] - fz) in h.inner]
        if not cand:
            return
        if f in 'NS':
            front_edge = max(c[1] for c in cand) if f == 'S' else min(c[1] for c in cand)
            cand = [c for c in cand if abs(c[1] - front_edge) <= 2]
            mid = sum(c[0] for c in cand) / len(cand)
            c0 = min(cand, key=lambda c: abs(c[0] - mid))
        else:
            front_edge = min(c[0] for c in cand)
            cand = [c for c in cand if c[0] <= front_edge + 1]
            mid = sum(c[1] for c in cand) / len(cand)
            c0 = min(cand, key=lambda c: abs(c[1] - mid))
        h.door = c0
        for y, p in ((b + 1, 'lower'), (b + 2, 'upper')):
            self.set(c0[0], y, c0[1], f"spruce_door[facing={ {'S':'south','N':'north','W':'west','E':'east'}[f] },half={p},hinge=left,open=false]")
        st = (c0[0] + fx, c0[1] + fz)
        self.set(st[0], b, st[1], 'smooth_stone')
        for y in range(b + 1, b + 4):
            self.set(st[0], y, st[1], 'air')
        # stair inward from the door, ascending away from the front
        ix, iz = -fx, -fz
        cells = [(c0[0] + ix * d, c0[1] + iz * d) for d in (2, 3, 4)]
        if all(c in h.inner for c in cells):
            for i, c in enumerate(cells):
                self.set(c[0], b + 1 + i, c[1], stair('spruce', {'S': 'north', 'N': 'south', 'W': 'east', 'E': 'west'}[f]))
            for c in cells[:2]:
                self.set(c[0], b + 3, c[1], 'air')
        # rear door
        cand = [c for c in h.walls if self.exposed(c, r) and (c[0] - DIRS[r][0], c[1] - DIRS[r][1]) in h.inner]
        if cand:
            if r in 'NS':
                e = min(c[1] for c in cand) if r == 'N' else max(c[1] for c in cand)
                cc = [c for c in cand if abs(c[1] - e) <= 2]
                m = sum(c[0] for c in cc) / len(cc)
                c1 = min(cc, key=lambda c: abs(c[0] - m))
            else:
                e = max(c[0] for c in cand)
                cc = [c for c in cand if c[0] >= e - 1]
                m = sum(c[1] for c in cc) / len(cc)
                c1 = min(cc, key=lambda c: abs(c[1] - m))
            h.rear = c1
            rf = {'N': 'north', 'E': 'east', 'S': 'south', 'W': 'west'}[r]
            for y, p in ((b + 1, 'lower'), (b + 2, 'upper')):
                self.set(c1[0], y, c1[1], f'spruce_door[facing={rf},half={p},hinge=right,open=false]')
            sx, sz = c1[0] + DIRS[r][0], c1[1] + DIRS[r][1]
            self.set(sx, b, sz, 'smooth_stone')
            for y in range(b + 1, b + 4):
                self.set(sx, y, sz, 'air')
        else:
            h.rear = None

    def windows(self, k, h):
        b = h.b
        door = {getattr(h, 'door', None), getattr(h, 'rear', None)}
        for c in h.walls:
            exp = [d for d in 'NSEW' if self.exposed(c, d)]
            if len(exp) != 1:
                continue
            d = exp[0]
            lat = [(0, 1), (0, -1)] if d in 'EW' else [(1, 0), (-1, 0)]
            ok = True
            for lx, lz in lat:
                n = (c[0] + lx, c[1] + lz)
                if n not in h.walls or not self.exposed(n, d):
                    ok = False
            if not ok:
                continue
            if any(abs(c[0] - q[0]) + abs(c[1] - q[1]) < 3 for q in door if q):
                continue
            par = c[0] if d in 'NS' else c[1]
            if par % 2:
                continue
            axis = 'z' if d in 'EW' else 'x'
            self.set(c[0], b + 2, c[1], pane(axis))
            self.set(c[0], b + 5, c[1], pane(axis))

    def roof(self):
        done = {}
        seen = set()
        todo = []
        for g in GROUPS:
            hs = [h for h in self.houses if h.group is g]
            if g['mode'] == 'group':
                todo.append((hs, set().union(*[h.cells for h in hs])))
            else:
                todo.extend(([h], h.cells) for h in hs)
        chim = []
        for hs, own in todo:
            rs = set(own)
            for (x, z) in own:
                for dx, dz in N8:
                    n = (x + dx, z + dz)
                    if n not in self.owner:
                        rs.add(n)
            # chebyshev distance to outside of rs
            dist = {}
            front = [c for c in rs if any((c[0] + dx, c[1] + dz) not in rs for dx, dz in N8)]
            for c in front:
                dist[c] = 0
            q = list(front)
            while q:
                nq = []
                for c in q:
                    for dx, dz in N8:
                        n = (c[0] + dx, c[1] + dz)
                        if n in rs and n not in dist:
                            dist[n] = dist[c] + 1
                            nq.append(n)
                q = nq
            b = hs[0].b
            for c, d in dist.items():
                y = b + 6 + d // 2
                t = 'bottom' if d % 2 == 0 else 'top'
                key = (y, 1 if t == 'top' else 0)
                cur = done.get(c)
                if cur is None or key > cur[0]:
                    done[c] = (key, t, b, c in self.owner)
            best = max(dist, key=lambda c: (dist[c] if c in own else -1, -abs(c[0] - sum(x for x, _ in own) / len(own))))
            chim.append((best, b, hs[0].group))
        for (x, z), (key, t, b, inside) in done.items():
            y = key[0]
            if inside:
                for yy in range(b + 6, y):
                    self.set(x, yy, z, WALL)
            self.set(x, y, z, f'{ROOF}_slab[type={t}]')
        for (x, z), b, g in chim:
            ridge = max(k[0][0] for (xx, zz), k in done.items() if abs(xx - x) <= 1 and abs(zz - z) <= 1)
            for y in range(b + 6, ridge + 3):
                self.set(x, y, z, WALL)

    def build(self):
        self.by_no_all_cells = set(self.owner)
        for h in self.houses:
            h.b = self.floor_y(h)
        # a group shares one floor level
        for g in GROUPS:
            hs = [h for h in self.houses if h.group is g]
            if g['mode'] == 'group':
                bb = min(h.b for h in hs)
                for h in hs:
                    h.b = bb
        self.clear()
        for k, h in enumerate(self.houses):
            self.shell(k, h)
        for k, h in enumerate(self.houses):
            self.doors(k, h, set())
            self.windows(k, h)
        self.roof()
        for q, v in osm_footprints.guard(self.p.cells)['outside'].items():
            if 'slab' in v[0]:
                del self.p.cells[q]
        for h in self.houses:
            print(h.no, 'b', h.b, 'cells', len(h.cells), 'door', getattr(h, 'door', None), 'rear', getattr(h, 'rear', None))
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
