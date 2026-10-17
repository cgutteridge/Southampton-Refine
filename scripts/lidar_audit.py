#!/usr/bin/env python3
"""Audit the live world against the pristine lidar height map (I-064 / I-065).

For one cell, take the height map of the live world (same rules as lidar_heightmap: carpet ignored, leaves
and logs count) and compare it with the pristine one. The target for a column is the lidar roof top where
Geocraft had a roof (carpet y), else the lidar surface h.

Per lump (building in the lidar): live vs lidar ridge, eave-free shape check (share of columns within 1 block),
mean and worst difference. Per cell: share within tolerance, lidar tree columns with no live tree (missing),
live trees where the lidar had none (extra), and the worst columns.

  python3 scripts/lidar_audit.py --cell 49,-43                 # table
  python3 scripts/lidar_audit.py --cell 49,-43 --json --tol 2  # machine-readable
  python3 scripts/lidar_audit.py --grid 6160,-5540,6206,-5492  # live-minus-lidar over a bbox (crosses cell edges)
  python3 scripts/lidar_audit.py --grid 6160,-5540,6206,-5492 --min 2   # only |diff| >= 2

Differences of a few blocks are normal where a build deliberately replaced the lump; the tool shows where to look,
it does not say what is wrong.
"""
from __future__ import annotations

import argparse
import json

import numpy as np

import cellmath
import lidar_heightmap as L


def target(pri: dict) -> np.ndarray:
    """Per-column lidar height to compare against: roof carpet y where there is a roof, else h."""
    return np.where(pri['roof'] > 0, pri['roof'], pri['h']).astype(np.int32)


def audit(live: dict, pri: dict, tol: int = 1, worst: int = 10) -> dict:
    """Compare two height maps of the same cell.

    @param live: heightmap() of the live world
    @param pri: heightmap() of the pristine world
    @param tol: columns within this many blocks count as matching
    @param worst: how many worst columns to list
    @returns: {'columns', 'within', 'tree_missing', 'tree_extra', 'lumps': [...], 'worst': [...]}
    """
    tgt = target(pri)
    diff = live['h'].astype(np.int32) - tgt                   # + = live is higher than the lidar
    known = (pri['h'] > 0) | (pri['roof'] > 0)
    within = (np.abs(diff) <= tol) & known
    tree_p = np.isin(pri['kind'], (L.TREE, L.TREE_OVER_ROOF))
    tree_l = np.isin(live['kind'], (L.TREE, L.TREE_OVER_ROOF))
    x0, z0 = pri['x0'], pri['z0']
    lumps = []
    for lp in L.lumps(pri):
        xs = np.array([c[0] - x0 for c in lp['cols']])
        zs = np.array([c[1] - z0 for c in lp['cols']])
        d = diff[xs, zs]
        live_roof = live['h'][xs, zs]
        lumps.append({'bbox': lp['bbox'], 'columns': lp['columns'], 'lidar_ridge': lp['ridge_y'],
                      'live_ridge': int(live_roof.max()), 'lidar_storeys': lp['storeys'],
                      'within': round(float((np.abs(d) <= tol).mean()), 3), 'mean_diff': round(float(d.mean()), 2),
                      'lowest': int(d.min()), 'highest': int(d.max())})
    order = np.dstack(np.unravel_index(np.argsort(-np.abs(diff * known).ravel())[:worst], diff.shape))[0]
    return {'columns': int(known.sum()), 'within': round(float(within.sum() / max(1, known.sum())), 3),
            'tree_missing': int((tree_p & ~tree_l).sum()), 'tree_extra': int((tree_l & ~tree_p).sum()),
            'lumps': sorted(lumps, key=lambda m: m['within']),
            'worst': [[int(x0 + i), int(z0 + j), int(live['h'][i, j]), int(tgt[i, j])] for i, j in order if known[i, j] and diff[i, j]]}


def format_audit(cell, res: dict, tol: int) -> str:
    """Plain-text report."""
    lines = [f'LIDAR AUDIT cell {cell[0]},{cell[1]} (tol {tol}): {res["within"]:.0%} of {res["columns"]} lidar columns match; '
             f'trees missing {res["tree_missing"]}, extra {res["tree_extra"]}',
             'lump bbox                  cols  ridge live/lidar  st  within  mean  low high']
    for m in res['lumps']:
        b = m['bbox']
        lines.append(f'{b[0]},{b[1]}..{b[2]},{b[3]}'.ljust(27) + f'{m["columns"]:>4}  {m["live_ridge"]:>5}/{m["lidar_ridge"]:<5}      '
                     f'{m["lidar_storeys"]:>2}  {m["within"]:>6.0%} {m["mean_diff"]:>5} {m["lowest"]:>4} {m["highest"]:>4}')
    if res['worst']:
        lines.append('worst columns (x, z, live, lidar): ' + '  '.join(f'{x},{z}:{a}/{b}' for x, z, a, b in res['worst']))
    return '\n'.join(lines)


def parse_bbox(spec: str) -> tuple[int, int, int, int]:
    """Parse ``x0,z0,x1,z1`` (inclusive).

    @param spec: comma-separated bbox
    @returns: (x0, z0, x1, z1) with x0<=x1, z0<=z1
    """
    parts = [p.strip() for p in str(spec).split(',')]
    if len(parts) != 4:
        raise SystemExit(f'expected x0,z0,x1,z1 got {spec!r}')
    try:
        x0, z0, x1, z1 = (int(p) for p in parts)
    except ValueError as e:
        raise SystemExit(f'expected x0,z0,x1,z1 got {spec!r}') from e
    return min(x0, x1), min(z0, z1), max(x0, x1), max(z0, z1)


def grid_diff(live: L.Maps, pri: L.Maps, x0: int, z0: int, x1: int, z1: int,
              min_abs: int = 0) -> list[tuple[int, int, int, int, int]]:
    """Live-minus-lidar columns over a bbox (works across cell edges).

    @param live: Maps over the live world
    @param pri: Maps over the pristine lidar
    @param x0: inclusive min X
    @param z0: inclusive min Z
    @param x1: inclusive max X
    @param z1: inclusive max Z
    @param min_abs: keep only columns with abs(live - lidar) >= this
    @returns: list of (x, z, live_y, lidar_y, diff) sorted by |diff| desc, then x, z
    """
    rows = []
    for x in range(x0, x1 + 1):
        for z in range(z0, z1 + 1):
            ly = live.top_at(x, z)
            py = pri.top_at(x, z)
            d = ly - py
            if abs(d) >= min_abs:
                rows.append((x, z, ly, py, d))
    rows.sort(key=lambda r: (-abs(r[4]), r[0], r[1]))
    return rows


def format_grid(bbox: tuple[int, int, int, int], rows: list, min_abs: int) -> str:
    """Plain-text live-minus-lidar listing (+ = live higher than lidar)."""
    x0, z0, x1, z1 = bbox
    n = (x1 - x0 + 1) * (z1 - z0 + 1)
    lines = [f'LIVE-MINUS-LIDAR {x0},{z0}..{x1},{z1}  ({len(rows)} of {n} columns'
             + (f' with |d|>={min_abs}' if min_abs else '')
             + '; + = live higher)',
             'x,z              live lidar   d']
    for x, z, ly, py, d in rows:
        lines.append(f'{x},{z}'.ljust(16) + f'{ly:>5} {py:>5} {d:>+3}')
    if rows:
        worst = max(abs(r[4]) for r in rows)
        mean = sum(r[4] for r in rows) / len(rows)
        lines.append(f'summary: {len(rows)} listed; mean d={mean:+.2f}; worst |d|={worst}')
    return '\n'.join(lines)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--cell', help='tx,tz')
    ap.add_argument('--grid', help='x0,z0,x1,z1 inclusive bbox: print live-minus-lidar (crosses cell edges)')
    ap.add_argument('--min', type=int, default=0, dest='min_abs',
                    help='with --grid: only list columns with |live-lidar| >= N (default 0 = all)')
    ap.add_argument('--tol', type=int, default=1)
    ap.add_argument('--json', action='store_true')
    a = ap.parse_args(argv)
    if not a.cell and not a.grid:
        ap.error('--cell or --grid is required')
    from site_kit import World
    if a.grid:
        bbox = parse_bbox(a.grid)
        live = L.Maps(World(), use_cache=False)
        pri = L.Maps()                                          # pristine; use .npz when present
        rows = grid_diff(live, pri, *bbox, min_abs=a.min_abs)
        if a.json:
            print(json.dumps({'bbox': list(bbox), 'min_abs': a.min_abs,
                              'columns': [{'x': x, 'z': z, 'live': ly, 'lidar': py, 'diff': d}
                                          for x, z, ly, py, d in rows]}, indent=1))
        else:
            print(format_grid(bbox, rows, a.min_abs))
        return 0
    cell = cellmath.parse_cell(a.cell)
    res = audit(L.heightmap(World(), cell), L.heightmap(L.pristine_world(), cell), tol=a.tol)
    print(json.dumps(res, indent=1) if a.json else format_audit(cell, res, a.tol))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
