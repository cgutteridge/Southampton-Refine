#!/usr/bin/env python3
"""Clear leaf blocks with no trunk (Geocraft canopy remnants) in a coverage cell.

  python3 scripts/clear_floating_leaves.py --cell 48,-44
  python3 scripts/clear_floating_leaves.py --cell 48,-44 --apply

Save the world first. Uses the same rules as ``floaters.floating_leaves``.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'scripts'))

import coverage as cov  # noqa: E402
from floaters import floating_leaves  # noqa: E402
from floater_scan import cell_output_stem, parse_cell  # noqa: E402
from floater_scan import parse_y_range  # noqa: E402
from site_kit import Plan, World, apply, built_cells  # noqa: E402


def plan_clears(
    w: World,
    x0: int,
    y0: int,
    z0: int,
    x1: int,
    y1: int,
    z1: int,
    *,
    name: str,
    max_log_dist: int = 6,
) -> Plan:
    """Plan air for every floating leaf in the scan box.

    @param w: live world reader
    @param x0: min X inclusive
    @param y0: min Y inclusive
    @param z0: min Z inclusive
    @param x1: max X inclusive
    @param y1: max Y inclusive
    @param z1: max Z inclusive
    @param name: kit build name
    @param max_log_dist: trunk search radius
    @returns: plan with clears only
    """
    p = Plan(name)
    for x in range(x0, x1 + 1):
        for z in range(z0, z1 + 1):
            for y in range(y0, y1 + 1):
                st = w.block(x, y, z)
                if not st or 'leaves' not in st:
                    continue
                if floating_leaves(w.block, x, y, z, st, max_log_dist=max_log_dist):
                    p.set(x, y, z, 'air')
    return p


def modifies_for(plan: Plan) -> tuple[str, ...]:
    """Earlier build names this clear may supersede on planned cells.

    @param plan: kit plan
    @returns: sorted build names for ``apply(modifies=...)``
    """
    owned = built_cells(exclude={plan.name})
    names = {owned[q][0] for q in plan.cells if q in owned}
    return tuple(sorted(names))


def main(argv: list[str] | None = None) -> int:
    """CLI entry.

    @param argv: optional argument list
    @returns: exit code
    """
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--cell', required=True, metavar='TX,TZ', help='128² coverage cell')
    ap.add_argument('--y', metavar='Y0,Y1', default='45,100', help='Y range (default 45,100)')
    ap.add_argument('--log-dist', type=int, default=6, help='trunk search through foliage')
    ap.add_argument('--apply', action='store_true', help='apply via MCP (needs site lock)')
    args = ap.parse_args(argv)

    tx, tz = parse_cell(args.cell)
    x0, z0, x1, z1 = cov.cell_bbox(tx, tz, tx, tz)
    y0, y1 = parse_y_range(args.y)
    name = f'clear_floating_leaves_{cell_output_stem(tx, tz)}'
    w = World()
    plan = plan_clears(w, x0, y0, z0, x1, y1, z1, name=name, max_log_dist=max(1, args.log_dist))
    print(f'{name}: {len(plan.cells)} leaf blocks to air')
    if not plan.cells:
        return 0
    mods = modifies_for(plan)
    if mods:
        print('modifies:', ', '.join(mods))
    if not args.apply:
        print('dry-run only — pass --apply to write')
        apply(plan, dry=True, modifies=mods)
        return 0
    apply(plan, modifies=mods)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
