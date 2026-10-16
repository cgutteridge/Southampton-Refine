#!/usr/bin/env python3
"""Tree review: the lidar crown inventory against the live world (I-067 method, I-073 per-cell check).

Geocraft draws every lidar tree as log + leaf, so the PRISTINE save is a crown inventory (position, height,
spread; lidar_heightmap kind 2 = tree, 3 = tree over a roof). Lidar filters small things (shrubs, cars,
street furniture) and is blind to trees planted after the survey, so it is evidence, not truth: the Google
sheet decides what is real. This tool lines the two up and says where to look.

Per crown (connected tree columns): size, mean height above ground, and what the live world has there.
  MISSING  lidar tree, live has <  MISS_COVER of its columns as tree     (a crown was never planted, or was cleared)
  LOW/HIGH live tree there but its height differs from the lidar by >= HEIGHT_TOL blocks
  INVENTED live tree with <  MISS_COVER overlap with any lidar tree      (planted from the aerial only; check Google)
  ROOF     lidar tree over a roof (kind 3), live has a tree there too    (a crown over a building: check Google)
  ok       the rest (not listed unless --all)

  python3 scripts/tree_review.py --cell 48,-44                       # one cell
  python3 scripts/tree_review.py --zone 6150,-5787,6349,-5583        # a block rectangle (cells it touches)
  python3 scripts/tree_review.py --zone ... --marks out.json         # colours for google_aerial.py sheet --marks
  python3 scripts/tree_review.py --zone ... --json

Then look at the same area on the Google sheet:
  python3 scripts/google_aerial.py sheet --at X,Z --radius 60 --marks out.json    (red missing, blue invented, orange height)
and decide per crown: keep, add (extra crown in reference/trees-extra-crowns.json or trees_layer re-run), or remove.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

import cellmath
import lidar_heightmap as L
from script_env import ROOT  # noqa: E402

MISS_COVER = 0.3        # share of a crown's columns that must be a live tree, else MISSING / INVENTED
HEIGHT_TOL = 3          # blocks of mean height difference before LOW / HIGH
MIN_COLUMNS = 6         # ignore slivers (single trunks, stray leaf columns)
COLOURS = {'MISSING': '#ff0000', 'INVENTED': '#0066ff', 'LOW': '#ff9900', 'HIGH': '#ff9900', 'ROOF': '#aa00ff'}


def tree_mask(hm: dict) -> np.ndarray:
    """Boolean [x - x0, z - z0]: the column is a tree (kind 2) or a tree over a roof (kind 3)."""
    return np.isin(hm['kind'], (L.TREE, L.TREE_OVER_ROOF))


def tree_height(hm: dict) -> np.ndarray:
    """Tree height above the ground under it, per column (0 where there is no tree)."""
    return np.where(tree_mask(hm), np.maximum(hm['h'].astype(int) - hm['base'].astype(int), 0), 0)


def crowns(mask: np.ndarray, x0: int, z0: int, min_columns: int = MIN_COLUMNS) -> list[set]:
    """Connected tree columns as sets of absolute (x, z), largest first."""
    cols = {(x0 + int(i), z0 + int(j)) for i, j in zip(*np.nonzero(mask))}
    return [c for c in L._group(cols) if len(c) >= min_columns]


def _stats(comp: set, hm: dict, hgt: np.ndarray) -> dict:
    x0, z0 = hm['x0'], hm['z0']
    xs = [x for x, _ in comp]
    zs = [z for _, z in comp]
    hs = [int(hgt[x - x0, z - z0]) for x, z in comp]
    over = sum(1 for x, z in comp if hm['kind'][x - x0, z - z0] == L.TREE_OVER_ROOF)
    return {'centre': [round(sum(xs) / len(xs)), round(sum(zs) / len(zs))], 'bbox': [min(xs), min(zs), max(xs), max(zs)],
            'columns': len(comp), 'radius': round((len(comp) / 3.14159) ** 0.5, 1),
            'height': round(sum(hs) / len(hs), 1), 'top': max(hs), 'over_roof': over}


def review_cell(live: dict, pri: dict, miss_cover: float = MISS_COVER, height_tol: int = HEIGHT_TOL) -> list[dict]:
    """Compare two height maps of one cell. Returns one dict per crown with a 'verdict'."""
    x0, z0 = pri['x0'], pri['z0']
    pm, lm = tree_mask(pri), tree_mask(live)
    ph, lh = tree_height(pri), tree_height(live)
    out = []
    for comp in crowns(pm, x0, z0):
        s = _stats(comp, pri, ph)
        idx = ([x - x0 for x, _ in comp], [z - z0 for _, z in comp])
        covered = lm[idx]
        s['cover'] = round(float(covered.mean()), 2)
        s['live_height'] = round(float(lh[idx][covered].mean()), 1) if covered.any() else 0.0
        s['source'] = 'lidar'
        if s['cover'] < miss_cover:
            s['verdict'] = 'MISSING'
        else:
            d = s['live_height'] - s['height']
            s['verdict'] = 'LOW' if d <= -height_tol else 'HIGH' if d >= height_tol else 'ROOF' if s['over_roof'] else 'ok'
        out.append(s)
    for comp in crowns(lm, x0, z0):
        idx = ([x - x0 for x, _ in comp], [z - z0 for _, z in comp])
        if pm[idx].mean() < miss_cover:
            s = _stats(comp, live, lh)
            s.update({'cover': round(float(pm[idx].mean()), 2), 'live_height': s['height'], 'source': 'live', 'verdict': 'INVENTED'})
            out.append(s)
    return out


def cells_for_zone(x0: int, z0: int, x1: int, z1: int) -> list[tuple[int, int]]:
    """Cells a block rectangle touches, in ring order from the focus is not needed: row by row."""
    n = cellmath.CELL
    return [(tx, tz) for tz in range(z0 // n, z1 // n + 1) for tx in range(x0 // n, x1 // n + 1)]


def run(cells: list[tuple[int, int]], zone: tuple[int, int, int, int] | None = None) -> list[dict]:
    from site_kit import World
    live_w, pri_w = World(), L.pristine_world()
    rows = []
    for cell in cells:
        for r in review_cell(L.heightmap(live_w, cell), L.heightmap(pri_w, cell)):
            cx, cz = r['centre']
            if zone and not (zone[0] <= cx <= zone[2] and zone[1] <= cz <= zone[3]):
                continue          # a crown belongs to the zone its centre is in
            r['cell'] = f'{cell[0]},{cell[1]}'
            rows.append(r)
    return rows


def format_report(rows: list[dict], show_all: bool = False) -> str:
    n_l = [r for r in rows if r['source'] == 'lidar']
    counts = {v: sum(1 for r in rows if r['verdict'] == v) for v in ('MISSING', 'LOW', 'HIGH', 'ROOF', 'INVENTED', 'ok')}
    lines = [f'TREE REVIEW: {len(n_l)} lidar crowns; ' + ', '.join(f'{v} {n}' for v, n in counts.items()),
             'verdict   cell     centre         cols  r    lidar-h  live-h  cover  roof']
    for r in sorted(rows, key=lambda r: (r['verdict'] == 'ok', r['verdict'], -r['columns'])):
        if r['verdict'] == 'ok' and not show_all:
            continue
        lines.append(f'{r["verdict"]:<9} {r["cell"]:<8} {r["centre"][0]},{r["centre"][1]}'.ljust(38)
                     + f'{r["columns"]:>4} {r["radius"]:>4} {r["height"]:>8} {r["live_height"]:>7} {r["cover"]:>6} {r["over_roof"]:>5}')
    return '\n'.join(lines)


def marks(rows: list[dict]) -> list[list]:
    """[[x, z, colour]] for google_aerial.py --marks: the centre column of each crown that needs a look."""
    return [[r['centre'][0], r['centre'][1], COLOURS[r['verdict']]] for r in rows if r['verdict'] in COLOURS]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--cell', help='tx,tz')
    ap.add_argument('--zone', help='x0,z0,x1,z1 block rectangle')
    ap.add_argument('--all', action='store_true', help='list matching crowns too')
    ap.add_argument('--json', action='store_true')
    ap.add_argument('--marks', help='write colours for google_aerial.py sheet --marks to this file')
    a = ap.parse_args(argv)
    if bool(a.cell) == bool(a.zone):
        ap.error('give exactly one of --cell or --zone')
    if a.cell:
        cells, zone = [cellmath.parse_cell(a.cell)], None
    else:
        zone = tuple(int(v) for v in a.zone.split(','))
        cells = cells_for_zone(*zone)
    rows = run(cells, zone)
    if a.marks:
        Path(a.marks).write_text(json.dumps(marks(rows)))
    print(json.dumps(rows, indent=1) if a.json else format_report(rows, a.all))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
