#!/usr/bin/env python3
"""I-057 cell 49,-42: the unrefined Geocraft house lumps (Church Lane, Hilldown Road, Welbeck Avenue) - HOUSES ONLY from OSM footprints.

Same process as build_welbeck_ave_50_lumps.py (+ fix_welbeck_ave_50_lumps.py folded in, so nothing is re-fixed afterwards):
floors from the natural lawn ring by a downward surface scan (never from y41); fringe lump remnants (bricks/carpet) retexed to
lawn; door stoop + steps are stairs where the ground in front is 2+ lower. Per house: levels from OSM building:levels (2 default),
flat roof for apartments / garages, pitched deepslate-tile slab roof otherwise (hint, no aerial of roof pitch).
Fronts: toward the nearest OSM street (Church Lane houses E; no.53-59 etc), Hilldown Road N/S/E by the street foot point.
Order: mask_undo of the 49,-42 trees/decor masks that overlap the footprints FIRST, then this build, then the trees re-run.
Ways: Church Lane w173805559 563 564 568 573 575 577 579 (+ garages w280523743 lump); Hilldown Rd w173807207 219 280523081
and w173807199 208 216 218 220 196 (lump); Oakdene Court w173805553 (Welbeck Avenue, 4 levels, flat).

  python3 scripts/build_cell_49_m42_lumps.py            # dry run + preview + door reachability (dry-run overlay)
  SITE_OWNER=... python3 scripts/build_cell_49_m42_lumps.py --apply
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

MODIFIES = ('highfield_49_m42_ground', 'highfield_49_m42_trees', 'highfield_49_m42_decor',
            'highfield_48_m42_ground', 'highfield_48_m42_trees', 'highfield_48_m42_decor',
            'highfield_50_m42_ground', 'highfield_49_m41_ground')  # layers the footprints replace; NOT a cell marker
NAME = 'cell_49_m42_lumps'
GROUND = ('minecraft:stone', 'minecraft:gray_terracotta', 'minecraft:polished_granite', 'minecraft:polished_diorite', 'minecraft:light_gray_concrete', 'minecraft:grass_block', 'minecraft:dirt', 'minecraft:coarse_dirt', 'minecraft:gravel')
WALL, FLOOR, ROOF = 'bricks', 'spruce_planks', 'deepslate_tile'
TOP = 30
LOW = 30       # lowest y scanned: the Hilldown Road lawn here is at y39-40, so a scan stopping at 40 (or 41) finds no ground

# way id -> (front, levels, flat roof)
SPEC = {
    # Church Lane (front E onto the lane; 563 on the corner faces N)
    '173805559': ('E', 2, False), '173805563': ('N', 2, False), '173805564': ('E', 2, False), '173805568': ('E', 2, False),
    '173805573': ('E', 2, False), '173805575': ('E', 2, False), '173805577': ('E', 2, False), '173805579': ('E', 2, False),
    # Hilldown Road, 3 houses
    '173807207': ('S', 2, False), '173807219': ('E', 2, False), '280523081': ('S', 2, False),
    # Hilldown Road, 5 houses + lump (no.12, w173807196)
    '173807199': ('N', 2, False), '173807208': ('N', 2, False), '173807216': ('N', 2, False), '173807218': ('N', 2, False),
    '173807220': ('N', 2, False), '173807196': ('N', 2, False),
    # Welbeck Avenue: Oakdene Court (apartments, 4 levels, roof:levels=0) fronts W onto Church Lane's carriageway
    '173805553': ('W', 4, True),
    # Church Lane lump: garages block (single storey, flat)
    '280523743': ('W', 1, True),
}
GROUPS = [dict(nos=[w for w, v in SPEC.items() if v[0] == f], mode='each', front=f) for f in 'NSEW']
GROUPS = [g for g in GROUPS if g['nos']]
WAYS = {w: w for w in SPEC}
ROOFS = {w: 'deepslate_tile' for w in SPEC}
DIRS = {'N': (0, -1), 'S': (0, 1), 'W': (-1, 0), 'E': (1, 0)}
OPP = {'N': 'S', 'S': 'N', 'W': 'E', 'E': 'W'}
N8 = [(dx, dz) for dx in (-1, 0, 1) for dz in (-1, 0, 1) if dx or dz]


def pane(axis):
    return 'glass_pane[east=true,west=true]' if axis == 'x' else 'glass_pane[north=true,south=true]'


def stair(mat, facing, half='bottom'):
    return f'{mat}_stairs[facing={facing},half={half}]'


LUMP_SURFACE = ('minecraft:bricks', 'minecraft:light_gray_carpet')   # Geocraft building remnants left in a house's fringe


FACE = {(0, -1): 'north', (0, 1): 'south', (-1, 0): 'west', (1, 0): 'east'}


def door_steps(set_, surf, st, f, blocked, b):
    """Walkable way from a stoop (top block at y=b, column ``st``) down to the real ground in front of it.

    The floor is the median of the lawn ring, so on a slope the ground in front of the stoop can be 2+ below (or 1 above: a stair up)
    it (site_walk steps down 1 at a time). Steps and the stoop are stairs so the way UP to the door is walkable too (site_walk). Follow the ground out along ``f`` for 6 columns and wherever it drops more
    than one below the walking level lay a one-wide smooth_stone step (stone beneath); clear the head room. Returns the number of steps.
    """
    st_ = f"stone_stairs[facing={FACE[(-f[0], -f[1])]},half=bottom]"
    prev, L, n = st, b, 0
    for k in range(1, 7):
        c = (st[0] + f[0] * k, st[1] + f[1] * k)
        if c in blocked:
            break
        g = surf(*c)
        if g == L + 1:                # ground rises one in front of the stoop (street above the lawn): a stair, walkable UP in site_walk
            set_(c[0], g, c[1], f"stone_stairs[facing={FACE[f]},half=bottom]")
            for y in range(g + 1, g + 5):
                set_(c[0], y, c[1], 'air')
            n += 1
            prev, L = c, g
            continue
        if g > L:
            break
        if g >= L - 1:
            Lk = g                    # walkable as it is
        else:
            Lk = L - 1                # drop of 2+: lay a step
            for y in range(g + 1, Lk):
                set_(c[0], y, c[1], 'stone')
            set_(c[0], Lk, c[1], st_)
            for y in range(Lk + 1, Lk + 5):
                set_(c[0], y, c[1], 'air')
            n += 1
        if Lk == L - 1:               # going back UP the one-block rise must land on a stair (the previous column)
            set_(prev[0], L, prev[1], st_)
            n += 1 if g >= L - 1 else 0
        prev, L = c, Lk
    return n


class House:
    def __init__(self, no, cells, group):
        self.no, self.cells, self.group = no, cells, group
        self.front = group['front']
        _f, self.levels, self.flat = SPEC[no]
        self.H = 3 * self.levels          # wall height: storeys of 3 (2 storeys = 6 as in the other Welbeck builds)


class Build:
    def __init__(self):
        self.p = Plan(NAME)
        self.live = World()
        idx = osm_footprints.OSMIndex()
        by_no = {}
        for (x, z), i in idx.cells().items():
            n = WAYS.get(str(idx.buildings[i][1].get('osm_way_id')))
            if n:
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

    SOFT = ('leaves', '_log', 'short_grass', 'tall_grass', 'fern', 'flower', 'tulip', 'poppy', 'dandelion', 'bush', 'vine', 'azalea', 'fence', 'hedge')
    LAWN = ('minecraft:grass_block', 'minecraft:coarse_dirt', 'minecraft:dirt', 'minecraft:podzol')

    def surf(self, x, z, top=110):
        """(y, block) of the top solid block of a column, skipping air, foliage, trunks and fences (scan from above)."""
        for y in range(top, LOW, -1):
            b = self.live.block(x, y, z) or 'minecraft:air'
            n = b.split('[')[0].replace('minecraft:', '')
            if n in ('air', 'cave_air', 'void_air', 'light') or any(t in n for t in self.SOFT):
                continue
            return y, b.split('[')[0]
        return LOW + 1, ''

    def top_all(self, x, z):
        for y in range(110, LOW, -1):
            b = self.live.block(x, y, z) or 'minecraft:air'
            if b not in ('minecraft:air', 'minecraft:cave_air') and not b.endswith('_wool'):   # cell marker (I-045) is wool: never touched
                return y
        return LOW + 1

    def floor_y(self, h):
        """Natural ground round the house: median surface of the lawn ring (7 blocks) outside every OSM building,
        skipping lump / roof / paving columns; falls back to all ground-class columns."""
        lawn, other = [], []
        for (x, z) in h.cells:
            for dx in range(-3, 4):
                for dz in range(-3, 4):
                    c = (x + dx, z + dz)
                    if c in self.owner or c in self.by_no_all_cells:
                        continue
                    y, b = self.surf(*c)
                    if b in self.LAWN:
                        lawn.append(y)
                    elif b in GROUND:
                        other.append(y)
        ys = lawn if len(lawn) >= 12 else lawn + other
        return int(statistics.median(ys))

    def clear(self):
        cols = set()
        for (x, z) in self.owner:
            cols.update((x + dx, z + dz) for dx in (-2, -1, 0, 1, 2) for dz in (-2, -1, 0, 1, 2))
        self.cols = cols
        bcol = {}
        for h in self.houses:
            for (x, z) in h.cells:
                for dx in range(-2, 3):
                    for dz in range(-2, 3):
                        c = (x + dx, z + dz)
                        bcol[c] = min(bcol.get(c, 99), h.b)
        for x, z in cols:
            if (x, z) in self.foreign or (x, z) in self.earlier:
                continue
            b = bcol[(x, z)]
            gy, gb = self.surf(x, z)
            # footprint columns: everything above the new floor goes; fringe on real ground: only what stands above it
            lo = b if ((x, z) in self.owner or gb not in self.LAWN + GROUND or gb == 'minecraft:stone' and gy > b + 1) else min(gy, b)
            for y in range(lo + 1, max(self.top_all(x, z), b + TOP) + 1):
                if self.live.block(x, y, z) not in ('minecraft:air', None):
                    self.set(x, y, z, 'air')
            if (x, z) not in self.owner and gb in LUMP_SURFACE:      # remnant of the lump in the fringe: back to lawn
                self.set(x, min(gy, b), z, 'grass_block')

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
            for y in range(b, b + h.H):
                self.set(x, y, z, WALL)
        for x, z in h.inner:
            self.set(x, b, z, FLOOR)
            for y in range(b + 1, b + h.H):
                self.set(x, y, z, 'air')
            for k in range(1, h.levels):
                self.set(x, b + 3 * k, z, FLOOR)

    def doors(self, k, h, taken):
        b = h.b
        f = h.front
        # diagonal strips: fall back to the nearest side that has a wall cell with an interior cell behind it
        for alt in (f, 'E', 'W', 'N'):
            if [c for c in h.walls if self.exposed(c, alt) and (c[0] - DIRS[alt][0], c[1] - DIRS[alt][1]) in h.inner]:
                f = alt
                break
        h.frontused = f
        h.passage = None
        if not [c for c in h.walls if self.exposed(c, f) and (c[0] - DIRS[f][0], c[1] - DIRS[f][1]) in h.inner]:
            # thin diagonal edge: door through a double-thick stretch; carve the second wall cell as a hall
            for alt in (f, 'E', 'W', 'N'):
                dx, dz = DIRS[alt]
                ok = [c for c in h.walls if self.exposed(c, alt) and (c[0] - dx, c[1] - dz) in h.walls and (c[0] - 2 * dx, c[1] - 2 * dz) in h.inner]
                if ok:
                    f = alt
                    h.frontused = f
                    h.passage = [(c[0] - dx, c[1] - dz) for c in ok]
                    h.inner = h.inner | set(h.passage)
                    h.walls = h.walls - set(h.passage)
                    for (x, z) in h.passage:
                        self.set(x, b, z, FLOOR)
                        for y in range(b + 1, b + h.H):
                            self.set(x, y, z, 'air')
                        for k in range(1, h.levels):
                            self.set(x, b + 3 * k, z, FLOOR)
                    break
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
        elif f == 'E':
            front_edge = max(c[0] for c in cand)
            cand = [c for c in cand if c[0] >= front_edge - 1]
            mid = sum(c[1] for c in cand) / len(cand)
            c0 = min(cand, key=lambda c: abs(c[1] - mid))
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
        door_steps(self.set, lambda x, z: self.surf(x, z, b + 2)[0], st, (fx, fz), self.owner.keys() | self.foreign, b)
        # stair inward from the door, ascending away from the front
        ix, iz = -fx, -fz
        cells = [(c0[0] + ix * d, c0[1] + iz * d) for d in (2, 3, 4)]
        if h.levels > 1 and all(c in h.inner for c in cells):
            for i, c in enumerate(cells):
                self.set(c[0], b + 1 + i, c[1], stair('spruce', {'S': 'north', 'N': 'south', 'W': 'east', 'E': 'west'}[f]))
            for c in cells[:2]:
                self.set(c[0], b + 3, c[1], 'air')
        # rear door
        cand = [c for c in h.walls if self.exposed(c, r) and (c[0] - DIRS[r][0], c[1] - DIRS[r][1]) in h.inner
                and (c[0] + DIRS[r][0], c[1] + DIRS[r][1]) not in self.foreign and (c[0] + DIRS[r][0], c[1] + DIRS[r][1]) not in self.earlier]   # a rear door must open onto open ground, not a neighbour's wall (219 -> w590171653)
        if cand:
            if r in 'NS':
                e = min(c[1] for c in cand) if r == 'N' else max(c[1] for c in cand)
                cc = [c for c in cand if (c[1] <= e + 2 if r == 'N' else c[1] >= e - 2)]
                m = sum(c[0] for c in cc) / len(cc)
                c1 = min(cc, key=lambda c: abs(c[0] - m))
            elif r == 'W':
                e = min(c[0] for c in cand)
                cc = [c for c in cand if c[0] <= e + 1]
                m = sum(c[1] for c in cc) / len(cc)
                c1 = min(cc, key=lambda c: abs(c[1] - m))
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
            door_steps(self.set, lambda x, z: self.surf(x, z, b + 2)[0], (sx, sz), DIRS[r], self.owner.keys() | self.foreign, b)
        else:
            h.rear = None

    def windows(self, k, h):
        b = h.b
        if h.levels == 1:          # garages: no windows
            return
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
            for k in range(h.levels):
                self.set(c[0], b + 2 + 3 * k, c[1], pane(axis))

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
                    if n not in self.owner and n not in self.foreign and n not in self.earlier:
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
            b, H, flat = hs[0].b, hs[0].H, hs[0].flat
            for c, d in dist.items():
                d = 0 if flat else d          # flat roof (apartments, garages): one slab course over footprint + 1 overhang
                y = b + H + d // 2
                t = 'bottom' if d % 2 == 0 else 'top'
                key = (y, 1 if t == 'top' else 0)
                cur = done.get(c)
                if cur is None or key > cur[0]:
                    done[c] = (key, t, b, c in self.owner, ROOFS[hs[0].no], H)
            if not flat:
                best = max(dist, key=lambda c: (dist[c] if c in own else -1, -abs(c[0] - sum(x for x, _ in own) / len(own))))
                chim.append((best, b, H))
        for (x, z), (key, t, b, inside, rm, H) in done.items():
            y = key[0]
            if inside:
                for yy in range(b + H, y):
                    self.set(x, yy, z, WALL)
            self.set(x, y, z, f'{rm}_slab[type={t}]')
        for (x, z), b, H in chim:
            ridge = max(k[0][0] for (xx, zz), k in done.items() if abs(xx - x) <= 1 and abs(zz - z) <= 1)
            for y in range(b + H, ridge + 3):
                self.set(x, y, z, WALL)

    def build(self):
        self.foreign = {c for c in self.idx.cells() if c not in self.owner}
        self.by_no_all_cells = set(self.owner) | self.foreign
        # columns already roofed by an earlier build (Welbeck 7-13 / University Rd): never clear or roof twice
        self.earlier = set()
        for (x, z) in {(x + dx, z + dz) for (x, z) in self.owner for dx in range(-3, 4) for dz in range(-3, 4)}:
            if (x, z) in self.owner or (x, z) in self.foreign:
                continue
            for y in range(LOW, 75):
                if 'slab' in (self.live.block(x, y, z) or '') and 'nether_brick' in self.live.block(x, y, z) or 'deepslate_tile_slab' in (self.live.block(x, y, z) or ''):
                    self.earlier.add((x, z))
                    break
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
        from site_kit import built_cells
        owned = built_cells(exclude=set(MODIFIES) | {NAME})      # roof-overhang fringe that meets a neighbour's earlier roof: theirs stays
        for q in [q for q, st in self.p.cells.items() if q in owned and owned[q][1] != st]:
            del self.p.cells[q]
        for h in self.houses:
            print(h.no, 'front', h.frontused, 'b', h.b, 'cells', len(h.cells), 'door', getattr(h, 'door', None), 'rear', getattr(h, 'rear', None))
        return self.p


class Overlay:
    """Live world with a dry-run plan laid over it (door reachability before apply)."""

    def __init__(self, cells=None):
        self.w, self.cells = World(), cells or {}

    def block(self, x, y, z):
        return self.cells.get((x, y, z)) or self.w.block(x, y, z)


def door_report(cells=None, box=(6262, -5380, 6402, -5240)):
    """Door reachability as site_walk components: flood-fill (site_walk step rules) from the standing cell just OUTSIDE every
    lower door half in ``box`` (live world, ``cells`` plan overlaid); a door is reachable when its component is the main one
    (the one holding most doors' outside cells and the road). A fixed goal point 10 blocks out gave false alarms on slopes and
    under trees, so there is no goal point.

    @returns: {(x, y, z): bool}"""
    from collections import deque
    import site_walk
    w = Overlay(cells)
    F = {'north': (0, -1), 'south': (0, 1), 'west': (-1, 0), 'east': (1, 0)}
    x0, z0, x1, z1 = box

    def ok(x, y, z):
        return (x0 <= x <= x1 and z0 <= z <= z1 and not site_walk.solid(w.block(x, y, z))
                and not site_walk.solid(w.block(x, y + 1, z)) and site_walk.solid(w.block(x, y - 1, z)))

    def flood(start, comp, cid):
        comp[start] = cid
        q = deque([start])
        while q:
            x, y, z = q.popleft()
            for dx, dz in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                for dy in (0, 1, -1):
                    n = (x + dx, y + dy, z + dz)
                    if n in comp or not ok(*n):
                        continue
                    below = w.block(n[0], n[1] - 1, n[2]) or ''
                    if dy == 1 and 'stairs' not in below and 'slab' not in below:
                        continue
                    if dy == 1 and site_walk.solid(w.block(x, y + 2, z)):
                        continue
                    comp[n] = cid
                    q.append(n)
                    break

    doors = set((cells or {}).keys()) if False else set()
    for (x, y, z), st in (cells or {}).items():
        if '_door[' in st and 'half=lower' in st:
            doors.add((x, y, z))
    for z in range(z0, z1 + 1):
        for x in range(x0, x1 + 1):
            for y in range(36, 72):
                st = w.block(x, y, z) or ''
                if '_door[' in st and 'half=lower' in st:
                    doors.add((x, y, z))
    comp, out, cid = {}, {}, 0
    starts = {}
    for (x, y, z) in sorted(doors):
        st = w.block(x, y, z)
        fx, fz = F[st.split('facing=')[1].split(',')[0].split(']')[0]]
        cand = [(x + fx, y + dy, z + fz) for dy in (0, -1, 1)]
        starts[(x, y, z)] = next((c for c in cand if ok(*c)), None)
    for d, c in starts.items():
        if c is not None and c not in comp:
            cid += 1
            flood(c, comp, cid)
    count = {}
    for d, c in starts.items():
        if c is not None:
            count[comp[c]] = count.get(comp[c], 0) + 1
    size = {}
    for c, i in comp.items():
        size[i] = size.get(i, 0) + 1
    main = max(size, key=size.get) if size else None
    door_report.sizes = {d: (size[comp[c]] if c is not None else 0) for d, c in starts.items()}
    door_report.main = main
    for d, c in starts.items():     # not sealed into a pocket: a component of 1000+ standing cells (stoop, garden, street)
        out[d] = c is not None and size[comp[c]] >= 1000
    return out


def build():
    return Build().build()


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--apply', action='store_true')
    ap.add_argument('--doors-live', action='store_true', help='report door reachability of the live world only and exit')
    a = ap.parse_args()
    if a.doors_live:
        r = door_report()
        bad = sorted(k for k, v in r.items() if not v)
        print('doors', len(r), 'unreachable', len(bad), bad)
        raise SystemExit(0)
    plan = build()
    r = door_report(plan.cells)
    bad = sorted(k for k, v in r.items() if not v)
    print('door reachability (dry-run overlay): doors', len(r), 'unreachable', len(bad), bad)
    out = ROOT / f'verification/site/{NAME}-preview.png'
    preview(plan, out, scale=4)
    print(json.dumps(plan.summary())[:600])
    apply(plan, dry=not a.apply, modifies=MODIFIES)
