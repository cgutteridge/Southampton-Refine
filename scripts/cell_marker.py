#!/usr/bin/env python3
"""Temporary 128² cell perimeter markers (black/yellow wool ~30 m above ground).

  python3 scripts/cell_marker.py --raise 48,-44
  python3 scripts/cell_marker.py --raise 48,-44 --dry-run
  python3 scripts/cell_marker.py --clear 48,-44
  python3 scripts/cell_marker.py --clear 48,-44 --dry-run
  python3 scripts/cell_marker.py --status
  python3 scripts/cell_marker.py --adopt 48,-46     # one-off: record an already-raised ring

Focus is tracked in site/CURRENT-CELL.json, written ONLY by this script: raise
sets it, clear releases it. Raise refuses if the file names another cell or any
other cell_marker_*-cells.json registry is on disk, so at most one ring exists.

Raise places one horizontal wool ring on the cell bbox at a single Y (~30 blocks
above the highest sampled ground in the cell). Black and yellow wool alternate
along the perimeter like hazard tape. Only minecraft:air (and cave/void air) is
replaced — occupied voxels are skipped so teardown is trivial.
Clear removes every marker wool on the cell perimeter: coordinates in
*-cells.json plus a legacy Y-band sweep (~30 m above ground through +5 bumps,
matching the old per-column raise). Refuses non-wool blocks or cells owned by
other builds. Re-raise strips leftover wool in that band before placing the
flat ring. Markers use build names
cell_marker_<tx>_m<abs_tz> (e.g. cell_marker_48_m44 for tz=-44).
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

from script_env import ROOT  # noqa: E402

import coverage as cov  # noqa: E402
import site_kit  # noqa: E402
from site_kit import Plan, World, apply, bid, built_cells  # noqa: E402

HEIGHT_ABOVE = 30
GROUND_SAMPLE_STEP = 16
# Pre–flat-ring raises stacked wool per column up to +LEGACY_BUMP_MAX when blocked.
LEGACY_BUMP_MAX = 5
WOOL = ('black_wool', 'yellow_wool')
AIRS = frozenset({'minecraft:air', 'minecraft:cave_air', 'minecraft:void_air'})
OUT = site_kit.OUT
CURRENT_FILE = ROOT / 'site' / 'CURRENT-CELL.json'
REGISTRY_RE = re.compile(r'^cell_marker_(\d+)_(m?)(\d+)-cells\.json$')


from cellmath import parse_cell  # noqa: E402,F401


def marker_name(tx: int, tz: int) -> str:
    """Kit build name for a cell marker.

    @param tx: cell X index
    @param tz: cell Z index
    @returns: build name (cell_marker_* prefix for coverage touch exclusion)
    """
    tz_tag = f'm{abs(tz)}' if tz < 0 else str(tz)
    return f'cell_marker_{tx}_{tz_tag}'


def cell_bounds(tx: int, tz: int) -> tuple[int, int, int, int]:
    """Inclusive MC bounds for one coverage cell.

    @param tx: cell X index
    @param tz: cell Z index
    @returns: (x0, z0, x1, z1)
    """
    return cov.cell_bbox(tx, tz, tx, tz)


def perimeter_columns(tx: int, tz: int) -> list[tuple[int, int]]:
    """Edge columns of one 128² cell (closed ring, no duplicate corners).

    @param tx: cell X index
    @param tz: cell Z index
    @returns: [(x, z), ...] in order along the boundary
    """
    x0, z0, x1, z1 = cell_bounds(tx, tz)
    top = [(x, z0) for x in range(x0, x1 + 1)]
    right = [(x1, z) for z in range(z0 + 1, z1 + 1)]
    bottom = [(x, z1) for x in range(x1 - 1, x0 - 1, -1)]
    left = [(x0, z) for z in range(z1 - 1, z0, -1)]
    return top + right + bottom + left


def reference_ground_y(world: World, tx: int, tz: int) -> int | None:
    """Highest ground Y sampled inside the cell (defines the marker plane base).

    @param world: live or pristine reader
    @param tx: cell X index
    @param tz: cell Z index
    @returns: ground Y or None if no samples
    """
    x0, z0, x1, z1 = cell_bounds(tx, tz)
    peak: int | None = None
    step = GROUND_SAMPLE_STEP
    for x in range(x0, x1 + 1, step):
        for z in range(z0, z1 + 1, step):
            y = world.ground(x, z)
            if y is None:
                continue
            peak = y if peak is None else max(peak, y)
    if peak is None:
        for x, z in perimeter_columns(tx, tz):
            y = world.ground(x, z)
            if y is None:
                continue
            peak = y if peak is None else max(peak, y)
    return peak


def marker_y_band(base: int) -> range:
    """World Y values used by current and legacy perimeter markers.

    @param base: reference ground Y inside the cell
    @returns: inclusive Y range from the nominal plane through legacy bumps
    """
    y0 = base + HEIGHT_ABOVE
    return range(y0, y0 + LEGACY_BUMP_MAX + 1)


def marker_plane_y(world: World, tx: int, tz: int) -> int | None:
    """Single Y for the whole perimeter ring (~30 blocks above cell ground peak).

    @param world: live or pristine reader
    @param tx: cell X index
    @param tz: cell Z index
    @returns: world Y for wool placement, or None if ground unknown
    """
    base = reference_ground_y(world, tx, tz)
    if base is None:
        return None
    return base + HEIGHT_ABOVE


def wool_along_perimeter(index: int) -> str:
    """Hazard-tape wool colour at one step around the cell ring.

    @param index: 0-based position along ``perimeter_columns`` order
    @returns: black_wool or yellow_wool
    """
    return WOOL[index % 2]


def is_marker_wool(state: str | None) -> bool:
    """True when a block is black or yellow wool (marker material).

    @param state: minecraft block id string
    @returns: whether this is marker wool
    """
    return bid(state or 'minecraft:air')[10:] in WOOL


def is_air(state: str | None) -> bool:
    """True when a block state is replaceable air.

    @param state: minecraft block id string
    @returns: whether raise may place here
    """
    return bid(state or 'minecraft:air') in AIRS


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


def _clear_positions(tx: int, tz: int, world: World, registry: dict[str, str],
                     extra_y: int | None = None) -> set[tuple[int, int, int]]:
    """All voxels teardown should attempt for one cell marker.

    @param tx: cell X index
    @param tz: cell Z index
    @param world: live or pristine reader
    @param registry: parsed *-cells.json map
    @param extra_y: also sweep this exact Y (ring raised when ground read differently)
    @returns: positions from registry plus legacy-band wool on the perimeter
    """
    positions: set[tuple[int, int, int]] = {
        tuple(int(v) for v in key.split(',')) for key in registry
    }
    base = reference_ground_y(world, tx, tz)
    ys = list(marker_y_band(base)) if base is not None else []
    if extra_y is not None:
        ys.append(extra_y)
    for x, z in perimeter_columns(tx, tz):
        for y in ys:
            if is_marker_wool(world.block(x, y, z)):
                positions.add((x, y, z))
    return positions


def _strip_legacy_wool(
    plan: Plan,
    tx: int,
    tz: int,
    world: World,
    name: str,
    owned: dict,
    y_ring: int,
    stats: dict,
) -> None:
    """Remove pre–flat-ring wool on perimeter columns before placing the ring.

    @param plan: plan under construction
    @param tx: cell X index
    @param tz: cell Z index
    @param world: live or pristine reader
    @param name: marker build name
    @param owned: built_cells() map
    @param y_ring: Y of the new flat ring
    @param stats: mutable stats dict (stripped_legacy incremented)
    """
    base = reference_ground_y(world, tx, tz)
    if base is None:
        return
    for x, z in perimeter_columns(tx, tz):
        for y in marker_y_band(base):
            if y == y_ring:
                continue
            pos = (x, y, z)
            if _occupied_by_other(owned, pos, name):
                continue
            if not is_marker_wool(world.block(x, y, z)):
                continue
            plan.set(x, y, z, 'air')
            stats['stripped_legacy'] = stats.get('stripped_legacy', 0) + 1


def _protect_not_air(_pos: tuple[int, int, int], existing: str | None) -> bool:
    """site_kit apply protect: refuse any non-air overwrite.

    @param _pos: block position (unused)
    @param existing: live block state
    @returns: True to refuse apply at this cell
    """
    return not is_air(existing)


def plan_raise(tx: int, tz: int, world: World | None = None) -> tuple[Plan, dict]:
    """Build a plan for the perimeter wool ring at one Y, air-only.

    @param tx: cell X index
    @param tz: cell Z index
    @param world: optional World reader (default: live save)
    @returns: (plan, stats dict)
    """
    world = world or World()
    name = marker_name(tx, tz)
    plan = Plan(name)
    plan.outside_footprint_ok = (
        'cell perimeter visibility marker: black/yellow wool ~30 m above ground '
        '(cell_marker.py); not a building footprint placement'
    )
    y_ring = marker_plane_y(world, tx, tz)
    owned = built_cells(exclude={name})
    stats = {
        'placed': 0,
        'stripped_legacy': 0,
        'skipped_not_air': 0,
        'skipped_foreign': 0,
        'skipped_no_plane': 0,
        'plane_y': y_ring,
    }
    if y_ring is None:
        stats['skipped_no_plane'] = len(perimeter_columns(tx, tz))
        return plan, stats
    _strip_legacy_wool(plan, tx, tz, world, name, owned, y_ring, stats)
    ring = perimeter_columns(tx, tz)
    for i, (x, z) in enumerate(ring):
        pos = (x, y_ring, z)
        if _occupied_by_other(owned, pos, name):
            stats['skipped_foreign'] += 1
            continue
        live = world.block(x, y_ring, z)
        if not is_air(live):
            stats['skipped_not_air'] += 1
            continue
        plan.set(x, y_ring, z, wool_along_perimeter(i))
        stats['placed'] += 1
    return plan, stats


def plan_clear(tx: int, tz: int, world: World | None = None,
               extra_y: int | None = None) -> tuple[Plan, dict]:
    """Build a plan that clears marker wool at registered coordinates.

    @param tx: cell X index
    @param tz: cell Z index
    @param world: optional World reader
    @param extra_y: extra exact Y to sweep for wool on the perimeter
    @returns: (plan, stats with cleared, skipped_foreign, skipped_not_wool, missing_registry)
    """
    world = world or World()
    name = marker_name(tx, tz)
    reg = OUT / f'{name}-cells.json'
    registry: dict[str, str] = json.loads(reg.read_text()) if reg.exists() else {}
    candidates = _clear_positions(tx, tz, world, registry, extra_y)
    stats = {
        'cleared': 0,
        'skipped_foreign': 0,
        'skipped_not_wool': 0,
        'missing_registry': not reg.exists() and not candidates,
        'sweep_extra': 0,
    }
    if stats['missing_registry']:
        return Plan(name), stats
    plan = Plan(name)
    owned = built_cells(exclude={name})
    registry_positions = {
        tuple(int(v) for v in key.split(',')) for key in registry
    }
    for pos in sorted(candidates):
        if pos not in registry_positions and is_marker_wool(world.block(*pos)):
            stats['sweep_extra'] += 1
        if _occupied_by_other(owned, pos, name):
            stats['skipped_foreign'] += 1
            continue
        live = world.block(*pos) or 'minecraft:air'
        nb = bid(live)[10:]
        if nb not in WOOL and nb != 'air':
            stats['skipped_not_wool'] += 1
            continue
        if nb == 'air':
            continue
        x, y, z = pos
        plan.set(x, y, z, 'air')
        stats['cleared'] += 1
    return plan, stats


def read_current() -> tuple[int, int] | None:
    """Cell that currently owns the focus ring.

    @returns: (tx, tz) from CURRENT-CELL.json, or None when no ring is held
    """
    if not CURRENT_FILE.exists():
        return None
    data = json.loads(CURRENT_FILE.read_text())
    if not data or data.get('tx') is None:
        return None
    return int(data['tx']), int(data['tz'])


def write_current(cell: tuple[int, int] | None) -> None:
    """Record (or release) the focus cell. Only raise/clear/adopt call this.

    @param cell: (tx, tz) to hold, or None to release
    """
    body = {'tx': None, 'tz': None} if cell is None else {'tx': cell[0], 'tz': cell[1]}
    body['note'] = 'Written only by scripts/cell_marker.py (raise/clear/adopt). Do not edit.'
    CURRENT_FILE.write_text(json.dumps(body, indent=2) + '\n')


def registered_cells() -> list[tuple[int, int]]:
    """Cells that still have a marker registry on disk (ring probably in the world).

    @returns: sorted (tx, tz) list
    """
    found = []
    for f in OUT.glob('cell_marker_*-cells.json'):
        m = REGISTRY_RE.match(f.name)
        if m:
            tz = int(m.group(3))
            found.append((int(m.group(1)), -tz if m.group(2) else tz))
    return sorted(found)


def check_can_raise(cell: tuple[int, int]) -> str | None:
    """Refuse a raise that would create a second ring.

    @param cell: cell about to be raised
    @returns: error message, or None when allowed
    """
    cur = read_current()
    if cur is not None and cur != cell:
        return (f'focus is held by {cur[0]},{cur[1]}: run --clear {cur[0]},{cur[1]} '
                f'before raising {cell[0]},{cell[1]}')
    strays = [c for c in registered_cells() if c != cell]
    if strays:
        s = ', '.join(f'{a},{b}' for a, b in strays)
        return f'stray marker registry for {s}: --clear each (or --adopt then --clear) before raising'
    return None


def cmd_status() -> int:
    """Print focus cell and any stray registries.

    @returns: 0 when consistent, 1 when focus and registries disagree
    """
    cur = read_current()
    regs = registered_cells()
    print(f'current: {cur[0]},{cur[1]}' if cur else 'current: none')
    print('registries: ' + (', '.join(f'{a},{b}' for a, b in regs) or 'none'))
    bad = [c for c in regs if c != cur]
    if bad:
        print('INCONSISTENT: stray ring(s) ' + ', '.join(f'{a},{b}' for a, b in bad), file=sys.stderr)
        return 1
    if cur and cur not in regs:
        print('note: focus held but no registry (ring not raised yet, or already cleared)')
    return 0


def cmd_adopt(cell: tuple[int, int]) -> int:
    """One-off bootstrap: declare an already-raised ring as the focus.

    @param cell: cell whose ring is live
    @returns: process exit code
    """
    cur = read_current()
    if cur is not None and cur != cell:
        print(f'focus already held by {cur[0]},{cur[1]}', file=sys.stderr)
        return 1
    write_current(cell)
    print(f'current: {cell[0]},{cell[1]}')
    return 0


def cmd_raise(tx: int, tz: int, dry: bool) -> int:
    """Apply or preview a marker raise.

    @param tx: cell X index
    @param tz: cell Z index
    @param dry: preview only
    @returns: process exit code
    """
    err = check_can_raise((tx, tz))
    if err:
        print(f'refused: {err}', file=sys.stderr)
        return 2
    plan, stats = plan_raise(tx, tz)
    print(f'{plan.name}: {stats}')
    if not plan.cells:
        print('nothing to place', file=sys.stderr)
        return 1
    if dry:
        print(f'dry-run: would place {len(plan.cells)} cells')
        return 0
    apply(plan, dry=False, protect=_protect_not_air)
    write_current((tx, tz))
    return 0


def cmd_clear(tx: int, tz: int, dry: bool, stray: bool = False, y: int | None = None) -> int:
    """Apply or preview marker teardown.

    @param tx: cell X index
    @param tz: cell Z index
    @param dry: preview only
    @param y: extra exact Y to sweep (stray rings at an unexpected height)
    @param stray: allow clearing a ring that is not the focus cell (leaves focus untouched)
    @returns: process exit code
    """
    cur = read_current()
    if cur is not None and cur != (tx, tz) and not stray:
        print(f'refused: focus is {cur[0]},{cur[1]}; {tx},{tz} is a stray ring. '
              f'Clear it with --stray-clear {tx},{tz} if it really is a leftover.', file=sys.stderr)
        return 2
    plan, stats = plan_clear(tx, tz, extra_y=y)
    print(f'{plan.name}: {stats}')
    if stats.get('missing_registry'):
        print('no marker registry on disk', file=sys.stderr)
        if cur == (tx, tz) and not dry:
            write_current(None)
            print('released focus (ring already gone)')
        return 1
    if not plan.cells:
        print('nothing to clear')
        if not dry:
            (OUT / f'{plan.name}-cells.json').unlink(missing_ok=True)
            (OUT / f'{plan.name}-backup.json').unlink(missing_ok=True)
            if cur == (tx, tz):
                write_current(None)
        return 0
    if dry:
        print(f'dry-run: would clear {len(plan.cells)} cells')
        return 0
    apply(plan, dry=False, modifies=(plan.name,))
    if stats['cleared'] > 0:
        (OUT / f'{plan.name}-cells.json').unlink(missing_ok=True)
        (OUT / f'{plan.name}-backup.json').unlink(missing_ok=True)
    if cur == (tx, tz):
        write_current(None)
    return 0


def main() -> int:
    """CLI entry point.

    @returns: process exit code
    """
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument('--raise', dest='raise_cell', metavar='TX,TZ', help='place perimeter marker')
    g.add_argument('--clear', dest='clear_cell', metavar='TX,TZ', help='remove marker and release focus')
    g.add_argument('--stray-clear', dest='stray_cell', metavar='TX,TZ', help='remove a leftover ring that is not the focus')
    g.add_argument('--adopt', dest='adopt_cell', metavar='TX,TZ', help='record an already-raised ring as focus')
    g.add_argument('--status', action='store_true', help='show focus cell and stray registries')
    p.add_argument('--y', type=int, help='with --clear/--stray-clear: also sweep this exact ring Y')
    p.add_argument('--dry-run', action='store_true', help='plan only, no MCP apply')
    args = p.parse_args()
    if args.status:
        return cmd_status()
    if args.adopt_cell:
        return cmd_adopt(parse_cell(args.adopt_cell))
    if args.stray_cell:
        tx, tz = parse_cell(args.stray_cell)
        return cmd_clear(tx, tz, args.dry_run, stray=True, y=args.y)
    if args.raise_cell:
        tx, tz = parse_cell(args.raise_cell)
        return cmd_raise(tx, tz, args.dry_run)
    tx, tz = parse_cell(args.clear_cell)
    return cmd_clear(tx, tz, args.dry_run, y=args.y)


if __name__ == '__main__':
    sys.exit(main())
