#!/usr/bin/env python3
"""Q-012 mod: restore diagonal stoop floors at y26 after door clearance."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'scripts'))

from site_kit import Plan, apply  # noqa: E402

NAME = 'portswood_x_broadlands_terrace_facade_2c'
MODIFIES = (
    'portswood_x_broadlands_terrace_facade_1b',
    'portswood_x_broadlands_terrace_facade_2',
    'portswood_x_broadlands_terrace_facade_2b',
)
BRICK = 'minecraft:bricks'
STOOPS = ((7088, -5529), (7073, -5534))


def build_plan() -> Plan:
    """Place solid floors under cleared +Z door stoops.

    @returns: Plan
    """
    plan = Plan(NAME)
    for x, z in STOOPS:
        plan.set(x, 26, z, BRICK)
    return plan


def main() -> None:
    """CLI: dry / apply.

    @returns: None
    """
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--apply', action='store_true')
    args = ap.parse_args()
    plan = build_plan()
    print(f'{NAME}: {len(plan.cells)} cells; bounds {plan.bounds()}')
    apply(plan, dry=not args.apply, modifies=MODIFIES)


if __name__ == '__main__':
    main()
