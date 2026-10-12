#!/usr/bin/env python3
"""Q-012: next Portswood Rd SW terrace bay + I-008 door clearance.

Evidence sequence matches Q-010: useful=yes KartaView 1471277657 typology
(2-storey red brick, door + window rhythm); EDGE pinned from Geocraft
eastmost building column at y26 with road/pavement immediately east
(not max-X across the carriageway).

Bay SW of terrace_facade_1b: MC X7068..7078 Z-5537..-5533.
Also clears I-008: oak_door at 7088,27,-5530 was blocked by diagonal hull
bricks at 7088,*,-5529 — open that street-side column at door height.

Street-only shell (depth ~2–3); no invented private interiors.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'scripts'))

from site_kit import Plan, apply, preview  # noqa: E402

NAME = 'portswood_x_broadlands_terrace_facade_2'
MODIFIES = (
    'portswood_x_broadlands_terrace_facade_1',
    'portswood_x_broadlands_terrace_facade_1b',
    'portswood_x_broadlands_streetscape_r0',
    'portswood_x_broadlands_streetscape_q013b',
)

# West Portswood frontage — surveyed y26 eastmost gray_terracotta/bricks
# before polished_diorite/smooth_stone/stone (2026-10-11).
EDGE = [
    (7068, -5537),
    (7071, -5536),
    (7073, -5535),
    (7076, -5534),
    (7078, -5533),
]

BRICK = 'minecraft:bricks'
PANE = 'minecraft:glass_pane'
AIR = 'minecraft:air'
DOOR_L = 'minecraft:oak_door[facing=east,half=lower,hinge=left,open=false]'
DOOR_U = 'minecraft:oak_door[facing=east,half=upper,hinge=left,open=false]'
STAIR_E = 'minecraft:brick_stairs[facing=east,half=bottom,shape=straight]'
STAIR_W = 'minecraft:brick_stairs[facing=west,half=bottom,shape=straight]'

Y_PLINTH = 25
Y_DOOR = 27
Y_EAVES = 35
Y_ROOF = 36

# I-008: door column on façade_1b — clear outer shell toward pavement (+Z).
I008_DOOR_XZ = (7088, -5530)


def build_plan() -> Plan:
    """Build continuous west street-hull for the next bay + I-008 air.

    @returns: Plan
    """
    plan = Plan(NAME)
    hull: set[tuple[int, int]] = set()
    face: dict[int, int] = {}

    for i, (ex, z) in enumerate(EDGE):
        face[z] = ex
        for x in (ex, ex - 1, ex - 2):
            hull.add((x, z))
        if i:
            px, _pz = EDGE[i - 1]
            for x in range(min(px, ex), max(px, ex) + 1):
                hull.add((x, z))
                hull.add((x - 1, z))

    roles = {
        EDGE[0][1]: 'wall',
        EDGE[1][1]: 'window',
        EDGE[2][1]: 'door',
        EDGE[3][1]: 'window',
        EDGE[4][1]: 'wall',
    }

    door_faces: list[tuple[int, int]] = []

    for x, z in sorted(hull):
        for y in range(Y_PLINTH, Y_ROOF + 1):
            plan.set(x, y, z, AIR)
        for y in range(Y_PLINTH, Y_EAVES + 1):
            plan.set(x, y, z, BRICK)

        fx = face.get(z)
        if fx is None:
            continue
        if x == fx:
            plan.set(x, Y_ROOF, z, STAIR_E)
            role = roles.get(z, 'wall')
            if role == 'door':
                plan.set(x, Y_DOOR, z, DOOR_L)
                plan.set(x, Y_DOOR + 1, z, DOOR_U)
                plan.set(x, 32, z, PANE)
                plan.set(x, 33, z, PANE)
                door_faces.append((x, z))
            elif role == 'window':
                plan.set(x, 28, z, PANE)
                plan.set(x, 29, z, PANE)
                plan.set(x, 32, z, PANE)
                plan.set(x, 33, z, PANE)
        elif x in (fx - 1, fx - 2):
            plan.set(x, Y_ROOF, z, STAIR_W)

    def clear_door_opening(dx: int, door_z: int) -> None:
        """Clear facing-axis (±X) and diagonal +Z so patrol/walk pass.

        Patrol flags solid on facing or opposite; diagonal hull fill on
        door_z+1 also bricks in the stoop (I-008).
        """
        for y in (Y_DOOR, Y_DOOR + 1):
            plan.set(dx + 1, y, door_z, AIR)
            plan.set(dx - 1, y, door_z, AIR)
            plan.set(dx, y, door_z + 1, AIR)

    for dx, dz in door_faces:
        clear_door_opening(dx, dz)

    # I-008: same clearance on façade_1b door (not in this bay's EDGE).
    clear_door_opening(I008_DOOR_XZ[0], I008_DOOR_XZ[1])

    return plan


def main() -> None:
    """CLI: preview / dry / apply modification.

    @returns: None
    """
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--apply', action='store_true')
    ap.add_argument('--dry', action='store_true')
    args = ap.parse_args()
    plan = build_plan()
    out = ROOT / 'verification/site' / f'{NAME}-preview.png'
    try:
        preview(plan, out)
        print('preview:', out)
    except Exception as e:
        print('preview skipped:', e)
    print(f'{NAME}: {len(plan.cells)} cells; bounds {plan.bounds()}')
    apply(plan, dry=not args.apply, modifies=MODIFIES)


if __name__ == '__main__':
    main()
