#!/usr/bin/env python3
"""Q-020: Broadlands Road nos. 40-46, north side — two post-war (1950s-60s)
brick blocks of flats, whole properties (Claude, 11 Oct 2026).

Not the Victorian terrace generator: the street photo shows plain two-storey
blocks with hipped roofs, no bays.

Evidence
  Street  kartaview-1471277609 (camera MC ~7035,-5546, looking ENE along the
          north side): nearest left is a white rendered Victorian house (#48),
          then a two-storey red-brick block (bins numbered 44 in front): hipped
          brown tile roof, chimney on the front slope near the ridge, white
          3-light casements, a beige render panel between the ground- and
          first-floor windows of the end bays, plain brick piers; front gardens
          raised ~1.5 m above the pavement behind brick retaining walls, brick
          steps with a handrail at the west end. A second block of the same type
          (#40/42) follows behind the ivy/hedges, chimney on its ridge; a gap
          between the blocks; then the bay terrace (#36..).
  Aerial  q020-aerial-annot.png (z18 mosaic + OSM): 871+836 one roof (40/42),
          878+920 one roof (44/46) with a lower rear part; long lawns to the
          rear lane, pale shed by the lane behind 40/42, grey outbuilding roofs
          behind 44/46, tree crowns mid-garden.
  OSM     ways 177978871 (40) 836 (42) 878 (44) 920 (46); 40/42 block 12.8 x
          11.4 m, 44/46 block 9.7 x 15.6 m (incl. rear part), rotated ~22 deg.
          Squared here N-S like the 26-36 terrace: block centres within ~0.5 of
          the OSM centres, corners off by up to ~2.
  LIDAR   pristine Geocraft: ridge carpets y40 on both blocks, low rear part of
          44/46 at y35 (single storey), house ground y30/31, pavement y29,
          gardens rise to y31-32 at the rear lane.
  Hints   entrances are not in the photo (front shows windows only): common
          doors are put at the rear/side off the gap path between the blocks.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'scripts'))
from site_kit import Plan, World, apply, preview  # noqa: E402

NAME = 'broadlands_rd_40_46'
CFG = json.loads((ROOT / 'config/world.json').read_text())
P = World(CFG['pristine_region_path'])

SNAP = ROOT / 'backups/regions/2026-10-11-232002-Q-020'   # pre-Q-020 region snap
X0, X1 = 7041, 7063            # columns this build owns (7064 = #36's end wall / fence)
PATH_X = 7050                  # gap path between the two blocks (photo + aerial)
TOP = 48                       # clear Geocraft carpets/bricks up to here
WALL, RENDER, WHITE = 'bricks', 'white_terracotta', 'smooth_quartz'
FLOOR = 'oak_planks'
ROOF = 'brick'                 # brown-red concrete tile (photo); slabs 1:2


class Block:
    """Two-storey hipped block: walls x0..x1, rows r..f (f = front, south)."""

    def __init__(self, nos, x0, x1, f, r, b, mid, ov_w, ov_e, chimney):
        self.nos, self.x0, self.x1, self.f, self.r, self.b = nos, x0, x1, f, r, b
        self.mid, self.ov_w, self.ov_e, self.chimney = mid, ov_w, ov_e, chimney
        self.trim = set()        # eave cells left off (squared corner beyond the OSM front)

    def walls(self):
        return {(x, z) for x in range(self.x0, self.x1 + 1) for z in range(self.r, self.f + 1)
                if x in (self.x0, self.x1, self.mid) or z in (self.r, self.f)}

    def interior(self):
        return [(x, z) for x in range(self.x0 + 1, self.x1) for z in range(self.r + 1, self.f)
                if x != self.mid]

    def halves(self):
        """(inner columns, stair column) per flat pair; the stair sits by the middle wall."""
        w = list(range(self.x0 + 1, self.mid))
        e = list(range(self.mid + 1, self.x1))
        return [(w, w[-1]), (e, e[0])]


A = Block(('42', '40'), 7051, 7063, -5551, -5561, 30, 7057, 1, 0, [(7057, -5555), (7057, -5556)])
B = Block(('46', '44'), 7041, 7049, -5555, -5564, 31, 7045, 0, 0, [(7044, -5557), (7044, -5558)])
A.trim = {(7050, -5550), (7051, -5550)}
WING = (7043, 7049, -5569)     # B's single-storey rear part: walls x 7043..7049, rows -5565..-5569


def pav_row(x):
    """Northmost pavement row (pristine polished_diorite)."""
    for z in range(-5565, -5535):
        for y in range(25, 32):
            if 'polished_diorite' in (P.block(x, y, z) or ''):
                return z
    raise SystemExit(f'no pavement at x={x}')


def lane_row(x):
    """Southmost row of the rear lane (pristine gray_terracotta behind the gardens)."""
    for z in range(-5575, -5610, -1):
        y = P.ground(x, z, top=45, bottom=20)
        if 'gray_terracotta' in P.block(x, y, z):
            return z
    raise SystemExit(f'no lane at x={x}')


def stone_top(x, z):
    for y in range(45, 20, -1):
        if P.block(x, y, z) in ('minecraft:stone', 'minecraft:gray_terracotta', 'minecraft:polished_diorite'):
            return y
    return 31


# OSM 177978838 (#48), still Geocraft: never touch it (or its 1-block raster fringe)
N48 = [(7034.4, -5559.2), (7040.4, -5573.5), (7045.1, -5571.6), (7039.1, -5557.2)]


def near_48(x, z, margin=0.8):
    px, pz = x + 0.5, z + 0.5
    inside, d = False, 1e9
    for (ax, az), (bx, bz) in zip(N48, N48[1:] + N48[:1]):
        if (az > pz) != (bz > pz) and px < ax + (pz - az) * (bx - ax) / (bz - az):
            inside = not inside
        vx, vz = bx - ax, bz - az
        t = max(0.0, min(1.0, ((px - ax) * vx + (pz - az) * vz) / (vx * vx + vz * vz)))
        d = min(d, ((px - ax - t * vx) ** 2 + (pz - az - t * vz) ** 2) ** 0.5)
    return inside or d <= margin


def owned(x, z):
    if not (X0 <= x <= X1 and lane_row(x) + 1 <= z <= pav_row(x) - 1):
        return False
    return not (z <= -5556 and near_48(x, z))


def block_of(x):
    return B if x < PATH_X else A


def pane(axis):
    return 'glass_pane[east=true,west=true]' if axis == 'x' else 'glass_pane[north=true,south=true]'


def stair(mat, facing, half='bottom'):
    return f'{mat}_stairs[facing={facing},half={half}]'


class Build:
    def __init__(self):
        self.p = Plan(NAME)
        self.cols = [(x, z) for x in range(X0, X1 + 1) for z in range(-5600, -5540) if owned(x, z)]
        self.lawn = {}

    def set(self, x, y, z, s):
        self.p.set(x, y, z, s)

    # --- ground ------------------------------------------------------------
    def surface(self, x, z):
        if x == PATH_X:
            if z >= pav_row(x) - 1:
                return 30
            return 30 if z >= -5563 else 31
        blk = block_of(x)
        if z > blk.r - 1 or (blk is B and z >= -5577):   # 44/46: level lawn round #48's rear
            return blk.b                                 # front garden, house, yard/patio
        if blk is A and z >= -5563:
            return blk.b
        return max(blk.b, min(stone_top(x, z), blk.b + 1))

    def ground(self):
        for x, z in self.cols:
            y = self.surface(x, z)
            self.lawn[(x, z)] = y
            for yy in range(y - 3, y):
                self.set(x, yy, z, 'dirt')
            self.set(x, y, z, 'grass_block')
            for yy in range(y + 1, TOP):
                self.set(x, yy, z, 'air')

    # --- houses -------------------------------------------------------------
    def shell(self, k):
        b = k.b
        for x, z in k.walls():
            self.set(x, b - 1, z, 'stone')
            for y in range(b, b + 7):
                self.set(x, y, z, WALL)
        for x, z in k.interior():
            self.set(x, b - 1, z, 'stone')
            self.set(x, b, z, FLOOR)
            for y in range(b + 1, b + 7):
                self.set(x, y, z, 'air')
            self.set(x, b + 4, z, FLOOR)

    def window(self, x, z, ys, axis='x'):
        for y in ys:
            self.set(x, y, z, pane(axis))

    def door(self, x, z, b, facing, hinge='left'):
        self.set(x, b + 1, z, f'spruce_door[facing={facing},half=lower,hinge={hinge},open=false]')
        self.set(x, b + 2, z, f'spruce_door[facing={facing},half=upper,hinge={hinge},open=false]')

    def stairs(self, k):
        b, f = k.b, k.f
        for _cols, sx in k.halves():
            for i, z in enumerate((f - 2, f - 3, f - 4, f - 5)):
                self.set(sx, b + 1 + i, z, stair('spruce', 'north'))
            for z in (f - 2, f - 3, f - 4):
                self.set(sx, b + 4, z, 'air')

    def front(self, k, render_cols, window_cols):
        b, f = k.b, k.f
        for x in render_cols + window_cols:
            self.window(x, f, (b + 2, b + 3))
            self.window(x, f, (b + 5, b + 6))
        for x in render_cols:
            self.set(x, b + 4, f, RENDER)

    def roof(self, k):
        """1:2 hip (bottom/top slabs), 1-block overhang except on attached ends."""
        b = k.b
        rx0, rx1 = k.x0 - k.ov_w, k.x1 + k.ov_e
        rz0, rz1 = k.r - 1, k.f + 1
        for x in range(rx0, rx1 + 1):
            for z in range(rz0, rz1 + 1):
                d = min(x - rx0, rx1 - x, z - rz0, rz1 - z)
                y = b + 7 + d // 2
                inside = k.x0 <= x <= k.x1 and k.r <= z <= k.f
                if (x, z) in k.trim:
                    continue
                if inside:
                    for yy in range(b + 7, y):
                        self.set(x, yy, z, 'bricks')
                self.set(x, y, z, f'{ROOF}_slab[type={"bottom" if d % 2 == 0 else "top"}]')
        top = b + 7 + max(min(x - rx0, rx1 - x, z - rz0, rz1 - z)
                          for x in range(rx0, rx1 + 1) for z in range(rz0, rz1 + 1)) // 2
        for x, z in k.chimney:
            for y in range(b + 7, top + 3):
                self.set(x, y, z, 'bricks')

    def block_a(self):
        k = A
        b = k.b
        self.shell(k)
        self.front(k, [7052, 7053, 7061, 7062], [7055, 7056, 7058, 7059])
        r = k.r
        # rear: a door per flat pair off the patio, windows over
        self.door(7052, r, b, 'north')
        self.door(7062, r, b, 'north', hinge='right')
        for x in (7054, 7055, 7059, 7060):
            self.window(x, r, (b + 2, b + 3))
        for x in (7052, 7053, 7055, 7059, 7061, 7062):
            self.window(x, r, (b + 5, b + 6))
        # west side onto the gap path
        for z in (-5554, -5558):
            self.window(k.x0, z, (b + 2, b + 3), 'z')
            self.window(k.x0, z, (b + 5, b + 6), 'z')
        self.stairs(k)
        self.roof(k)

    def block_b(self):
        k = B
        b = k.b
        self.shell(k)
        self.front(k, [7042, 7043, 7047, 7048], [7044, 7046])
        r = k.r
        for x in (7042, 7043, 7047, 7048):
            self.window(x, r, (b + 5, b + 6))
        self.window(7042, r, (b + 2, b + 3))
        for z in (-5559,):
            self.window(k.x1, z, (b + 2, b + 3), 'z')
            self.window(k.x1, z, (b + 5, b + 6), 'z')
        # single-storey rear part: common entrance from the gap path
        wx0, wx1, wr = WING
        for x in range(wx0, wx1 + 1):
            for z in range(wr, r):
                edge = x in (wx0, wx1) or z == wr
                self.set(x, b - 1, z, 'stone')
                for y in range(b, b + 4):
                    self.set(x, y, z, WALL if edge else ('air' if y > b else FLOOR))
                self.set(x, b + 4, z, 'smooth_stone_slab[type=bottom]')
        for x in (7044, 7047):              # hall openings into each half of the main block
            self.set(x, b + 1, r, 'air')
            self.set(x, b + 2, r, 'air')
        self.door(wx1, -5567, b, 'east')
        for x in (7045, 7047):
            self.window(x, wr, (b + 2, b + 3))
        self.stairs(k)
        self.roof(k)

    # --- gardens ------------------------------------------------------------
    def front_gardens(self):
        for x in range(X0, X1 + 1):
            zb = pav_row(x) - 1
            k = block_of(x)
            py = stone_top(x, zb + 1)                      # pavement level in front
            zw = pav_row(x - 1) - 1 if x > X0 else zb
            for z in range(min(zb, zw), zb + 1):
                if z != zb and x in (7042, PATH_X):
                    continue
                for y in range(py + 1, k.b + 1):
                    self.set(x, y, z, WALL)
                if x == PATH_X:
                    continue
                if k is A:                                 # ivy/hedge over the wall (photo)
                    self.set(x, k.b + 1, z, 'oak_leaves[persistent=true]')
                    self.set(x, k.b + 2, z, 'oak_leaves[persistent=true]')
                # 44/46: retaining wall flush with the raised lawn (photo: first tier)
            # gate steps: west end of 44/46 (photo, with handrail) and the gap path
            if x == 7042:
                self.set(x, 30, zb, stair('brick', 'north'))
                self.set(x, 31, zb, 'air'); self.set(x, 32, zb, 'air')
                self.set(x, 31, zb - 1, stair('brick', 'north'))
                self.set(x, 32, zb - 1, 'air')
                self.set(7041, 32, zb - 1, 'iron_bars')
                for z in range(zb - 2, B.f):
                    self.set(x, 31, z, 'polished_andesite')
            if x == PATH_X:
                self.set(x, 30, zb, stair('stone_brick', 'north'))
                for y in (31, 32):
                    self.set(x, y, zb, 'air')
        # the 44/46 garden is a step above the path: brick edge, not a dirt face
        for z in range(B.f + 1, pav_row(7049) - 1):
            self.set(7049, 30, z, WALL)
        # shrubs in the front gardens (photo: bush in front of the end bay)
        for x, z in ((7043, B.f + 2), (7047, B.f + 2), (7054, A.f + 2), (7060, A.f + 2)):
            k = block_of(x)
            self.set(x, k.b + 1, z, 'oak_leaves[persistent=true]')

    def path(self):
        x = PATH_X
        for z in range(-5571, pav_row(x) - 1):
            y = self.lawn[(x, z)]
            self.set(x, y, z, 'polished_andesite')
        self.set(x, 31, -5564, stair('stone_brick', 'north'))
        self.set(x, 30, -5564, 'dirt')

    def back(self):
        # patios / yards
        for x in range(A.x0, A.x1 + 1):
            for z in (-5562, -5563):
                self.set(x, A.b, z, 'smooth_stone')
        for x in range(7042, 7050):
            for z in (-5570, -5571):
                if owned(x, z) and owned(x - 1, z):
                    self.set(x, B.b, z, 'smooth_stone')
        for z in range(-5569, -5564):
            for x in (7041, 7042):
                if owned(x, z):
                    self.set(x, B.b, z, 'smooth_stone')
        # steps from patio to lawn where the lawn is a block up
        for x, zs in ((7053, range(-5600, -5563)), (7061, range(-5600, -5563)),
                      (7044, range(-5600, -5571)), (7047, range(-5600, -5571))):
            for z in zs:
                if (x, z) in self.lawn and (x, z + 1) in self.lawn:
                    y0, y1 = self.lawn[(x, z + 1)], self.lawn[(x, z)]
                    if y1 == y0 + 1:
                        self.set(x, y1, z, stair('stone_brick', 'north'))
        # fences: plot lines to the lane, rear fence, west boundary
        lines = {7045: -5576, PATH_X: -5572, 7057: -5564}
        for x, z_start in lines.items():
            for z in range(lane_row(x) + 1, z_start + 1):
                if owned(x, z):
                    self.fence(x, z)
        for x in range(X0, X1 + 1):
            a = lane_row(x) + 1
            c = lane_row(x - 1) + 1 if x > X0 else a
            for z in range(min(a, c), max(a, c) + 1):
                if owned(x, z):
                    self.fence(x, z)
        prev = None
        for z in range(-5562, -5600, -1):
            xs = [x for x in range(X0, X1 + 1) if owned(x, z)]
            if not xs:
                continue
            xw = xs[0]
            self.fence(xw, z)
            if prev is not None and xw < prev:
                for x in range(xw + 1, prev):
                    self.fence(x, z)
            elif prev is not None and xw > prev:
                for x in range(prev + 1, xw):
                    self.fence(x, z + 1)
            prev = xw
        # outbuildings by the lane (aerial): pale shed behind 40, grey roofs behind 44/46
        self.shed(7058, 7059, lane_row(7059) + 2, 3, 'smooth_quartz', 'birch_slab')
        self.shed(7043, 7046, lane_row(7046) + 2, 3, 'stone_bricks', 'smooth_stone_slab')
        # trees mid-garden (aerial crowns)
        self.tree(7047, -5581)
        self.tree(7061, -5575)

    def fence(self, x, z):
        if (x, z) not in self.lawn:
            return
        y = self.lawn[(x, z)]
        if self.p.get(x, y + 1, z) not in (None, 'minecraft:air'):
            return                              # wall / wing / shed already there
        self.set(x, y + 1, z, 'spruce_fence')
        self.set(x, y + 2, z, 'spruce_fence')

    def shed(self, x0, x1, z0, depth, wall, roof):
        cells = [(x, z) for x in range(x0, x1 + 1) for z in range(z0, z0 + depth)]
        y = max(self.lawn[c] for c in cells)
        for x, z in cells:
            for yy in range(self.lawn[(x, z)] + 1, y + 1):
                self.set(x, yy, z, 'dirt')
            self.set(x, y + 1, z, wall)
            self.set(x, y + 2, z, wall)
            self.set(x, y + 3, z, f'{roof}[type=bottom]')
        self.set(x0, y + 1, z0 + depth - 1, 'spruce_door[facing=south,half=lower,hinge=left,open=false]')
        self.set(x0, y + 2, z0 + depth - 1, 'spruce_door[facing=south,half=upper,hinge=left,open=false]')

    def tree(self, x, z):
        y = self.lawn[(x, z)]
        for i in range(1, 6):
            self.set(x, y + i, z, 'oak_log')
        for dx in range(-2, 3):
            for dz in range(-2, 3):
                for dy in range(4, 8):
                    if abs(dx) + abs(dz) + max(0, dy - 6) * 2 <= 3 and not (dx == dz == 0 and dy < 6):
                        if owned(x + dx, z + dz) and self.p.get(x + dx, y + dy, z + dz) in (None, 'minecraft:air'):
                            self.set(x + dx, y + dy, z + dz, 'oak_leaves[persistent=true]')

    def connect(self):
        dirs = {'north': (0, -1), 'south': (0, 1), 'east': (1, 0), 'west': (-1, 0)}
        for (x, y, z), s in list(self.p.cells.items()):
            if s.startswith('minecraft:spruce_fence'):
                props = []
                for kk, (dx, dz) in dirs.items():
                    n = self.p.get(x + dx, y, z + dz) or ''
                    ok = 'fence' in n or (n and not any(t in n for t in ('air', 'leaves', 'pane', 'stairs', 'slab', 'door')))
                    props.append(f'{kk}={"true" if ok else "false"}')
                self.p.cells[(x, y, z)] = 'minecraft:spruce_fence[' + ','.join(sorted(props)) + ']'

    def restore_orphans(self):
        """Cells the first apply of this build took inside #48's raster fringe (looser
        owner rule) go back to their pre-Q-020 state from the region snap."""
        old = ROOT / f'verification/site/{NAME}-cells.json'
        if not old.exists() or not SNAP.exists():
            return
        snap = World(SNAP)
        for k in json.loads(old.read_text()):
            x, y, z = map(int, k.split(','))
            if not owned(x, z) and self.p.get(x, y, z) is None:
                self.set(x, y, z, snap.block(x, y, z))

    def build(self, restore=True):
        """Assemble the plan.

        @param restore: put back first-apply orphans from the region snap (False = only the
            cells this build's own rules write; broadlands_rd_48_54 uses that to tell #46's
            fabric from the #48 Geocraft fringe restored here)
        @returns: the Plan
        """
        if restore:
            self.restore_orphans()
        self.ground()
        self.front_gardens()
        self.block_a()
        self.block_b()
        self.path()
        self.back()
        self.connect()
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
