#!/usr/bin/env python3
"""Q-021: Broadlands Road nos. 48-54, north side, west of the 44/46 flats —
whole properties (Claude, 11 Oct 2026).

The queue item named 48-52; #52 (OSM 856) and #54 (882) are one hipped semi
block in the LIDAR (continuous ridge y41-42 across the party wall, hips at
both ends), so both halves are built here rather than leaving half a semi as
Geocraft.

Evidence
  Street  kartaview-1471277609 (camera MC ~7035,-5546, looking ENE): only the
          east corner of #48 at the left edge: white-rendered two-storey
          Victorian, sash windows, brick boundary pier at the pavement, raised
          front garden. 50/52/54 are behind the camera (no photo): their fronts,
          doors, bays and boundaries are a same-street `hint`.
  Aerial  q021-aerial-annot.png (z18 mosaic + OSM): 838 (48) + 901 (50) dark
          slate roofs, a narrow Victorian pair attached to 46; 901 has a rear
          outrigger on its east side. 856 (52) red-brown tiles + 882 (54) dark
          grey tiles, one hipped roof. Long gardens NNE to the diagonal rear lane
          (z -5597 at x7042 .. -5607 at x7018): small pale shed mid-garden behind
          50, large grey outbuilding by the lane behind 48/50, tree crowns behind
          50/52, pale building by the lane behind 54. 911 (#56, Geocraft) runs
          back behind 54 to z -5585.
  OSM     ways 177978838 (48) 901 (50) 856 (52) 882 (54); rotated ~22 deg.
          Squared N-S like 2-46: 48 party walls 7035..7040 (46's wall is 7041),
          50 7030..7035; semi 7018..7029 (party wall 7023), front row -5563.
  LIDAR   pristine Geocraft: ground y31 (48/50) / y32 (52/54), pavement y29-31;
          ridges y40 (48/50) and y41-42 (52/54); #48's rear part y35 = single
          storey, #50's outrigger y36-39 = two storeys.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'scripts'))
from site_kit import Plan, World, apply, built_cells, preview  # noqa: E402
from terrace import House, Terrace  # noqa: E402
import build_broadlands_rd_40_46 as b4046  # noqa: E402

NAME = 'broadlands_rd_48_54'
CFG = json.loads((ROOT / 'config/world.json').read_text())
P = World(CFG['pristine_region_path'])

X0, X1 = 7017, 7040      # columns this build owns (+ #48's wedge east of 7040, see wedge())
TX0 = 7030               # terrace part (48/50) starts here; semi part is X0..7029
TOP = 48                 # clear Geocraft carpets/bricks up to here
SNAP = ROOT / 'backups/regions/2026-10-11-233631-Q-021'   # pre-Q-021 region snap (pruned)
LATER = ('broadlands_rd_56_62',)   # later builds with modifies=(NAME,): their cells win
RENDER = 'white_concrete'

# semi 52/54: walls x 7018..7029, rows R..F, party wall MID
SX0, SX1, MID, F, R, SB = 7018, 7029, 7023, -5563, -5571, 32
FENCE_52_54 = 7024       # garden line 52|54 (one east of the party wall so #54 keeps a
                         # walkable strip past #56's long Geocraft rear)

# OSM 177978911 (#56,56a), Geocraft: never touch it (or its raster fringe)
N56 = [(7011.6, -5567.6), (7018.4, -5584.8), (7022.6, -5583.1), (7015.8, -5565.9)]


def stone_top(x, z):
    """Pristine ground ignoring Geocraft roof carpets."""
    for y in range(45, 20, -1):
        if P.block(x, y, z) in ('minecraft:stone', 'minecraft:gray_terracotta',
                                'minecraft:polished_diorite', 'minecraft:smooth_stone'):
            return y
    return 31


def pav_row(x):
    """Northmost pavement row (pristine polished_diorite)."""
    for z in range(-5565, -5535):
        for y in range(25, 33):
            if 'polished_diorite' in (P.block(x, y, z) or ''):
                return z
    raise SystemExit(f'no pavement at x={x}')


def pav_y(x):
    z = pav_row(x)
    return next(y for y in range(32, 24, -1) if 'polished_diorite' in (P.block(x, y, z) or ''))


def lane_row(x):
    """Southmost row of the rear lane (pristine gray_terracotta behind the gardens)."""
    for z in range(-5585, -5615, -1):
        if 'gray_terracotta' in P.block(x, stone_top(x, z), z):
            return z
    raise SystemExit(f'no lane at x={x}')


def near(poly, x, z, margin):
    px, pz = x + 0.5, z + 0.5
    inside, d = False, 1e9
    for (ax, az), (bx, bz) in zip(poly, poly[1:] + poly[:1]):
        if (az > pz) != (bz > pz) and px < ax + (pz - az) * (bx - ax) / (bz - az):
            inside = not inside
        vx, vz = bx - ax, bz - az
        t = max(0.0, min(1.0, ((px - ax) * vx + (pz - az) * vz) / (vx * vx + vz * vz)))
        d = min(d, ((px - ax - t * vx) ** 2 + (pz - az - t * vz) ** 2) ** 0.5)
    return inside or d <= margin


def geocraft_56(x, z):
    """#56's Geocraft mass (carpet roof) or its OSM outline: left alone."""
    if near(N56, x, z, 0.5):
        return True
    return near(N56, x, z, 1.6) and 'carpet' in (P.block(x, P.ground(x, z, top=50, bottom=20), z) or '')


def stair(mat, facing, half='bottom', shape=None):
    s = f'{mat}_stairs[facing={facing},half={half}'
    return s + (f',shape={shape}]' if shape else ']')


HOUSES = [
    House('50', 7030, 7035, -5560, 31, 'E', door_block='spruce_door'),
    House('48', 7035, 7040, -5558, 31, 'W', wall=RENDER, door_block='dark_oak_door', out_storeys=1),
]


class Build:
    def __init__(self):
        self.p = Plan(NAME)
        self.kit = built_cells(exclude=(NAME,))
        self.lawn = {}

    def set(self, x, y, z, s):
        self.p.set(x, y, z, s)

    # --- 48/50: terrace.py ----------------------------------------------------
    def terrace(self):
        self.t = Terrace(self.p, HOUSES, lambda x, z: stone_top(x, z) + 1, pav_row, lane_row, (TX0, X1))
        self.t.build()
        h48 = HOUSES[1]
        # 46 is fenced on its own west edge (broadlands_rd_40_46): no second fence on 7040
        # behind #48's main block; the yard opens onto the wedge east of it
        for z in range(lane_row(X1) + 1, h48.f - 7):
            for y in range(28, TOP):
                s = self.p.get(X1, y, z) or ''
                if 'fence' in s or (z < h48.f - 7 and s == 'minecraft:bricks' and y > h48.b):
                    self.set(X1, y, z, 'air')

    def wedge(self):
        """#48's ground east of 7040 that broadlands_rd_40_46 left (838's real rear part and
        the raster fringe of #48's Geocraft along the 46|48 line).

        40_46 kept that fringe as Geocraft while #48 was unbuilt and re-wrote it from its
        region snap (restore_orphans), so those cells sit in its record. Here every cell of
        a column 40_46's owner rule leaves to #48 is rebuilt as #48's yard / lawn, except the
        cells 40_46's own rules write (#46's west wall and eaves on that line).
        """
        own46 = set(b4046.Build().build(restore=False).cells)
        b = HOUSES[1].b
        for x in range(X1 + 1, 7047):
            for z in range(-5576, -5555):
                if b4046.owned(x, z):
                    continue
                if (x, b, z) not in own46:
                    self.lawn[(x, z)] = b
                for y in range(b - 3, TOP):
                    if (x, y, z) in own46 or self.p.get(x, y, z) is not None:
                        continue
                    if y < b:
                        s = 'dirt'
                    elif y == b:
                        s = 'grass_block' if z < -5571 else 'smooth_stone'
                    else:
                        s = 'air'
                    self.set(x, y, z, s)

    # --- 52/54: hipped semi ---------------------------------------------------
    def owned(self, x, z):
        return (X0 <= x < TX0 and lane_row(x) + 1 <= z <= pav_row(x) - 1
                and not geocraft_56(x, z))

    def semi_ground(self):
        for x in range(X0, TX0):
            for z in range(-5615, -5540):
                if not self.owned(x, z):
                    continue
                if z >= R - 3:
                    y = SB                      # front garden, house, patio
                else:
                    y = max(SB, min(stone_top(x, z), SB + 1))
                self.lawn[(x, z)] = y
                for yy in range(y - 3, y):
                    self.set(x, yy, z, 'dirt')
                self.set(x, y, z, 'grass_block')
                for yy in range(y + 1, TOP):
                    self.set(x, yy, z, 'air')

    def semi(self):
        b = SB
        walls = {(x, z) for x in range(SX0, SX1 + 1) for z in range(R, F + 1)
                 if x in (SX0, SX1, MID) or z in (R, F)}
        for x in range(SX0, SX1 + 1):
            for z in range(R, F + 1):
                self.set(x, b - 1, z, 'stone')
                if (x, z) in walls:
                    for y in range(b, b + 7):
                        self.set(x, y, z, 'bricks')
                else:
                    self.set(x, b, z, 'spruce_planks')
                    self.set(x, b + 4, z, 'spruce_planks')
                    for y in (b + 1, b + 2, b + 3, b + 5, b + 6):
                        self.set(x, y, z, 'air')
        pane_x = 'glass_pane[east=true,west=true]'
        pane_z = 'glass_pane[north=true,south=true]'
        # front: doors at the outer ends (hint), white porch hood; windows with
        # white sills; first floor over each ground-floor window
        for door_x, gf, ff, hinge in ((SX0 + 1, (7021, 7022), (7019, 7021, 7022), 'left'),
                                      (SX1 - 1, (7024, 7025, 7026), (7024, 7025, 7027, 7028), 'right')):
            self.set(door_x, b + 1, F, f'spruce_door[facing=south,half=lower,hinge={hinge},open=false]')
            self.set(door_x, b + 2, F, f'spruce_door[facing=south,half=upper,hinge={hinge},open=false]')
            self.set(door_x, b + 3, F, 'smooth_quartz')
            for x in gf:
                self.set(x, b + 1, F, 'smooth_quartz')
                self.set(x, b + 2, F, pane_x)
                self.set(x, b + 3, F, pane_x)
            for x in ff:
                self.set(x, b + 4, F, 'smooth_quartz')
                self.set(x, b + 5, F, pane_x)
                self.set(x, b + 6, F, pane_x)
            # stair along the door side, rising to the back
            for i, z in enumerate((F - 2, F - 3, F - 4, F - 5)):
                self.set(door_x, b + 1 + i, z, stair('spruce', 'north'))
            for z in (F - 2, F - 3, F - 4):
                self.set(door_x, b + 4, z, 'air')
        # rear: back doors by the party wall, windows
        for door_x, gf, ff in ((MID - 1, (7019, 7020), (7019, 7021)),
                               (MID + 2, (7027, 7028), (7025, 7027))):   # 7024 = garden fence line
            self.set(door_x, b + 1, R, 'spruce_door[facing=north,half=lower,hinge=left,open=false]')
            self.set(door_x, b + 2, R, 'spruce_door[facing=north,half=upper,hinge=left,open=false]')
            for x in gf:
                self.set(x, b + 2, R, pane_x)
                self.set(x, b + 3, R, pane_x)
            for x in ff:
                self.set(x, b + 5, R, pane_x)
                self.set(x, b + 6, R, pane_x)
        # west end (54's side): windows
        for z in (-5566, -5568):
            for y in (b + 2, b + 3, b + 5, b + 6):
                self.set(SX0, y, z, pane_z)
        self.semi_roof()

    def semi_roof(self):
        """Hipped roof in 1:2 slabs (ridge y41-42 as LIDAR), 1-block overhang on the
        west and rear; none on the east where #50 abuts, none at the front (the
        squared front row already sits ~1.5 ahead of 882's OSM front). Red-brown tile over 52,
        dark grey over 54 (aerial)."""
        b = SB
        rx0, rx1, rz0, rz1 = SX0 - 1, SX1, R - 1, F
        top = 0
        for x in range(rx0, rx1 + 1):
            for z in range(rz0, rz1 + 1):
                if x < SX0 and z == F:
                    continue        # squared west front corner: no eave beyond 882's front
                d = min(x - rx0, rx1 - x, z - rz0, rz1 - z)
                y = b + 7 + d // 2
                top = max(top, y)
                mat = 'granite' if x > MID else 'deepslate_tile'
                if SX0 <= x <= SX1 and R <= z <= F:
                    for yy in range(b + 7, y):
                        self.set(x, yy, z, 'bricks')
                self.set(x, y, z, f'{mat}_slab[type={"bottom" if d % 2 == 0 else "top"}]')
                for yy in range(y + 1, TOP):        # Geocraft carpets left over the roof
                    self.set(x, yy, z, 'air')
        # shared stack on the party wall at the ridge
        for z in (-5566, -5567, -5568):
            for y in range(b + 7, top + 3):
                self.set(MID, y, z, 'bricks')
            self.set(MID, top + 3, z, 'flower_pot')

    def semi_gardens(self):
        b = SB
        # front: brick boundary at the back of the pavement (diagonal steps closed),
        # gate gaps at the paths; low wall on the party line and the west side
        for x in range(X0, TX0):
            zb = pav_row(x) - 1
            zw = pav_row(x - 1) - 1 if x > X0 else zb
            gate = x in (SX0 + 1, SX1 - 1)
            for z in range(min(zb, zw), zb + 1):
                if gate and z == zb:
                    continue
                self.set(x, b + 1, z, 'bricks')
            if gate:
                for z in range(F + 1, zb + 1):
                    self.set(x, b, z, 'polished_andesite')
        for x in (X0, MID):
            for z in range(F + 1, pav_row(x) - 1):
                self.set(x, b + 1, z, 'bricks')
        # shrubs in the front gardens
        for x, z in ((7021, F + 2), (7026, F + 2)):
            self.set(x, b + 1, z, 'oak_leaves[persistent=true]')
        # rear patio band
        for x in range(SX0 + 1, SX1):
            for z in (R - 1, R - 2):
                if self.owned(x, z):
                    self.set(x, b, z, 'smooth_stone')
        # steps where the lawn rises a block
        for x in (MID, 7026):           # 7023 stays clear of #56's rear; 7026 of the tree
            for z in range(-5615, R - 1):
                if (x, z) in self.lawn and (x, z + 1) in self.lawn:
                    if self.lawn[(x, z)] == self.lawn[(x, z + 1)] + 1:
                        self.set(x, self.lawn[(x, z)], z, stair('stone_brick', 'north'))
        # fences: 52|54 line, west boundary (westmost owned cell per row), rear lane
        for z in range(lane_row(FENCE_52_54) + 1, R):
            self.fence(FENCE_52_54, z)
        # west boundary: on x7017 where #56's garden is open ground; along #56's long
        # Geocraft rear (rows -5566..-5585) its own wall is the boundary, so no fence
        # there (a stepped fence would close #54's strip past it)
        for z in range(R - 1, -5615, -1):
            if self.owned(X0, z):
                carpet = 'carpet' in (P.block(X0 - 1, P.ground(X0 - 1, z, top=50, bottom=20), z) or '')
                if not carpet:
                    self.fence(X0, z)
        for x in range(X0, TX0):
            a = lane_row(x) + 1
            c = lane_row(x - 1) + 1 if x > X0 else a
            for z in range(min(a, c), max(a, c) + 1):
                if self.owned(x, z):
                    self.fence(x, z)

    # --- front retaining walls + steps (all four plots) -----------------------
    def front_edges(self):
        """Gardens sit 1-2 blocks above the pavement (LIDAR): brick retaining face on
        the boundary row, stone steps up at every gate."""
        for x in range(X0, X1 + 1):
            zb = pav_row(x) - 1
            py = pav_y(x)
            b = SB if x < TX0 else next(h.b for h in HOUSES if h.pw <= x <= h.pe)
            gate = x in (SX0 + 1, SX1 - 1) or x in [h.door_col for h in HOUSES]
            for y in range(py + 1, b + (0 if gate else 1)):
                self.set(x, y, zb, 'bricks')
            if b - py >= 2:     # 2-block retaining face is the boundary (as 44/46): no wall on top
                for z in range(zb - 2, zb + 1):
                    if self.p.get(x, b + 1, z) in ('minecraft:bricks', 'minecraft:oak_leaves[persistent=true]'):
                        if z == zb or self.p.get(x, b, z) == 'minecraft:grass_block':
                            self.set(x, b + 1, z, 'air')
                            self.set(x, b + 2, z, 'air')
            if gate:
                rise = b - py
                for i in range(rise):          # i-th step up from the pavement
                    self.set(x, py + 1 + i, zb - i, stair('stone_brick', 'south'))
                    for yy in range(py + 2 + i, b + 3):
                        self.set(x, yy, zb - i, 'air')
                    for yy in range(py - 1, py + 1 + i):
                        self.set(x, yy, zb - i, 'stone')

    # --- outbuildings, trees (aerial) -----------------------------------------
    def top(self, x, z):
        if (x, z) in self.lawn:
            return self.lawn[(x, z)]
        return self.t._top(x, z)

    def fence(self, x, z):
        y = self.top(x, z)
        if self.p.get(x, y + 1, z) not in (None, 'minecraft:air'):
            return
        self.set(x, y + 1, z, 'spruce_fence')
        self.set(x, y + 2, z, 'spruce_fence')

    def shed(self, x0, x1, z0, depth, wall, roof, door_x):
        cells = [(x, z) for x in range(x0, x1 + 1) for z in range(z0, z0 + depth)]
        y = max(self.top(*c) for c in cells)
        for x, z in cells:
            for yy in range(self.top(x, z) + 1, y + 1):
                self.set(x, yy, z, 'dirt')
            for yy in range(y + 1, y + 6):
                self.set(x, yy, z, 'air')
            self.set(x, y + 1, z, wall)
            self.set(x, y + 2, z, wall)
            self.set(x, y + 3, z, f'{roof}[type=bottom]')
        self.set(door_x, y + 1, z0 + depth - 1, 'spruce_door[facing=south,half=lower,hinge=left,open=false]')
        self.set(door_x, y + 2, z0 + depth - 1, 'spruce_door[facing=south,half=upper,hinge=left,open=false]')

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

    def back(self):
        # large grey outbuilding by the lane behind 48 (aerial), pale shed mid-garden behind 50
        self.shed(7036, 7039, lane_row(7039) + 2, 4, 'stone_bricks', 'smooth_stone_slab', 7036)
        self.shed(7031, 7032, -5586, 3, 'smooth_quartz', 'birch_slab', 7031)
        # pale building by the lane behind 54
        self.shed(7019, 7022, lane_row(7022) + 2, 4, 'smooth_quartz', 'smooth_stone_slab', 7019)
        # tree crowns behind 50 and 52
        self.tree(7033, -5577, TX0 + 1, 7034)
        self.tree(7027, -5584, FENCE_52_54 + 1, TX0 - 1)

    def restore_orphans(self):
        """Cells an earlier apply of this build placed that the plan no longer has
        (first west-fence version) go back to their pre-Q-021 state from the snap.
        Once the snap is pruned they keep the state this build last recorded, so a
        re-apply neither leaves them unrecorded nor guesses at Geocraft."""
        old = ROOT / f'verification/site/{NAME}-cells.json'
        if not old.exists():
            return
        rec = json.loads(old.read_text())
        snap = World(SNAP) if SNAP.exists() else None
        for k, st in rec.items():
            x, y, z = map(int, k.split(','))
            if self.p.get(x, y, z) is None:
                self.set(x, y, z, snap.block(x, y, z) if snap else st)

    def yield_to_later(self):
        """Cells a later build took over (it declared modifies=(NAME,)) keep that build's
        recorded state, so a re-apply here neither clashes with nor undoes it."""
        for name in LATER:
            f = ROOT / f'verification/site/{name}-cells.json'
            if not f.exists():
                continue
            for k, st in json.loads(f.read_text()).items():
                q = tuple(int(v) for v in k.split(','))
                if q in self.p.cells:
                    self.p.cells[q] = st

    def build(self):
        self.terrace()
        self.wedge()
        self.semi_ground()
        self.semi()
        self.semi_gardens()
        self.front_edges()
        self.back()
        self.t.connect()
        self.restore_orphans()
        self.yield_to_later()
        return self.p


def build():
    return Build().build()


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--apply', action='store_true')
    a = ap.parse_args()
    for h in HOUSES:
        print(h.no, h.pw, h.pe, 'front', h.f, 'b', h.b, 'pav', pav_row(h.door_col), pav_y(h.door_col),
              'lane', lane_row(h.door_col))
    print('semi', SX0, SX1, 'front', F, 'pav', pav_row(7020), pav_y(7020), pav_row(7028), pav_y(7028),
          'lane', lane_row(7020), lane_row(7028))
    plan = build()
    preview(plan, ROOT / f'verification/site/{NAME}-preview.png', scale=4)
    print(json.dumps(plan.summary())[:600])
    apply(plan, dry=not a.apply, modifies=(b4046.NAME,))   # wedge(): #48 fringe 40_46 restored
