#!/usr/bin/env python3
"""Read-only cross-cell / cross-zone reports for ground and foliage handoff.

  python3 scripts/cross_zone.py report --area highfield --cell 48,-44 [--margin 8]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'scripts'))

from coverage import cell_bbox, load_area, load_signoffs, stats, touched_by_build, union  # noqa: E402
CELL = 128
DEFAULT_MARGIN = 8


def neighbor_cells(tx: int, tz: int, *, chebyshev: int = 1) -> list[tuple[int, int]]:
    """Coverage cell indices within Chebyshev distance of ``(tx, tz)``.

    @param tx: cell X index
    @param tz: cell Z index
    @param chebyshev: distance (1 = 8-neighbour ring)
    @returns: sorted list including centre when chebyshev >= 0
    """
    out = []
    for dx in range(-chebyshev, chebyshev + 1):
        for dz in range(-chebyshev, chebyshev + 1):
            if max(abs(dx), abs(dz)) <= chebyshev:
                out.append((tx + dx, tz + dz))
    return sorted(out)


def expanded_cell_bbox(tx: int, tz: int, margin: int = 0) -> tuple[int, int, int, int]:
    """Inclusive MC bbox for a cell optionally padded by ``margin`` blocks.

    @param tx: cell X
    @param tz: cell Z
    @param margin: block padding on each side
    @returns: (x0, z0, x1, z1)
    """
    x0, z0, x1, z1 = cell_bbox(tx, tz, tx, tz)
    if margin:
        return x0 - margin, z0 - margin, x1 + margin, z1 + margin
    return x0, z0, x1, z1


def legacy_zones_for_cell(tx: int, tz: int) -> list[dict]:
    """Retired: the old nine-zone ground split no longer exists, so no cell has zones."""
    return []


def parcels_on_cell_edge(area_name: str, tx: int, tz: int) -> list[str]:
    """Parcel ids with at least one column on the cell bbox border.

    @param area_name: coverage area
    @param tx: cell X
    @param tz: cell Z
    @returns: sorted parcel ids
    """
    area = load_area(area_name)
    x0, z0, x1, z1 = cell_bbox(tx, tz, tx, tz)
    hit = []
    for pid, p in area.parcels.items():
        for x, z in p['set']:
            if (x, z) in p['set'] and (x == x0 or x == x1 or z == z0 or z == z1):
                hit.append(pid)
                break
    return sorted(set(hit))


def parcel_straddle_summary(area_name: str, pid: str, tx: int, tz: int) -> dict:
    """Count parcel columns inside vs outside a coverage cell.

    @param area_name: coverage area
    @param pid: parcel id
    @param tx: cell X
    @param tz: cell Z
    @returns: {inside, outside, total}
    """
    area = load_area(area_name)
    p = area.parcels[pid]
    x0, z0, x1, z1 = cell_bbox(tx, tz, tx, tz)
    inside = sum(1 for x, z in p['set'] if x0 <= x <= x1 and z0 <= z <= z1)
    total = p['n']
    return {'inside': inside, 'outside': total - inside, 'total': total}


def columns_outside_cell(columns: set[tuple[int, int]], tx: int, tz: int) -> set[tuple[int, int]]:
    """Subset of columns not in the cell bbox.

    @param columns: {(x, z)}
    @param tx: cell X
    @param tz: cell Z
    @returns: columns outside cell
    """
    x0, z0, x1, z1 = cell_bbox(tx, tz, tx, tz)
    return {(x, z) for x, z in columns if x < x0 or x > x1 or z < z0 or z > z1}


def cross_zone_report(
    area_name: str,
    tx: int,
    tz: int,
    *,
    margin: int = DEFAULT_MARGIN,
    plan_columns: set[tuple[int, int]] | None = None,
) -> dict:
    """Unified cross-zone warnings for handoff and foliage dry-run.

    @param area_name: coverage area
    @param tx: cell X
    @param tz: cell Z
    @param margin: foliage margin blocks
    @param plan_columns: optional planned {(x, z)} from a dry-run plan
    @returns: report dict with warnings, deferrals, and metadata
    """
    area = load_area(area_name)
    touched = union(touched_by_build())
    signoffs = load_signoffs()
    st = stats(area, touched, signoffs)
    warnings: list[str] = []
    deferrals: list[str] = []

    zones = legacy_zones_for_cell(tx, tz)
    if len(zones) > 1:
        warnings.append(
            'grounds zones: ' + '+'.join(z['name'] for z in zones),
        )

    edge_parcels = parcels_on_cell_edge(area_name, tx, tz)
    for pid in edge_parcels[:8]:
        if not pid.startswith(('open:', 'gap:', 'path:')):
            continue
        sm = parcel_straddle_summary(area_name, pid, tx, tz)
        if sm['outside'] > 0:
            warnings.append(f'{pid} straddles cell edge ({sm["outside"]} cols outside)')

    if plan_columns:
        outside = columns_outside_cell(plan_columns, tx, tz)
        if outside:
            warnings.append(f'plan writes {len(outside)} columns outside cell {tx},{tz}')
            by_cell: dict[tuple[int, int], int] = {}
            for x, z in outside:
                ct = (x // CELL, z // CELL)
                by_cell[ct] = by_cell.get(ct, 0) + 1
            for (ntx, ntz), n in sorted(by_cell.items()):
                deferrals.append(f'foliage straddle: {n} cols → cell {ntx},{ntz}')

    ex0, ez0, ex1, ez1 = expanded_cell_bbox(tx, tz, margin)
    for ntx, ntz in neighbor_cells(tx, tz, chebyshev=1):
        if (ntx, ntz) == (tx, tz):
            continue
        nx0, nz0, nx1, nz1 = cell_bbox(ntx, ntz, ntx, ntz)
        open_unsigned = []
        for pid, p in area.parcels.items():
            if p['kind'] not in ('open', 'gap', 'path'):
                continue
            if not (p['set'] & {(x, z) for x in range(nx0, nx1 + 1) for z in range(nz0, nz1 + 1)}):
                continue
            if st[pid]['state'] != 'done':
                open_unsigned.append(pid)
        if open_unsigned and margin:
            warnings.append(
                f'neighbor {ntx},{ntz}: {len(open_unsigned)} open/gap/path parcels not done '
                f'(margin {margin} may touch them)',
            )

    return {
        'cell': [tx, tz],
        'margin': margin,
        'expanded_bbox': [ex0, ez0, ex1, ez1],
        'legacy_zones': zones,
        'neighbors': neighbor_cells(tx, tz),
        'edge_parcels': edge_parcels[:20],
        'warnings': warnings,
        'deferrals': deferrals,
    }


def format_report(report: dict) -> str:
    """Human-readable cross-zone report.

    @param report: ``cross_zone_report`` result
    @returns: multi-line text
    """
    lines = [
        f"CROSS-ZONE cell {report['cell'][0]},{report['cell'][1]} "
        f"margin={report['margin']} zones={[z['name'] for z in report['legacy_zones']]}",
    ]
    for w in report['warnings']:
        lines.append(f'  warn: {w}')
    for d in report['deferrals']:
        lines.append(f'  defer: {d}')
    if not report['warnings'] and not report['deferrals']:
        lines.append('  (no cross-zone warnings)')
    return '\n'.join(lines)


def main() -> int:
    """CLI entry.

    @returns: exit code
    """
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest='cmd', required=True)
    rep = sub.add_parser('report', help='print cross-zone report')
    rep.add_argument('--area', default='highfield')
    rep.add_argument('--cell', required=True, help='tx,tz')
    rep.add_argument('--margin', type=int, default=DEFAULT_MARGIN)
    rep.add_argument('--json', action='store_true')
    args = ap.parse_args()
    tx, tz = (int(v.strip()) for v in args.cell.split(','))
    r = cross_zone_report(args.area, tx, tz, margin=args.margin)
    if args.json:
        print(json.dumps(r, indent=2))
    else:
        print(format_report(r))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
