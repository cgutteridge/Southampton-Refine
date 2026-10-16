#!/usr/bin/env python3
"""Tree review: the lidar crown inventory against the live world (I-067 method, I-073 per-cell check).

Geocraft draws every lidar tree as log + leaf, so the PRISTINE save is a crown inventory (position, height,
spread; lidar_heightmap kind 2 = tree, 3 = tree over a roof). Lidar filters small things (shrubs, cars,
street furniture) and is blind to trees planted after the survey, so it is evidence, not truth: the Google
sheet decides what is real. This tool lines the two up and says where to look.

Per crown (connected tree columns): size, mean height above ground, and what the live world has there.
Crowns are matched by their TOPS (highest tree column in a 3-block window; the live canopy merges crowns, so
blobs are not comparable). A lidar top and a live top within MATCH_R blocks are the same tree.
  MISSING  lidar crown top with no live crown top near it                (never planted, or cleared)
  LOW/HIGH matched, but the live top is >= HEIGHT_TOL blocks lower/higher than the lidar
  INVENTED live crown top with no lidar top near it                      (planted from the aerial only; check Google)
  ROOF     lidar crown over a roof (kind 3), matched                     (a crown over a building: check Google)
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

PEAK_R = 3              # a crown top is the highest tree column within this many blocks
MIN_PEAK = 3            # ignore tree tops lower than this above ground (shrubs, hedges: decor owns them)
MATCH_R = 4             # a lidar crown and a live crown are the same tree when their tops are within this many blocks
HEIGHT_TOL = 4          # blocks of top-height difference before LOW / HIGH (lidar crowns are noisy)
COLOURS = {'MISSING': '#ff0000', 'INVENTED': '#0066ff', 'LOW': '#ff9900', 'HIGH': '#ff9900', 'ROOF': '#aa00ff'}


def tree_mask(hm: dict) -> np.ndarray:
    """Boolean [x - x0, z - z0]: the column is a tree (kind 2) or a tree over a roof (kind 3)."""
    return np.isin(hm['kind'], (L.TREE, L.TREE_OVER_ROOF))


def tree_height(hm: dict) -> np.ndarray:
    """Tree height above the ground under it, per column (0 where there is no tree)."""
    return np.where(tree_mask(hm), np.maximum(hm['h'].astype(int) - hm['base'].astype(int), 0), 0)


def _window_max(a: np.ndarray, r: int) -> np.ndarray:
    """Maximum over the (2r+1)^2 window around every element."""
    pad = np.pad(a, r, mode='constant')
    h, w = a.shape
    return np.max([pad[i:i + h, j:j + w] for i in range(2 * r + 1) for j in range(2 * r + 1)], axis=0)


def peaks(hgt: np.ndarray, x0: int, z0: int, radius: int = PEAK_R, min_height: int = MIN_PEAK) -> list[tuple[int, int, int]]:
    """Crown tops as (x, z, height): the highest tree column in its window; a flat top is one peak at its middle."""
    top = (hgt >= min_height) & (hgt == _window_max(hgt, radius))
    cols = {(x0 + int(i), z0 + int(j)) for i, j in zip(*np.nonzero(top))}
    out = []
    for comp in L._group(cols):
        xs = [x for x, _ in comp]
        zs = [z for _, z in comp]
        cx, cz = round(sum(xs) / len(xs)), round(sum(zs) / len(zs))
        out.append((cx, cz, int(hgt[cx - x0, cz - z0]) or int(hgt[min(comp)[0] - x0, min(comp)[1] - z0])))
    return out


def _near(p: tuple, others: list, r: int) -> tuple | None:
    best = min(others, key=lambda q: (q[0] - p[0]) ** 2 + (q[1] - p[1]) ** 2, default=None)
    return best if best and (best[0] - p[0]) ** 2 + (best[1] - p[1]) ** 2 <= r * r else None


def _leaf_dist(live: dict, x: int, z: int, reach: int = 8) -> int | None:
    """Blocks from (x, z) to the nearest live tree column of any height (None beyond reach): 0 = a live crown covers the spot."""
    x0, z0 = live['x0'], live['z0']
    mask = tree_mask(live)
    best = None
    for i in range(max(0, x - x0 - reach), min(mask.shape[0], x - x0 + reach + 1)):
        for j in range(max(0, z - z0 - reach), min(mask.shape[1], z - z0 + reach + 1)):
            if mask[i, j]:
                d = round(((x0 + i - x) ** 2 + (z0 + j - z) ** 2) ** 0.5)
                best = d if best is None or d < best else best
    return best


def review_cell(live: dict, pri: dict, match_r: int = MATCH_R, height_tol: int = HEIGHT_TOL) -> list[dict]:
    """Compare two height maps of one cell. One dict per crown top with a 'verdict' (see the module doc)."""
    x0, z0 = pri['x0'], pri['z0']
    ph, lh = tree_height(pri), tree_height(live)
    pp, lp = peaks(ph, x0, z0), peaks(lh, x0, z0)
    out = []
    for x, z, h in pp:
        q = _near((x, z), lp, match_r)
        over = int(pri['kind'][x - x0, z - z0] == L.TREE_OVER_ROOF)
        row = {'centre': [x, z], 'height': h, 'live_height': q[2] if q else 0, 'over_roof': over, 'source': 'lidar'}
        if not q:
            row['verdict'] = 'MISSING'
            row['live_leaf_dist'] = _leaf_dist(live, x, z)
        else:
            d = q[2] - h
            row['verdict'] = 'LOW' if d <= -height_tol else 'HIGH' if d >= height_tol else 'ROOF' if over else 'ok'
        out.append(row)
    for x, z, h in lp:
        if not _near((x, z), pp, match_r):
            out.append({'centre': [x, z], 'height': 0, 'live_height': h, 'over_roof': 0, 'source': 'live', 'verdict': 'INVENTED'})
    return out


def cover_summary(live: dict, pri: dict) -> dict:
    """Column counts: lidar tree columns, live tree columns, and how many are both."""
    pm, lm = tree_mask(pri), tree_mask(live)
    return {'lidar': int(pm.sum()), 'live': int(lm.sum()), 'both': int((pm & lm).sum())}


def cells_for_zone(x0: int, z0: int, x1: int, z1: int) -> list[tuple[int, int]]:
    """Cells a block rectangle touches, in ring order from the focus is not needed: row by row."""
    n = cellmath.CELL
    return [(tx, tz) for tz in range(z0 // n, z1 // n + 1) for tx in range(x0 // n, x1 // n + 1)]


def run(cells: list[tuple[int, int]], zone: tuple[int, int, int, int] | None = None) -> list[dict]:
    from site_kit import World
    live_w, pri_w = World(), L.pristine_world()
    rows = []
    for cell in cells:
        live, pri = L.heightmap(live_w, cell), L.heightmap(pri_w, cell)
        for r in review_cell(live, pri):
            cx, cz = r['centre']
            if zone and not (zone[0] <= cx <= zone[2] and zone[1] <= cz <= zone[3]):
                continue          # a crown belongs to the zone its centre is in
            r['cell'] = f'{cell[0]},{cell[1]}'
            rows.append(r)
    return rows


def format_report(rows: list[dict], show_all: bool = False) -> str:
    n_l = sum(1 for r in rows if r['source'] == 'lidar')
    counts = {v: sum(1 for r in rows if r['verdict'] == v) for v in ('MISSING', 'LOW', 'HIGH', 'ROOF', 'INVENTED', 'ok')}
    lines = [f'TREE REVIEW: {n_l} lidar crown tops, {sum(1 for r in rows if r["source"] == "live" or r["live_height"])} live; '
             + ', '.join(f'{v} {n}' for v, n in counts.items()),
             'verdict   cell     centre            lidar-h  live-h  roof  nearest live leaf (MISSING)']
    for r in sorted(rows, key=lambda r: (r['verdict'] == 'ok', r['verdict'], r['cell'], r['centre'])):
        if r['verdict'] == 'ok' and not show_all:
            continue
        lines.append(f'{r["verdict"]:<9} {r["cell"]:<8} {r["centre"][0]},{r["centre"][1]}'.ljust(38)
                     + f'{r["height"]:>5} {r["live_height"]:>7} {r["over_roof"]:>5}'
                     + (f'  {r["live_leaf_dist"] if r["live_leaf_dist"] is not None else ">8"}' if 'live_leaf_dist' in r else ''))
    return '\n'.join(lines)


def marks(rows: list[dict], size: int = 3) -> list[list]:
    """[[x, z, colour]] for google_aerial.py --marks: a size x size patch at each crown top that needs a look.

    Matched crowns (ok) are left off so the sheet shows only the differences.
    """
    half = size // 2
    return [[r['centre'][0] + dx, r['centre'][1] + dz, COLOURS[r['verdict']]]
            for r in rows if r['verdict'] in COLOURS for dx in range(-half, half + 1) for dz in range(-half, half + 1)]


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
