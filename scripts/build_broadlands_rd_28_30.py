#!/usr/bin/env python3
"""Q-017: Broadlands Road nos. 28 + 30 — whole properties (squared redo).

Evidence
--------
- Street: kartaview-1471277657 (camera MC ~7071,-5531) — 2-storey red brick,
  white frames, dark pitched roofs, chimneys, tall trimmed front hedges,
  ground-floor bay typology. Cream render on nearer #32 is hint for Q-018 only.
- Aerial: q017-aerial-28-30 — grey/dark roofs, ridge ≈ parallel to street;
  long back gardens with pale patio just behind rear wall, lawn, trees north.
- Footprints: OSM ways 177978867 (#28) and 177978885 (#30); fronts at
  MC [7080,-5541] and [7075,-5543] (~12.4 setback). LIDAR carpet top ≈ y35–36.

Redo (11 Oct evening): prior jagged OSM extrusion + stair/messy slab roofs
failed client view. This plan uses world-axis squared 5×11 footprints (within
OSM ±2 margin), Geocraft envelope clear, and a 1:2 stone-slab roof.

Also places rough sealed placeholders for nos. 32 + 34 (west, in the street
camera) so Geocraft ruin is not left beside the finished pair — Q-018 replaces
them with full properties.

Unit of work: house on all sides + floors/stair (no rooms) + front and back
garden. Walls on the squared plot only — no outside_footprint_ok.
"""
from __future__ import annotations

import argparse
import sys
from collections import deque
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'scripts'))

from osm_footprints import OSMIndex  # noqa: E402
from site_kit import Plan, World, apply, bid, preview  # noqa: E402

NAME = 'broadlands_rd_28_30'
OSM_IDS = {'177978867': '28', '177978885': '30'}
# Cleared + rough placeholders only (full rebuild is Q-018).
PLACEHOLDER_OSM = {'177978846': '32', '177978855': '34'}

# Squared world-axis footprints (craftsmanship: square the mass, not diamond-trace).
# Fronts match survey Z; party wall at x=7080|7081; all cells within OSM margin 2.
SQUARED = {
    '30': {'x0': 7076, 'x1': 7080, 'z0': -5553, 'z1': -5543},  # front z=-5543
    '28': {'x0': 7081, 'x1': 7085, 'z0': -5551, 'z1': -5541},  # front z=-5541
}
# Continue the terrace west — rough placeholders until Q-018.
PLACEHOLDER_SQUARED = {
    '32': {'x0': 7071, 'x1': 7075, 'z0': -5555, 'z1': -5545},  # front z=-5545
    '34': {'x0': 7066, 'x1': 7070, 'z0': -5556, 'z1': -5546},  # front z=-5546
}

# Heights from LIDAR / live Geocraft massing (carpet top ≈ y35).
Y_GARDEN = 27
Y_GF = 28
Y_FF = 32
Y_EAVES = 34
# Ceiling seals the living volume (FF headroom = y33–34). LIDAR carpet/ridge
# sits ≈ y35–36 — use a shallow sealed deck + slight ridge, not a tall 1:2
# ziggurat (reads as broken steps from the street camera).
Y_CEIL = 35
Y_DECK = 36
Y_RIDGE = 37
Y_CLEAR_TOP = 42
ROOF_UNDER = 'minecraft:stone'
ROOF_DECK = 'minecraft:stone'

BRICK = 'minecraft:bricks'
BRICK_SLAB = 'minecraft:brick_slab[type=bottom]'
PANE = 'minecraft:glass_pane'
AIR = 'minecraft:air'
FLOOR = 'minecraft:oak_planks'
STAIR_UP = 'minecraft:oak_stairs[facing={facing},half=bottom,shape=straight]'
# Shallow Southampton pitch: 1:2 slab courses (NOT stair 45°).
ROOF_SLAB_BOTTOM = 'minecraft:stone_slab[type=bottom]'
ROOF_SLAB_TOP = 'minecraft:stone_slab[type=top]'
CHIMNEY = 'minecraft:bricks'
GEOCRAFT_JUNK = (
    'light_gray_carpet', 'gray_carpet', 'white_carpet', 'black_carpet',
    'gray_wool', 'light_gray_wool', 'stone_stairs', 'cobblestone_stairs',
    'andesite_stairs', 'stone_slab', 'cobblestone_slab',
)
HEDGE = 'minecraft:oak_leaves[persistent=true]'
GRASS = 'minecraft:grass_block'
DIRT_PATH = 'minecraft:dirt_path'
FENCE = 'minecraft:oak_fence'
LOG = 'minecraft:oak_log[axis=y]'
LEAVES = 'minecraft:oak_leaves[persistent=true]'
PATIO = 'minecraft:smooth_stone'
SHED = 'minecraft:spruce_planks'


def _rect_cells(box: dict) -> set[tuple[int, int]]:
    """Fill an inclusive axis-aligned rectangle.

    @param box: x0,x1,z0,z1 inclusive
    @returns: cell set
    """
    return {(x, z)
            for x in range(box['x0'], box['x1'] + 1)
            for z in range(box['z0'], box['z1'] + 1)}


def _osm_cells(idx: OSMIndex, ids: dict[str, str] | None = None) -> dict[str, set[tuple[int, int]]]:
    """OSM raster cells for the given way-id → housenumber map.

    @param idx: loaded OSM index
    @param ids: osm way id -> housenumber (default: 28/30)
    @returns: housenumber -> cells
    """
    want = ids or OSM_IDS
    cells_map = idx.cells()
    out: dict[str, set[tuple[int, int]]] = {}
    for i, (_rings, props) in enumerate(idx.buildings):
        oid = props.get('osm_way_id') or props.get('osm_id')
        if oid not in want:
            continue
        out[want[oid]] = {(x, z) for (x, z), bi in cells_map.items() if bi == i}
    if set(out) != set(want.values()):
        raise SystemExit(f'expected OSM houses {sorted(want.values())}, got {sorted(out)}')
    return out


def _house_records(idx: OSMIndex) -> dict[str, dict]:
    """Squared house records with street vectors for gardens.

    @param idx: loaded OSM index
    @returns: map housenumber -> {cells, front, outward, along, setback, osm}
    """
    osm = _osm_cells(idx)
    out: dict[str, dict] = {}
    for num, box in SQUARED.items():
        cells = _rect_cells(box)
        # South face toward Broadlands Road; outward = +Z.
        front = ((box['x0'] + box['x1'] + 1) / 2.0, box['z1'] + 0.5)
        outward = (0.0, 1.0)
        along = (1.0, 0.0)
        s = idx.nearest_street(front[0], front[1])
        out[num] = {
            'cells': cells,
            'front': front,
            'outward': outward,
            'along': along,
            'setback': s[0] if s else 12.4,
            'osm': osm[num],
            'box': box,
        }
    return out


def _perimeter(cells: set[tuple[int, int]]) -> set[tuple[int, int]]:
    """Footprint cells with a 4-neighbour outside the house.

    @param cells: house footprint cells
    @returns: perimeter subset
    """
    return {(x, z) for x, z in cells
            if any((x + dx, z + dz) not in cells
                   for dx, dz in ((1, 0), (-1, 0), (0, 1), (0, -1)))}


def _depth_score(cells: set[tuple[int, int]], outward: tuple[float, float],
                 front: tuple[float, float]) -> dict[tuple[int, int], float]:
    """Signed depth from the front point along −outward (into the plot).

    @returns: cell -> depth (0 at front, larger toward the back)
    """
    ox, oz = outward
    fx, fz = front
    return {(x, z): -((x + 0.5 - fx) * ox + (z + 0.5 - fz) * oz)
            for x, z in cells}


def _along_score(cells: set[tuple[int, int]], along: tuple[float, float],
                 front: tuple[float, float]) -> dict[tuple[int, int], float]:
    """Coordinate along the street axis.

    @returns: cell -> along-street scalar
    """
    ax, az = along
    fx, fz = front
    return {(x, z): (x + 0.5 - fx) * ax + (z + 0.5 - fz) * az
            for x, z in cells}


def _is_corner(cells: set[tuple[int, int]], x: int, z: int) -> bool:
    """True if a perimeter cell is an outside corner (two open cardinals).

    @param cells: footprint
    @param x: cell x
    @param z: cell z
    @returns: whether the cell is a corner
    """
    open_n = sum((x + dx, z + dz) not in cells
                 for dx, dz in ((1, 0), (-1, 0), (0, 1), (0, -1)))
    return open_n >= 2


def _punch_window(plan: Plan, cells: set[tuple[int, int]], x: int, z: int,
                  y0: int, y1: int) -> None:
    """Punch a flanked glass opening; skip corners and unflanked cells.

    @param plan: mutating plan
    @param cells: footprint
    @param x: wall cell x
    @param z: wall cell z
    @param y0: lower pane y
    @param y1: upper pane y inclusive
    """
    if _is_corner(cells, x, z):
        return
    # Opaque flanks on the wall line (left/right along the longer run).
    flanks = []
    if (x - 1, z) in cells and (x + 1, z) in cells:
        flanks = [(x - 1, z), (x + 1, z)]
    elif (x, z - 1) in cells and (x, z + 1) in cells:
        flanks = [(x, z - 1), (x, z + 1)]
    else:
        return
    for fx, fz in flanks:
        for y in range(y0, y1 + 1):
            st = plan.cells.get((fx, y, fz), BRICK)
            if 'glass_pane' in st:
                return
    for y in range(y0, y1 + 1):
        plan.set(x, y, z, PANE)
    # Sill / head: keep brick below and above (already brick from wall fill).


def _place_slab_roof(plan: Plan, cells: set[tuple[int, int]], box: dict,
                     avoid: set[tuple[int, int]], chim_x: int) -> tuple[int, int]:
    """Shallow sealed roof: ceiling + continuous deck + slight ridge + eaves lip.

    Matches LIDAR massing (~y35–36). A tall 1:2 full-block under-fill reads as a
    broken ziggurat from the Broadlands street camera; a continuous deck does not.

    @param plan: mutating plan
    @param cells: footprint cells for this house
    @param box: squared x0,x1,z0,z1
    @param avoid: cells belonging to other houses (skip)
    @param chim_x: chimney X on the ridge
    @returns: (chim_x, ridge_z)
    """
    ridge_z = (box['z0'] + box['z1']) // 2
    peri = _perimeter(cells)

    roof_xz: set[tuple[int, int]] = set()
    for x in range(box['x0'] - 1, box['x1'] + 2):
        for z in range(box['z0'] - 1, box['z1'] + 2):
            if (x, z) in avoid:
                continue
            in_foot = (x, z) in cells
            eaves = (box['x0'] <= x <= box['x1']
                     and z in (box['z0'] - 1, box['z1'] + 1))
            gable = (box['z0'] <= z <= box['z1']
                     and x in (box['x0'] - 1, box['x1'] + 1))
            if in_foot or eaves or gable:
                roof_xz.add((x, z))

    for x, z in roof_xz:
        for y in range(Y_CEIL if (x, z) in cells else Y_EAVES, Y_CLEAR_TOP + 1):
            plan.set(x, y, z, AIR)

    for x, z in cells:
        if (x, z) in avoid:
            continue
        # Wall-plate brick on the shell; stone ceiling inside.
        plan.set(x, Y_CEIL, z, BRICK if (x, z) in peri else ROOF_UNDER)
        plan.set(x, Y_DECK, z, ROOF_DECK)

    for x, z in roof_xz:
        if (x, z) in cells:
            continue
        # Overhang: deck lip (bottom slab) — light eaves, still opaque from above.
        plan.set(x, Y_DECK, z, ROOF_SLAB_BOTTOM)

    # Shallow visible pitch on top of the sealed deck (2-step 1:2, ridge // street).
    # Deck stays opaque; these slabs are the only courses above it.
    for x, z in cells:
        if (x, z) in avoid:
            continue
        r = abs(z - ridge_z)
        if r == 0:
            plan.set(x, Y_DECK + 1, z, ROOF_SLAB_BOTTOM)
            plan.set(x, Y_DECK + 2, z, ROOF_SLAB_BOTTOM)
        elif r == 1:
            plan.set(x, Y_DECK + 1, z, ROOF_SLAB_TOP)
            plan.set(x, Y_DECK + 2, z, ROOF_SLAB_BOTTOM)
        elif r == 2:
            plan.set(x, Y_DECK + 1, z, ROOF_SLAB_BOTTOM)

    # Gable ends: brick only up to the ceiling plate — deck stays stone.
    for x in (box['x0'], box['x1']):
        for z in range(box['z0'], box['z1'] + 1):
            if (x, z) not in cells or (x, z) in avoid:
                continue
            for y in range(Y_EAVES, Y_CEIL + 1):
                plan.set(x, y, z, BRICK)
            plan.set(x, Y_DECK, z, ROOF_DECK)

    def _pitch_top(x: int, z: int) -> int:
        if (x, z) not in cells:
            return Y_DECK
        r = abs(z - ridge_z)
        if r == 0:
            return Y_DECK + 2
        if r <= 2:
            return Y_DECK + 1
        return Y_DECK

    for x, z in roof_xz:
        if (x, z) == (chim_x, ridge_z):
            continue
        for y in range(_pitch_top(x, z) + 1, Y_CLEAR_TOP + 1):
            plan.set(x, y, z, AIR)

    # Final assert — sealed deck + shallow pitch courses.
    for x, z in cells:
        if (x, z) in avoid:
            continue
        plan.set(x, Y_CEIL, z, BRICK if (x, z) in peri else ROOF_UNDER)
        # Deck is always stone — never brick on/above the roof plane (chimney only).
        plan.set(x, Y_DECK, z, ROOF_DECK)
        r = abs(z - ridge_z)
        if r == 0:
            plan.set(x, Y_DECK + 1, z, ROOF_SLAB_BOTTOM)
            plan.set(x, Y_DECK + 2, z, ROOF_SLAB_BOTTOM)
        elif r == 1:
            plan.set(x, Y_DECK + 1, z, ROOF_SLAB_TOP)
            plan.set(x, Y_DECK + 2, z, ROOF_SLAB_BOTTOM)
        elif r == 2:
            plan.set(x, Y_DECK + 1, z, ROOF_SLAB_BOTTOM)
    for x, z in roof_xz:
        if (x, z) in cells or (x, z) in avoid:
            continue
        plan.set(x, Y_DECK, z, ROOF_SLAB_BOTTOM)
    # Strip any brick above the deck except the chimney column.
    for x, z in cells:
        if (x, z) in avoid:
            continue
        for y in range(Y_DECK + 1, Y_CLEAR_TOP + 1):
            if (x, z) == (chim_x, ridge_z):
                continue
            st = plan.cells.get((x, y, z), AIR)
            if st == BRICK or st == CHIMNEY:
                plan.set(x, y, z, AIR)
    for y in range(Y_EAVES, Y_DECK + 3):
        plan.set(chim_x, y, ridge_z, CHIMNEY)
    plan.set(chim_x, Y_DECK + 3, ridge_z, BRICK_SLAB)
    return chim_x, ridge_z


def _build_placeholder_shell(plan: Plan, world: World, num: str, box: dict,
                             osm: set[tuple[int, int]],
                             avoid: set[tuple[int, int]]) -> None:
    """Rough sealed house + front grass strip (placeholder until a full queue item).

    @param plan: mutating plan
    @param world: live world
    @param num: housenumber label
    @param box: squared footprint
    @param osm: OSM cells for this house (cleared with the square)
    @param avoid: cells owned by finished neighbours — do not overwrite
    """
    cells = _rect_cells(box) - avoid
    if not cells:
        return
    peri = _perimeter(cells)
    interior = cells - peri
    door_x = (box['x0'] + box['x1']) // 2

    clear = set(cells) | set(osm)
    for x, z in list(clear):
        for dx in range(-2, 3):
            for dz in range(-2, 3):
                clear.add((x + dx, z + dz))
    for x, z in clear:
        if (x, z) in avoid:
            continue  # other houses (28/30/sibling placeholders)
        if (x, z) in cells:
            for y in range(Y_GF, Y_CLEAR_TOP + 1):
                plan.set(x, y, z, AIR)
            plan.set(x, Y_GF - 1, z, 'minecraft:stone')
            continue
        for y in range(Y_GARDEN + 1, Y_CLEAR_TOP + 1):
            if (x, y, z) in plan.cells and plan.cells[(x, y, z)] != AIR:
                continue  # keep already-planned neighbour solids
            live = bid(world.block(x, y, z)).replace('minecraft:', '').split('[')[0]
            if live.endswith('_carpet') or live in GEOCRAFT_JUNK or live == 'bricks' or (
                    live.endswith('_stairs') and not live.startswith('oak')):
                plan.set(x, y, z, AIR)

    for x, z in cells:
        plan.set(x, Y_GF, z, FLOOR)
        plan.set(x, Y_FF, z, FLOOR)
        plan.set(x, Y_CEIL, z, ROOF_UNDER)
    for x, z in peri:
        for y in range(Y_GF, Y_EAVES + 1):
            plan.set(x, y, z, BRICK)
    for x, z in interior:
        for y in range(Y_GF + 1, Y_FF):
            plan.set(x, y, z, AIR)
        for y in range(Y_FF + 1, Y_CEIL):
            plan.set(x, y, z, AIR)

    # Door + a few flanked windows.
    dz = box['z1']
    plan.set(door_x, Y_GF + 1, dz,
             'minecraft:oak_door[facing=south,half=lower,hinge=left,open=false]')
    plan.set(door_x, Y_GF + 2, dz,
             'minecraft:oak_door[facing=south,half=upper,hinge=left,open=false]')
    plan.set(door_x, Y_GF + 1, dz - 1, AIR)
    plan.set(door_x, Y_GF + 2, dz - 1, AIR)
    plan.set(door_x, Y_GF, dz + 1, BRICK_SLAB)
    for yy in range(Y_GF + 1, Y_EAVES + 1):
        plan.set(door_x, yy, dz + 1, AIR)
    for x, z in peri:
        if z != box['z1'] or x == door_x or _is_corner(cells, x, z):
            continue
        if (x - door_x) % 2 == 0:
            continue
        _punch_window(plan, cells, x, z, Y_GF + 2, Y_GF + 3)
        _punch_window(plan, cells, x, z, Y_FF + 1, Y_FF + 2)

    chim_x = box['x1'] if num == '32' else box['x0']
    _place_slab_roof(plan, cells, box, avoid, chim_x)

    # Front grass + hedge line (rough); clear grey Geocraft stone desert.
    STREET = {'gray_terracotta', 'smooth_stone', 'polished_diorite'}
    for x in range(box['x0'], box['x1'] + 1):
        for z in range(box['z1'] + 1, box['z1'] + 8):
            if (x, z) in avoid or (x, z) in cells:
                continue
            gy = world.ground(x, z, top=120, bottom=0)
            surf = bid(world.block(x, gy, z)).replace('minecraft:', '').split('[')[0]
            if surf in STREET:
                break
            plan.set(x, Y_GARDEN, z, GRASS)
            for yy in range(Y_GARDEN + 1, Y_EAVES + 1):
                plan.set(x, yy, z, AIR)
        # Hedge on the southmost garden cell before pavement.
        for z in range(box['z1'] + 7, box['z1'], -1):
            if plan.cells.get((x, Y_GARDEN, z)) == GRASS:
                plan.set(x, Y_GARDEN + 1, z, HEDGE)
                plan.set(x, Y_GARDEN + 2, z, HEDGE)
                break


def build_plan() -> Plan:
    """Plan whole properties for Broadlands Road 28 and 30.

    @returns: Plan ready for preview / apply
    """
    plan = Plan(NAME)
    idx = OSMIndex()
    world = World()
    houses = _house_records(idx)
    ph_osm = _osm_cells(idx, PLACEHOLDER_OSM)

    all_house = set().union(*(h['cells'] for h in houses.values()))
    all_osm = set().union(*(h['osm'] for h in houses.values()))
    ph_cells = set().union(*(_rect_cells(b) for b in PLACEHOLDER_SQUARED.values()))
    all_osm |= set().union(*ph_osm.values())
    chimneys: set[tuple[int, int]] = set()

    # Clear Geocraft / prior refine on squared footprints, OSM leftovers,
    # placeholder neighbours (32+34), and a dilated envelope.
    clear_xz = set(all_house) | set(all_osm) | set(ph_cells)
    for x, z in list(clear_xz):
        for dx in range(-3, 4):
            for dz in range(-3, 4):
                clear_xz.add((x + dx, z + dz))

    for x, z in clear_xz:
        if (x, z) in all_house:
            for y in range(Y_GF, Y_CLEAR_TOP + 1):
                plan.set(x, y, z, AIR)
            plan.set(x, Y_GF - 1, z, 'minecraft:stone')
            continue
        for y in range(Y_GARDEN + 1, Y_CLEAR_TOP + 1):
            live = bid(world.block(x, y, z)).replace('minecraft:', '').split('[')[0]
            junk = (live.endswith('_carpet') or live in GEOCRAFT_JUNK
                    or (live.endswith('_stairs') and not live.startswith('oak'))
                    or (live in ('stone', 'cobblestone', 'andesite', 'stone_bricks',
                                 'bricks') and y >= Y_EAVES))
            if junk or (y >= Y_EAVES and live not in ('air', 'cave_air')):
                if live.endswith('_leaves') or live.endswith('_fence') or live.endswith('_log'):
                    continue
                plan.set(x, y, z, AIR)

    for num, h in houses.items():
        cells = h['cells']
        box = h['box']
        peri = _perimeter(cells)
        interior = cells - peri
        depth = _depth_score(cells, h['outward'], h['front'])
        along = _along_score(cells, h['along'], h['front'])
        d_vals = list(depth.values())
        d_min, d_max = min(d_vals), max(d_vals)
        d_mid = (d_min + d_max) / 2
        a_vals = list(along.values())
        a_min, a_max = min(a_vals), max(a_vals)
        a_mid = (a_min + a_max) / 2
        facing = 'south'
        step = (0, 1)

        # --- floors ---
        for x, z in cells:
            plan.set(x, Y_GF, z, FLOOR)
            plan.set(x, Y_FF, z, FLOOR)

        # --- walls on perimeter (solid shell; openings punched later) ---
        for x, z in peri:
            plan.set(x, Y_GF, z, BRICK)
            for y in range(Y_GF + 1, Y_EAVES + 1):
                plan.set(x, y, z, BRICK)
            plan.set(x, Y_FF, z, BRICK)

        # Interior air between floors (walkable volume).
        for x, z in interior:
            for y in range(Y_GF + 1, Y_FF):
                plan.set(x, y, z, AIR)
            for y in range(Y_FF + 1, Y_EAVES + 1):
                plan.set(x, y, z, AIR)

        # Side bands for openings.
        front_band = {(x, z) for x, z in peri if z == box['z1']}
        back_band = {(x, z) for x, z in peri if z == box['z0']}
        side_band = peri - front_band - back_band

        # Door toward the outer end; bay toward the party wall.
        front_xs = sorted(x for x, _z in front_band)
        if num == '30':
            door_x = front_xs[1]          # near west outer
            bay_xs = front_xs[2:]         # toward party (east)
        else:
            door_x = front_xs[-2]         # near east outer
            bay_xs = front_xs[:-2]        # toward party (west)
        door_cell = (door_x, box['z1'])
        dx, dz = door_cell
        door_l = (f'minecraft:oak_door[facing={facing},half=lower,'
                  f'hinge=left,open=false]')
        door_u = (f'minecraft:oak_door[facing={facing},half=upper,'
                  f'hinge=left,open=false]')
        plan.set(dx, Y_GF + 1, dz, door_l)
        plan.set(dx, Y_GF + 2, dz, door_u)
        plan.set(dx, Y_FF + 1, dz, PANE)
        plan.set(dx, Y_FF + 2, dz, PANE)
        # Clear one cell inside behind the door.
        plan.set(dx, Y_GF + 1, dz - 1, AIR)
        plan.set(dx, Y_GF + 2, dz - 1, AIR)

        # Approach corridor door → street.
        STREET_SURF = ('minecraft:polished_diorite', 'minecraft:smooth_stone',
                       'minecraft:gray_terracotta')
        ox_, oz_ = dx, dz + 1
        for i in range(10):
            if (ox_, oz_) in cells:
                break
            live = bid(world.block(
                ox_, world.ground(ox_, oz_, top=120, bottom=0), oz_))
            if live in STREET_SURF and i > 0:
                break
            if i == 0:
                plan.set(ox_, Y_GF, oz_, BRICK_SLAB)
                plan.set(ox_, Y_GARDEN, oz_, 'minecraft:stone')
            else:
                plan.set(ox_, Y_GARDEN, oz_, DIRT_PATH)
                surf = bid(world.block(
                    ox_, world.ground(ox_, oz_ + 1, top=120, bottom=0), oz_ + 1))
                if surf in STREET_SURF:
                    plan.set(ox_, Y_GARDEN, oz_, 'minecraft:stone_slab[type=bottom]')
            # Full headroom on the approach (prior brick often hangs at y30+).
            for yy in range(Y_GARDEN + 1, Y_EAVES + 1):
                if i == 0 and yy == Y_GF:
                    continue  # keep stoop slab
                plan.set(ox_, yy, oz_, AIR)
            oz_ += 1

        # Windows — flanked, skip door / corners.
        for x, z in sorted(front_band):
            if (x, z) == door_cell or x in bay_xs:
                continue
            _punch_window(plan, cells, x, z, Y_GF + 2, Y_GF + 3)
            _punch_window(plan, cells, x, z, Y_FF + 1, Y_FF + 2)
        for i, (x, z) in enumerate(sorted(back_band)):
            if i % 2 != 0:
                continue
            _punch_window(plan, cells, x, z, Y_GF + 2, Y_GF + 3)
            _punch_window(plan, cells, x, z, Y_FF + 1, Y_FF + 2)
        for i, (x, z) in enumerate(sorted(side_band)):
            if i % 3 != 1:
                continue
            _punch_window(plan, cells, x, z, Y_GF + 2, Y_GF + 3)
            _punch_window(plan, cells, x, z, Y_FF + 1, Y_FF + 2)

        # Rear door (walkable street→door→stair→back).
        rear_xs = sorted(x for x, _z in back_band)
        rear_x = rear_xs[len(rear_xs) // 2]
        rear_door = (rear_x, box['z0'])
        rx, rz = rear_door
        plan.set(rx, Y_GF + 1, rz,
                 'minecraft:oak_door[facing=north,half=lower,hinge=left,open=false]')
        plan.set(rx, Y_GF + 2, rz,
                 'minecraft:oak_door[facing=north,half=upper,hinge=left,open=false]')
        plan.set(rx, Y_FF + 1, rz, PANE)
        plan.set(rx, Y_FF + 2, rz, PANE)
        plan.set(rx, Y_GF + 1, rz + 1, AIR)
        plan.set(rx, Y_GF + 2, rz + 1, AIR)
        plan.set(rx, Y_GARDEN, rz - 1, PATIO)
        plan.set(rx, Y_GARDEN + 1, rz - 1, AIR)
        plan.set(rx, Y_GARDEN + 2, rz - 1, AIR)

        # --- ground-floor bay (1 block south, structural, sealed) ---
        bay_mid = bay_xs[len(bay_xs[:3]) // 2] if bay_xs[:3] else None
        for x in bay_xs[:3]:
            bx, bz = x, box['z1'] + 1
            if (bx, bz) in all_house:
                continue
            plan.set(bx, Y_GF, bz, BRICK)
            for y in range(Y_GF + 1, Y_GF + 4):
                plan.set(bx, y, bz, BRICK)
            # Glass on every bay face (flanks are the end bay brick returns).
            plan.set(bx, Y_GF + 2, bz, PANE)
            plan.set(bx, Y_GF + 3, bz, PANE)
            plan.set(bx, Y_GF + 4, bz, BRICK_SLAB)
            # Main wall behind bay: glass, never air (air read as shell holes).
            if (x, box['z1']) != door_cell:
                plan.set(x, Y_GF + 2, box['z1'], PANE)
                plan.set(x, Y_GF + 3, box['z1'], PANE)

        # --- stair GF → FF (4 treads, climb south toward street) ---
        if interior:
            sx = box['x0'] + 2 if num == '30' else box['x1'] - 2
            sz = box['z0'] + 3
            for s in range(4):
                x, z = sx, sz + s
                if (x, z) not in cells:
                    continue
                y = Y_GF + 1 + s
                plan.set(x, y, z, STAIR_UP.format(facing='south'))
                for hy in range(y + 1, min(y + 3, Y_CEIL)):
                    plan.set(x, hy, z, AIR)
                if s < 3:
                    plan.set(x, Y_FF, z, AIR)

        # --- roof: shallow sealed deck (LIDAR ~y36) ---
        avoid_others = all_house - cells
        chim_x = box['x1'] if num == '30' else box['x0']
        cx, cz = _place_slab_roof(plan, cells, box, avoid_others, chim_x)
        chimneys.add((cx, cz))

        _build_front_garden(plan, world, idx, cells, h, door_cell)
        # Re-assert stoop after garden air-wipe (door + 1 toward street).
        sx_, sz_ = door_cell[0] + step[0], door_cell[1] + step[1]
        plan.set(sx_, Y_GARDEN, sz_, 'minecraft:stone')
        plan.set(sx_, Y_GF, sz_, BRICK_SLAB)
        for yy in range(Y_GF + 1, Y_EAVES + 1):
            plan.set(sx_, yy, sz_, AIR)
        _build_back_garden(plan, world, idx, cells, h, num)

    # Rough sealed placeholders for 32+34 (west) — do not leave Geocraft ruin
    # in the street view beside the finished pair. Q-018 replaces these.
    # Each placeholder must avoid every other house footprint or its dilated
    # clear will air the neighbour's walls (bug that hollowed #32).
    all_ph = set().union(*(_rect_cells(b) for b in PLACEHOLDER_SQUARED.values()))
    for num, box in PLACEHOLDER_SQUARED.items():
        mine = _rect_cells(box)
        _build_placeholder_shell(
            plan, world, num, box, ph_osm[num],
            avoid=all_house | (all_ph - mine))

    # Final strip: Geocraft carpet / stone stairs / stray brick pillars on our
    # plots + placeholder fringe — never carve unrelated house footprints.
    planned_solid = {(x, y, z) for (x, y, z), st in plan.cells.items() if st != AIR}
    our_xz = set(all_house) | set(all_osm) | set(clear_xz) | set(ph_cells)
    # Front-garden / approach band (stop before the public pavement line).
    STREET_SURF = {'gray_terracotta', 'smooth_stone', 'polished_diorite'}
    for x in range(7066, 7087):
        for z in range(-5546, -5532):
            gy = world.ground(x, z, top=120, bottom=0)
            surf = bid(world.block(x, gy, z)).replace('minecraft:', '').split('[')[0]
            if surf in STREET_SURF:
                continue
            our_xz.add((x, z))
    foreign = set(idx.cells()) - all_osm
    for x, z in our_xz:
        if (x, z) in foreign:
            continue
        for y in range(Y_GARDEN + 1, Y_CLEAR_TOP + 1):
            if (x, y, z) in planned_solid:
                continue
            live = bid(world.block(x, y, z)).replace('minecraft:', '').split('[')[0]
            junk = (
                live.endswith('_carpet')
                or live in GEOCRAFT_JUNK
                or (live.endswith('_stairs') and not live.startswith('oak'))
                or live in ('bricks', 'stone', 'cobblestone', 'andesite',
                            'stone_bricks', 'brick_slab', 'stone_slab')
            )
            if junk:
                plan.set(x, y, z, AIR)

    return plan


def _build_front_garden(plan: Plan, world: World, idx: OSMIndex,
                        house: set[tuple[int, int]], h: dict,
                        door_cell: tuple[int, int]) -> None:
    """Boundary hedge, gate gap, path and lawn for one front garden.

    @param plan: mutating plan
    @param world: live world for surface grades
    @param idx: OSM index (front_zone)
    @param house: footprint cells
    @param h: house record
    @param door_cell: front door footprint cell
    """
    ox, oz = h['outward']
    STREET = {'gray_terracotta', 'smooth_stone', 'polished_diorite'}
    GARDEN_OK = {'stone', 'grass_block', 'dirt', 'dirt_path', 'coarse_dirt',
                 'gravel', 'oak_leaves', 'spruce_leaves', 'birch_leaves'}
    cx = sum(x for x, _ in house) / len(house)
    cz = sum(z for _, z in house) / len(house)
    a_house = _along_score(house, h['along'], h['front'])
    a_lo, a_hi = min(a_house.values()), max(a_house.values())
    max_out = min(9.0, max(4.0, h['setback'] - 4.0))
    garden = set()
    for dx in range(-10, 11):
        for dz in range(-10, 11):
            x, z = int(cx) + dx, int(cz) + dz
            if (x, z) in house:
                continue
            out = ((x + 0.5 - h['front'][0]) * ox
                   + (z + 0.5 - h['front'][1]) * oz)
            if out < -0.5 or out > max_out:
                continue
            a = ((x + 0.5 - h['front'][0]) * h['along'][0]
                 + (z + 0.5 - h['front'][1]) * h['along'][1])
            if a < a_lo - 0.5 or a > a_hi + 0.5:
                continue
            y = world.ground(x, z, top=120, bottom=0)
            here = bid(world.block(x, y, z)).replace('minecraft:', '').split('[')[0]
            if here in STREET:
                continue
            if here not in GARDEN_OK and here not in ('air',):
                if not idx.front_zone(x, z):
                    continue
            garden.add((x, z))

    if not garden:
        return

    edge = set()
    for x, z in garden:
        nx, nz = x, z + 1
        nb = bid(world.block(nx, world.ground(nx, nz, top=120, bottom=0), nz)).replace(
            'minecraft:', '').split('[')[0]
        if nb in STREET or (nx, nz) not in garden:
            here = bid(world.block(x, world.ground(x, z, top=120, bottom=0), z)).replace(
                'minecraft:', '').split('[')[0]
            if here not in STREET:
                edge.add((x, z))

    dx, dz = door_cell
    target = (dx, dz + 2)
    gate = min(edge, key=lambda c: (c[0] - target[0]) ** 2 + (c[1] - target[1]) ** 2) if edge else None

    for x, z in garden:
        plan.set(x, Y_GARDEN, z, GRASS)
        # Clear leftover Geocraft / prior brick hanging over the path (blocks
        # the stoop step-up if headroom at y30 is solid).
        for yy in range(Y_GARDEN + 1, Y_EAVES + 1):
            plan.set(x, yy, z, AIR)

    for x, z in edge:
        if gate and (x, z) == gate:
            plan.set(x, Y_GARDEN, z, DIRT_PATH)
            for yy in range(Y_GARDEN + 1, Y_EAVES + 1):
                plan.set(x, yy, z, AIR)
            continue
        plan.set(x, Y_GARDEN, z, GRASS)
        plan.set(x, Y_GARDEN + 1, z, HEDGE)
        plan.set(x, Y_GARDEN + 2, z, HEDGE)
        for yy in range(Y_GARDEN + 3, Y_EAVES + 1):
            plan.set(x, yy, z, AIR)

    if gate:
        gx, gz = gate
        x, z = dx, dz + 1
        for _ in range(20):
            if (x, z) in garden or (x, z) == (gx, gz):
                plan.set(x, Y_GARDEN, z, DIRT_PATH)
                if (x, z) != (gx, gz):
                    plan.set(x, Y_GARDEN + 1, z, AIR)
                    plan.set(x, Y_GARDEN + 2, z, AIR)
            if (x, z) == (gx, gz):
                break
            if abs(gx - x) >= abs(gz - z):
                x += 0 if gx == x else (1 if gx > x else -1)
            else:
                z += 0 if gz == z else (1 if gz > z else -1)


def _build_back_garden(plan: Plan, world: World, idx: OSMIndex,
                       house: set[tuple[int, int]], h: dict, num: str) -> None:
    """Fences, lawn, patio, shed and trees for one back garden from aerial cues.

    @param plan: mutating plan
    @param world: live world
    @param idx: OSM index
    @param house: footprint cells
    @param h: house record
    @param num: housenumber label
    """
    ox, oz = h['outward']
    ix, iz = -ox, -oz
    depth = _depth_score(house, h['outward'], h['front'])
    along = _along_score(house, h['along'], h['front'])
    a_min, a_max = min(along.values()), max(along.values())
    d_max = max(depth.values())
    BACK_DEPTH = 20

    # Squared footprint sits inside the jagged OSM polygon — allow flood through
    # this house's own OSM leftovers, but stop at any other building footprint.
    osm_own = set(h.get('osm') or ())
    osm_other = set(idx.cells()) - osm_own

    q: deque[tuple[int, int, int]] = deque()
    seen: set[tuple[int, int]] = set()
    cells: set[tuple[int, int]] = set()
    for x, z in house:
        for dx, dz in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            nx, nz = x + dx, z + dz
            if (nx, nz) in house:
                continue
            if ((nx + 0.5 - h['front'][0]) * ox + (nz + 0.5 - h['front'][1]) * oz) > -0.5:
                continue
            if idx.front_zone(nx, nz):
                continue
            q.append((nx, nz, 1))
    while q:
        x, z, dist = q.popleft()
        if (x, z) in seen or dist > BACK_DEPTH:
            continue
        a = (x + 0.5 - h['front'][0]) * h['along'][0] + (z + 0.5 - h['front'][1]) * h['along'][1]
        if a < a_min - 0.5 or a > a_max + 0.5:
            continue
        out = ((x + 0.5 - h['front'][0]) * ox
               + (z + 0.5 - h['front'][1]) * oz)
        if out > -0.5:
            continue
        if (x, z) in house:
            continue
        if (x, z) in osm_other:
            continue
        seen.add((x, z))
        cells.add((x, z))
        for dx, dz in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            q.append((x + dx, z + dz, dist + 1))

    if not cells:
        return

    owned = cells | house
    fence_line = {(x, z) for x, z in cells
                  if any((x + dx, z + dz) not in owned
                         for dx, dz in ((1, 0), (-1, 0), (0, 1), (0, -1)))}

    def _inward(c: tuple[int, int]) -> float:
        x, z = c
        return ((x + 0.5 - h['front'][0]) * ix + (z + 0.5 - h['front'][1]) * iz)

    rear_line = d_max + 0.5
    patio = {c for c in cells if rear_line <= _inward(c) <= rear_line + 3.5}
    deep = {c for c in cells if _inward(c) >= 12}

    for x, z in cells:
        y = Y_GARDEN
        g = world.ground(x, z, top=120, bottom=0)
        if g < Y_GARDEN:
            for yy in range(g + 1, Y_GARDEN):
                plan.set(x, yy, z, 'minecraft:dirt')
        plan.set(x, y, z, PATIO if (x, z) in patio else GRASS)
        for yy in range(y + 1, y + 6):
            plan.set(x, yy, z, AIR)

    for x, z in fence_line:
        plan.set(x, Y_GARDEN + 1, z, FENCE)
        plan.set(x, Y_GARDEN + 2, z, AIR)

    if cells:
        target_a = a_max if num == '28' else a_min
        shed_c = max(cells, key=lambda c: (
            _inward(c)
            - abs((c[0] + 0.5 - h['front'][0]) * h['along'][0]
                  + (c[1] + 0.5 - h['front'][1]) * h['along'][1] - target_a)
        ))
        sx, sz = shed_c
        for dx in (0, 1):
            for dz in (0, 1):
                x, z = sx + dx, sz + dz
                if (x, z) not in cells:
                    continue
                plan.set(x, Y_GARDEN, z, PATIO)
                for yy in range(Y_GARDEN + 1, Y_GARDEN + 4):
                    plan.set(x, yy, z, SHED)
                plan.set(x, Y_GARDEN + 4, z, 'minecraft:spruce_slab[type=bottom]')

    tree_cells = sorted(deep, key=lambda c: (c[0] + c[1]) % 7)[:3]
    for x, z in tree_cells:
        if (x, z) in fence_line:
            continue
        plan.set(x, Y_GARDEN, z, 'minecraft:dirt')
        plan.set(x, Y_GARDEN + 1, z, LOG)
        plan.set(x, Y_GARDEN + 2, z, LOG)
        for dx in (-1, 0, 1):
            for dz in (-1, 0, 1):
                for dy in (3, 4):
                    plan.set(x + dx, Y_GARDEN + dy, z + dz, LEAVES)


def main() -> None:
    """CLI: preview by default; ``--apply`` writes the live world.

    @returns: None
    """
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--apply', action='store_true', help='write live world (needs SITE_OWNER lock)')
    ap.add_argument('--dry', action='store_true', help='plan + clash/footprint check only')
    args = ap.parse_args()
    plan = build_plan()
    out = ROOT / 'verification/site' / f'{NAME}-preview.png'
    preview(plan, out)
    print(plan.summary())
    print('preview:', out)
    modifies = (
        'broadlands_rd_28_30', 'broadlands_rd_28_30_b', 'broadlands_rd_24_26',
        'broadlands_facade_revert',
        # I-009 pavement-façade leftovers still claimed in front of 28+30.
        'portswood_x_broadlands_terrace_facade_1',
        'portswood_x_broadlands_terrace_facade_1b',
        'portswood_x_broadlands_terrace_facade_2',
        'portswood_x_broadlands_terrace_facade_2b',
        'portswood_x_broadlands_terrace_facade_2c',
    )
    if args.dry:
        apply(plan, dry=True, modifies=modifies)
    elif args.apply:
        apply(plan, modifies=modifies)


if __name__ == '__main__':
    main()
