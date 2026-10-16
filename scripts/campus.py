#!/usr/bin/env python3
"""Shared kit for flat-roofed campus blocks (Q-025), generalised from build_highfield_b35.py.

A building is a list of Parts. Each Part is a set of rectangles / polygons in a frame:
  UV  = B35's rotated 2:1 frame (u along MC (2,1), v along (-1,2)); walls step regularly
  XZ  = plain MC axes (block centres)
A cell belongs to the first Part that contains its centre (list order = priority).
Every Part has base (ground floor y), floors (slab ys, base first), deck (roof y) and
optional top (coping y; parapet between). Walls are the exposed cells; glass sits in
`rows` above each floor on single-faced wall cells, broken by piers every `pier` cells.
Public buildings: floors + one stair only (no interior refs).
"""
import math
import sys
from pathlib import Path

from script_env import ROOT  # noqa: E402
from site_kit import Plan, World, built_cells  # noqa: E402
from osm_footprints import OSMIndex, PRISTINE  # noqa: E402

OX, OZ = 6385.0, -5500.0          # B35 frame origin (same as build_highfield_b35)
R5 = math.sqrt(5)
CLEAR_TO = 84
from cellmath import N4  # noqa: E402,F401
FACING = {(1, 0): 'east', (-1, 0): 'west', (0, 1): 'south', (0, -1): 'north'}
TERRAIN = ('stone', 'gray_terracotta', 'grass_block', 'dirt', 'polished_diorite', 'granite',
           'black_wool', 'smooth_stone', 'coarse_dirt', 'gravel', 'andesite', 'spruce_planks',
           'polished_andesite', 'dirt_path', 'podzol')
# Refine tarmac / asphalt surfaces (CRAFTSMANSHIP.txt §3a): public roads, service=driveway,
# service=parking_aisle, amenity=parking (incl. bay lines on white_concrete), cycleways
# surface=asphalt, and Broadlands streetscape carriageways.
TARMAC = 'gray_concrete'
KEEP = ('leaves', '_log', 'air')


def is_water(b):
    """Water block by id ('water' alone also matches waterlogged=false on stairs/leaves)."""
    return (b or '').split('[')[0] == 'minecraft:water'


def oid(p):
    """OSM id of a building feature: the way id, or the relation id for multipolygons."""
    return p.get('osm_way_id') or p.get('osm_id')


def UV(x, z):
    dx, dz = x + 0.5 - OX, z + 0.5 - OZ
    return (2 * dx + dz) / R5, (-dx + 2 * dz) / R5


def XZ(x, z):
    return x + 0.5, z + 0.5


def inside(px, pz, poly):
    c = False
    for (ax, az), (bx, bz) in zip(poly, poly[1:] + poly[:1]):
        if (az > pz) != (bz > pz) and px < ax + (pz - az) * (bx - ax) / (bz - az):
            c = not c
    return c


class Part:
    def __init__(self, name, base, deck, top=None, floors=(), rects=(), polys=(), frame=UV,
                 wall='bricks', glass='glass', slab='light_gray_concrete', floor='smooth_stone',
                 rows=(1,), pier=0, band=(), corner_glass=False, band_block='smooth_quartz', light='light[level=15]',
                 cells=None, ground=None):
        self.ground = ground      # dict(wall=, glass=, pier=) overriding the style of the bottom storey
        self.name, self.base, self.deck, self.top = name, base, deck, top
        self.cells = set(cells) if cells is not None else None
        self.floors = floors or (base,)
        self.rects, self.polys, self.frame = list(rects), [list(p) for p in polys], frame
        self.wall, self.glass, self.slab, self.floor = wall, glass, slab, floor
        self.corner_glass = corner_glass
        self.rows, self.pier, self.band, self.band_block, self.light = rows, pier, band, band_block, light

    def has(self, x, z):
        if self.cells is not None:
            return (x, z) in self.cells
        a, b = self.frame(x, z)
        return (any(a0 <= a < a1 and b0 <= b < b1 for a0, a1, b0, b1 in self.rects)
                or any(inside(a, b, p) for p in self.polys))


class Campus:
    """parts: priority list. ways: OSM way ids this build replaces (their old Geocraft is cleared).
    box: (x0, z0, x1, z1) search window for part cells."""

    def __init__(self, name, parts, ways, box, doors=(), stair=None, avoid_built=False, step_down_stairs=False,
                 max_fill=None):
        self.step_down_stairs = step_down_stairs
        self.clear_to = max([CLEAR_TO] + [max([p.top or p.deck, p.deck] + list(getattr(p, 'roof', {}).values())) + 3
                                          for p in parts])
        self.max_fill = max_fill                          # cap on fringe levelling above terrain
        self.keep_water = max_fill is not None             # new-style builds also keep pristine water
        self.name, self.parts, self.ways = name, parts, set(ways)
        self.p = Plan(name)
        self.w = World()
        self.pw = World(PRISTINE) if PRISTINE and Path(PRISTINE).exists() else self.w
        self.idx = OSMIndex()
        self.built = set((x, z) for x, _y, z in built_cells(exclude=(name,)))
        self.part = {}
        x0, z0, x1, z1 = box
        for x in range(x0, x1 + 1):
            for z in range(z0, z1 + 1):
                if avoid_built and any((x + a, z + b) in self.built for a in (-1, 0, 1) for b in (-1, 0, 1)):
                    continue                              # leave a cell's gap to earlier builds
                for pt in parts:
                    if pt.has(x, z):
                        self.part[(x, z)] = pt
                        break
        self.door_specs, self.stair_spec = doors, stair
        self._terr = {}
        cells = self.idx.cells()
        self.other = {q for q, i in cells.items() if oid(self.idx.buildings[i][1]) not in self.ways}

    # --- helpers -----------------------------------------------------------------------
    def terrain(self, x, z):
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
        return [(dx, dz) for dx, dz in N4 if self.deck(x + dx, z + dz) < y
                or (self.part.get((x + dx, z + dz)) and self.part[(x + dx, z + dz)].base > y)]

    def set(self, x, y, z, s):
        self.p.set(x, y, z, s)

    def outside_ground(self, x, z):
        if not self.idx.covered(x, z) or (x, z) in self.other:
            return self.terrain(x, z)
        near = sorted(self.terrain(x + dx, z + dz) for dx in range(-5, 6) for dz in range(-5, 6)
                      if (x + dx, z + dz) not in self.idx.cells() and (x + dx, z + dz) not in self.part)
        return near[len(near) // 2] if near else self.terrain(x, z)

    # --- shell ---------------------------------------------------------------------------
    def shells(self):
        for (x, z), pt in self.part.items():
            for y in range(pt.base - 3, pt.base):
                self.set(x, y, z, 'stone')
            top = pt.top if pt.top else pt.deck
            roof = getattr(pt, 'roof', None)
            if roof:
                top = roof.get((x, z), pt.deck)
            for y in range(pt.base, self.clear_to + 1):
                if roof and y > pt.deck:
                    self.set(x, y, z, self.roof_block(x, y, z, pt) if y <= top else 'air')
                    continue
                if y > top:
                    self.set(x, y, z, 'air')
                    continue
                ex = self.exposed(x, z, y)
                if y > pt.deck:
                    edge = any(self.deck(x + dx, z + dz) < pt.deck for dx, dz in N4)
                    self.set(x, y, z, ('smooth_stone_slab[type=bottom]' if y == top else pt.wall) if edge else 'air')
                elif ex:
                    self.set(x, y, z, self.wall_block(x, y, z, pt, ex))
                elif y == pt.deck:
                    self.set(x, y, z, pt.slab)
                elif y in pt.floors:
                    self.set(x, y, z, pt.floor)
                else:
                    self.set(x, y, z, 'air')

    def roof_block(self, x, y, z, pt):
        """Pitched roof following the part's LIDAR surface: stairs up-slope on the top course,
        roof blocks under it; gable/hip edges below the surface stay roof material."""
        r = pt.roof
        t = r[(x, z)]
        if y < t:
            return pt.roof_fill
        up = [(dx, dz) for dx, dz in N4 if r.get((x + dx, z + dz), -1) > t]
        if not up:
            return pt.roof_ridge
        dx, dz = max(up, key=lambda d: r[(x + d[0], z + d[1])])
        return f'{pt.roof_stair}[facing={FACING[(dx, dz)]},half=bottom]'

    def wall_block(self, x, y, z, pt, ex):
        if pt.ground and y < (pt.floors[1] if len(pt.floors) > 1 else pt.deck):
            import copy
            pt = copy.copy(pt)
            for k, v in pt.ground.items():
                setattr(pt, k, v)
            pt.ground = None
        if y in pt.band:
            return pt.band_block
        ribbon = pt.corner_glass and len(ex) == 2 and ex[0][0] != -ex[1][0] and ex[0][1] != -ex[1][1]
        if (len(ex) != 1 and not ribbon) or y == pt.base or y == pt.deck:
            return pt.wall
        f = max(fl for fl in pt.floors if fl <= y)
        if y - f not in pt.rows:
            return pt.wall
        if ribbon and any(self.part.get((x + a, z + b)) is None and self.outside_ground(x + a, z + b) >= y - 1
                          for a, b in ex):
            return pt.wall
        dx, dz = ex[0]
        if pt.pier:
            a, b = pt.frame(x, z)
            fa, fb = pt.frame(x + dx, z + dz)
            along = a if abs(fb - b) > abs(fa - a) else b       # coordinate along the wall face
            if math.floor(along) % pt.pier == 0:
                return pt.wall
        if self.part.get((x + dx, z + dz)) is None and self.outside_ground(x + dx, z + dz) >= y - 1:
            return pt.wall
        return pt.glass

    # --- stair (switchback, spacing = floor height) --------------------------------------
    def stair(self):
        specs = self.stair_spec if isinstance(self.stair_spec, list) else [self.stair_spec] if self.stair_spec else []
        self.stairs_at = []
        for spec in specs:
            if len(next(p for p in self.parts if p.name == spec[0]).floors) < 2:
                continue                                   # single storey: no stair
            self.stair_at = None
            self._stair(*spec)
            if self.stair_at:
                self.stairs_at.append(self.stair_at)

    def _stair(self, pname, anchor):
        ax, az = anchor
        pt = next(p for p in self.parts if p.name == pname)
        fl = list(pt.floors)
        h = max(b - a for a, b in zip(fl, fl[1:]))
        for sx, sz in sorted((q for q, p in self.part.items() if p is pt),
                             key=lambda q: math.hypot(q[0] - ax, q[1] - az)):
            box = [(x, z) for x in range(sx - 1, sx + h + 1) for z in (sz, sz + 1)]
            if all(self.part.get(q) is pt and not self.exposed(q[0], q[1], pt.base + 1) for q in box):
                break
        else:
            if getattr(self, 'soft_stairs', False):
                self.no_stair = getattr(self, 'no_stair', []) + [pname]
                return
            raise SystemExit(f'no room for the stair in {pname}')
        self.stair_at = (sx, sz)
        for i, f in enumerate(fl[:-1]):
            g = fl[i + 1]
            n = g - f
            lane = sz if i % 2 == 0 else sz + 1
            xs = [sx + k for k in range(n)] if i % 2 == 0 else [sx + n - 1 - k for k in range(n)]
            face = 'east' if i % 2 == 0 else 'west'
            for k, x in enumerate(xs):
                self.set(x, f + 1 + k, lane, f'stone_brick_stairs[facing={face},half=bottom]')
                for y in range(f + 2 + k, f + 5 + k):
                    if y < g or self.p.get(x, y, lane) == f'minecraft:{pt.floor}':
                        self.set(x, y, lane, 'air')
            step = 1 if i % 2 == 0 else -1
            for x in [xs[0] - step] + xs:                      # headroom hole in the floor above
                if x != xs[-1]:
                    self.set(x, g, lane, 'air')

    # --- doors -----------------------------------------------------------------------------
    def doors(self):
        self.door_cells = []
        for pname, ax, az, f in self.door_specs:
            pts = [p for p in self.parts if pname is None or p.name == pname]
            best = None
            for (x, z), q in self.part.items():
                if q not in pts:
                    continue
                pt = q
                f = pt.base if pname is None else f
                ex = self.exposed(x, z, f + 1)
                if len(ex) != 1:
                    continue
                dx, dz = ex[0]
                if (x - dx, z - dz) not in self.part or self.exposed(x - dx, z - dz, f + 1):
                    continue
                if (x + dx, z + dz) in self.other:
                    continue
                d = math.hypot(x - ax, z - az)
                if best is None or d < best[0]:
                    best = (d, x, z, dx, dz, f)
            _, x, z, dx, dz, f = best
            face = FACING[(dx, dz)]
            self.set(x, f + 1, z, f'dark_oak_door[facing={face},half=lower,hinge=left,open=false]')
            self.set(x, f + 2, z, f'dark_oak_door[facing={face},half=upper,hinge=left,open=false]')
            self.set(x - dx, f + 1, z - dz, 'air')
            self.set(x - dx, f + 2, z - dz, 'air')
            self.door_cells.append((pname, x, f + 1, z, face))
            prev = f
            for k in range(1, 6):
                ax2, az2 = x + dx * k, z + dz * k
                if (ax2, az2) in self.part or (ax2, az2) in self.other:
                    break
                g = self.outside_ground(ax2, az2)
                if self.step_down_stairs:                  # meet the real terrain, not just the median
                    g = max(g, self.terrain(ax2, az2))
                s = f if k == 1 else (prev + 1 if g > prev else prev - 1 if g < prev else g)
                for side in (-1, 0, 1):
                    bx, bz = ax2 + (dz * side if dz else 0), az2 + (dx * side if dx else 0)
                    if (bx, bz) in self.part or (bx, bz) in self.other or (bx, bz) in self.built:
                        continue
                    for y in range(min(s, g) - 1, s):
                        self.set(bx, y, bz, 'stone')
                    self.set(bx, s, bz, f'stone_brick_stairs[facing={FACING[(-dx, -dz)]},half=bottom]'
                             if s > prev else 'polished_andesite')
                    for y in range(s + 1, max(g, s) + 3):
                        self.set(bx, y, bz, 'air')
                    if self.step_down_stairs and k > 1 and s < prev:   # walk back up: stair on the upper step
                        self.set(bx - dx, prev, bz - dz, f'stone_brick_stairs[facing={FACING[(-dx, -dz)]},half=bottom]')
                if s == g:
                    break
                prev = s

    # --- envelope: clear the old Geocraft block + fringe around the new shell ---------------
    def envelope(self, ring=3):
        cs = set(self.part)
        env = {(x + dx, z + dz) for x, z in cs for dx in range(-ring, ring + 1) for dz in range(-ring, ring + 1)} - cs
        old = {q for q, i in self.idx.cells().items() if oid(self.idx.buildings[i][1]) in self.ways}
        env |= {(x + dx, z + dz) for x, z in old - cs for dx in range(-2, 3) for dz in range(-2, 3)} - cs
        for x, z in env:
            if (x, z) in self.other or (x, z) in self.built or self.idx.near_footprint(x, z, 1) and \
                    any((x + dx, z + dz) in self.other for dx in (-1, 0, 1) for dz in (-1, 0, 1)):
                continue
            t = self.terrain(x, z)
            g = self.outside_ground(x, z)
            if self.max_fill is not None:
                g = min(g, t + self.max_fill)
                if self.keep_water:
                    # beside pristine water the ground stays at least as high as its surface (the
                    # old Geocraft block may have been the pond's bank)
                    wn = [y for a in (-1, 0, 1) for b in (-1, 0, 1) if (a, b) != (0, 0)
                          for y in range(t - 4, t + 4) if is_water(self.pw.block(x + a, y, z + b))]
                    if wn and not is_water(self.pw.block(x, max(wn), z)):
                        g = max(g, max(wn))
                if (x, z) not in old:
                    g = max(g, t)       # natural ground (banks, slopes) is never cut below pristine
                # put back pristine solid ground up to g that an earlier apply removed (water/air now)
                for y in range(t - 14, min(t, g) + 1):
                    pb = self.pw.block(x, y, z) or ''
                    lb = (self.w.block(x, y, z) or 'minecraft:air').split('[')[0]
                    if pb and pb.split('[')[0] not in ('minecraft:air', 'minecraft:water') \
                            and not any(k in pb for k in SKIP_TOP) \
                            and lb in ('minecraft:air', 'minecraft:water') and (x, y, z) not in self.p.cells:
                        self.set(x, y, z, pb.split(':', 1)[1])
            for y in range(min(t, g) + 1, g + 1):
                if (x, y, z) not in self.p.cells:
                    self.set(x, y, z, 'stone')
            if (x, g, z) not in self.p.cells:
                b = self.w.block(x, g, z) or ''
                if 'bricks' in b or 'carpet' in b:
                    self.set(x, g, z, 'gray_terracotta')
            for y in range(g + 1, self.clear_to + 1):
                b = self.w.block(x, y, z) or 'minecraft:air'
                if (x, y, z) in self.p.cells or any(k in b for k in KEEP):
                    continue
                self.set(x, y, z, 'air')
            if self.keep_water and (x, z) not in self.part:  # streams/ponds: pristine column exactly
                ys = range(min(t, g) - 2, max(t, g) + 12)
                col = {y: self.pw.block(x, y, z) or 'minecraft:air' for y in ys}
                if any(is_water(b) for b in col.values()):
                    for y, pb in col.items():
                        self.set(x, y, z, pb.split(':', 1)[1])

    # --- lighting: invisible light blocks under each ceiling (no lamps in slabs or roofs) ---
    def lights(self, grid=7):
        """Hang ``pt.light`` (default invisible ``light[level=15]``) one block under every
        ceiling — the next floor slab, or the deck for the top storey — on a ``grid``-block
        lattice of interior cells. Only cells the plan leaves as air are used, so walls,
        stairs, doors and their headroom are never touched. Run after stair() and doors().

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
                    self.set(x, y, z, pt.light)
                    n += 1
        return n

    def build(self, extra=None):
        """Plan the whole building: shells, optional ``extra(self)`` hook, stair, doors,
        ceiling lights, then the cleared Geocraft envelope.

        @param extra: optional callable(campus) run after the shells (roof plant, flues, ...)
        @returns: the site_kit Plan
        """
        self.shells()
        if extra:
            extra(self)
        self.stair()
        self.doors()
        self.lights()
        self.envelope()
        return self.p


class RoofView:
    """Stand-in for Campus over an already built feature: roof tops come from the build's own cells file.

    Lets roof_greeblies() run as a follow-up step after the feature build (the full build cannot be re-planned once
    later builds stand beside it). ``part`` = the build's cells inside ``only``; ``deck`` = the topmost block it placed
    there (-999 elsewhere); edge cells carry the coping, so roof_greeblies skips them.
    """

    def __init__(self, name, only=None):
        from site_kit import OUT, _parse_cells_file
        adds, _air = _parse_cells_file(OUT / f'{name}-cells.json')
        top = {}
        for (x, y, z) in adds:
            if only is None or (x, z) in only:
                top[(x, z)] = max(top.get((x, z), -999), y)
        self.p = Plan(f'{name}-greeblies')
        self.part = {q: name for q in top}
        self._top = top

    def deck(self, x, z):
        return self._top.get((x, z), -999)

    def set(self, x, y, z, s):
        self.p.set(x, y, z, s)


def roof_greeblies(c, items):
    """Roof greeblies (plant blocks, vents, hatches, skylights, domes) placed after the shells, as part of the feature.

    Positions are measured off the Google sheet (google_aerial.py). Items, in this order of effect:
      ('plinth', poly, h, block)   raised pale roof block, h above the deck, over cells inside poly
      ('vent', x, z[, block])      round vent / roof light: one block (default white) on the roof (or plinth)
      ('patch', poly, block, lvl)  area of one block: lvl 0 recolours the roof surface, lvl 1 stands on it (solar panels);
                                   edge (coping) cells are never touched
      ('line', [(x, z), ...], block, lvl)  1-wide run (seam, duct) along the points, same levels as patch
      ('hatch', x, z)              access hatch: flat iron trapdoor
      ('louvre', poly)                louvred plant vent (user: these are vents, not skylights): flat iron trapdoors on the roof
      ('dome', x, z)               2x2 round rooflight: glass over quartz slabs
      ('fan', x, z)                extract fan / plant unit: one gray block
    Only cells of the build's own parts are touched; a position off the roof is skipped and counted.

    @param c: Campus (after shells)
    @param items: list of tuples as above
    @returns: {'placed': n, 'skipped': n}
    """
    top, n_ok, n_skip = {}, 0, 0

    def y_of(x, z):
        return c.deck(x, z) + 1 + top.get((x, z), 0)

    def ok(x, z):
        return (x, z) in c.part and c.deck(x, z) > -999

    def edge(x, z):
        return any(c.deck(x + dx, z + dz) < c.deck(x, z) for dx, dz in N4)

    for it in (i for i in items if i[0] == 'plinth'):
        _, poly, h, blk = it
        xs, zs = [q[0] for q in poly], [q[1] for q in poly]
        for x in range(min(xs), max(xs) + 1):
            for z in range(min(zs), max(zs) + 1):
                if ok(x, z) and not edge(x, z) and inside(x + 0.5, z + 0.5, poly):
                    for k in range(h):
                        c.set(x, c.deck(x, z) + 1 + k, z, blk)
                    top[(x, z)] = h
                    n_ok += 1
    def cells_of(it):
        if it[0] == 'patch':
            poly = it[1]
            xs, zs = [q[0] for q in poly], [q[1] for q in poly]
            return [(x, z) for x in range(min(xs), max(xs) + 1) for z in range(min(zs), max(zs) + 1)
                    if inside(x + 0.5, z + 0.5, poly)]
        out = []
        for (ax, az), (bx, bz) in zip(it[1], it[1][1:]):
            n = max(abs(bx - ax), abs(bz - az), 1)
            out += [(round(ax + (bx - ax) * i / n), round(az + (bz - az) * i / n)) for i in range(n + 1)]
        return out

    for it in items:
        kind = it[0]
        if kind == 'plinth':
            continue
        if kind in ('patch', 'line'):
            blk, lvl = it[2], it[3]
            cells = [q for q in cells_of(it) if ok(*q) and not edge(*q)]
            for x, z in cells:
                c.set(x, c.deck(x, z) + lvl if lvl == 0 else y_of(x, z), z, blk)
                if lvl:
                    top[(x, z)] = top.get((x, z), 0) + 1
            n_ok += bool(cells)
            n_skip += not cells
            continue
        if kind == 'louvre':
            poly = it[1]
            xs, zs = [q[0] for q in poly], [q[1] for q in poly]
            cells = [(x, z) for x in range(min(xs), max(xs) + 1) for z in range(min(zs), max(zs) + 1)
                     if inside(x + 0.5, z + 0.5, poly) and ok(x, z)]
            for x, z in cells:
                c.set(x, y_of(x, z), z, 'iron_trapdoor[facing=north,half=bottom,open=false]')
            n_ok += bool(cells)
            n_skip += not cells
            continue
        x, z = it[1], it[2]
        cells = [(x + a, z + b) for a in (0, 1) for b in (0, 1)] if kind == 'dome' else [(x, z)]
        if not all(ok(*q) for q in cells):
            n_skip += 1
            continue
        for qx, qz in cells:
            y = y_of(qx, qz)
            if kind == 'vent':
                c.set(qx, y, qz, it[3] if len(it) > 3 else 'white_concrete')
            elif kind == 'hatch':
                c.set(qx, y, qz, 'iron_trapdoor[facing=north,half=bottom,open=false]')
            elif kind == 'fan':
                c.set(qx, y, qz, 'gray_concrete')
            elif kind == 'dome':
                c.set(qx, y, qz, 'smooth_quartz_slab[type=bottom]')
        n_ok += 1
    return {'placed': n_ok, 'skipped': n_skip}


# --- OSM footprint + LIDAR bands → Parts (campus-wide pass, Q-027+) ---------------------------
_IDX, _PW = None, None
SKIP_TOP = ('air', 'leaves', '_log', 'vine', 'short_grass', 'tall_grass', 'fern', 'flower')


def _shared():
    global _IDX, _PW
    if _IDX is None:
        _IDX = OSMIndex()
        _PW = World(PRISTINE) if PRISTINE and Path(PRISTINE).exists() else World()
    return _IDX, _PW


def way_cells(way):
    idx, _ = _shared()
    ids = {i for i, (_r, p) in enumerate(idx.buildings) if oid(p) == str(way)}
    return {q for q, i in idx.cells().items() if i in ids}


def lidar_top(x, z, ymax=120, ymin=30):
    _, pw = _shared()
    y = ymax
    while y > ymin:
        b = pw.block(x, y, z) or 'minecraft:air'
        if not any(s in b for s in SKIP_TOP):
            return y
        y -= 1
    return y


def _fill_pockets(cells, solid, band, side):
    """{cell: band} for footprint cells outside `solid` that sit in no side x side clear square
    of open footprint cells, each taking the band of the nearest solid cell (BFS over 8-neighbours)."""
    openc = cells - solid
    keep = set()
    for x0, z0 in openc:
        sq = [(x0 + i, z0 + j) for i in range(side) for j in range(side)]
        if all(q in openc for q in sq):
            keep.update(sq)
    fill = openc - keep
    out, frontier = {}, dict(band)
    while fill and frontier:
        nxt = {}
        for (x, z), b in frontier.items():
            for dx in (-1, 0, 1):
                for dz in (-1, 0, 1):
                    q = (x + dx, z + dz)
                    if q in fill and q not in out and q not in nxt:
                        nxt[q] = b
        out.update(nxt)
        fill -= set(nxt)
        frontier = nxt
    return out


def lidar_parts(way, prefix=None, base=None, merge=1, min_cells=10, open_below=2, storey=3,
                parapet=1, only=None, fill_pockets=0, **style):
    """Parts for one OSM way from its pristine LIDAR roof bands.

    Cells of the OSM footprint whose LIDAR top is within `open_below` of ground are open
    (courtyards / light wells) and left out. Remaining tops are grouped into bands (values
    within `merge` of each other), smoothed with a 3x3 majority filter, and components under
    `min_cells` fold into their commonest neighbour. `fill_pockets` = side of the smallest square
    (e.g. 7) a footprint hole must contain to count as a real courtyard; speckled/thin open
    cells (LIDAR noise on low wings) that cannot hold one are filled with the nearest band. Each band becomes one Part with
    deck = band top, floors every `storey` from `base` (ground: median terrain 3 out from the
    footprint), coping `parapet` above the deck. `only` = optional cell set to restrict to.
    Returns (parts, info) — info carries ground, bands and open cells for the docstring/notes."""
    prefix = prefix or f'w{way}'
    cells = way_cells(way)
    if only is not None:
        cells &= set(only)
    top = {q: lidar_top(*q) for q in cells}
    idx, _ = _shared()
    allc = idx.cells()
    edge = []
    for x, z in cells:
        for dx, dz in ((3, 0), (-3, 0), (0, 3), (0, -3)):
            q = (x + dx, z + dz)
            if q not in allc:
                edge.append(lidar_top(*q))
    g = base if base is not None else sorted(edge)[len(edge) // 2]
    solid = {q for q, y in top.items() if y > g + open_below}
    hist = {}
    for q in solid:
        hist[top[q]] = hist.get(top[q], 0) + 1
    # peaks: values that are the max of the histogram within +-(merge+1) and >= 6% of the cells
    peaks = sorted(v for v in hist if hist[v] >= 0.06 * len(solid)
                   and all(hist[v] >= hist.get(v + k, 0) for k in range(-merge - 1, merge + 2)))
    if not peaks:
        peaks = [max(hist, key=hist.get)]
    band = {q: min(peaks, key=lambda pk: (abs(pk - top[q]), -pk)) for q in solid}
    if fill_pockets:
        band.update(_fill_pockets(cells, solid, band, fill_pockets))
    for _ in range(2):
        nb = {}
        for (x, z), b in band.items():
            c = {}
            for dx in (-1, 0, 1):
                for dz in (-1, 0, 1):
                    v = band.get((x + dx, z + dz))
                    if v is not None:
                        c[v] = c.get(v, 0) + 1
            best = max(c, key=lambda v: (c[v], v == b))
            nb[(x, z)] = best if c[best] >= 5 else b
        band = nb
    # fold tiny components
    changed = True
    while changed:
        changed = False
        seen = set()
        for q0 in list(band):
            if q0 in seen:
                continue
            comp, stack = [], [q0]
            seen.add(q0)
            while stack:
                x, z = stack.pop()
                comp.append((x, z))
                for dx, dz in N4:
                    n = (x + dx, z + dz)
                    if n not in seen and band.get(n) == band[q0]:
                        seen.add(n)
                        stack.append(n)
            if len(comp) < min_cells and len(set(band.values())) > 1:
                cs = set(comp)
                c = {}
                for x, z in comp:
                    for dx, dz in N4:
                        v = band.get((x + dx, z + dz))
                        if (x + dx, z + dz) not in cs and v is not None:
                            c[v] = c.get(v, 0) + 1
                if c:
                    v = max(c, key=c.get)
                    for q in comp:
                        band[q] = v
                    changed = True
    parts = []
    for deck in sorted(set(band.values()), reverse=True):
        cs = {q for q, b in band.items() if b == deck}
        d = max(deck, g + storey)
        floors = tuple(range(g, d - storey + 1, storey)) or (g,)
        parts.append(Part(f'{prefix}_{d}', g, d, d + parapet if parapet else None, floors,
                          frame=XZ, cells=cs, **style))
    info = dict(way=way, ground=g, bands={p.deck: len(p.cells) for p in parts},
                open=len(cells) - len(solid), cells=len(cells))
    return parts, info


def centre(part):
    xs = [x for x, _ in part.cells]
    zs = [z for _, z in part.cells]
    return round(sum(xs) / len(xs)), round(sum(zs) / len(zs))


def bbox(parts, pad=8):
    xs = [x for p in parts for x, _ in p.cells]
    zs = [z for p in parts for _, z in p.cells]
    return min(xs) - pad, min(zs) - pad, max(xs) + pad, max(zs) + pad


def aerial_rgb(cells, mosaic=None):
    """{(x, z): (r, g, b)} sampled from the z18 campus mosaic at each cell centre."""
    import re
    import subprocess
    from PIL import Image
    from osgb import to_osgb
    mosaic = mosaic or str(ROOT / 'reference/aerial/highfield-campus/mosaic-z18-8x8-centre-130055-87834.png')
    m = re.search(r'mosaic-z(\d+)-(\d+)x\d+-centre-(\d+)-(\d+)', mosaic)
    zz, h = int(m[1]), int(m[2]) // 2
    ox, oy = (int(m[3]) - h) * 256, (int(m[4]) - h) * 256
    img = Image.open(mosaic).convert('RGB')
    cells = list(cells)
    inp = ''.join('%f %f\n' % to_osgb(x + 0.5, z + 0.5) for x, z in cells)
    out = subprocess.run(['gdaltransform', '-s_srs', 'EPSG:27700', '-t_srs', 'EPSG:4326'], input=inp.encode(),
                         capture_output=True, check=True).stdout.decode().split('\n')
    res = {}
    n = 2 ** zz * 256
    for q, line in zip(cells, [l for l in out if l.strip()]):
        lon, lat = map(float, line.split()[:2])
        X = (lon + 180) / 360 * n - ox
        Y = (1 - math.log(math.tan(math.radians(lat)) + 1 / math.cos(math.radians(lat))) / math.pi) / 2 * n - oy
        if 0 <= X < img.width and 0 <= Y < img.height:
            res[q] = img.getpixel((int(X), int(Y)))
    return res


def tiled(rgb, loose=False):
    """Red-brown clay tile pitched roof colour in the aerial (loose: weathered brown tile)."""
    r, g, b = rgb
    if loose:
        return r > g + 12 and r > b + 15 and r > 80
    return r > g + 18 and r > b + 30 and r > 90


def pitched_part(name, cells, base, eaves=None, floors=None, storey=3, roof_fill='bricks',
                 roof_stair='brick_stairs', roof_ridge='brick_slab[type=bottom]', smooth=1, **style):
    """One Part with walls to `eaves` and a roof following the smoothed LIDAR surface above it.
    eaves default: 15th percentile of the LIDAR tops (the low edge of the roof)."""
    cells = set(cells)
    top = {q: lidar_top(*q) for q in cells}
    if eaves is None:
        v = sorted(top.values())
        eaves = v[len(v) * 15 // 100]
    rt = dict(top)
    for _ in range(smooth):
        nt = {}
        for (x, z) in cells:
            ns = sorted(rt[(x + a, z + b)] for a in (-1, 0, 1) for b in (-1, 0, 1) if (x + a, z + b) in rt)
            nt[(x, z)] = ns[len(ns) // 2]
        rt = nt
    rt = {q: max(eaves + 1, y) for q, y in rt.items()}
    floors = floors or tuple(range(base, eaves - storey + 1, storey)) or (base,)
    pt = Part(name, base, eaves, None, floors, frame=XZ, cells=cells, **style)
    pt.roof, pt.roof_fill, pt.roof_stair, pt.roof_ridge = rt, roof_fill, roof_stair, roof_ridge
    return pt


TILE = dict(roof_fill='granite', roof_stair='granite_stairs', roof_ridge='granite_slab[type=bottom]')
SLATE = dict(roof_fill='deepslate_tiles', roof_stair='deepslate_tile_stairs', roof_ridge='deepslate_tile_slab[type=bottom]')


def majority(cells, inside, rounds=2):
    """3x3 majority smoothing of a cell mask, limited to `inside`."""
    m = set(cells)
    for _ in range(rounds):
        m = {(x, z) for x, z in inside
             if sum((x + a, z + b) in m for a in (-1, 0, 1) for b in (-1, 0, 1)) >= 5}
    return m


def auto_parts(way, prefix, only=None, roof=TILE, min_tiled=30, loose=False, **style):
    """Parts for one OSM building: red-tile cells (aerial colour, smoothed, widened by 1) as a
    pitched part on the LIDAR surface; the rest as flat LIDAR bands. Returns (parts, info)."""
    cells = way_cells(way)
    if only is not None:
        cells &= set(only)
    rgb = aerial_rgb(cells)
    t = majority({q for q in cells if q in rgb and tiled(rgb[q], loose)}, cells)
    t = {(x + a, z + b) for x, z in t for a, b in N4 + ((0, 0),)} & cells
    parts = []
    rest = cells
    flat, info = [], {}
    if len(t) >= min_tiled:
        rest = cells - t
    if rest:
        flat, info = lidar_parts(way, prefix, only=rest, **style)
    if len(t) >= min_tiled:
        g = info.get('ground') if info else None
        if g is None:
            _, i2 = lidar_parts(way, prefix + '_tmp', only=cells, **style)
            g = i2['ground']
        parts.append(pitched_part(f'{prefix}_roof', t, g, **roof, **style))
        info['tiled'] = len(t)
    return parts + flat, info
