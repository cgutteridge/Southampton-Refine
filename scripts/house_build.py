#!/usr/bin/env python3
"""Generic OSM-footprint house builder (house only: walls, floors, doors, windows, slab roofs).

One module for every "house only" run (layered pass 1: Granby Grove, Merton Rd, Ripstone and Blenheim Gardens
q165..q176 and later). A run is a small JSON spec in site/builds/<name>.json instead of a 390-line script copy:

  name           plan name (also the verification/site/<name>-cells.json record)
  notes          provenance: OSM ways, aerial/Street View evidence, date, queue item (free text, never read by code)
  modifies       earlier builds this one may overwrite (default [])
  ways           {"<osm way id>": "<label>"} the footprints to build
  roofs          {"<label>": "<slab material>"} e.g. brick, mud_brick, deepslate_tile, cobbled_deepslate
  groups         [{"nos": [labels], "mode": "each"|"group", "front": "N"|"S"|"E"|"W"}]
                 "group" = one roof over several houses sharing a floor level
  floor_min      minimum floor y (front pavement height) or null
  step_max       how far a door stoop looks outward for ground to level or step (default 4; 13 on long ledges)
  ledge_stair    true: ground that ends at a 1-block ledge beyond 4 columns gets a rising stair (default false)
  keep_edits     true: stoop/step cells survive the earlier-build clash filter (needed when `modifies` a ground build)

Usage:  .venv/bin/python scripts/house_build.py site/builds/<name>.json [--apply]   (dry run unless --apply)
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

GROUND = ('minecraft:stone', 'minecraft:gray_terracotta', 'minecraft:polished_granite', 'minecraft:polished_diorite', 'minecraft:light_gray_concrete', 'minecraft:grass_block', 'minecraft:dirt', 'minecraft:coarse_dirt', 'minecraft:gravel')
WALL, FLOOR = 'bricks', 'spruce_planks'
TOP = 20
DIRS = {'N': (0, -1), 'S': (0, 1), 'W': (-1, 0), 'E': (1, 0)}
OPP = {'N': 'S', 'S': 'N', 'W': 'E', 'E': 'W'}
N8 = [(dx, dz) for dx in (-1, 0, 1) for dz in (-1, 0, 1) if dx or dz]
FACE = {'S': 'south', 'N': 'north', 'W': 'west', 'E': 'east'}
TOWARD = {'S': 'north', 'N': 'south', 'W': 'east', 'E': 'west'}       # facing of a stair that rises toward the house


def pane(axis):
    return 'glass_pane[east=true,west=true]' if axis == 'x' else 'glass_pane[north=true,south=true]'


def stair(mat, facing, half='bottom'):
    return f'{mat}_stairs[facing={facing},half={half}]'


def load_spec(path):
    """Read and minimally validate a build spec; fills defaults.

    @param path: spec JSON path
    @returns: spec dict
    """
    spec = json.loads(Path(path).read_text())
    for k in ('name', 'ways', 'roofs', 'groups'):
        if k not in spec:
            raise SystemExit(f'{path}: missing "{k}"')
    spec.setdefault('modifies', [])
    spec.setdefault('floor_min', None)
    spec.setdefault('step_max', 4)
    spec.setdefault('ledge_stair', False)
    spec.setdefault('keep_edits', False)
    labels = set(spec['ways'].values())
    for g in spec['groups']:
        if g['front'] not in DIRS or g.get('mode', 'each') not in ('each', 'group'):
            raise SystemExit(f'{path}: bad group {g}')
        g.setdefault('mode', 'each')
        for no in g['nos']:
            if no not in labels or no not in spec['roofs']:
                raise SystemExit(f'{path}: label {no} needs a way and a roof')
    return spec


class House:
    def __init__(self, no, cells, group):
        self.no, self.cells, self.group = no, cells, group
        self.front = group['front']


class Build:
    def __init__(self, spec):
        self.spec = spec
        self.name = spec['name']
        self.groups = spec['groups']
        self.keep = set()
        self.p = Plan(self.name)
        self.live = World()
        idx = osm_footprints.OSMIndex()
        by_no = {}
        for (x, z), i in idx.cells().items():
            bp = idx.buildings[i][1]
            n = self.spec['ways'].get(str(bp.get('osm_way_id') or bp.get('osm_id')))
            if n:
                by_no.setdefault(n, set()).add((x, z))
        self.idx = idx
        self.houses = []
        for g in self.groups:
            for no in g['nos']:
                self.houses.append(House(no, by_no[no], g))
        self.owner = {}
        for k, h in enumerate(self.houses):
            for c in h.cells:
                self.owner[c] = k
        self.by_no_all = by_no

    def set(self, x, y, z, s):
        self.p.set(x, y, z, s)

    def kset(self, x, y, z, st):
        """Set a stoop/step cell; with keep_edits it survives the earlier-build clash filter."""
        if self.spec['keep_edits']:
            self.keep.add((x, y, z))
        self.set(x, y, z, st)

    def ground_top(self, x, z):
        y = 41
        while (self.live.block(x, y + 1, z) or '').split('[')[0] in GROUND:
            y += 1
        return y

    def surf(self, x, z):
        for y in range(75, 30, -1):
            n = (self.live.block(x, y, z) or 'minecraft:air').split('[')[0]
            if n in ('minecraft:stone', 'minecraft:grass_block', 'minecraft:dirt', 'minecraft:coarse_dirt', 'minecraft:granite'):
                return y
            if n in GROUND:
                return None  # road/pavement: not a house-plot reference
        return None

    def floor_y(self, h):
        # The old Geocraft building leaves gaps, so a scan from the bottom fails. Reference = untouched
        # plot-edge columns 4-7 from the footprint (stone / grass / dirt tops, not paving).
        ring = set()
        for (x, z) in h.cells:
            for dx in range(-7, 8):
                for dz in range(-7, 8):
                    c = (x + dx, z + dz)
                    if max(abs(dx), abs(dz)) >= 4 and c not in self.by_no_all_cells:
                        ring.add(c)
        near = {(x + dx, z + dz) for (x, z) in h.cells for dx in range(-3, 4) for dz in range(-3, 4)}
        ys = [self.surf(x, z) for x, z in ring - near]
        ys = [y for y in ys if y]
        print('ref surface n', len(ys), 'min', min(ys), 'max', max(ys))
        y = int(statistics.median(ys))
        # floor_min: flush with the front pavement so doors are walkable to the road without a 1-block hop (site_walk)
        return max(y, self.spec['floor_min']) if self.spec['floor_min'] is not None else y

    def clear(self):
        cols = set()
        for (x, z) in self.owner:
            cols.update((x + dx, z + dz) for dx in (-2, -1, 0, 1, 2) for dz in (-2, -1, 0, 1, 2))
        self.cols = cols
        for x, z in cols:
            b = min(self.houses, key=lambda h: min(max(abs(x - c[0]), abs(z - c[1])) for c in h.cells)).b
            if (x, z) in self.foreign or (x, z) in self.shared:
                continue
            own = (x, z) in self.owner
            for y in range(37, b):
                self.set(x, y, z, 'stone')
            if own:
                top = b + TOP
                rng = range(b, top + 1)
            else:
                if (self.live.block(x, b, z) or 'minecraft:air') == 'minecraft:air':
                    self.set(x, b, z, 'stone')
                rng = range(b + 1, b + TOP + 1)
            for y in rng:
                if own or (self.live.block(x, y, z) or 'minecraft:air').split('[')[0] not in GROUND:
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
        if f == 'N':
            front_edge = min(c[1] for c in cand)
            cand = [c for c in cand if c[1] <= front_edge + 2]
            mid = sum(c[0] for c in cand) / len(cand)
            c0 = min(cand, key=lambda c: abs(c[0] - mid))
        elif f == 'S':
            front_edge = max(c[1] for c in cand)
            cand = [c for c in cand if c[1] >= front_edge - 2]
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
        self.step_out(st, f, b)
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
                cc = [c for c in cand if (c[1] <= e + 2 if r == 'N' else c[1] >= e - 2)]
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
            self.step_out((sx, sz), r, b)
        else:
            h.rear = None

    def top_solid(self, x, z):
        # natural/Geocraft ground only (ignores roof fringe slabs and earlier steps of this build)
        for y in range(70, 40, -1):
            n = (self.live.block(x, y, z) or 'minecraft:air').split('[')[0]
            if n in GROUND and n != 'minecraft:stone_stairs':
                return y
        return None

    def step_out(self, st, d, b):
        # walk outward from the stoop to the road: ground ABOVE the floor in the way (old Geocraft ledge) is
        # lowered to the floor level; at the first column BELOW the floor a stair rises toward the house
        # (a 1-block hop is not walkable in site_walk)
        dx, dz = DIRS[d]
        facing = TOWARD[d]
        for k in range(1, self.spec['step_max'] + 1):
            n = (st[0] + dx * k, st[1] + dz * k)
            if n in self.owner or n in self.foreign:
                continue
            g = self.top_solid(*n)
            if g is None:
                continue
            if self.spec['ledge_stair'] and g == b + 1 and k > 4:
                # lowered ground ends at a 1-block ledge: stair rising away from the house onto it
                self.kset(n[0], g, n[1], stair('stone', FACE[d]))
                print('ledge stair at', n)
                return
            if g > b + 1 or (g > b and k > 4):
                return  # real slope/terrace: leave it
            if g > b:
                self.kset(n[0], b, n[1], 'stone')
                for y in range(b + 1, g + 1):
                    self.kset(n[0], y, n[1], 'air')
                continue
            if g < b:
                self.kset(n[0], b, n[1], stair('stone', facing))
                for y in range(g + 1, b):
                    self.kset(n[0], y, n[1], 'stone')
                for y in range(b + 1, b + 4):
                    self.kset(n[0], y, n[1], 'air')
                print('step at', n, 'ground', g, 'floor', b)
                return

    def windows(self, k, h):
        b = h.b
        door = {getattr(h, 'door', None), getattr(h, 'rear', None)}
        for c in h.walls:
            exp = [d for d in 'NSEW' if self.exposed(c, d)]
            if not exp:
                continue
            d = exp[0]
            diag = len(exp) > 1
            lat = [(0, 1), (0, -1)] if d in 'EW' else [(1, 0), (-1, 0)]
            ok = True
            for lx, lz in ([] if diag else lat):
                n = (c[0] + lx, c[1] + lz)
                if n not in h.walls or not self.exposed(n, d):
                    ok = False
            if not ok:
                continue
            if any(abs(c[0] - q[0]) + abs(c[1] - q[1]) < 3 for q in door if q):
                continue
            par = (c[0] + c[1]) if diag else (c[0] if d in 'NS' else c[1])
            if par % (3 if diag else 2):
                continue
            axis = 'z' if d in 'EW' else 'x'
            self.set(c[0], b + 2, c[1], pane(axis))
            self.set(c[0], b + 5, c[1], pane(axis))

    def roof(self):
        done = {}
        seen = set()
        todo = []
        for g in self.groups:
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
                    if n not in self.owner and n not in self.foreign and n not in self.shared:
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
                    done[c] = (key, t, b, c in self.owner, self.spec['roofs'][hs[0].no])
            best = max(dist, key=lambda c: (dist[c] if c in own else -1, -abs(c[0] - sum(x for x, _ in own) / len(own))))
            chim.append((best, b, hs[0].group))
        for (x, z), (key, t, b, inside, rm) in done.items():
            y = key[0]
            if inside:
                for yy in range(b + 6, y):
                    self.set(x, yy, z, WALL)
            self.set(x, y, z, f'{rm}_slab[type={t}]')
        for (x, z), b, g in chim:
            ridge = max(k[0][0] for (xx, zz), k in done.items() if abs(xx - x) <= 1 and abs(zz - z) <= 1)
            for y in range(b + 6, ridge + 3):
                self.set(x, y, z, WALL)

    def build(self):
        self.foreign = {c for c in self.idx.cells() if c not in self.owner}
        self.by_no_all_cells = set(self.owner) | self.foreign
        # columns next to neighbouring buildings: their roof overhang is already there
        self.shared = {(x + dx, z + dz) for (x, z) in self.foreign for dx, dz in N8} - self.foreign - set(self.owner)
        for h in self.houses:
            h.b = self.floor_y(h)
        # a group shares one floor level
        for g in self.groups:
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
        own1 = {(x + dx, z + dz) for (x, z) in self.owner for dx in (-1, 0, 1) for dz in (-1, 0, 1)}
        for q in list(self.p.cells):
            if (q[0], q[2]) not in own1 and 'leaves' in (self.live.block(*q) or ''):
                del self.p.cells[q]
        self.p.outside_footprint_ok = 'roof-overhang fringe slabs; evidence: footprint-hits json'
        # roof-overhang slabs of a neighbouring earlier build that spill onto our corner are theirs: leave them
        from site_kit import built_cells
        owned = built_cells(exclude={self.name}, within=self.p.cells)
        for q in [q for q, st in self.p.cells.items() if q in owned and owned[q][1] != st and q not in self.keep]:
            del self.p.cells[q]
        for h in self.houses:
            print(h.no, 'b', h.b, 'cells', len(h.cells), 'door', getattr(h, 'door', None), 'rear', getattr(h, 'rear', None))
        return self.p



def build(spec):
    return Build(spec).build()


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('spec', help='site/builds/<name>.json')
    ap.add_argument('--apply', action='store_true')
    a = ap.parse_args()
    spec = load_spec(a.spec)
    plan = build(spec)
    out = ROOT / f'verification/site/{spec["name"]}-preview.png'
    preview(plan, out, scale=4)
    print(json.dumps(plan.summary())[:600])
    apply(plan, dry=not a.apply, modifies=tuple(spec['modifies']))
