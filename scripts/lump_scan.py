#!/usr/bin/env python3
"""Residual Geocraft: find building blobs a cell still carries; they are part of "cell done" (I-047, I-057).

site_handoff.cell_gaps calls scan_cell/lump_features, so a finished cell with lumps is re-queued as
feature items automatically; running this CLI by hand is only a diagnostic.

A "lump" is a building the original Geocraft import generated (roof = light_gray_carpet in the
untouched save at reference/pristine_region_path, walls/fill below it) that no *feature* build has
refined. Layer passes (ground, trees, decor) do NOT count as refining: the ground pass happily
recolours a lump's roof (granite/concrete) and paints lawn round it, so a surface check alone passes
while the blob stands (49,-43, 2026-10-15: every University Road house south of the road was a lump).

Detection, per column of the cell:
  roof   pristine surface block is *_carpet (Geocraft roof) at y = roof_y
  intact the live block just under roof_y is the pristine one and solid (wall / fill not yet cleared)
  open   no feature build (cell_features.feature_columns) wrote the column
Open roof+intact columns are grouped (8-connected); groups under MIN_COLUMNS are ignored.
Each lump reports bbox, centre, roof Y range, height over the surrounding ground, column count and the
OSM building(s) under it; lumps with no OSM building are flagged unmapped (build them from the aerial /
Street View, whatever year: see site/PROCESS.txt "Newer than OSM").

  python3 scripts/lump_scan.py --cell 49,-43            # report; exit 1 if unrecorded lumps remain
  python3 scripts/lump_scan.py --cell 49,-43 --bbox 6330,-5450,6420,-5380
  python3 scripts/lump_scan.py --cell 49,-43 --record   # write the result into the cell STAGES file

Exceptions (a lump that is really a ruin / roofed shed we decided to keep) are recorded by hand in
site/cells/<tx>_<tz>-STAGES.json stages.lump_sweep.exceptions = [{"bbox": [x0,z0,x1,z1], "reason": ...}];
a lump whose centre lies in an exception bbox is reported as excepted and does not fail the check.
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
from pathlib import Path

from script_env import ROOT  # noqa: E402

MIN_COLUMNS = 12      # ignore slivers (bin stores, sheds under 12 columns)
TOP = 140             # highest y scanned
_AIRS = ('minecraft:air', 'minecraft:cave_air', 'minecraft:void_air', 'minecraft:light')
_SOFT = ('leaves', '_log', 'short_grass', 'tall_grass', 'fern', 'flower', 'tulip', 'poppy', 'dandelion',
         'bush', 'vine', 'daisy', 'bluet', 'orchid', 'allium', 'cornflower', 'lily', 'sugar_cane', 'mushroom')
N8 = [(dx, dz) for dx in (-1, 0, 1) for dz in (-1, 0, 1) if dx or dz]


def _id(b) -> str:
    return (b or 'minecraft:air').split('[')[0]


def surface(world, x: int, z: int, top: int = TOP) -> tuple[int, str]:
    """Top solid block of a column, skipping air, plants, leaves and logs.

    @param world: object with block(x, y, z)
    @returns: (y, block id without properties); (0, '') if nothing found
    """
    skip = getattr(world, 'uniform_air', None)            # a real World can jump whole empty 16-block sections
    y = top
    while y > 0:
        if skip is not None and skip(x, y, z, _AIRS):
            y = ((y >> 4) << 4) - 1                        # top of the section below
            continue
        b = _id(world.block(x, y, z))
        if b not in _AIRS and not any(k in b for k in _SOFT):
            return y, b
        y -= 1
    return 0, ''


def roof_columns(cols, live, pristine) -> dict:
    """Columns still carrying a Geocraft roof volume.

    @param cols: iterable of (x, z)
    @param live: World over the live save
    @param pristine: World over the untouched Geocraft save
    @returns: {(x, z): roof_y}
    """
    out = {}
    for x, z in cols:
        py, pb = surface(pristine, x, z)
        if not pb.endswith('_carpet'):
            continue
        below_p = _id(pristine.block(x, py - 1, z))
        below_l = _id(live.block(x, py - 1, z))
        if below_p in _AIRS or below_l != below_p:
            continue
        out[(x, z)] = py
    return out


def group(cols, connect=N8) -> list:
    """Connected components of a column set, largest first.

    @param cols: set of (x, z)
    @param connect: neighbour offsets
    @returns: list of sets
    """
    left, out = set(cols), []
    while left:
        seed = min(left)
        comp, todo = {seed}, [seed]
        left.discard(seed)
        while todo:
            x, z = todo.pop()
            for dx, dz in connect:
                n = (x + dx, z + dz)
                if n in left:
                    left.discard(n)
                    comp.add(n)
                    todo.append(n)
        out.append(comp)
    return sorted(out, key=lambda c: (-len(c), min(c)))


def ground_around(comp: set, live, reach: int = 2) -> int | None:
    """Median live surface Y of the columns ringing a lump (reach columns out, not in the lump).

    @returns: Y, or None when the lump has no free neighbours
    """
    ring = {(x + dx, z + dz) for x, z in comp for dx in range(-reach, reach + 1)
            for dz in range(-reach, reach + 1)} - comp
    ys = [surface(live, x, z)[0] for x, z in sorted(ring)[::3]]
    ys = [y for y in ys if y]
    return int(statistics.median(ys)) if ys else None


def find_lumps(cols, live, pristine, covered: set | frozenset = frozenset(), min_columns: int = MIN_COLUMNS) -> list:
    """Unrefined Geocraft building blobs among the given columns.

    @param cols: iterable of (x, z) to scan (e.g. one cell)
    @param live: World over the live save
    @param pristine: World over the untouched Geocraft save
    @param covered: columns a feature build wrote (these are never lumps)
    @param min_columns: smallest lump reported
    @returns: [{'bbox': [x0, z0, x1, z1], 'centre': [x, z], 'columns': n, 'roof_y': [lo, hi],
                'ground_y': int|None, 'height': int|None, 'cols': set}] largest first
    """
    roofs = roof_columns((c for c in cols if c not in covered), live, pristine)
    out = []
    for comp in group(set(roofs)):
        if len(comp) < min_columns:
            continue
        xs = [x for x, _ in comp]
        zs = [z for _, z in comp]
        ys = [roofs[c] for c in comp]
        g = ground_around(comp, live)
        out.append({'bbox': [min(xs), min(zs), max(xs), max(zs)],
                    'centre': [(min(xs) + max(xs)) // 2, (min(zs) + max(zs)) // 2],
                    'columns': len(comp), 'roof_y': [min(ys), max(ys)], 'ground_y': g,
                    'height': (max(ys) - g) if g is not None else None, 'cols': comp})
    return out


def in_bbox(pt, bbox) -> bool:
    """@returns: whether (x, z) lies inside the inclusive bbox [x0, z0, x1, z1]"""
    return bbox[0] <= pt[0] <= bbox[2] and bbox[1] <= pt[1] <= bbox[3]


def apply_exceptions(lumps: list, exceptions: list) -> None:
    """Mark lumps whose centre lies in a recorded exception bbox (sets 'exception' to the reason).

    @param lumps: find_lumps() output (modified in place)
    @param exceptions: [{'bbox': [...], 'reason': str}]
    """
    for lp in lumps:
        for ex in exceptions or []:
            if in_bbox(lp['centre'], ex['bbox']):
                lp['exception'] = ex.get('reason', 'recorded')
                break


def osm_under(lump: dict, idx) -> list:
    """OSM buildings sharing at least a quarter of the smaller footprint (min 4 columns) with the lump.

    @param lump: one find_lumps() item
    @param idx: osm_footprints.OSMIndex
    @returns: [osm ref]
    """
    from coverage import osm_ref, scan_polygon
    x0, z0, x1, z1 = lump['bbox']
    out = []
    for rings, p in idx.buildings:
        xs = [x for x, _ in rings[0]]
        zs = [z for _, z in rings[0]]
        if max(xs) < x0 or min(xs) > x1 or max(zs) < z0 or min(zs) > z1:
            continue
        fp = set(scan_polygon(rings, (x0 - 2, z0 - 2, x1 + 2, z1 + 2)))
        if fp and len(fp & lump['cols']) >= max(4, min(len(fp), lump['columns']) / 4):
            out.append(osm_ref(p))
    return out


def lump_features(lumps: list, taken_refs=(), streets=()) -> list:
    """Package residual lumps as queue features (same shape as cell_features.missing_features).

    Excepted lumps and lumps whose OSM buildings a pending mapped feature already lists are dropped.
    The rest are single-link clustered (cell_features.JOIN_GAP) and labelled by nearest street.
    Unmapped / outside-clip lumps get refs ['unmapped'] (footprint traced from aerial per PROCESS 2d-i).

    @param lumps: scan_cell() output (with 'osm')
    @param taken_refs: OSM refs already covered by missing_features items
    @param streets: OSMIndex.streets for naming
    @returns: [{'kind': 'lumps', 'label', 'street', 'refs', 'bbox'}]
    """
    from cell_features import _split_runs, _street_of
    taken = set(taken_refs)
    items = [{'bbox': tuple(lp['bbox']), 'refs': lp.get('osm') or [], 'cols': lp['columns']}
             for lp in lumps if 'exception' not in lp
             and not (lp.get('osm') and set(lp['osm']) <= taken)]
    out = []
    for run in sorted(_split_runs(items), key=lambda g: min(o['bbox'][:2] for o in g)):
        bbox = (min(o['bbox'][0] for o in run), min(o['bbox'][1] for o in run),
                max(o['bbox'][2] for o in run), max(o['bbox'][3] for o in run))
        refs = sorted({r for o in run for r in o['refs']})
        unmapped = sum(1 for o in run if not o['refs'])
        street = _street_of({}, bbox, streets)
        out.append({'kind': 'lumps', 'street': street, 'refs': refs or ['unmapped'], 'bbox': bbox,
                    'label': f'{street or "unnamed street"} ({len(run)} unrefined Geocraft building(s)'
                             + (f', {unmapped} not in OSM' if unmapped else '') + ')'})
    return out


def stage_path(tx: int, tz: int) -> Path:
    """@returns: path of the cell stage file"""
    return ROOT / 'site' / 'cells' / f'{tx}_{tz}-STAGES.json'


def recorded_exceptions(tx: int, tz: int) -> list:
    """@returns: stages.lump_sweep.exceptions from the cell stage file ([] if none)"""
    try:
        st = json.loads(stage_path(tx, tz).read_text())
    except (OSError, json.JSONDecodeError):
        return []
    return st.get('stages', {}).get('lump_sweep', {}).get('exceptions', [])


def scan_cell(tx: int, tz: int, bbox=None, with_osm: bool = True, idx=None) -> list:
    """Lump sweep of one cell (or a bbox inside it) against the live world.

    @param tx: cell X
    @param tz: cell Z
    @param bbox: optional (x0, z0, x1, z1) inclusive clip
    @param with_osm: also list the OSM buildings under each lump
    @param idx: optional shared osm_footprints.OSMIndex
    @returns: find_lumps() items with 'osm' and exceptions applied
    """
    from cell_features import feature_columns
    from coverage import cell_bbox
    from site_kit import World
    pristine_path = json.loads((ROOT / 'config/world.json').read_text())['pristine_region_path']
    x0, z0, x1, z1 = bbox or cell_bbox(tx, tz, tx, tz)
    cols = [(x, z) for x in range(x0, x1 + 1) for z in range(z0, z1 + 1)]
    lumps = find_lumps(cols, World(), World(pristine_path), feature_columns())
    if with_osm:
        from osm_footprints import OSMIndex
        idx = idx or OSMIndex()
        for lp in lumps:
            lp['osm'] = osm_under(lp, idx)
            cx, cz = lp['centre']
            lp['in_osm_clip'] = any(e[0] <= cx <= e[2] and e[1] <= cz <= e[3] for e in idx.extents)
    apply_exceptions(lumps, recorded_exceptions(tx, tz))
    return lumps


def summary(lumps: list) -> dict:
    """@returns: {'remaining': n unrecorded, 'excepted': n, 'unmapped': n with no OSM building, 'no_clip': n outside any OSM clip}"""
    rem = [lp for lp in lumps if 'exception' not in lp]
    return {'remaining': len(rem), 'excepted': len(lumps) - len(rem),
            'unmapped': sum(1 for lp in rem if not lp.get('osm', [1])),
            'no_clip': sum(1 for lp in rem if not lp.get('in_osm_clip', True))}


def _public(lp: dict) -> dict:
    return {k: v for k, v in lp.items() if k != 'cols'}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--cell', required=True, help='tx,tz')
    ap.add_argument('--bbox', help='x0,z0,x1,z1 clip inside the cell')
    ap.add_argument('--no-osm', action='store_true')
    ap.add_argument('--record', action='store_true', help='write stages.lump_sweep into the cell STAGES file')
    ap.add_argument('--json', action='store_true')
    a = ap.parse_args(argv)
    tx, tz = (int(v) for v in a.cell.split(','))
    bbox = tuple(int(v) for v in a.bbox.split(',')) if a.bbox else None
    lumps = scan_cell(tx, tz, bbox, with_osm=not a.no_osm)
    s = summary(lumps)
    if a.json:
        print(json.dumps({'cell': [tx, tz], **s, 'lumps': [_public(lp) for lp in lumps]}, indent=1))
    else:
        for i, lp in enumerate(lumps, 1):
            tag = f' EXCEPTION: {lp["exception"]}' if 'exception' in lp else ''
            osm = lp.get('osm')
            where = ('OSM ' + ','.join(osm)) if osm else (
                ('NO OSM CLIP here (osm_extract.py first)' if not lp.get('in_osm_clip', True)
                 else 'no OSM building (unmapped: build from aerial/Street View)') if osm is not None else '')
            print(f'lump {i}: bbox={lp["bbox"]} centre={lp["centre"]} cols={lp["columns"]} '
                  f'roof_y={lp["roof_y"][0]}..{lp["roof_y"][1]} height={lp["height"]} {where}{tag}')
        print(f'cell {tx},{tz}: {s["remaining"]} lump(s) remaining, {s["excepted"]} excepted, '
              f'{s["unmapped"]} without an OSM building ({s["no_clip"]} outside any OSM clip)')
    if a.record:
        from datetime import datetime
        path = stage_path(tx, tz)
        st = json.loads(path.read_text()) if path.exists() else {'cell': f'{tx},{tz}', 'stages': {}}
        old = st['stages'].get('lump_sweep', {})
        st['stages']['lump_sweep'] = {
            'status': 'verified' if not s['remaining'] else 'open',
            'remaining': s['remaining'], 'checked': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'exceptions': old.get('exceptions', []),
            'note': 'lump_scan.py: ' + (f'{s["excepted"]} recorded exception(s)' if s['excepted'] else 'no Geocraft lumps left')}
        path.write_text(json.dumps(st, indent=1) + '\n')
    return 1 if s['remaining'] else 0


if __name__ == '__main__':
    sys.exit(main())
