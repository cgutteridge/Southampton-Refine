#!/usr/bin/env python3
"""Q-024: University Highfield campus, Building 35 (David Kiddle), OSM way 146985470.

Evidence
  OSM      reference/osm/highfield-b35 (outline; loc_ref 35)
  aerial   reference/aerial/highfield-b35/mosaic-z18-3x3-centre-130056-87836.png
           grey flat roofs, dark central courtyard, brown pitched roof on the NW wing
  LIDAR    Geocraft massing (pristine region): north range top 62, other ranges 59,
           west strip 54, courtyard infill 52, rotunda 57, NW wing eaves 56 / ridge 58
  photo    kartaview-1519868249 (north road, camera ~6392,-5530 looking ESE):
           dark red brick, ground floor under a white band, 3 storeys of paired
           white-framed windows above, flat roof with thin parapet

The building is rotated ~25 deg; every wall is axis-aligned in a 2:1 frame
(u along (2,1), v along (-1,2), atan(1/2) = 26.6 deg) so walls step regularly instead
of tracing OSM jags. Parts are rectangles in (u, v) read off the OSM vertices.
Floors are shared (48/51/54/57) so the ranges connect; one switchback stair in the
north range. Public building: floors + stair only (no interior refs).

  python3 scripts/build_highfield_b35.py            # preview + dry-run guards
  SITE_OWNER=... python3 scripts/build_highfield_b35.py --apply
"""
import argparse
import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'scripts'))
from site_kit import Plan, World, apply, preview  # noqa: E402
from osm_footprints import OSMIndex, PRISTINE  # noqa: E402

NAME = 'highfield_b35'
WAY = '146985470'
OX, OZ = 6385.0, -5500.0
R5 = math.sqrt(5)

BRICK = 'bricks'
BAND = 'smooth_quartz'
GLASS = 'glass'
FLOOR = 'smooth_stone'
DECK = 'light_gray_concrete'
COPING = 'smooth_stone_slab[type=bottom]'
LIGHT = 'light[level=15]'  # invisible; hung under ceilings, never in a slab or the roof
TILE = 'granite'            # NW wing: brown tiles on the aerial
CLEAR_TO = 80

TERRAIN = ('stone', 'gray_terracotta', 'grass_block', 'dirt', 'polished_diorite', 'granite',
           'black_wool', 'smooth_stone', 'coarse_dirt', 'gravel', 'andesite', 'spruce_planks',
           'polished_andesite', 'dirt_path', 'podzol')
KEEP = ('leaves', '_log', 'air')


def uv(x, z):
    """Rotated-frame coordinates of block (x, z)'s centre."""
    dx, dz = x + 0.5 - OX, z + 0.5 - OZ
    return (2 * dx + dz) / R5, (-dx + 2 * dz) / R5


class Part:
    def __init__(self, name, rects, base, deck, top=None, floors=(), circle=None):
        self.name, self.rects, self.base, self.deck = name, rects, base, deck
        self.top = top                  # coping y (parapet bricks deck+1..top-1); None = no parapet
        self.floors = floors            # interior floor slabs (base first)
        self.circle = circle            # (u, v, r) rounded end

    def has(self, u, v):
        if any(u0 <= u < u1 and v0 <= v < v1 for u0, u1, v0, v1 in self.rects):
            return True
        if self.circle:
            cu, cv, r = self.circle
            return (u - cu) ** 2 + (v - cv) ** 2 <= r * r
        return False


F4 = (48, 51, 54, 57)
F3 = (48, 51, 54)
# priority = order (first match wins): taller ranges over lower ones where rects overlap
PARTS = [
    Part('north', [(-3.4, 23.2, -17.4, -10.0), (23.2, 27.1, -14.8, -10.0), (27.1, 28.8, -11.9, -10.0)],
         48, 60, 62, F4),
    Part('east', [(19.5, 29.5, -10.0, 24.9)], 48, 57, 59, F3),
    Part('south', [(-6.4, 19.5, 4.0, 10.6)], 48, 57, 59, F3),
    Part('west', [(1.0, 7.0, -10.0, 4.0)], 48, 57, 59, F3),
    Part('rotunda', [(13.3, 19.5, 13.9, 18.3)], 48, 57, None, F3, circle=(13.3, 16.1, 2.2)),
    Part('west_strip', [(-8.0, 1.0, -13.8, 4.0)], 48, 54, None, (48, 51)),
    Part('courtyard', [(7.0, 19.5, -10.0, 4.0)], 48, 51, None, (48,)),
]
NW = Part('nw_wing', [(-40.8, -11.6, -19.4, -11.2), (-30.6, -19.6, -11.2, -4.0)], 52, 56, None, (52,))

# doors: (part, u, v, floor) — nearest single-faced wall cell to (u, v)
DOORS = [
    ('north', -1.0, -17.4, 51),     # main entrance off the north road (photo: entrance under band)
    ('north', 21.0, -17.4, 48),     # NE steps (OSM 230359499)
    ('east', 29.5, 2.0, 48),        # service yard
    ('south', 6.0, 10.6, 48),       # south, off the Estates spur road
    ('nw_wing', -35.0, -11.2, 52),  # to the west car park
    ('nw_wing', -26.0, -19.4, 52),  # to the north road
]
N4 = ((1, 0), (-1, 0), (0, 1), (0, -1))
FACING = {(1, 0): 'east', (-1, 0): 'west', (0, 1): 'south', (0, -1): 'north'}


class Build:
    def __init__(self):
        self.p = Plan(NAME)
        self.w = World()
        self.pw = World(PRISTINE) if PRISTINE and Path(PRISTINE).exists() else self.w
        self.idx = OSMIndex()
        self.part = {}                       # (x, z) -> Part
        for x in range(6340, 6430):
            for z in range(-5550, -5450):
                u, v = uv(x, z)
                for pt in PARTS + [NW]:
                    if pt.has(u, v):
                        self.part[(x, z)] = pt
                        break
        self._terr = {}
        cells = self.idx.cells()
        self.other = {q for q, i in cells.items() if self.idx.buildings[i][1].get('osm_way_id') != WAY}

    # --- helpers -------------------------------------------------------------
    def terrain(self, x, z):
        """Top of the contiguous terrain column in pristine Geocraft (ignores brick walls on it)."""
        if (x, z) not in self._terr:
            y = 30
            while y < 70 and not self._is_terrain(self.pw.block(x, y, z)):
                y += 1
            while self._is_terrain(self.pw.block(x, y + 1, z)):
                y += 1
            self._terr[(x, z)] = y
        return self._terr[(x, z)]

    @staticmethod
    def _is_terrain(b):
        return bool(b) and b.split('[')[0][10:] in TERRAIN

    def deck(self, x, z):
        pt = self.part.get((x, z))
        return pt.deck if pt else -999

    def exposed(self, x, z, y):
        """Neighbour offsets at which the wall cell (x, y, z) faces open air."""
        return [(dx, dz) for dx, dz in N4 if self.deck(x + dx, z + dz) < y
                or (self.part.get((x + dx, z + dz)) and self.part[(x + dx, z + dz)].base > y)]

    def set(self, x, y, z, s):
        self.p.set(x, y, z, s)

    def outside_ground(self, x, z):
        """Ground level for a non-building cell: pristine terrain, or (inside the old Geocraft
        footprint, whose floor sits low) the median of nearby open terrain."""
        if not self.idx.covered(x, z) or (x, z) in self.other:
            return self.terrain(x, z)
        near = sorted(self.terrain(x + dx, z + dz) for dx in range(-5, 6) for dz in range(-5, 6)
                      if not self.idx.covered(x + dx, z + dz) and (x + dx, z + dz) not in self.part)
        return near[len(near) // 2] if near else self.terrain(x, z)

    # --- shell -----------------------------------------------------------------
    def shells(self):
        for (x, z), pt in self.part.items():
            for y in range(pt.base - 3, pt.base):
                self.set(x, y, z, 'stone')
            top = pt.top if pt.top else pt.deck
            for y in range(pt.base, CLEAR_TO + 1):
                if y > top:
                    self.set(x, y, z, 'air')
                    continue
                ex = self.exposed(x, z, y)
                if y > pt.deck:                          # parapet ring only on outer edges
                    edge = any(self.deck(x + dx, z + dz) < pt.deck for dx, dz in N4)
                    self.set(x, y, z, (COPING if y == top else BRICK) if edge else 'air')
                elif ex:
                    self.set(x, y, z, self.wall_block(x, y, z, pt, ex))
                elif y == pt.deck:
                    self.set(x, y, z, DECK)
                elif y in pt.floors:
                    self.set(x, y, z, FLOOR)
                else:
                    self.set(x, y, z, 'air')

    def wall_block(self, x, y, z, pt, ex):
        if pt.name == 'north' and y == 51:
            return BAND
        if len(ex) != 1 or y == pt.base or y == pt.deck:
            return BRICK
        f = max(fl for fl in pt.floors if fl <= y)
        if y - f not in (1, 2):
            return BRICK
        if pt is NW and y < 54:
            return BRICK                                 # one tall storey: windows high
        dx, dz = ex[0]
        if self.part.get((x + dx, z + dz)) is None and self.outside_ground(x + dx, z + dz) >= y - 1:
            return BRICK                                 # below outside ground (semi-basement)
        return GLASS

    # --- NW wing hipped roof (1:2, granite) ------------------------------------------
    def nw_roof(self):
        cells = [q for q, pt in self.part.items() if pt is NW]
        cs = set(cells)
        outside = [(x + dx, z + dz) for x, z in cells for dx in range(-1, 2) for dz in range(-1, 2)
                   if (x + dx, z + dz) not in cs]
        outside = set(outside)

        def dist(x, z):
            return min(math.hypot(x - a, z - b) for a, b in outside if abs(x - a) < 7 and abs(z - b) < 7)

        e = NW.deck
        for x, z in cells:
            k = max(0, round(dist(x, z) - 1))            # ring 0 = wall cells
            s2 = 2 * (e + 1) + 1 + k                     # surface height in half blocks
            ytop = (s2 - 1) // 2
            for y in range(e + 1, ytop):
                self.set(x, y, z, TILE)
            self.set(x, ytop, z, f'{TILE}_slab[type={"bottom" if s2 % 2 else "top"}]')
        for x, z in outside:                             # eave overhang lip
            if (x, z) in self.part or (x, z) in self.other:
                continue
            if any((x + dx, z + dz) in cs for dx, dz in N4):
                self.set(x, e, z, f'{TILE}_slab[type=top]')

    # --- stair (north range, switchback) -----------------------------------------
    def stair(self):
        north = PARTS[0]
        for sx, sz in sorted(((x, z) for (x, z), pt in self.part.items() if pt is north),
                             key=lambda q: math.hypot(*(a - b for a, b in zip(uv(*q), (8, -13.5))))):
            box = [(x, z) for x in range(sx - 1, sx + 4) for z in (sz, sz + 1)]
            if all(self.part.get(q) is north and not self.exposed(q[0], q[1], 49) for q in box):
                break
        else:
            raise SystemExit('no room for the stair')
        self.stair_at = (sx, sz)
        fl = north.floors
        for i, f in enumerate(fl[:-1]):
            lane = sz if i % 2 == 0 else sz + 1
            xs = [sx, sx + 1, sx + 2] if i % 2 == 0 else [sx + 2, sx + 1, sx]
            face = 'east' if i % 2 == 0 else 'west'
            for k, x in enumerate(xs):
                self.set(x, f + 1 + k, lane, f'stone_brick_stairs[facing={face},half=bottom]')
                for y in range(f + 2 + k, f + 5 + k):
                    if y < f + 3 or self.p.get(x, y, lane) == f'minecraft:{FLOOR}':
                        self.set(x, y, lane, 'air')
            step = 1 if i % 2 == 0 else -1
            for x in [xs[0] - step] + xs[:2]:            # headroom hole in the floor above
                self.set(x, f + 3, lane, 'air')

    # --- doors -------------------------------------------------------------------------
    def doors(self):
        self.door_cells = []
        for pname, du, dv, f in DOORS:
            pt = NW if pname == 'nw_wing' else next(p for p in PARTS if p.name == pname)
            best = None
            for (x, z), q in self.part.items():
                if q is not pt:
                    continue
                ex = self.exposed(x, z, f + 1)
                if len(ex) != 1:
                    continue
                dx, dz = ex[0]
                if (x - dx, z - dz) not in self.part or self.exposed(x - dx, z - dz, f + 1):
                    continue
                d = math.hypot(*(a - b for a, b in zip(uv(x, z), (du, dv))))
                if best is None or d < best[0]:
                    best = (d, x, z, dx, dz)
            _, x, z, dx, dz = best
            face = FACING[(dx, dz)]
            self.set(x, f + 1, z, f'dark_oak_door[facing={face},half=lower,hinge=left,open=false]')
            self.set(x, f + 2, z, f'dark_oak_door[facing={face},half=upper,hinge=left,open=false]')
            self.set(x - dx, f + 1, z - dz, 'air')
            self.set(x - dx, f + 2, z - dz, 'air')
            self.door_cells.append((pname, x, f + 1, z, face))
            # approach: landing at floor level, then steps toward the outside ground
            prev = f
            for k in range(1, 5):
                ax, az = x + dx * k, z + dz * k
                if (ax, az) in self.part or (ax, az) in self.other:
                    break
                g = self.outside_ground(ax, az)
                if k == 1:
                    s = f
                elif g > prev:
                    s = prev + 1
                elif g < prev:
                    s = prev - 1
                else:
                    s = g
                for side in (-1, 0, 1):                  # 3 wide
                    bx, bz = ax + (dz * side if dz else 0), az + (dx * side if dx else 0)
                    if (bx, bz) in self.part or (bx, bz) in self.other:
                        continue
                    for y in range(min(s, g) - 1, s):
                        self.set(bx, y, bz, 'stone')
                    if s > prev:
                        self.set(bx, s, bz, f'stone_brick_stairs[facing={FACING[(-dx, -dz)]},half=bottom]')
                    elif s < prev and k > 1:
                        self.set(bx, s, bz, 'polished_andesite')
                    else:
                        self.set(bx, s, bz, 'polished_andesite')
                    for y in range(s + 1, max(g, s) + 3):
                        self.set(bx, y, bz, 'air')
                if s == g:
                    break
                prev = s

    # --- envelope: clear Geocraft walls / carpet roofs left around the new shell ---------
    def envelope(self):
        cs = set(self.part)
        env = {(x + dx, z + dz) for x, z in cs for dx in range(-3, 4) for dz in range(-3, 4)} - cs
        old = {q for q, i in self.idx.cells().items() if self.idx.buildings[i][1].get('osm_way_id') == WAY}
        env |= old - cs
        for x, z in env:
            if (x, z) in self.other:
                continue
            t = self.terrain(x, z)
            g = self.outside_ground(x, z)
            for y in range(min(t, g) + 1, g + 1):        # refill the old building's sunk floor
                if (x, y, z) not in self.p.cells:
                    self.set(x, y, z, 'stone')
            for y in range(g + 1, CLEAR_TO + 1):
                b = self.w.block(x, y, z) or 'minecraft:air'
                if (x, y, z) in self.p.cells or any(k in b for k in KEEP):
                    continue
                self.set(x, y, z, 'air')

    # --- lighting: invisible light blocks under each ceiling -------------------------
    def lights(self, grid=7):
        """Hang LIGHT one block under every ceiling (next floor slab, or the deck for the top
        storey) on a ``grid``-block lattice of interior cells the plan leaves as air.

        @param grid: lattice spacing in blocks along MC x and z
        @returns: number of light blocks placed
        """
        n = 0
        for (x, z), pt in self.part.items():
            if x % grid or z % grid:
                continue
            levels = sorted(set(pt.floors)) + [pt.deck]
            for f, g in zip(levels, levels[1:]):
                y = g - 1
                if y > f + 1 and self.p.get(x, y, z) == 'minecraft:air':
                    self.set(x, y, z, LIGHT)
                    n += 1
        return n

    def build(self):
        """Plan B35: shells, NW wing roof, stair, doors, ceiling lights, cleared envelope.

        @returns: the site_kit Plan
        """
        self.shells()
        self.nw_roof()
        self.stair()
        self.doors()
        self.lights()
        self.envelope()
        return self.p


def build():
    return Build().build()


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--apply', action='store_true')
    a = ap.parse_args()
    b = Build()
    plan = b.build()
    print('parts', {pt.name: sum(1 for q in b.part.values() if q is pt) for pt in PARTS + [NW]})
    print('stair at', b.stair_at, 'doors', b.door_cells)
    preview(plan, ROOT / f'verification/site/{NAME}-preview.png', scale=3)
    print(json.dumps(plan.summary())[:600])
    apply(plan, dry=not a.apply)
