"""Building entrances from the university portal register (reference/portals): one rule for every feature build.

The nearest straight stretch of the building's wall to the portal is the door: it faces out of the wall, sits at the height of
the ground outside, has a glass flank and a white jamb each side and a lintel, and a threshold block inside. Only the
building's own cells change (no landings, steps, paving or plants: those are the ground pass). Width follows the wall that is
really there: a double door needs 6 cells of straight wall, a single door 5, a narrow single 3.
"""
from __future__ import annotations

FACE = {(1, 0): 'east', (-1, 0): 'west', (0, 1): 'south', (0, -1): 'north'}
WALL, GLASS = 'white_concrete', 'glass'
MAX_AWAY = 9           # blocks: a portal further than this from any straight wall is off the mapped footprint
WIDTHS = {'wide': (-3, 4), 'double': (-2, 3), 'pair': (-1, 2), 'single': (-2, 2), 'narrow': (-1, 1)}   # k range along the wall, door cell is k = 0
GROUNDISH = ('air', 'cave_air', 'grass_block', 'dirt', 'coarse_dirt', 'podzol', 'gravel', 'sand', 'water', 'polished_granite',
             'polished_diorite', 'polished_andesite', 'gray_concrete', 'light_gray_concrete', 'stone', 'smooth_stone')


def top(world, x, z):
    """Highest solid, non-foliage block of a column (y).

    @param world: site_kit.World
    @param x: block X
    @param z: block Z
    @returns: y
    """
    for y in range(75, 45, -1):
        b = (world.block(x, y, z) or 'minecraft:air').split('[')[0][10:]
        if b not in ('air', 'cave_air', 'void_air') and 'leaves' not in b and 'log' not in b and 'trapdoor' not in b \
                and 'fern' not in b and 'grass' not in b.replace('grass_block', '') and 'flower' not in b:
            return y
    return 48


def wall_cell(cells, px, pz, width='single', world=None, facing=None):
    """Nearest straight stretch of wall to a point, of the width a door needs.

    Every cell of the stretch is in ``cells`` with open air outside the same way (and, with ``world``, a real wall block standing
    at door height: the OSM footprint can be bigger than what was built, and a door must not hang in a gap).

    @param cells: set of (x, z) cells of the building
    @param px: portal X
    @param pz: portal Z
    @param width: 'double' | 'pair' | 'single' | 'narrow' (WIDTHS) (WIDTHS)
    @param world: optional site_kit.World
    @param facing: optional (dx, dz): only walls facing this way (a front the references say)
    @returns: (x, z, dx, dz, distance squared) or None; (x, z) is the door cell (k = 0)
    """
    lo, hi = WIDTHS[width]
    best = None
    for (x, z) in cells:
        for dx, dz in FACE:
            if facing and (dx, dz) != tuple(facing):
                continue
            ax, az = abs(dz), abs(dx)
            run = [(x + k * ax, z + k * az) for k in range(lo, hi + 1)]
            if not all(c in cells and (c[0] + dx, c[1] + dz) not in cells for c in run):
                continue
            if world is not None and not all(
                    (world.block(c[0], top(world, c[0] + dx, c[1] + dz) + 1, c[1]) or 'minecraft:air').split('[')[0][10:]
                    not in GROUNDISH for c in run):
                continue
            d = (x - px) ** 2 + (z - pz) ** 2
            if best is None or d < best[4]:
                best = (x, z, dx, dz, d)
    return best


def door(plan, world, x, z, dx, dz, notes, width='single', y0=None, leaf='iron_door', frame=WALL, fascia=False):
    """A framed glazed door (or pair) at wall cell (x, z) facing (dx, dz).

    @param plan: Plan to add to
    @param world: site_kit.World (ground height outside)
    @param x: wall cell X (the door; a pair is cells k = 0 and 1)
    @param z: wall cell Z
    @param dx: outward X step
    @param dz: outward Z step
    @param notes: list the one-line description is appended to
    @param width: 'double' | 'pair' | 'single' | 'narrow' (WIDTHS)
    @param y0: door height override (default: ground outside + 1)
    @param frame: jamb/lintel block (black_concrete metal frames at the Union, gray_concrete at the Jubilee porch, bricks, white); glass flanks
                  only beside a metal/white frame, matching brick beside a brick one
    @param fascia: a white sign band one high over the lintel, as wide as the door frame (the Us. entrance, 40-A)
    @param leaf: door block: 'iron_door' (grey metal: the glazed metal-framed doors in the portal photos) or 'dark_oak_door'
    """
    face = FACE[(dx, dz)]
    y0 = y0 or top(world, x + dx, z + dz) + 1
    ax, az = abs(dz), abs(dx)
    lo, hi = WIDTHS[width]
    doors = tuple(range(-2, 4)) if width == 'wide' else (0, 1) if width in ('double', 'pair') else (0,)
    for k in range(lo, hi + 1):
        cx, cz = x + k * ax, z + k * az
        if k in doors and leaf is not None:
            hinge = 'right' if (width in ('double', 'pair', 'wide') and k % 2 == 1) else 'left'
            plan.set(cx, y0, cz, f'minecraft:{leaf}[facing={face},half=lower,hinge={hinge},open=false]')
            plan.set(cx, y0 + 1, cz, f'minecraft:{leaf}[facing={face},half=upper,hinge={hinge},open=false]')
            plan.set(cx - dx, y0 - 1, cz - dz, 'minecraft:smooth_stone')       # floor inside, level with the door
            for yy in (y0, y0 + 1):
                plan.set(cx - dx, yy, cz - dz, 'minecraft:air')
        elif k in doors:                                                        # an open passage: no leaf, floor level with outside
            plan.set(cx - dx, y0 - 1, cz - dz, 'minecraft:smooth_stone')
            for yy in (y0, y0 + 1):
                plan.set(cx, yy, cz, 'minecraft:air')
                plan.set(cx - dx, yy, cz - dz, 'minecraft:air')
        else:
            flank = GLASS if frame in (WALL, 'black_concrete', 'gray_concrete') else frame
            blk = frame if k in (lo, hi) else flank                             # jamb at the ends, flank inside it
            for yy in (y0, y0 + 1):
                plan.set(cx, yy, cz, blk)
        plan.set(cx, y0 + 2, cz, frame)                                         # lintel
    if fascia:
        for k in range(lo, hi + 1):
            plan.set(x + k * ax, y0 + 3, z + k * az, WALL)
    notes.append(f'{width} {leaf or "opening"}/{frame} at {x},{y0},{z} facing {face}, ground outside {y0 - 1}')


def entrances(plan, world, cells, found, notes, double=(), flat=(), style=None, check_walls=True, fascia=(), wide=(), facing=None):
    """Add a door for each portal.

    @param plan: Plan
    @param world: site_kit.World
    @param cells: set of (x, z) of the building
    @param found: {portal id: (x, z)}
    @param notes: list of report lines
    @param double: portal ids that are double doors (main entrances)
    @param flat: portal ids whose wall is made flush first (flatten) so a double door fits
    @param check_walls: require a real built wall at door height (default); False where the OSM footprint is what was built
                        (B42), so the result does not depend on the doors a previous run left in the world
    @param facing: optional (dx, dz) every door must face (the building's front, from the references)
    @param wide: ids of 6-wide entrances (a shop front's automatic doors), the wall made flush over 8 cells
    @param style: {portal id: (leaf, frame)}; default (iron_door, white_concrete). Chosen from the 800 px portal photos and
                  scripts/block_reference.py (iron_door light grey, dark_oak_door very dark brown; leaf None = open passage)
    """
    for pid, (px, pz) in found.items():
        if pid in flat or pid in wide:
            f = flatten(plan, world, cells, px, pz, notes, ks=range(-3, 5) if pid in wide else range(-2, 4), check_walls=check_walls, facing=facing)
            if f:
                lf, fr = (style or {}).get(pid, ('iron_door', WALL))
                door(plan, world, f[0], f[1], f[2], f[3], notes, 'wide' if pid in wide else 'double', leaf=lf, frame=fr, fascia=pid in fascia)
                continue
        order = ('double', 'pair', 'single', 'narrow') if pid in double else ('single', 'narrow')
        cands = [(wd, wall_cell(cells, px, pz, wd, world if check_walls else None, facing)) for wd in order]
        cands = [(wd, c) for wd, c in cands if c]
        if not cands:
            notes.append(f'{pid}: no straight wall near {px},{pz}: skipped')
            continue
        near = min(c[4] for _wd, c in cands)
        wd, c = next((wd, c) for wd, c in cands if c[4] <= near + 9)         # the widest door that is not much further away
        x, z, dx, dz, d = c
        if d > MAX_AWAY ** 2:
            notes.append(f'{pid}: portal {px},{pz}: nearest straight wall is {round(d ** 0.5)} blocks away (the portal is off the '
                         'mapped footprint): skipped')
            continue
        notes.append(f'{pid}: portal {px},{pz} -> wall {x},{z} {FACE[(dx, dz)]}, {round(d ** 0.5)} blocks away')
        lf, fr = (style or {}).get(pid, ('iron_door', WALL))
        door(plan, world, x, z, dx, dz, notes, wd, leaf=lf, frame=fr, fascia=pid in fascia)


def flatten(plan, world, cells, px, pz, notes, ks=range(-2, 4), check_walls=True, facing=None):
    """Make the wall flush along a 6-cell stretch near a portal so a double door fits.

    Takes the narrow straight wall nearest the portal for the direction, then for each column along the stretch finds its
    outermost wall cell and extends the shorter columns out to the outermost one by copying their wall blocks (the facade steps
    out by one or two cells at most; the building is never cut back). Returns the door cell on the new flush plane.

    @param plan: Plan to add the extension cells to
    @param world: site_kit.World
    @param cells: set of (x, z) of the building
    @param px: portal X
    @param pz: portal Z
    @param notes: report lines
    @param ks: stretch offsets along the wall
    @returns: (x, z, dx, dz) of the door cell on the flush plane, or None
    """
    w = wall_cell(cells, px, pz, 'narrow', world if check_walls else None, facing)
    if w is None or w[4] > MAX_AWAY ** 2:
        return None
    x, z, dx, dz, _d = w
    ax, az = abs(dz), abs(dx)
    edge = {}
    for k in ks:                                       # outermost building cell of each column, along the outward direction
        cx, cz = x + k * ax, z + k * az
        for step in range(-3, 4):
            q = (cx + dx * step, cz + dz * step)
            if q in cells and (q[0] + dx, q[1] + dz) not in cells:
                edge[k] = step
                break
        else:
            return None
    plane = max(edge.values())
    added = 0
    for k, e in edge.items():
        sx, sz = x + k * ax + dx * e, z + k * az + dz * e              # this column's wall cell
        ytop = max((y for y in range(48, 70) if (world.block(sx, y, sz) or 'minecraft:air').split('[')[0][10:] not in GROUNDISH
                    and 'air' not in (world.block(sx, y, sz) or 'air')), default=None)
        for step in range(e + 1, plane + 1):
            tx, tz = x + k * ax + dx * step, z + k * az + dz * step
            for y in range(top(world, tx + dx, tz + dz) + 1, (ytop or 60) + 1):
                plan.set(tx, y, tz, (world.block(sx, y, sz) or 'minecraft:bricks'))
            added += 1
    notes.append(f'flush wall: {added} cells added out to the plane {plane} along {FACE[(dx, dz)]} near {x},{z}')
    return x + dx * plane, z + dz * plane, dx, dz
