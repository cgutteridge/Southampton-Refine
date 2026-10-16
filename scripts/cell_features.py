#!/usr/bin/env python3
"""Find major features (buildings) a cell still lacks, packaged for queueing.

A feature is any build in verification/site/*-cells.json that is not a layer pass
(ground, trees, decor, foliage, canopy, undo, markers). An OSM building is "in a
feature" when at least COVERED_FRAC of its footprint columns are touched by one.

Packaging: each non-home building (campus block, shop, church...) is its own feature.
Homes that overlap the cell and are not yet in a feature are grouped by street, then
split where the gap between neighbouring footprints exceeds JOIN_GAP, so one terrace
or run of houses becomes one feature. Outbuildings (sheds, garages) are left to their
house plot.

  python3 scripts/cell_features.py --cell 48,-43
"""
from __future__ import annotations

import argparse
import math
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'scripts'))

from coverage import (  # noqa: E402
    HOMES,
    OUTBUILDINGS,
    cell_bbox,
    osm_ref,
    property_label,
    scan_polygon,
    touched_by_build,
)
from osm_footprints import OSMIndex  # noqa: E402

COVERED_FRAC = 0.5
JOIN_GAP = 12         # blocks between footprints that still count as one run of houses
STREET_REACH = 40     # nearest named street for homes with no addr:street
MIN_COLUMNS = 12      # ignore slivers (kiosks, bin stores)

LAYER_BUILD = re.compile(
    r'(_ground|_trees|_decor|_foliage|_canopy|_undo|_grounds_\w+)$|^cell_marker_|^clear_floating|'
    r'^highfield_grounds_|_grounds$')


def is_feature_build(name: str) -> bool:
    """Whether a build name is a feature rather than a layer pass.

    @param name: build name (verification/site/<name>-cells.json)
    @returns: True for features
    """
    return not LAYER_BUILD.search(name)


def feature_columns() -> set:
    """Columns touched by any feature build.

    @returns: set of (x, z)
    """
    cols = set()
    for name, c in touched_by_build().items():
        if is_feature_build(name):
            cols |= c
    return cols


def _street_of(p: dict, bbox, streets) -> str | None:
    from osm_footprints import _addr
    _num, street = _addr(p)
    if street:
        return street
    cx, cz = (bbox[0] + bbox[2]) / 2, (bbox[1] + bbox[3]) / 2
    best, best_d = None, STREET_REACH
    for name, _hw, pts in streets:
        if not name:
            continue
        for (ax, az), (bx, bz) in zip(pts, pts[1:]):
            dx, dz = bx - ax, bz - az
            t = 0 if dx == dz == 0 else max(0, min(1, ((cx - ax) * dx + (cz - az) * dz) / (dx * dx + dz * dz)))
            d = math.hypot(cx - (ax + t * dx), cz - (az + t * dz))
            if d < best_d:
                best, best_d = name, d
    return best


def _gap(a, b) -> float:
    dx = max(a[0] - b[2], b[0] - a[2], 0)
    dz = max(a[1] - b[3], b[1] - a[3], 0)
    return math.hypot(dx, dz)


def _split_runs(items: list) -> list:
    """Single-link cluster footprints whose bbox gap <= JOIN_GAP.

    @param items: [{'bbox': (x0, z0, x1, z1), ...}]
    @returns: list of lists
    """
    groups: list[list] = []
    for it in items:
        hit = [g for g in groups if any(_gap(it['bbox'], o['bbox']) <= JOIN_GAP for o in g)]
        merged = [it] + [o for g in hit for o in g]
        groups = [g for g in groups if g not in hit] + [merged]
    return groups


def missing_features(tx: int, tz: int, idx: OSMIndex | None = None, covered: set | None = None) -> list:
    """Buildings overlapping the cell that no feature build covers, packaged as features.

    @param tx: cell X
    @param tz: cell Z
    @param idx: optional shared OSMIndex
    @param covered: optional precomputed feature_columns()
    @returns: [{'kind': 'building'|'houses', 'label': str, 'street': str|None,
                'refs': [osm ref], 'bbox': (x0, z0, x1, z1)}], buildings first, then streets
    """
    idx = idx or OSMIndex()
    covered = feature_columns() if covered is None else covered
    cb = cell_bbox(tx, tz, tx, tz)
    singles, homes = [], []
    for rings, p in idx.buildings:
        if p.get('building') in OUTBUILDINGS:
            continue
        cols = list(scan_polygon(rings, cb))
        if len(cols) < MIN_COLUMNS:
            continue
        # whole footprint, so a building straddling the cell edge is judged as one
        full = list(scan_polygon(rings, (-10**9, -10**9, 10**9, 10**9))) if len(cols) < 4000 else cols
        if sum(c in covered for c in full) >= COVERED_FRAC * len(full):
            continue
        xs = [x for x, _ in rings[0]]
        zs = [z for _, z in rings[0]]
        item = {'ref': osm_ref(p), 'label': property_label(p), 'p': p,
                'bbox': (min(xs), min(zs), max(xs), max(zs))}
        (homes if p.get('building') in HOMES else singles).append(item)
    out = [{'kind': 'building', 'label': s['label'], 'street': None, 'refs': [s['ref']],
            'bbox': s['bbox']} for s in sorted(singles, key=lambda s: s['bbox'][:2])]
    by_street: dict = {}
    for h in homes:
        h['street'] = _street_of(h['p'], h['bbox'], idx.streets)
        by_street.setdefault(h['street'], []).append(h)
    for street in sorted(by_street, key=lambda s: s or ''):
        for run in sorted(_split_runs(by_street[street]), key=lambda g: min(o['bbox'][:2] for o in g)):
            out.append({
                'kind': 'houses', 'street': street,
                'label': f'{street or "unnamed street"} ({len(run)} houses)',
                'refs': sorted(o['ref'] for o in run),
                'bbox': (min(o['bbox'][0] for o in run), min(o['bbox'][1] for o in run),
                         max(o['bbox'][2] for o in run), max(o['bbox'][3] for o in run)),
            })
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--cell', required=True, help='tx,tz')
    a = ap.parse_args(argv)
    tx, tz = (int(v) for v in a.cell.split(','))
    for f in missing_features(tx, tz):
        print(f"{f['kind']:9} {f['label']}  bbox={f['bbox']}  {','.join(f['refs'][:6])}")
    return 0


if __name__ == '__main__':
    sys.exit(main())
