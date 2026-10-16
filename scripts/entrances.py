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
WIDTHS = {'double': (-2, 3), 'pair': (-1, 2), 'single': (-2, 2), 'narrow': (-1, 1)}   # k range along the wall, door cell is k = 0
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


def wall_cell(cells, px, pz, width='single', world=None):
    """Nearest straight stretch of wall to a point, of the width a door needs.

    Every cell of the stretch is in ``cells`` with open air outside the same way (and, with ``world``, a real wall block standing
    at door height: the OSM footprint can be bigger than what was built, and a door must not hang in a gap).

    @param cells: set of (x, z) cells of the building
    @param px: portal X
    @param pz: portal Z
    @param width: 'double' | 'pair' | 'single' | 'narrow' (WIDTHS) (WIDTHS)
    @param world: optional site_kit.World
    @returns: (x, z, dx, dz, distance squared) or None; (x, z) is the door cell (k = 0)
    """
    lo, hi = WIDTHS[width]
    best = None
    for (x, z) in cells:
        for dx, dz in FACE:
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


def door(plan, world, x, z, dx, dz, notes, width='single', y0=None):
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
    """
    face = FACE[(dx, dz)]
    y0 = y0 or top(world, x + dx, z + dz) + 1
    ax, az = abs(dz), abs(dx)
    lo, hi = WIDTHS[width]
    doors = (0, 1) if width in ('double', 'pair') else (0,)
    for k in range(lo, hi + 1):
        cx, cz = x + k * ax, z + k * az
        if k in doors:
            hinge = 'right' if (width in ('double', 'pair') and k == 1) else 'left'
            plan.set(cx, y0, cz, f'minecraft:dark_oak_door[facing={face},half=lower,hinge={hinge},open=false]')
            plan.set(cx, y0 + 1, cz, f'minecraft:dark_oak_door[facing={face},half=upper,hinge={hinge},open=false]')
            plan.set(cx - dx, y0 - 1, cz - dz, 'minecraft:smooth_stone')       # floor inside, level with the door
            for yy in (y0, y0 + 1):
                plan.set(cx - dx, yy, cz - dz, 'minecraft:air')
        else:
            blk = WALL if k in (lo, hi) else GLASS                              # jamb at the ends, glass flank inside it
            for yy in (y0, y0 + 1):
                plan.set(cx, yy, cz, blk)
        plan.set(cx, y0 + 2, cz, WALL)                                          # lintel
    notes.append(f'{width} door at {x},{y0},{z} facing {face}, ground outside {y0 - 1}')


def entrances(plan, world, cells, found, notes, double=()):
    """Add a door for each portal.

    @param plan: Plan
    @param world: site_kit.World
    @param cells: set of (x, z) of the building
    @param found: {portal id: (x, z)}
    @param notes: list of report lines
    @param double: portal ids that are double doors (main entrances)
    """
    for pid, (px, pz) in found.items():
        order = ('double', 'pair', 'single', 'narrow') if pid in double else ('single', 'narrow')
        cands = [(wd, wall_cell(cells, px, pz, wd, world)) for wd in order]
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
        door(plan, world, x, z, dx, dz, notes, wd)
