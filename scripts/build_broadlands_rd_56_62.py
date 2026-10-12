#!/usr/bin/env python3
"""Q-022: Broadlands Road nos. 56-62, north side, west of 54 — whole properties
(Claude, 11 Oct 2026).

The queue item named 56-58 (+ next west). 56/58 (OSM 911 + 890) and 60/62
(921 + 897) are two pairs, each under ONE roof whose ridge runs front-to-back
on the party wall (LIDAR peak y42 on the party line, eaves ~y37 on the outer
walls; the aerial roof colour splits on the party line = the two slopes, sunlit
east / shaded west). Both pairs are built here so no half-pair is left.

Evidence
  Street  kartaview-1471277529 (camera MC ~6980,-5569, looking ESE): the north
          side ahead-left is a row of two-storey front-gabled houses, dark
          concrete-tile roofs, white bargeboards; one gable white-rendered with
          brick side walls and white quoins, the next red brick. Which gable is
          which number is a `hint` (60/62 white render, 56/58 red brick).
          kartaview-1471277561 (camera ~7012,-5556, ESE) shows only 54 and east.
  Aerial  q022-aerial-annot.png: 890/911 dark grey (911 paler at the rear),
          921 pale / 897 dark (east/west slopes); lower rear parts; long lawns
          to the rear lane (z -5605..-5614); tree crowns behind 60/62.
  OSM     ways 177978911 (56,56a) 890 (58) 921 (60) 897 (62); rotated ~22 deg
          like 48-54 but ~17 m deep, ~4.3 m per house.
  LIDAR   ground y32 (front gardens) / y33 (house, back gardens); two-storey
          to ~-5581 (56/58) / -5584 (60/62), one storey (y37) behind that.

Model: each pair is one squared two-storey block (single party column for walls
and ridge) plus a one-storey rear wing whose party may step with the ~22 deg
OSM axis. Front gable on the street, 45 deg stair roof from outer eaves (b+5
overhang) to one straight party-wall ridge (b+10), single-storey rear with slab
roof. Do not step the party column along z within the two-storey roof — that
zig-zags every stair on the seam (I-034; scripts/roof_lint.py).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'scripts'))
from site_kit import Plan, World, apply, built_cells, preview  # noqa: E402
from build_broadlands_rd_48_54 import geocraft_56, lane_row, near, stone_top  # noqa: E402

NAME = 'broadlands_rd_56_62'
CFG = json.loads((ROOT / 'config/world.json').read_text())
P = World(CFG['pristine_region_path'])

B = 33                   # ground-floor floor Y (house, side passages, back gardens)
FG = 32                  # front-garden level
TOP = 50                 # clear Geocraft up to here
X0, X1 = 6999, 7023
RENDER = 'white_concrete'
N54 = 'broadlands_rd_48_54'    # modified: its west eave + strip cells under 56's walls
ROOF = 'deepslate_tile'

# OSM 177978874 (#66, Geocraft, west neighbour): left alone
N66 = [(6993.6, -5575.6), (6998.5, -5587.7), (7002.4, -5586.2), (6997.5, -5574.0)]


def stair(mat, facing, half='bottom'):
    return f'{mat}_stairs[facing={facing},half={half}]'


class Pair:
    """Two houses under one front-gabled roof. segs: (z_front, z_rear, party_x, storeys)."""

    def __init__(self, east, west, segs, wall, front):
        self.east, self.west, self.segs = east, west, segs
        self.wall, self.front = wall, front
        self.F = segs[0][0]
        self.R = segs[-1][1]

    def seg(self, z):
        for s in self.segs:
            if s[1] <= z <= s[0]:
                return s
        return None

    def cells(self, storeys=1):
        return {(x, z) for (zf, zr, p, n) in self.segs if n >= storeys
                for z in range(zr, zf + 1) for x in range(p - 4, p + 5)}

    def p(self, z):
        return self.seg(z)[2]

    def owner(self, x, z):
        p = self.p(z)
        return self.east if x > p else self.west if x < p else None

    def door_col(self, no):
        p = self.segs[0][2]
        return p + 3 if no == self.east else p - 3

    def roof_y(self, x, z):
        """Stair-roof heightfield: ridge b+10 on the party column, overhang b+5."""
        two = [s for s in self.segs if s[3] == 2]
        zf, zr = two[0][0] + 1, two[-1][1] - 1      # 1-row verge front and rear
        if not zr <= z <= zf:
            return None
        s = self.seg(z) or (two[0] if z > two[0][0] else two[-1])
        d = abs(x - s[2])
        return B + 10 - d if d <= 5 else None


PAIRS = [
    Pair('56', '58', [(-5568, -5581, 7015, 2), (-5582, -5585, 7015, 1)],
         'bricks', 'bricks'),
    Pair('60', '62', [(-5574, -5584, 7007, 2), (-5585, -5587, 7007, 1)],
         'bricks', RENDER),
]
HOUSE = set().union(*(pp.cells() for pp in PAIRS))
UPPER = set().union(*(pp.cells(2) for pp in PAIRS))


def pav_row(x):
    """Northmost pavement row (pristine polished_diorite)."""
    for z in range(-5575, -5540):
        for y in range(25, 33):
            if 'polished_diorite' in (P.block(x, y, z) or ''):
                return z
    raise SystemExit(f'no pavement at x={x}')


def pav_y(x):
    z = pav_row(x)
    return next(y for y in range(32, 24, -1) if 'polished_diorite' in (P.block(x, y, z) or ''))


def geocraft_66(x, z):
    if near(N66, x, z, 0.5):
        return True
    return near(N66, x, z, 1.6) and 'carpet' in (P.block(x, P.ground(x, z, top=50, bottom=20), z) or '')


class Build:
    def __init__(self):
        self.p = Plan(NAME)
        kit = built_cells(exclude=(NAME,))
        rec = ROOT / f'verification/site/{NAME}-cells.json'
        mine = json.loads(rec.read_text()) if rec.exists() else {}
        self.kitcol, kity, kitlo = set(), {}, {}
        for (x, y, z), (n, s) in kit.items():
            if n == N54 and mine.get(f'{x},{y},{z}') == s:
                continue        # 54 re-recorded our cell (its yield_to_later): still ours
            self.kitcol.add((x, z))
            kity[(x, z)] = max(kity.get((x, z), 0), y if n == N54 else 999)
            kitlo[(x, z)] = min(kitlo.get((x, z), 999), y if n == N54 else 0)
        self.own = set()
        self.air = set()        # 54's lawn-only columns: 56's eave may overhang (y >= B+5)
        self.cap = {}           # 54's eave-only columns over #56's Geocraft: ours below the eave
        self.lvl = {}
        for x in range(X0, X1 + 1):
            for z in range(lane_row(x) + 1, pav_row(x)):
                if geocraft_66(x, z):
                    continue
                if (x, z) in HOUSE and kity.get((x, z), 0) < 999:
                    self.own.add((x, z))          # 54's eave / lawn where 56's squared walls go
                elif (x, z) in self.kitcol:
                    if kity[(x, z)] <= B + 2:
                        self.air.add((x, z))
                    elif kitlo[(x, z)] >= B + 5 and geocraft_56(x, z):
                        self.own.add((x, z))
                        self.cap[(x, z)] = kitlo[(x, z)]
                elif x <= 7016 or geocraft_56(x, z):
                    self.own.add((x, z))

    def set(self, x, y, z, s):
        if y >= self.cap.get((x, z), 999):
            return
        if (x, z) in self.own or ((x, z) in self.air and y >= B + 5):
            self.p.set(x, y, z, s)

    def pair_at(self, x, z):
        return next((pp for pp in PAIRS if (x, z) in pp.cells()), None)

    def front_of(self, x, z):
        """Pair whose front garden this cell is in (south of its front row)."""
        for pp in PAIRS:
            p0 = pp.segs[0][2]
            if p0 - 4 <= x <= p0 + 4 and z > pp.F:
                return pp
        return None

    # --- ground ---------------------------------------------------------------
    def ground(self):
        for x, z in self.own:
            pp = self.front_of(x, z)
            front = pp is not None or z > -5568 or (x < 7009 and z > -5574)
            y = FG if front and (x, z) not in HOUSE else B
            self.lvl[(x, z)] = y
            for yy in range(y - 3, y):
                self.set(x, yy, z, 'dirt')
            self.set(x, y, z, 'grass_block')
            for yy in range(y + 1, TOP):
                self.set(x, yy, z, 'air')

    # --- houses ---------------------------------------------------------------
    def house(self, pp):
        b = B
        ground, upper = pp.cells(1), pp.cells(2)

        def boundary(c, s):
            x, z = c
            return any((x + dx, z + dz) not in s for dx, dz in ((1, 0), (-1, 0), (0, 1), (0, -1)))

        def wall_at(x, z, y):
            s = ground if y <= b + 3 else upper
            if (x, z) not in s:
                return False
            if x == pp.p(z) and pp.seg(z)[3] >= (1 if y <= b + 3 else 2):
                return True
            if boundary((x, z), s):
                return True
            # jog between segments: separate the two houses where the owner flips N/S
            o = pp.owner(x, z)
            for dz in (1, -1):
                if (x, z + dz) in s and pp.owner(x, z + dz) not in (o, None) and o is not None:
                    return True
            return False

        for x, z in ground:
            mat = pp.front if z == pp.F else pp.wall
            self.set(x, b - 1, z, 'stone')
            top = b + 3 if (x, z) not in upper else (pp.roof_y(x, z) or b + 6) - 1
            for y in range(b, top + 1):
                if y == b:
                    self.set(x, y, z, mat if wall_at(x, z, b + 1) else 'spruce_planks')
                elif y == b + 4 and (x, z) in upper:
                    self.set(x, y, z, mat if wall_at(x, z, y) else 'spruce_planks')
                elif wall_at(x, z, y):
                    self.set(x, y, z, mat)
                else:
                    self.set(x, y, z, 'air')
            if (x, z) not in upper:
                self.set(x, b + 4, z, f'{ROOF}_slab[type=bottom]')
                for y in range(b + 5, TOP):
                    self.set(x, y, z, 'air')
        self.roof(pp)
        self.openings(pp)

    def roof(self, pp):
        b = B
        upper = pp.cells(2)
        others = HOUSE - pp.cells()
        cells = {(x, z) for x in range(X0, X1 + 1) for z in range(pp.R - 1, pp.F + 2)
                 if pp.roof_y(x, z) is not None}
        for x, z in cells:
            if (x, z) in others:
                continue
            y = pp.roof_y(x, z)
            if (x, z) not in upper and y <= b + 5 and (x, z) in HOUSE:
                continue                    # overhang over the one-storey rear: its slab roof
            s = pp.seg(z) or (pp.segs[0] if z > pp.F else [s for s in pp.segs if s[3] == 2][-1])
            p = s[2]
            if x == p:
                self.set(x, y, z, f'{ROOF}s')
            else:
                self.set(x, y, z, stair(ROOF, 'east' if x < p else 'west'))
            for yy in range(y + 1, TOP):
                self.set(x, yy, z, 'air')
            if (x, z) in upper:
                # gable infill wherever a neighbour's roof is lower (front/rear gables, jogs)
                for dx, dz in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                    n = (x + dx, z + dz)
                    ny = pp.roof_y(*n) if n in upper else None
                    lo = b + 7 if ny is None else max(b + 7, ny)
                    for yy in range(lo, y):
                        self.set(x, yy, z, pp.front if z == pp.F else pp.wall)
            elif (x, z) not in HOUSE:
                for yy in range(B + 1, y):
                    if self.p.get(x, yy, z) not in ('minecraft:grass_block', 'minecraft:dirt'):
                        self.set(x, yy, z, 'air')
        # one stack on the party wall at the back of the front segment
        zf, zr, p, _ = pp.segs[0]
        for y in range(b + 7, b + 13):
            self.set(p, y, zr, 'bricks')
        self.set(p, b + 13, zr, 'flower_pot')

    def openings(self, pp):
        b = B
        F = pp.F
        p0 = pp.segs[0][2]
        pane_x = 'glass_pane[east=true,west=true]'
        pane_z = 'glass_pane[north=true,south=true]'
        for no, sgn in ((pp.east, 1), (pp.west, -1)):
            dc = pp.door_col(no)
            hinge = 'right' if sgn > 0 else 'left'
            self.set(dc, b + 1, F, f'spruce_door[facing=south,half=lower,hinge={hinge},open=false]')
            self.set(dc, b + 2, F, f'spruce_door[facing=south,half=upper,hinge={hinge},open=false]')
            self.set(dc, b + 3, F, 'smooth_quartz')
            self.set(dc, b + 4, F + 1, 'smooth_quartz_slab[type=bottom]')       # door hood
            self.set(dc, B, F + 1, stair('stone_brick', 'south'))              # step up from the path
            # canted bay (2 cols) beside the party wall, projecting one row
            for x in (p0 + sgn, p0 + 2 * sgn):
                for y in (b + 1, b + 2, b + 3):
                    self.set(x, y, F, 'air')
                self.set(x, b, F, 'spruce_planks')
                self.set(x, b, F + 1, 'stone')
                self.set(x, b + 1, F + 1, pp.wall)
                self.set(x, b + 2, F + 1, pane_x)
                self.set(x, b + 3, F + 1, pane_x)
                self.set(x, b + 4, F + 1, f'{ROOF}_slab[type=bottom]')
                self.set(x, b + 4, F, 'smooth_quartz')                         # bay head
                self.set(x, b + 5, F, pane_x)
                self.set(x, b + 6, F, pane_x)
            for y in range(b, b + 4):
                self.set(p0, y, F + 1, pp.wall)                                 # pier between the bays
            self.set(p0, b + 4, F + 1, f'{ROOF}_slab[type=bottom]')
            # stair along the door side, rising to the back; first-floor well above it
            for i, z in enumerate((F - 2, F - 3, F - 4, F - 5)):
                self.set(dc, b + 1 + i, z, stair('spruce', 'north'))
            for z in (F - 2, F - 3, F - 4):
                self.set(dc, b + 4, z, 'air')
            # attic/gable window
            self.set(p0 + sgn, b + 8, F, pane_x)
        # outer side walls: windows on both floors in the middle segment
        for zf, zr, p, n in pp.segs:
            zmid = (zf + zr) // 2
            for x, ys in ((p - 4, (b + 2, b + 3) + ((b + 5,) if n == 2 else ())),
                          (p + 4, (b + 2, b + 3) + ((b + 5,) if n == 2 else ()))):
                if (x, zmid) in HOUSE - pp.cells() or self.pair_at(x + (1 if x > p else -1), zmid):
                    continue
                for y in ys:
                    self.set(x, y, zmid, pane_z)
        # rear: back door per house in the one-storey part, windows above in the
        # two-storey rear wall
        zf, zr, p, _ = pp.segs[-1]
        for x in (p + 2, p - 2):
            self.set(x, b + 1, zr, 'spruce_door[facing=north,half=lower,hinge=left,open=false]')
            self.set(x, b + 2, zr, 'spruce_door[facing=north,half=upper,hinge=left,open=false]')
        for x in (p + 3, p - 3):
            self.set(x, b + 2, zr, pane_x)
        z2 = [s for s in pp.segs if s[3] == 2][-1]
        for x in (z2[2] + 2, z2[2] - 2, z2[2] + 3, z2[2] - 3):
            if (x, z2[1] - 1) not in pp.cells(2):
                self.set(x, b + 5, z2[1], pane_x)

    # --- gardens ----------------------------------------------------------------
    def top(self, x, z):
        return self.lvl.get((x, z), B)

    def fence(self, x, z):
        if (x, z) not in self.own or (x, z) in HOUSE:
            return
        y = self.top(x, z)
        if self.p.get(x, y + 1, z) not in (None, 'minecraft:air'):
            return
        self.set(x, y + 1, z, 'spruce_fence')
        self.set(x, y + 2, z, 'spruce_fence')

    def gardens(self):
        doors = {pp.door_col(no): pp for pp in PAIRS for no in (pp.east, pp.west)}
        # front: brick retaining face + low wall at the back of the pavement, gates
        for x in range(X0, X1 + 1):
            zb = pav_row(x) - 1
            if (x, zb) not in self.own:
                continue
            py = pav_y(x)
            zw = pav_row(x - 1) - 1 if (x - 1, pav_row(x - 1) - 1) in self.own else zb
            gate = x in doors
            for z in range(min(zb, zw), zb + 1):
                for y in range(py + 1, FG + 1):
                    self.set(x, y, z, 'bricks')
                if not gate:
                    self.set(x, FG + 1, z, 'bricks')
            if gate:
                self.set(x, py + 1, zb, stair('stone_brick', 'south'))
                self.set(x, FG + 1, zb, 'air')
                for z in range(doors[x].F + 2, zb):
                    self.set(x, FG, z, 'polished_andesite')
        # low walls between front gardens (party lines + west side), shrubs
        for pp in PAIRS:
            p0 = pp.segs[0][2]
            for x in (p0, p0 - 4):
                for z in range(pp.F + 2, pav_row(x) - 1):
                    if (x, z) in self.own and (x, z) not in HOUSE:
                        self.set(x, FG + 1, z, 'bricks')
            for x in (p0 + 2, p0 - 2):
                z = pp.F + 3
                if z < pav_row(x) - 1:
                    self.set(x, FG + 1, z, 'oak_leaves[persistent=true]')
        # step up from front garden to the side passage beside 62 (west) and 56 (east)
        for x in range(X0, X1 + 1):
            for z in range(-5590, -5560):
                if (x, z) in self.own and (x, z - 1) in self.own and (x, z) not in HOUSE \
                        and (x, z - 1) not in HOUSE and self.top(x, z) == FG and self.top(x, z - 1) == B:
                    if self.p.get(x, FG + 1, z) in (None, 'minecraft:air'):
                        self.set(x, B, z - 1, stair('stone_brick', 'south'))
                        self.set(x, B, z, 'grass_block')
                        self.lvl[(x, z - 1)] = B
        # back: rear patio strip, plot fences (squared, as 14-54: I-016), lane fence
        for pp in PAIRS:
            zf, zr, p, _ = pp.segs[-1]
            for x in range(p - 4, p + 5):
                if (x, zr - 1) in self.own and (x, zr - 1) not in HOUSE:
                    self.set(x, B, zr - 1, 'smooth_stone')
        for fx, zs in ((7013, -5588), (7009, -5588), (7002, -5588)):
            for z in range(lane_row(fx) + 1, zs + 1):
                self.fence(fx, z)
        for x in range(X0, X1 + 1):
            a = lane_row(x) + 1
            c = lane_row(x - 1) + 1 if x > X0 else a
            for z in range(min(a, c), max(a, c) + 1):
                self.fence(x, z)
        # west boundary beside #66's garden (its house wall is the boundary beside it)
        for z in range(-5589, -5616, -1):
            xs = [x for x in range(X0, 7003) if (x, z) in self.own]
            if xs and (min(xs) - 1, z) not in HOUSE:
                self.fence(min(xs), z)
        # tree crowns behind 60/62 (aerial)
        self.tree(7006, -5601, 7003, 7008)
        self.tree(7011, -5606, 7010, 7012)

    def tree(self, x, z, lo, hi):
        y = self.top(x, z)
        for i in range(1, 6):
            self.set(x, y + i, z, 'oak_log')
        for dx in range(-2, 3):
            for dz in range(-2, 3):
                for dy in range(4, 8):
                    if abs(dx) + abs(dz) + max(0, dy - 6) * 2 <= 3 and not (dx == dz == 0 and dy < 6):
                        xx, zz = x + dx, z + dz
                        if lo <= xx <= hi and self.p.get(xx, y + dy, zz) in (None, 'minecraft:air'):
                            self.set(xx, y + dy, zz, 'oak_leaves[persistent=true]')

    def build(self):
        self.ground()
        for pp in PAIRS:
            self.house(pp)
        self.gardens()
        return self.p


def build():
    return Build().build()


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--apply', action='store_true')
    a = ap.parse_args()
    for pp in PAIRS:
        print(pp.east, pp.west, 'F', pp.F, 'R', pp.R, 'segs', pp.segs,
              'pav', [(x, pav_row(x), pav_y(x)) for x in (pp.door_col(pp.east), pp.door_col(pp.west))],
              'lane', lane_row(pp.segs[-1][2]))
    plan = build()
    preview(plan, ROOT / f'verification/site/{NAME}-preview.png', scale=4)
    print(json.dumps(plan.summary())[:600])
    apply(plan, dry=not a.apply, modifies=(N54,))
