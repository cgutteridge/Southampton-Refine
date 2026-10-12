#!/usr/bin/env python3
"""Q-014: Broadlands Road nos. 20 + 22 — whole properties (pattern build).

Evidence
--------
- Street: kartaview-1471277657 (camera MC 7071,-5531) — 2-storey red brick
  semis/terrace, white window frames, dark pitched roofs, chimneys, tall
  trimmed front hedges, ground-floor bays (typology).
- Aerial: portswood-x-broadlands mosaic — grey/dark roofs, ridge roughly
  parallel to the street; rear gardens lawn + tree canopy; pale hardstanding
  just behind the rear wall (patio).
- Footprints: OSM ways 177978869 (#20) and 177978886 (#22); front walls at
  MC [7104,-5531] and [7099,-5533] (~12 blocks setback). LIDAR massing top
  ≈ y35 (Geocraft carpet); street ≈ y25; raised front garden stone ≈ y27.

Unit of work: house on all sides + floors/stair (no rooms) + front and back
garden. Walls on the OSM footprint only — no outside_footprint_ok.
"""
from __future__ import annotations

import argparse
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'scripts'))

from osm_footprints import OSMIndex, _addr  # noqa: E402
from site_kit import Plan, World, apply, bid, preview  # noqa: E402

NAME = 'broadlands_rd_20_22'
OSM_IDS = {'177978869': '20', '177978886': '22'}

# Heights from LIDAR / live Geocraft massing (carpet top ≈ y35).
Y_GARDEN = 27
Y_GF = 28
Y_FF = 32
Y_EAVES = 34
Y_RIDGE = 36
Y_CLEAR_TOP = 40

BRICK = 'minecraft:bricks'
BRICK_SLAB = 'minecraft:brick_slab[type=bottom]'
PANE = 'minecraft:glass_pane'
AIR = 'minecraft:air'
FLOOR = 'minecraft:oak_planks'
STAIR_UP = 'minecraft:oak_stairs[facing={facing},half=bottom,shape=straight]'
ROOF_STAIR = 'minecraft:stone_stairs[facing={facing},half=bottom,shape=straight]'
ROOF_SLAB = 'minecraft:stone_slab[type=bottom]'
CHIMNEY = 'minecraft:bricks'
HEDGE = 'minecraft:oak_leaves[persistent=true]'
GRASS = 'minecraft:grass_block'
DIRT_PATH = 'minecraft:dirt_path'
FENCE = 'minecraft:oak_fence'
GATE_S = 'minecraft:oak_fence_gate[facing=south,open=false,in_wall=false,powered=false]'
LOG = 'minecraft:oak_log[axis=y]'
LEAVES = 'minecraft:oak_leaves[persistent=true]'
PATIO = 'minecraft:smooth_stone'
SHED = 'minecraft:spruce_planks'


def _house_records(idx: OSMIndex) -> dict[str, dict]:
    """Load OSM footprint cells and front vectors for nos. 20 and 22.

    @param idx: loaded OSM index
    @returns: map housenumber -> {cells, rings, front, outward, along}
    """
    cells_map = idx.cells()
    out: dict[str, dict] = {}
    for i, (rings, props) in enumerate(idx.buildings):
        oid = props.get('osm_way_id') or props.get('osm_id')
        if oid not in OSM_IDS:
            continue
        num = OSM_IDS[oid]
        cells = {(x, z) for (x, z), bi in cells_map.items() if bi == i}
        # Front vertex = closest to own street centreline.
        cands = []
        for x, z in rings[0]:
            s = idx.nearest_street(x, z)
            if s:
                cands.append((s[0], (x, z), s[3]))
        dist, front, foot = min(cands, key=lambda t: t[0])
        outward = (foot[0] - front[0], foot[1] - front[1])
        ol = math.hypot(*outward) or 1.0
        outward = (outward[0] / ol, outward[1] / ol)
        # Along-street = perpendicular (keep right-handed with +Y up).
        along = (-outward[1], outward[0])
        out[num] = {
            'cells': cells,
            'rings': rings,
            'front': front,
            'outward': outward,
            'along': along,
            'setback': dist,
        }
    if set(out) != {'20', '22'}:
        raise SystemExit(f'expected houses 20 and 22, got {sorted(out)}')
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


def _door_facing(outward: tuple[float, float]) -> str:
    """Cardinal door facing toward the road.

    @param outward: unit vector house→street in XZ
    @returns: north/south/east/west
    """
    ox, oz = outward
    if abs(oz) >= abs(ox):
        return 'south' if oz > 0 else 'north'
    return 'east' if ox > 0 else 'west'


def _stair_facing_for_roof(toward_front: bool, outward: tuple[float, float]) -> str:
    """Roof stair facing (lower edge points downhill).

    @param toward_front: True if this slope faces the street
    @param outward: house→street unit vector
    @returns: facing string for stairs block
    """
    ox, oz = outward
    # Stair facing = direction the stair ascends away from… in MC, facing is
    # the direction of the lower-to-higher run (the face you walk up into).
    # For a pitch falling toward +outward, the stair faces −outward (up to ridge).
    if toward_front:
        dx, dz = -ox, -oz
    else:
        dx, dz = ox, oz
    if abs(dz) >= abs(dx):
        return 'south' if dz > 0 else 'north'
    return 'east' if dx > 0 else 'west'


def build_plan() -> Plan:
    """Plan whole properties for Broadlands Road 20 and 22.

    @returns: Plan ready for preview / apply
    """
    plan = Plan(NAME)
    idx = OSMIndex()
    world = World()
    houses = _house_records(idx)

    # Combined house cells for neighbour tests.
    all_house = set().union(*(h['cells'] for h in houses.values()))

    for num, h in houses.items():
        cells = h['cells']
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
        facing = _door_facing(h['outward'])

        # --- clear Geocraft carpet / hollow mass; keep solid undercroft ---
        for x, z in cells:
            # Air the walkable volume above GF; do not excavate the plinth.
            for y in range(Y_GF, Y_CLEAR_TOP + 1):
                plan.set(x, y, z, AIR)
            # Solid plinth under the GF floor (replace carpet/hollow leftovers).
            plan.set(x, Y_GF - 1, z, 'minecraft:stone')

        # --- floors ---
        for x, z in cells:
            plan.set(x, Y_GF, z, FLOOR)
            plan.set(x, Y_FF, z, FLOOR)

        # --- walls on perimeter ---
        for x, z in peri:
            for y in range(Y_GF + 1, Y_EAVES + 1):
                if y in (Y_FF,):
                    continue
                plan.set(x, y, z, BRICK)
            # Fill floor levels in wall line with brick (openings cut later).
            plan.set(x, Y_GF, z, BRICK)
            plan.set(x, Y_FF, z, BRICK)
            plan.set(x, Y_EAVES, z, BRICK)

        # Interior air between floors (walkable volume).
        for x, z in interior:
            for y in range(Y_GF + 1, Y_FF):
                plan.set(x, y, z, AIR)
            for y in range(Y_FF + 1, Y_EAVES + 1):
                plan.set(x, y, z, AIR)

        # --- openings: door + windows on every side ---
        # Front band: shallowest 30% of depth on perimeter.
        front_band = {c for c in peri if depth[c] <= d_min + 0.30 * (d_max - d_min)}
        back_band = {c for c in peri if depth[c] >= d_max - 0.30 * (d_max - d_min)}
        side_band = peri - front_band - back_band

        # Door on a front cell that already has a free street-side approach
        # (diagonal tips often have only one streetmost cell — don't hide the
        # door behind a second-row wall).
        step = {
            'south': (0, 1), 'north': (0, -1),
            'east': (1, 0), 'west': (-1, 0),
        }[facing]
        candidates = sorted(front_band, key=lambda c: (depth[c], abs(along[c] - a_mid)))
        door_cell = None
        for c in candidates:
            ox_, oz_ = c[0] + step[0], c[1] + step[1]
            if (ox_, oz_) not in cells:
                door_cell = c
                break
        if door_cell is None:
            door_cell = candidates[0]
        dx, dz = door_cell
        door_l = (f'minecraft:oak_door[facing={facing},half=lower,'
                  f'hinge=left,open=false]')
        door_u = (f'minecraft:oak_door[facing={facing},half=upper,'
                  f'hinge=left,open=false]')
        plan.set(dx, Y_GF + 1, dz, door_l)
        plan.set(dx, Y_GF + 2, dz, door_u)
        # FF window above door.
        plan.set(dx, Y_FF + 1, dz, PANE)
        plan.set(dx, Y_FF + 2, dz, PANE)
        # Clear one cell inside behind the door so the opening is enterable.
        ix, iz = dx - step[0], dz - step[1]
        if (ix, iz) in cells:
            plan.set(ix, Y_GF + 1, iz, AIR)
            plan.set(ix, Y_GF + 2, iz, AIR)
        # Approach corridor door → street: path + cleared air (cuts hedge).
        # First cell outside the door is a full stoop at GF so feet match the
        # doorway (path is y27 / feet 28; door stands on y28 brick / feet 29).
        ox_, oz_ = dx + step[0], dz + step[1]
        for i in range(10):
            if (ox_, oz_) in cells:
                break
            if i == 0:
                # Bottom slab stoop: walkable +1 from the path, level with the door.
                plan.set(ox_, Y_GF, oz_, BRICK_SLAB)
                plan.set(ox_, Y_GF + 1, oz_, AIR)
                plan.set(ox_, Y_GF + 2, oz_, AIR)
                plan.set(ox_, Y_GARDEN, oz_, 'minecraft:stone')
            else:
                plan.set(ox_, Y_GARDEN, oz_, DIRT_PATH)
                plan.set(ox_, Y_GARDEN + 1, oz_, AIR)
                plan.set(ox_, Y_GARDEN + 2, oz_, AIR)
                # Slab step where garden meets lower pavement (feet +1).
                surf = bid(world.block(
                    ox_ + step[0],
                    world.ground(ox_ + step[0], oz_ + step[1], top=120, bottom=0),
                    oz_ + step[1]))
                if surf in ('minecraft:polished_diorite', 'minecraft:smooth_stone',
                            'minecraft:gray_terracotta'):
                    plan.set(ox_, Y_GARDEN, oz_, 'minecraft:stone_slab[type=bottom]')
                    plan.set(ox_, Y_GARDEN + 1, oz_, AIR)
            ox_ += step[0]
            oz_ += step[1]

        def _windows(band: set[tuple[int, int]], skip: set[tuple[int, int]],
                     stride: int = 2) -> None:
            ordered = sorted(band, key=lambda c: along[c])
            for i, (x, z) in enumerate(ordered):
                if (x, z) in skip or i % stride != 0:
                    continue
                plan.set(x, Y_GF + 2, z, PANE)
                plan.set(x, Y_GF + 3, z, PANE)
                plan.set(x, Y_FF + 1, z, PANE)
                plan.set(x, Y_FF + 2, z, PANE)

        _windows(front_band, {door_cell}, stride=2)
        _windows(back_band, set(), stride=2)
        _windows(side_band, set(), stride=3)

        # Rear door so street→door→upstairs→back garden is walkable.
        rear_step = (-step[0], -step[1])
        rear_candidates = sorted(back_band, key=lambda c: (-depth[c], abs(along[c] - a_mid)))
        rear_door = None
        for c in rear_candidates:
            ox_, oz_ = c[0] + rear_step[0], c[1] + rear_step[1]
            if (ox_, oz_) not in cells:
                rear_door = c
                break
        if rear_door is None and rear_candidates:
            rear_door = rear_candidates[0]
        if rear_door:
            rx, rz = rear_door
            rear_facing = {
                'south': 'north', 'north': 'south',
                'east': 'west', 'west': 'east',
            }[facing]
            plan.set(rx, Y_GF + 1, rz,
                     f'minecraft:oak_door[facing={rear_facing},half=lower,hinge=left,open=false]')
            plan.set(rx, Y_GF + 2, rz,
                     f'minecraft:oak_door[facing={rear_facing},half=upper,hinge=left,open=false]')
            plan.set(rx, Y_FF + 1, rz, PANE)
            plan.set(rx, Y_FF + 2, rz, PANE)
            ix, iz = rx - rear_step[0], rz - rear_step[1]
            if (ix, iz) in cells:
                plan.set(ix, Y_GF + 1, iz, AIR)
                plan.set(ix, Y_GF + 2, iz, AIR)
            ox_, oz_ = rx + rear_step[0], rz + rear_step[1]
            plan.set(ox_, Y_GARDEN, oz_, PATIO)
            plan.set(ox_, Y_GARDEN + 1, oz_, AIR)
            plan.set(ox_, Y_GARDEN + 2, oz_, AIR)

        # --- ground-floor bay (1 block toward street, 3 wide) ---
        bay_cells = sorted(front_band, key=lambda c: along[c])
        # Pick three consecutive front cells around the third of the front
        # opposite the door if possible; else around centre.
        if len(bay_cells) >= 3:
            # Prefer the half of the front away from the door along-score.
            door_a = along[door_cell]
            if door_a <= a_mid:
                start = max(0, len(bay_cells) - 3)
            else:
                start = 0
            chosen = bay_cells[start:start + 3]
            ox, oz = h['outward']
            # Step one block toward the street from each front cell.
            for x, z in chosen:
                bx = x + (1 if ox >= 0.35 else -1 if ox <= -0.35 else 0)
                bz = z + (1 if oz >= 0.35 else -1 if oz <= -0.35 else 0)
                # Prefer pure cardinal step matching door facing.
                if facing == 'south':
                    bx, bz = x, z + 1
                elif facing == 'north':
                    bx, bz = x, z - 1
                elif facing == 'east':
                    bx, bz = x + 1, z
                else:
                    bx, bz = x - 1, z
                if (bx, bz) in all_house:
                    continue
                # Bay must stay near footprint (guard allows margin 1).
                plan.set(bx, Y_GF, bz, BRICK)
                for y in range(Y_GF + 1, Y_GF + 4):
                    plan.set(bx, y, bz, BRICK)
                plan.set(bx, Y_GF + 2, bz, PANE)
                plan.set(bx, Y_GF + 3, bz, PANE)
                plan.set(bx, Y_GF + 4, bz, BRICK_SLAB)
                # Open the main wall behind the bay into the room volume.
                if (x, z) != door_cell:
                    plan.set(x, Y_GF + 2, z, AIR)
                    plan.set(x, Y_GF + 3, z, AIR)

        # --- stair (one run, GF → FF) mid-house, climbing toward the street ---
        # 4 treads at y29..y32; top tread is level with the FF floor.
        if interior:
            # Start near mid-depth on the party-wall side so the run stays interior.
            stair_anchor = min(
                interior,
                key=lambda c: abs(depth[c] - (d_min + 0.55 * (d_max - d_min)))
                + 0.15 * abs(along[c] - a_mid))
            sx, sz = stair_anchor
            step_dir = {
                'south': (0, 1), 'north': (0, -1),
                'east': (1, 0), 'west': (-1, 0),
            }[facing]
            s_facing = facing
            # Ensure all 4 tread cells exist; nudge anchor back if needed.
            for _ in range(6):
                if all((sx + step_dir[0] * s, sz + step_dir[1] * s) in cells
                       for s in range(4)):
                    break
                sx -= step_dir[0]
                sz -= step_dir[1]
            for step in range(4):
                x = sx + step_dir[0] * step
                z = sz + step_dir[1] * step
                y = Y_GF + 1 + step  # 29..32
                plan.set(x, y, z, STAIR_UP.format(facing=s_facing))
                for hy in range(y + 1, min(y + 3, Y_EAVES + 1)):
                    plan.set(x, hy, z, AIR)
                # Keep a hole through the FF floor on the lower three treads;
                # the top tread at y32 is the landing (same feet Y as FF planks).
                if step < 3:
                    plan.set(x, Y_FF, z, AIR)

        # --- roof: ridge parallel to street at mid-depth; pitch front/back ---
        # Map depth → roof height. Ridge at d_mid, eaves at ends.
        for x, z in cells:
            d = depth[(x, z)]
            # Normalised distance from ridge (0 at ridge, 1 at front/back eaves).
            half = max(0.5, (d_max - d_min) / 2)
            t = abs(d - d_mid) / half
            # Height: ridge Y_RIDGE down to Y_EAVES.
            y_top = int(round(Y_RIDGE - t * (Y_RIDGE - Y_EAVES)))
            y_top = max(Y_EAVES, min(Y_RIDGE, y_top))
            toward_front = d < d_mid
            face = _stair_facing_for_roof(toward_front, h['outward'])
            # Clear above eaves then place roof shell.
            for y in range(Y_EAVES + 1, Y_CLEAR_TOP + 1):
                plan.set(x, y, z, AIR)
            if y_top == Y_RIDGE and t < 0.25:
                plan.set(x, Y_RIDGE, z, ROOF_SLAB)
            else:
                plan.set(x, y_top, z, ROOF_STAIR.format(facing=face))
            # Gable fill on side walls under the pitch.
            if (x, z) in peri and (x, z) in side_band:
                for y in range(Y_EAVES + 1, y_top):
                    plan.set(x, y, z, BRICK)

        # Chimney stack (plain massing) near the ridge, party-wall side.
        # #20 is NE of #22; put chimney toward the outer side.
        chim_a = a_max - 0.5 if num == '20' else a_min + 0.5
        chim = min(cells, key=lambda c: abs(depth[c] - d_mid) + abs(along[c] - chim_a))
        cx, cz = chim
        for y in range(Y_EAVES, Y_RIDGE + 2):
            plan.set(cx, y, cz, CHIMNEY)
            plan.set(cx, Y_RIDGE + 2, cz, BRICK_SLAB)

        # --- front garden ---
        _build_front_garden(plan, world, idx, cells, h, door_cell, facing)

        # --- back garden ---
        _build_back_garden(plan, world, idx, cells, h, num)

    return plan


def _build_front_garden(plan: Plan, world: World, idx: OSMIndex,
                        house: set[tuple[int, int]], h: dict,
                        door_cell: tuple[int, int], facing: str) -> None:
    """Boundary hedge, gate gap, path and lawn for one front garden.

    @param plan: mutating plan
    @param world: live world for surface grades
    @param idx: OSM index (front_zone)
    @param house: footprint cells
    @param h: house record
    @param door_cell: front door footprint cell
    @param facing: door facing
    """
    ox, oz = h['outward']
    # Gather front-garden candidates: front_zone near this house, not footprint.
    cx = sum(x for x, _ in house) / len(house)
    cz = sum(z for _, z in house) / len(house)
    garden = set()
    for dx in range(-10, 11):
        for dz in range(-10, 11):
            x, z = int(cx) + dx, int(cz) + dz
            if (x, z) in house:
                continue
            if not idx.front_zone(x, z):
                continue
            # Must be on the street side of this house (positive outward from rear).
            if ((x + 0.5 - h['front'][0]) * ox + (z + 0.5 - h['front'][1]) * oz) < -1:
                continue
            # Restrict to a strip in front of this house's along-range.
            a = ((x + 0.5 - h['front'][0]) * h['along'][0]
                 + (z + 0.5 - h['front'][1]) * h['along'][1])
            a_house = _along_score(house, h['along'], h['front'])
            if a < min(a_house.values()) - 1 or a > max(a_house.values()) + 1:
                continue
            garden.add((x, z))

    if not garden:
        return

    # Pavement-back edge: garden cells adjacent to non-garden / non-house toward street.
    STREET = {'gray_terracotta', 'smooth_stone', 'polished_diorite'}
    edge = set()
    for x, z in garden:
        y = world.ground(x, z, top=120, bottom=0)
        # Neighbour toward street
        nx = x + (1 if ox >= 0.35 else -1 if ox <= -0.35 else 0)
        nz = z + (1 if oz >= 0.35 else -1 if oz <= -0.35 else 0)
        if facing == 'south':
            nx, nz = x, z + 1
        elif facing == 'north':
            nx, nz = x, z - 1
        elif facing == 'east':
            nx, nz = x + 1, z
        else:
            nx, nz = x - 1, z
        nb = bid(world.block(nx, world.ground(nx, nz, top=120, bottom=0), nz)).replace('minecraft:', '')
        if nb in STREET or (nx, nz) not in garden:
            # Also require this cell itself not to be carriageway.
            here = bid(world.block(x, y, z)).replace('minecraft:', '')
            if here not in ('gray_terracotta',):
                edge.add((x, z))

    # Gate: edge cell closest to door projected outward.
    dx, dz = door_cell
    if facing == 'south':
        target = (dx, dz + 2)
    elif facing == 'north':
        target = (dx, dz - 2)
    elif facing == 'east':
        target = (dx + 2, dz)
    else:
        target = (dx - 2, dz)
    gate = min(edge, key=lambda c: (c[0] - target[0]) ** 2 + (c[1] - target[1]) ** 2) if edge else None

    for x, z in garden:
        # Lawn grade.
        plan.set(x, Y_GARDEN, z, GRASS)
        plan.set(x, Y_GARDEN + 1, z, AIR)
        plan.set(x, Y_GARDEN + 2, z, AIR)

    for x, z in edge:
        if gate and (x, z) == gate:
            # Gate gap (air) — walkable; fence_gate is solid to site_walk.
            plan.set(x, Y_GARDEN, z, DIRT_PATH)
            plan.set(x, Y_GARDEN + 1, z, AIR)
            plan.set(x, Y_GARDEN + 2, z, AIR)
            continue
        plan.set(x, Y_GARDEN, z, GRASS)
        plan.set(x, Y_GARDEN + 1, z, HEDGE)
        plan.set(x, Y_GARDEN + 2, z, HEDGE)

    # Path door → gate (Manhattan crawl).
    if gate:
        gx, gz = gate
        if facing == 'south':
            x, z = dx, dz + 1
        elif facing == 'north':
            x, z = dx, dz - 1
        elif facing == 'east':
            x, z = dx + 1, dz
        else:
            x, z = dx - 1, dz
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
    # Inward = into the plot (away from street).
    ix, iz = -ox, -oz
    depth = _depth_score(house, h['outward'], h['front'])
    along = _along_score(house, h['along'], h['front'])
    a_min, a_max = min(along.values()), max(along.values())
    d_max = max(depth.values())
    # Back garden depth from aerial (~18–22 blocks of lawn/trees behind ridge).
    BACK_DEPTH = 20
    # Side margins: continue party-wall strip (±1 beyond house along-range).
    cells = set()
    # Seed from rear perimeter walking inward on a grid in local axes.
    rear = [c for c in house if depth[c] >= d_max - 1.5]
    if not rear:
        rear = list(house)
    # Rasterise a parallelogram strip behind the house.
    for a_i in range(int(math.floor(a_min)) - 1, int(math.ceil(a_max)) + 2):
        for d_i in range(1, BACK_DEPTH + 1):
            # Approximate cell centre from front + along*a + inward*d
            # front is a float vertex; walk from house rear centroid.
            pass

    # Simpler: flood from rear neighbours away from street, bounded by along.
    from collections import deque
    q = deque()
    seen = set()
    for x, z in house:
        for dx, dz in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            nx, nz = x + dx, z + dz
            if (nx, nz) in house:
                continue
            # Must be on the back side (negative outward from front).
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
        if a < a_min - 1.5 or a > a_max + 1.5:
            continue
        if (x, z) in house:
            continue
        # Stop at other OSM footprints.
        # Skip other building footprints.
        if (x, z) in idx.cells() and (x, z) not in house:
            continue
        seen.add((x, z))
        cells.add((x, z))
        for dx, dz in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            q.append((x + dx, z + dz, dist + 1))

    if not cells:
        return

    # Fence on plot boundary (cells with neighbour outside the plot+house).
    owned = cells | house
    fence_line = {(x, z) for x, z in cells
                  if any((x + dx, z + dz) not in owned
                         for dx, dz in ((1, 0), (-1, 0), (0, 1), (0, -1)))}

    # Patio band: first ~3 blocks behind the rear wall (aerial pale hardstanding).
    def _inward(c):
        x, z = c
        return ((x + 0.5 - h['front'][0]) * ix + (z + 0.5 - h['front'][1]) * iz)

    rear_line = d_max + 0.5
    patio = {c for c in cells if rear_line <= _inward(c) <= rear_line + 3.5}

    # Tree spots: deeper dark canopy zone (approx every 5th cell near back).
    deep = {(x, z) for x, z in cells
            if ((x + 0.5 - h['front'][0]) * ix + (z + 0.5 - h['front'][1]) * iz) >= 12}

    for x, z in cells:
        y = Y_GARDEN
        # Match local grade: if live ground is lower, build up with dirt.
        g = world.ground(x, z, top=120, bottom=0)
        if g < Y_GARDEN:
            for yy in range(g + 1, Y_GARDEN):
                plan.set(x, yy, z, 'minecraft:dirt')
        if (x, z) in patio:
            plan.set(x, y, z, PATIO)
        else:
            plan.set(x, y, z, GRASS)
        # Clear junk above.
        for yy in range(y + 1, y + 6):
            plan.set(x, yy, z, AIR)

    for x, z in fence_line:
        plan.set(x, Y_GARDEN + 1, z, FENCE)
        plan.set(x, Y_GARDEN + 2, z, AIR)

    # One small shed per plot where aerial shows pale hardstanding near side/back.
    # Place in the back-left corner of each garden (outer side).
    if cells:
        target_a = a_max if num == '20' else a_min
        shed_c = max(cells, key=lambda c: (
            ((c[0] + 0.5 - h['front'][0]) * ix + (c[1] + 0.5 - h['front'][1]) * iz)
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

    # Trees in deep canopy (limit count).
    tree_cells = sorted(deep, key=lambda c: (c[0] + c[1]) % 7)[:3]
    for x, z in tree_cells:
        if (x, z) in fence_line:
            continue
        plan.set(x, Y_GARDEN, z, GRASS)
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
    if args.dry:
        apply(plan, dry=True)
    elif args.apply:
        apply(plan)


if __name__ == '__main__':
    main()
