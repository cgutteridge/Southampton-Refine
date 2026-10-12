#!/usr/bin/env python3
"""Temporary 128² cell perimeter markers (black/yellow wool ~30 m above ground).

  python3 scripts/cell_marker.py --raise 48,-44
  python3 scripts/cell_marker.py --raise 48,-44 --dry-run
  python3 scripts/cell_marker.py --clear 48,-44
  python3 scripts/cell_marker.py --clear 48,-44 --dry-run

Raise skips points where another build already owns the target cell (site_kit
built_cells). Clear only removes coordinates listed in the marker's *-cells.json
and refuses non-wool blocks or cells owned by other builds. Markers use build
names cell_marker_<tx>_m<abs_tz> (e.g. cell_marker_48_m44 for tz=-44).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'scripts'))

import coverage as cov  # noqa: E402
import site_kit  # noqa: E402
from site_kit import Plan, World, apply, bid, built_cells  # noqa: E402

HEIGHT_ABOVE = 30
BUMP_MAX = 5
WOOL = ('black_wool', 'yellow_wool')
OUT = site_kit.OUT


def parse_cell(spec: str) -> tuple[int, int]:
    """Parse ``tx,tz`` for a 128² cell key.

    @param spec: comma-separated cell indices
    @returns: (tx, tz)
    """
    parts = [p.strip() for p in spec.split(',')]
    if len(parts) != 2:
        raise SystemExit(f'expected tx,tz got {spec!r}')
    return int(parts[0]), int(parts[1])


def marker_name(tx: int, tz: int) -> str:
    """Kit build name for a cell marker.

    @param tx: cell X index
    @param tz: cell Z index
    @returns: build name (cell_marker_* prefix for coverage touch exclusion)
    """
    tz_tag = f'm{abs(tz)}' if tz < 0 else str(tz)
    return f'cell_marker_{tx}_{tz_tag}'


def perimeter_columns(tx: int, tz: int) -> list[tuple[int, int]]:
    """Edge columns of one 128² cell (closed ring, no duplicate corners).

    @param tx: cell X index
    @param tz: cell Z index
    @returns: [(x, z), ...] in order along the boundary
    """
    x0, z0, x1, z1 = cov.cell_bbox(tx, tz, tx, tz)
    top = [(x, z0) for x in range(x0, x1 + 1)]
    right = [(x1, z) for z in range(z0 + 1, z1 + 1)]
    bottom = [(x, z1) for x in range(x1 - 1, x0 - 1, -1)]
    left = [(x0, z) for z in range(z1 - 1, z0, -1)]
    return top + right + bottom + left


def _occupied_by_other(owned: dict, pos: tuple[int, int, int], skip_build: str) -> bool:
    """True if another build owns this exact cell.

    @param owned: built_cells() map
    @param pos: (x, y, z)
    @param skip_build: build name allowed to occupy (the marker itself)
    @returns: whether to skip placing or clearing here
    """
    hit = owned.get(pos)
    if not hit:
        return False
    return hit[0] != skip_build


def plan_raise(tx: int, tz: int, world: World | None = None) -> tuple[Plan, dict]:
    """Build a plan for the perimeter wool ring.

    @param tx: cell X index
    @param tz: cell Z index
    @param world: optional World reader (default: live save)
    @returns: (plan, stats dict with placed, skipped_conflict, skipped_ground)
    """
    world = world or World()
    name = marker_name(tx, tz)
    plan = Plan(name)
    owned = built_cells(exclude={name})
    stats = {'placed': 0, 'skipped_conflict': 0, 'skipped_no_ground': 0}
    for i, (x, z) in enumerate(perimeter_columns(tx, tz)):
        y_base = world.ground(x, z)
        if y_base is None:
            stats['skipped_no_ground'] += 1
            continue
        wool = WOOL[i % 2]
        placed = False
        for bump in range(BUMP_MAX + 1):
            y = y_base + HEIGHT_ABOVE + bump
            pos = (x, y, z)
            if _occupied_by_other(owned, pos, name):
                continue
            live = world.block(x, y, z) or 'minecraft:air'
            if bid(live) not in ('minecraft:air', 'minecraft:cave_air', 'minecraft:void_air'):
                if bump < BUMP_MAX:
                    continue
                stats['skipped_conflict'] += 1
                break
            plan.set(x, y, z, wool)
            stats['placed'] += 1
            placed = True
            break
        if not placed and stats['skipped_conflict'] == 0 and y_base is not None:
            pass
    return plan, stats


def plan_clear(tx: int, tz: int, world: World | None = None) -> tuple[Plan, dict]:
    """Build a plan that clears marker wool at registered coordinates.

    @param tx: cell X index
    @param tz: cell Z index
    @param world: optional World reader
    @returns: (plan, stats with cleared, skipped_foreign, skipped_not_wool, missing_registry)
    """
    world = world or World()
    name = marker_name(tx, tz)
    reg = OUT / f'{name}-cells.json'
    stats = {'cleared': 0, 'skipped_foreign': 0, 'skipped_not_wool': 0, 'missing_registry': not reg.exists()}
    if not reg.exists():
        return Plan(name), stats
    plan = Plan(name)
    owned = built_cells(exclude={name})
    for key, was in json.loads(reg.read_text()).items():
        x, y, z = (int(v) for v in key.split(','))
        pos = (x, y, z)
        if _occupied_by_other(owned, pos, name):
            stats['skipped_foreign'] += 1
            continue
        live = world.block(x, y, z) or 'minecraft:air'
        nb = bid(live)[10:]
        if nb not in WOOL and nb != 'air':
            stats['skipped_not_wool'] += 1
            continue
        plan.set(x, y, z, 'air')
        stats['cleared'] += 1
    return plan, stats


def cmd_raise(tx: int, tz: int, dry: bool) -> int:
    """Apply or preview a marker raise.

    @param tx: cell X index
    @param tz: cell Z index
    @param dry: preview only
    @returns: process exit code
    """
    plan, stats = plan_raise(tx, tz)
    print(f'{plan.name}: {stats}')
    if not plan.cells:
        print('nothing to place', file=sys.stderr)
        return 1
    if dry:
        print(f'dry-run: would place {len(plan.cells)} cells')
        return 0
    apply(plan, dry=False)
    return 0


def cmd_clear(tx: int, tz: int, dry: bool) -> int:
    """Apply or preview marker teardown.

    @param tx: cell X index
    @param tz: cell Z index
    @param dry: preview only
    @returns: process exit code
    """
    plan, stats = plan_clear(tx, tz)
    print(f'{plan.name}: {stats}')
    if stats.get('missing_registry'):
        print('no marker registry on disk', file=sys.stderr)
        return 1
    if not plan.cells:
        print('nothing to clear')
        return 0
    if dry:
        print(f'dry-run: would clear {len(plan.cells)} cells')
        return 0
    apply(plan, dry=False, modifies=(plan.name,))
    if stats['cleared'] > 0:
        (OUT / f'{plan.name}-cells.json').unlink(missing_ok=True)
        (OUT / f'{plan.name}-backup.json').unlink(missing_ok=True)
    return 0


def main() -> int:
    """CLI entry point.

    @returns: process exit code
    """
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument('--raise', dest='raise_cell', metavar='TX,TZ', help='place perimeter marker')
    g.add_argument('--clear', dest='clear_cell', metavar='TX,TZ', help='remove marker from registry')
    p.add_argument('--dry-run', action='store_true', help='plan only, no MCP apply')
    args = p.parse_args()
    if args.raise_cell:
        tx, tz = parse_cell(args.raise_cell)
        return cmd_raise(tx, tz, args.dry_run)
    tx, tz = parse_cell(args.clear_cell)
    return cmd_clear(tx, tz, args.dry_run)


if __name__ == '__main__':
    sys.exit(main())
