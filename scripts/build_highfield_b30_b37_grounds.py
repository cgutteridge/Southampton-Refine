#!/usr/bin/env python3
"""Q-026: Highfield campus grounds around the Q-025 blocks (B30 road front, B37 north + SW).

Evidence
  kartaview-1519868249 (camera 6396,-5526 ESE): B30's one-storey road front is a dark
           recessed colonnade: grey columns under a projecting dark fascia, glazing set
           back behind them, a strip of gravel, then a low red-brick wall with a stone
           coping at the back of a narrow footway (~1 m) on the road
  kartaview-1519868121 (6322,-5558 ESE): B37 north forecourt is a wide red-brown block
           paving between the kerb and the building with a row of steel Sheffield stands
           along the kerb (~10, perpendicular to it)
  kartaview-1471281241 (6308,-5462 NNW): B37's long SW face: low clipped hedge along the
           foot of the wall, grass verge with a line of young street trees, footway at the
           kerb; a full-height glazed stair tower at the NEAR (south-east) end of the face,
           where the OSM outline kinks (uv -59.2,45.1) — I-021 said NW end; the camera
           geometry puts it at the SE end
  survey   B30: wall cells at v≈-31, one stone fringe cell, 1-2 cells of footway, road.
           B37 north: road (gray_terracotta) v -25..-21, bare stone v -20..-12 to the wall.
           B37 SW: 9 cells of stone/grass between the wall and the road.

Modifies highfield_b29_b30 (B30 front cells) and highfield_b37 (tower + envelope ground).

  python3 scripts/build_highfield_b30_b37_grounds.py            # preview + dry-run guards
  SITE_OWNER=... python3 scripts/build_highfield_b30_b37_grounds.py --apply
"""
import argparse
import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'scripts'))
from site_kit import World, apply, preview, built_cells  # noqa: E402
from campus import Campus, UV, N4, FACING  # noqa: E402
import build_highfield_b29_b30 as B30  # noqa: E402
import build_highfield_b37 as B37  # noqa: E402

NAME = 'highfield_b30_b37_grounds'
ROAD = 'minecraft:gray_terracotta'
PAVE, KERB, FORECOURT = 'polished_diorite', 'smooth_stone', 'polished_granite'
HEDGE = 'oak_leaves[persistent=true]'
LEAVES = 'oak_leaves[persistent=true]'
KINK = (-59.2, 45.1)               # B37 SW face kink in uv: glazed stair tower
SW_A, SW_B = (-94, 19.5), (-49.5, 50.5)

w = World()


SURVEY = ROOT / f'verification/site/{NAME}-survey.json'
_seen = json.loads(SURVEY.read_text()) if SURVEY.exists() else {}


def block(x, y, z):
    """World reads frozen at the first run, so re-running the plan after apply does not see
    its own blocks (the first re-apply stacked bricks on the B30 coping)."""
    k = f'{x},{y},{z}'
    if k not in _seen:
        _seen[k] = w.block(x, y, z) or 'minecraft:air'
    return _seen[k]


def top(x, z, lo=40, hi=90):
    for y in range(hi, lo, -1):
        b = block(x, y, z)
        if b != 'minecraft:air' and 'leaves' not in b and '_log' not in b:
            return y, b.split('[')[0]
    return None, None


class Grounds:
    def __init__(self):
        self.c30 = Campus(B30.NAME, B30.PARTS, B30.WAYS, (6345, -5600, 6475, -5500), B30.DOORS, B30.STAIRS)
        self.c37 = B37.make()
        self.p = self.c30.p.__class__(NAME)
        self.parts = {**self.c30.part, **self.c37.part}
        owned = built_cells(exclude=(NAME, B30.NAME, B37.NAME))
        self.others = {(x, z) for x, _y, z in owned}
        self.notes = {}

    def set(self, x, y, z, s):
        self.p.set(x, y, z, s)

    # --- B30: recessed colonnade behind a low brick wall with stone coping (249) -------------
    def b30_front(self):
        c = self.c30
        front = {q for q, pt in c.part.items() if pt.name == 'b30_front'}
        road_side = lambda q: q not in self.parts and UV(*q)[1] > -31.0
        d1 = {q for q in front if any(road_side((q[0] + a, q[1] + b)) for a, b in N4)}
        d2 = {q for q in front - d1 if any((q[0] + a, q[1] + b) in d1 for a, b in N4)}
        d3 = {q for q in front - d1 - d2 if any((q[0] + a, q[1] + b) in d2 for a, b in N4)}
        old_door = (6399, -5528)
        door = min(d3, key=lambda q: math.hypot(q[0] - old_door[0], q[1] - old_door[1]))
        du = UV(*door)[0]
        for x, z in d1:                                   # open strip under the fascia: gravel
            near = abs(UV(x, z)[0] - du) < 1.6
            self.set(x, 51, z, 'polished_andesite' if near else 'gravel')
            for y in (52, 53, 54):
                self.set(x, y, z, 'air')
        cols = set()
        for x, z in sorted(d2):                           # columns every 4 along u
            u = UV(x, z)[0]
            k = math.floor(u)
            self.set(x, 51, z, 'polished_andesite')
            col = k % 4 == 0 and k not in cols and abs(u - du) > 1.6
            if col:
                cols.add(k)
            for y in (52, 53, 54):
                self.set(x, y, z, 'gray_concrete' if col else 'air')
            self.set(x, 55, z, 'gray_concrete')             # soffit
        for x, z in d3:                                   # new glazed line, mullions every 4
            k = math.floor(UV(x, z)[0])
            self.set(x, 51, z, 'gray_concrete')
            for y in (52, 53, 54):
                self.set(x, y, z, 'gray_concrete' if k % 4 == 2 else 'gray_stained_glass')
        x, z = door
        self.set(x, 52, z, 'dark_oak_door[facing=south,half=lower,hinge=left,open=false]')
        self.set(x, 53, z, 'dark_oak_door[facing=south,half=upper,hinge=left,open=false]')
        for a, b in N4:                                   # clear the hall cell behind the door
            q = (x + a, z + b)
            if q in front and q not in d2 and q not in d1 and q not in d3:
                self.set(q[0], 52, q[1], 'air')
                self.set(q[0], 53, q[1], 'air')
        # low wall at the back of the footway
        wall = {(x + a, z + b) for x, z in d1 for a, b in N4} - set(self.parts)
        wall = {q for q in wall if road_side(q) and q not in self.others}
        n = 0
        for x, z in wall:
            g, b = top(x, z, 44, 60)
            if b == ROAD:
                continue
            if abs(UV(x, z)[0] - du) < 1.6:              # gap for the entrance path, one step up
                self.set(x, g, z, 'polished_andesite')
                if g < 51:
                    a, b = next((a, b) for a, b in N4 if (x + a, z + b) in d1)
                    self.set(x, g + 1, z, f'stone_brick_stairs[facing={FACING[(a, b)]},half=bottom]')
                continue
            t = max(g + 1, 51)
            for y in range(g + 1, t + 1):
                self.set(x, y, z, 'bricks')
            self.set(x, t + 1, z, 'smooth_stone_slab[type=bottom,waterlogged=false]')
            n += 1
        self.notes['b30'] = dict(d1=len(d1), d2=len(d2), d3=len(d3), columns=len(cols), wall=n, door=door)

    # --- B37 north: red-brown paving + Sheffield stands along the kerb (121) ------------------
    def b37_north(self):
        cells = {}
        for x in range(6285, 6350):
            for z in range(-5575, -5530):
                u, v = UV(x, z)
                if not (-106 <= u < -54.5 and -20.6 <= v < -11.5) or (x, z) in self.parts or (x, z) in self.others:
                    continue
                g, b = top(x, z, 48, 60)
                if b != 'minecraft:stone' or block(x, g + 1, z) != 'minecraft:air':
                    continue                              # door paths / anything standing stays
                cells[(x, z)] = g
        road = lambda q: top(*q, 48, 60)[1] == ROAD
        kerb = {q for q in cells if any(road((q[0] + a, q[1] + b)) for a, b in N4)}
        stand_row = {q for q in cells if q not in kerb and any((q[0] + a, q[1] + b) in kerb for a, b in N4)}
        bins, stands = set(), 0
        for (x, z), g in cells.items():
            self.set(x, g, z, KERB if (x, z) in kerb else FORECOURT)
        for (x, z) in sorted(stand_row):
            u = UV(x, z)[0]
            k = math.floor(u / 3)
            if -100 <= u <= -62 and k not in bins:
                bins.add(k)
                self.set(x, cells[(x, z)] + 1, z, 'iron_bars')
                stands += 1
        self.notes['b37_north'] = dict(paved=len(cells), kerb=len(kerb), stands=stands)

    # --- B37 SW: hedge at the wall, grass verge with street trees, footway + kerb (241) -------
    def b37_sw(self):
        L = math.hypot(SW_B[0] - SW_A[0], SW_B[1] - SW_A[1])
        t = ((SW_B[0] - SW_A[0]) / L, (SW_B[1] - SW_A[1]) / L)
        nrm = (-t[1], t[0])                              # outward (away from the wing)
        cells = {}
        for x in range(6278, 6330):
            for z in range(-5530, -5465):
                if (x, z) in self.parts or (x, z) in self.others:
                    continue
                u, v = UV(x, z)
                s = (u - SW_A[0]) * t[0] + (v - SW_A[1]) * t[1]
                d = (u - SW_A[0]) * nrm[0] + (v - SW_A[1]) * nrm[1]
                if not (1 <= s <= L - 4 and 0 < d < 11):
                    continue
                g, b = top(x, z, 48, 60)
                if b == ROAD or b is None:
                    continue
                if b not in ('minecraft:stone', 'minecraft:grass_block', 'minecraft:polished_diorite',
                             'minecraft:smooth_stone', 'minecraft:dirt', 'minecraft:granite'):
                    continue
                cells[(x, z)] = (g, s, d)
        road = lambda q: top(*q, 48, 60)[1] == ROAD
        kerb = {q for q in cells if any(road((q[0] + a, q[1] + b)) for a, b in N4)}
        foot = {q for q in cells if q not in kerb and any((q[0] + a, q[1] + b) in kerb for a, b in N4)}
        wallside = {q for q in cells if any((q[0] + a, q[1] + b) in self.c37.part for a in (-1, 0, 1) for b in (-1, 0, 1))}
        hedge = wallside - kerb - foot                 # ~1 m clipped hedge (241)
        trees = []
        for (x, z), (g, s, d) in cells.items():
            if (x, z) in kerb:
                self.set(x, g, z, KERB)
            elif (x, z) in foot:
                self.set(x, g, z, PAVE)
            else:
                self.set(x, g, z, 'grass_block[snowy=false]')
                if (x, z) in hedge:
                    self.set(x, g + 1, z, HEDGE)
        # street trees: a line in the verge, ~7 apart
        for k in range(8):
            want = 4 + 7 * k
            cand = [(abs(s - want) + abs(d - 5.0), q) for q, (g, s, d) in cells.items()
                    if q not in hedge and q not in kerb and q not in foot]
            if not cand:
                continue
            err, (x, z) = min(cand)
            if err > 1.5:
                continue
            g = cells[(x, z)][0]
            self.tree(x, g, z)
            trees.append((x, z))
        self.notes['b37_sw'] = dict(cells=len(cells), hedge=len(hedge), kerb=len(kerb), foot=len(foot), trees=trees)

    def tree(self, x, g, z):
        """Young street tree: 5-block trunk, narrow oval crown (241: slim, light canopy)."""
        for y in range(g + 1, g + 6):
            self.set(x, y, z, 'oak_log[axis=y]')
        for y in range(g + 4, g + 10):
            r = 1 if y in (g + 4, g + 9) else 2
            for a in range(-r, r + 1):
                for b in range(-r, r + 1):
                    if (a, b) == (0, 0) and y < g + 6:
                        continue
                    if r == 2 and abs(a) == 2 and abs(b) == 2:
                        continue
                    q = (x + a, z + b)
                    if q in self.parts or q in self.others:
                        continue
                    if (x + a, y, z + b) not in self.p.cells:
                        self.set(x + a, y, z + b, LEAVES)

    # --- B37 glazed stair tower at the SW face's SE kink (241, I-021) -------------------------
    def b37_tower(self):
        c = self.c37
        cells = {q for q, pt in c.part.items() if pt.name == 'b37_wing'
                 and math.hypot(UV(*q)[0] - KINK[0], UV(*q)[1] - KINK[1]) < 3.2}
        n = 0
        for x, z in cells:
            ex = [(a, b) for a, b in N4 if (x + a, z + b) not in c.part]
            if not ex:
                continue
            for y in range(55, 68):
                self.set(x, y, z, 'white_stained_glass')
            self.set(x, 68, z, 'smooth_quartz_slab[type=bottom,waterlogged=false]')
            n += 1
        for x, z in cells:                               # inside the tower: rise to 67 under a cap
            if (x, 68, z) not in self.p.cells:
                self.set(x, 67, z, 'air')
                self.set(x, 68, z, 'smooth_quartz_slab[type=bottom,waterlogged=false]')
        self.notes['b37_tower'] = dict(cells=len(cells), glazed=n)

    def build(self):
        self.b30_front()
        self.b37_north()
        self.b37_sw()
        self.b37_tower()
        if not SURVEY.exists():
            SURVEY.write_text(json.dumps(_seen))
        return self.p


def build():
    return Grounds().build()


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--apply', action='store_true')
    a = ap.parse_args()
    gr = Grounds()
    plan = gr.build()
    print(json.dumps(gr.notes, default=str))
    preview(plan, ROOT / f'verification/site/{NAME}-preview.png', scale=2)
    print(json.dumps(plan.summary())[:500])
    apply(plan, dry=not a.apply, modifies=(B30.NAME, B37.NAME, 'highfield_b35_grounds'))
