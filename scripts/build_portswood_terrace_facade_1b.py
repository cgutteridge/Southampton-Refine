#!/usr/bin/env python3
"""Q-010 mod: close diagonal gaps + fix door/kerb clash on terrace façade_1.

Modifies portswood_x_broadlands_terrace_facade_1 and the r0 kerb cells that
sat on the west street-edge columns (smooth_stone at y26 through the façade).
Uses the surveyed west EDGE polyline (not max-X across the road).
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'scripts'))

from site_kit import Plan, apply, preview  # noqa: E402

NAME = 'portswood_x_broadlands_terrace_facade_1b'
MODIFIES = (
    'portswood_x_broadlands_terrace_facade_1',
    'portswood_x_broadlands_streetscape_r0',
)

# West Portswood frontage from façade_1 survey (eastmost gray_terracotta per Z).
EDGE = [
    (7083, -5532),
    (7086, -5531),
    (7088, -5530),
    (7090, -5529),
    (7093, -5528),
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


def build_plan() -> Plan:
    """Build continuous west street-hull façade for the bay.

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
            # Fill eastward step on this Z so the diagonal does not leave notches.
            for x in range(px, ex + 1):
                hull.add((x, z))
                hull.add((x - 1, z))

    roles = {
        EDGE[0][1]: 'wall',
        EDGE[1][1]: 'window',
        EDGE[2][1]: 'door',
        EDGE[3][1]: 'window',
        EDGE[4][1]: 'wall',
    }

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
            elif role == 'window':
                plan.set(x, 28, z, PANE)
                plan.set(x, 29, z, PANE)
                plan.set(x, 32, z, PANE)
                plan.set(x, 33, z, PANE)
        elif x in (fx - 1, fx - 2):
            plan.set(x, Y_ROOF, z, STAIR_W)

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
