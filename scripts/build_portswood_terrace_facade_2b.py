#!/usr/bin/env python3
"""Q-012 mod: fix door_to_wall on façade_1b (I-008) and façade_2.

Patrol checks solid blocks on the door facing axis (±east here), not only
the diagonal +Z stoop. Clear one cell east (street) and one cell west
(through the depth-2 shell) at door height so each door is walkable.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'scripts'))

from site_kit import Plan, apply, preview  # noqa: E402

NAME = 'portswood_x_broadlands_terrace_facade_2b'
MODIFIES = (
    'portswood_x_broadlands_terrace_facade_1',
    'portswood_x_broadlands_terrace_facade_1b',
    'portswood_x_broadlands_terrace_facade_2',
    'portswood_x_broadlands_streetscape_q013b',
)

AIR = 'minecraft:air'
Y_DOOR = 27

# (door_x, door_z) — facing=east doors from façade_1b / façade_2
DOORS = (
    (7088, -5530),  # I-008
    (7073, -5535),  # façade_2
)


def build_plan() -> Plan:
    """Clear facing-axis cells at door height for listed doors.

    @returns: Plan
    """
    plan = Plan(NAME)
    for dx, dz in DOORS:
        for y in (Y_DOOR, Y_DOOR + 1):
            plan.set(dx + 1, y, dz, AIR)  # street / facing
            plan.set(dx - 1, y, dz, AIR)  # through shell
        # Keep diagonal stoop open at door height (leave y26 floor solid).
        for y in (Y_DOOR, Y_DOOR + 1):
            plan.set(dx, y, dz + 1, AIR)
    return plan


def main() -> None:
    """CLI: preview / dry / apply modification.

    @returns: None
    """
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--apply', action='store_true')
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
