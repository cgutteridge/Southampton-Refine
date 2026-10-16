#!/usr/bin/env python3
"""Scan a saved-world box for floaters (offline region read, no MCP).

Looks at every block in the box, counts air vs non-air, and reports:
  - attachable glitches (same rules as ``site_patrol.py`` sweep)
  - unsupported mass: solid blocks with no solid support within ``--depth`` below
    (default 10; only straight down — fast heuristic)

  python3 scripts/floater_scan.py 7090,64,-5530,7110,90,-5510
  python3 scripts/floater_scan.py --bbox 7090,-5530,7110,-5510 --y 64,90
  python3 scripts/floater_scan.py --cell 48,-44 --y 50,90 --no-structural
  python3 scripts/floater_scan.py 7090,64,-5530,7110,90,-5510 --no-attachables -o verification/site/my-floater-scan.json

Save the world first. ``hit_scan_floor`` on a finding means support may sit below ``y0``.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'scripts'))

import coverage as cov  # noqa: E402
from floaters import scan_box  # noqa: E402
from site_kit import OUT, World  # noqa: E402


def parse_cell(spec: str) -> tuple[int, int]:
    """Parse ``tx,tz`` for a 128² coverage cell key.

    @param spec: comma-separated cell indices
    @returns: (tx, tz)
    @raises SystemExit: on bad input
    """
    parts = [p.strip() for p in spec.split(',')]
    if len(parts) != 2:
        raise SystemExit(f'expected tx,tz got {spec!r}')
    return int(parts[0]), int(parts[1])


def cell_output_stem(tx: int, tz: int) -> str:
    """Default JSON filename stem for one cell scan.

    @param tx: cell X index
    @param tz: cell Z index
    @returns: e.g. ``48_m44`` for tz=-44
    """
    tz_tag = f'm{abs(tz)}' if tz < 0 else str(tz)
    return f'{tx}_{tz_tag}'


def parse_bbox(raw: str) -> tuple[int, int, int, int, int, int]:
    """Parse ``x0,y0,z0,x1,y1,z1`` or ``x0,z0,x1,z1`` (Y defaults 0..319).

    @param raw: comma-separated bbox
    @returns: inclusive min/max for X, Y, Z
    @raises SystemExit: on bad input
    """
    parts = [int(p.strip()) for p in raw.split(',')]
    if len(parts) == 4:
        x0, z0, x1, z1 = parts
        return x0, 0, z0, x1, 319, z1
    if len(parts) == 6:
        x0, y0, z0, x1, y1, z1 = parts
        return x0, y0, z0, x1, y1, z1
    raise SystemExit(f'bbox needs 4 (x0,z0,x1,z1) or 6 (x0,y0,z0,x1,y1,z1) numbers, got {len(parts)}')


def parse_y_range(raw: str) -> tuple[int, int]:
    """Parse ``yMin,yMax`` inclusive.

    @param raw: two integers separated by comma
    @returns: (y0, y1)
    """
    y0, y1 = (int(p.strip()) for p in raw.split(','))
    if y0 > y1:
        y0, y1 = y1, y0
    return y0, y1


def main(argv: list[str] | None = None) -> int:
    """CLI entry: scan region files and print / write a JSON report.

    @param argv: optional argument list (defaults to ``sys.argv[1:]``)
    @returns: exit code (1 if any finding, 0 if clean)
    """
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('bbox', nargs='?', help='x0,y0,z0,x1,y1,z1 or x0,z0,x1,z1')
    ap.add_argument('--bbox', dest='bbox_flag', metavar='X0,Z0,X1,Z1', help='XZ only; combine with --y')
    ap.add_argument(
        '--cell',
        metavar='TX,TZ',
        help='128² coverage cell (same grid as coverage.py); sets XZ bbox; combine with --y',
    )
    ap.add_argument('--y', metavar='Y0,Y1', help='Y range with --bbox or --cell (default 0,319)')
    ap.add_argument('--depth', type=int, default=10, help='blocks to search downward (default 10)')
    ap.add_argument('--no-attachables', action='store_true', help='skip lantern/sign/door checks')
    ap.add_argument('--no-structural', action='store_true', help='skip unsupported-mass checks')
    ap.add_argument('--no-foliage', action='store_true', help='skip floating-leaves (no log) checks')
    ap.add_argument(
        '--log-dist',
        type=int,
        default=6,
        help='max foliage steps when searching for a trunk (default 6)',
    )
    ap.add_argument('-o', '--output', type=Path, help='write full JSON here')
    ap.add_argument('--sample', type=int, default=12, help='max lines printed per finding kind')
    args = ap.parse_args(argv)

    cell_key: tuple[int, int] | None = None
    if args.cell and (args.bbox or args.bbox_flag):
        ap.error('--cell conflicts with positional bbox or --bbox')
    if args.cell:
        tx, tz = parse_cell(args.cell)
        cell_key = (tx, tz)
        x0, z0, x1, z1 = cov.cell_bbox(tx, tz, tx, tz)
        y0, y1 = parse_y_range(args.y) if args.y else (0, 319)
    else:
        raw = args.bbox or args.bbox_flag
        if not raw:
            ap.print_help()
            return 2
        x0, y0, z0, x1, y1, z1 = parse_bbox(raw)
        if args.bbox_flag and args.y:
            y0, y1 = parse_y_range(args.y)
        elif args.bbox_flag and not args.y:
            y0, y1 = 0, 319

    w = World()
    report = scan_box(
        w.block,
        x0,
        y0,
        z0,
        x1,
        y1,
        z1,
        depth=max(1, args.depth),
        attachables=not args.no_attachables,
        structural=not args.no_structural,
        foliage=not args.no_foliage,
        max_log_dist=max(1, args.log_dist),
    )
    report['time'] = time.strftime('%Y-%m-%d %H:%M')
    if cell_key is not None:
        report['cell'] = list(cell_key)

    out_path = args.output
    if out_path is None:
        if cell_key is not None:
            out_path = OUT / f'floater-scan-{cell_output_stem(*cell_key)}.json'
        else:
            stamp = time.strftime('%Y%m%d-%H%M%S')
            out_path = OUT / f'floater-scan-{stamp}.json'
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, indent=1))

    summary: dict = {
        'bbox': report['bbox'],
        'counts': report['counts'],
        'totals': report['totals'],
        'output': str(out_path),
    }
    if cell_key is not None:
        summary['cell'] = list(cell_key)
    print(json.dumps(summary, indent=1))
    for kind, rows in report['findings'].items():
        for row in rows[: args.sample]:
            print(f'  {kind}: {row}')
        if len(rows) > args.sample:
            print(f'  … {len(rows) - args.sample} more {kind}')

    return 1 if report['totals'] else 0


if __name__ == '__main__':
    raise SystemExit(main())
