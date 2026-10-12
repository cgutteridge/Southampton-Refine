#!/usr/bin/env python3
"""Sparse spatial index for reference imagery (manifest.jsonl).

Files stay under reference/aerial|photos/<place>/. The manifest adds
query keys — never a folder-per-tile tree.

  MC tiles:  128×128 block cells  →  \"128:{tx}:{tz}\"   (sparse)
  WM tiles:  web-mercator XYZ     →  \"{z}/{x}/{y}\"     (aerial fetch unit)

  python3 scripts/ref_manifest.py add PATH --place SO173SF --kind aerial \\
      --source hampshire-hub --useful yes --models footprint,roof \\
      [--url URL] [--wm 18/130062/87838] [--at 6949,-5345] [--bbox x0,z0,x1,z1]
  python3 scripts/ref_manifest.py find --xz 6949,-5345 [--useful yes] [--place ID]
  python3 scripts/ref_manifest.py find --wm 18/130062/87838
  python3 scripts/ref_manifest.py list [--place SO173SF]
  python3 scripts/ref_manifest.py backfill   # upgrade existing lines with tiles
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import subprocess
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'scripts'))
from geodetic import wgs84_to_osgb  # noqa: E402
from osgb import to_mc, to_osgb  # noqa: E402

REF = ROOT / 'reference'
MANIFEST = REF / 'manifest.jsonl'
MC_TILE = 128


def sha256_file(path: Path) -> str:
    """Return hex SHA-256 of a file.

    @param path: file path
    @returns: hex digest
    """
    h = hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda: f.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


def mc_tile_id(x: int, z: int, size: int = MC_TILE) -> str:
    """Return sparse MC tile id covering block (x, z).

    @param x: Minecraft X
    @param z: Minecraft Z
    @param size: tile edge in blocks (default 128)
    @returns: e.g. \"128:54:-42\"
    """
    tx = math.floor(x / size)
    tz = math.floor(z / size)
    return f'{size}:{tx}:{tz}'


def mc_tiles_for_bbox(x0: int, z0: int, x1: int, z1: int, size: int = MC_TILE) -> list[str]:
    """All MC tile ids overlapping an inclusive XZ bbox.

    @param x0: min X
    @param z0: min Z
    @param x1: max X
    @param z1: max Z
    @param size: tile edge
    @returns: sorted unique tile ids
    """
    if x0 > x1:
        x0, x1 = x1, x0
    if z0 > z1:
        z0, z1 = z1, z0
    out = []
    for tx in range(math.floor(x0 / size), math.floor(x1 / size) + 1):
        for tz in range(math.floor(z0 / size), math.floor(z1 / size) + 1):
            out.append(f'{size}:{tx}:{tz}')
    return out


def deg2num(lat_deg: float, lon_deg: float, zoom: int) -> tuple[int, int]:
    """WGS84 → web-mercator tile indices.

    @param lat_deg: latitude
    @param lon_deg: longitude
    @param zoom: zoom level
    @returns: (xtile, ytile)
    """
    lat_rad = math.radians(lat_deg)
    n = 2.0 ** zoom
    xtile = int((lon_deg + 180.0) / 360.0 * n)
    ytile = int((1.0 - math.asinh(math.tan(lat_rad)) / math.pi) / 2.0 * n)
    return xtile, ytile


def num2deg(xtile: int, ytile: int, zoom: int) -> tuple[float, float]:
    """NW corner of a web-mercator tile → WGS84 lat/lon.

    @param xtile: tile X
    @param ytile: tile Y
    @param zoom: zoom level
    @returns: (lat, lon)
    """
    n = 2.0 ** zoom
    lon_deg = xtile / n * 360.0 - 180.0
    lat_rad = math.atan(math.sinh(math.pi * (1 - 2 * ytile / n)))
    return math.degrees(lat_rad), lon_deg


def wm_tile_bbox_mc(z: int, x: int, y: int) -> tuple[int, int, int, int]:
    """Minecraft inclusive XZ bbox covering a web-mercator tile.

    @param z: zoom
    @param x: tile X
    @param y: tile Y
    @returns: (x0, z0, x1, z1)
    """
    lat_nw, lon_nw = num2deg(x, y, z)
    lat_se, lon_se = num2deg(x + 1, y + 1, z)
    e_nw, n_nw = wgs84_to_osgb(lat_nw, lon_nw)
    e_se, n_se = wgs84_to_osgb(lat_se, lon_se)
    # also NE / SW for safety on axis alignment
    e_ne, n_ne = wgs84_to_osgb(lat_nw, lon_se)
    e_sw, n_sw = wgs84_to_osgb(lat_se, lon_nw)
    easts = [e_nw, e_se, e_ne, e_sw]
    norths = [n_nw, n_se, n_ne, n_sw]
    corners = [to_mc(e, n) for e, n in zip(easts, norths)]
    xs = [c[0] for c in corners]
    zs = [c[1] for c in corners]
    return min(xs), min(zs), max(xs), max(zs)


def parse_wm(s: str) -> tuple[int, int, int]:
    """Parse \"z/x/y\" web-mercator id.

    @param s: tile id
    @returns: (z, x, y)
    """
    z, x, y = s.strip().split('/')
    return int(z), int(x), int(y)


def load_manifest(path: Path = MANIFEST) -> list[dict]:
    """Load all manifest records.

    @param path: JSONL path
    @returns: list of dicts
    """
    if not path.exists():
        return []
    rows = []
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        rows.append(json.loads(line))
    return rows


def save_manifest(rows: list[dict], path: Path = MANIFEST) -> None:
    """Rewrite manifest JSONL (used by backfill).

    @param rows: records
    @param path: output path
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(''.join(json.dumps(r, separators=(',', ':')) + '\n' for r in rows))


def append_manifest(row: dict, path: Path = MANIFEST) -> None:
    """Append one record.

    @param row: record
    @param path: JSONL path
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('a') as f:
        f.write(json.dumps(row, separators=(',', ':')) + '\n')


def find_dup(rows: list[dict], url: str, sha: str) -> dict | None:
    """Return existing row with same url or sha256.

    @param rows: manifest
    @param url: remote URL or \"\"
    @param sha: file hash
    @returns: matching row or None
    """
    for r in rows:
        if sha and r.get('sha256') == sha:
            return r
        if url and r.get('url') == url:
            return r
    return None


def enrich_spatial(
    row: dict,
    *,
    wm: str | None = None,
    at: tuple[int, int] | None = None,
    bbox: tuple[int, int, int, int] | None = None,
) -> dict:
    """Fill wm_tiles / mc_tiles / bbox_mc on a row.

    @param row: manifest record (mutated and returned)
    @param wm: optional \"z/x/y\"
    @param at: optional MC point (x, z)
    @param bbox: optional MC bbox
    @returns: row
    """
    # Always recompute spatial fields from wm / path / at / bbox args.
    wm_tiles: list[str] = []
    bbox_mc = None
    path = row.get('path') or ''

    if wm:
        wm_tiles = [wm]

    # Infer centre wm from path/url aer-zZ-X-Y or /aer/Z/X/Y
    if not wm_tiles:
        blob = path + ' ' + (row.get('url') or '')
        m = re.search(r'(?:aer[-/]|/aer/)(?:z)?(\d+)[-/](\d+)[-/](\d+)', blob)
        if m:
            wm_tiles = [f'{m.group(1)}/{m.group(2)}/{m.group(3)}']
        else:
            m2 = re.search(r'mosaic-z(\d+)-(\d+)x(\d+)-centre-(\d+)-(\d+)', path)
            if m2:
                wm_tiles = [f'{m2.group(1)}/{m2.group(4)}/{m2.group(5)}']

    # Mosaic: N×N around named centre (size from path when present)
    if 'mosaic' in path and wm_tiles:
        z, cx, cy = parse_wm(wm_tiles[0])
        msize = re.search(r'mosaic-z\d+-(\d+)x(\d+)-centre-', path)
        n = int(msize.group(1)) if msize else 3
        if n < 1 or n % 2 == 0:
            n = 3
        half = n // 2
        offs = [(dx, dy) for dx in range(-half, half + 1) for dy in range(-half, half + 1)]
        wm_tiles = sorted(f'{z}/{cx + dx}/{cy + dy}' for dx, dy in offs)
        boxes = [wm_tile_bbox_mc(z, cx + dx, cy + dy) for dx, dy in offs]
        bbox_mc = [
            min(b[0] for b in boxes), min(b[1] for b in boxes),
            max(b[2] for b in boxes), max(b[3] for b in boxes),
        ]
    elif wm_tiles:
        bbox_mc = list(wm_tile_bbox_mc(*parse_wm(wm_tiles[0])))

    if bbox:
        bbox_mc = list(bbox)
    if at and bbox_mc is None:
        x, z = at
        bbox_mc = [x, z, x, z]

    mc_tiles: list[str] = []
    if bbox_mc is not None:
        x0, z0, x1, z1 = (int(v) for v in bbox_mc)
        mc_tiles = mc_tiles_for_bbox(x0, z0, x1, z1)
        bbox_mc = [x0, z0, x1, z1]

    row['wm_tiles'] = wm_tiles
    row['mc_tiles'] = mc_tiles
    row['bbox_mc'] = bbox_mc
    row['mc_tile_size'] = MC_TILE
    return row


def cmd_add(args: argparse.Namespace) -> int:
    """Add a file to the manifest (refuse duplicates).

    @param args: CLI args
    @returns: exit code
    """
    path = Path(args.path)
    if not path.is_file():
        # allow path relative to reference/
        alt = REF / args.path
        if alt.is_file():
            path = alt
        else:
            print(f'not a file: {args.path}', file=sys.stderr)
            return 2
    try:
        rel = str(path.resolve().relative_to(REF.resolve()))
    except ValueError:
        print('file must live under reference/', file=sys.stderr)
        return 2

    rows = load_manifest()
    sha = sha256_file(path)
    url = args.url or ''
    dup = find_dup(rows, url, sha)
    if dup:
        print(f'duplicate of {dup.get("id")} ({dup.get("path")}) — not added', file=sys.stderr)
        return 1

    models = [x for x in (args.models or '').split(',') if x]
    not_for = [x for x in (args.not_for or 'private_interior').split(',') if x]
    at = tuple(map(int, args.at.split(','))) if args.at else None
    bbox = tuple(map(int, args.bbox.split(','))) if args.bbox else None

    row = {
        'id': re.sub(r'[^a-zA-Z0-9]+', '-', rel).strip('-').lower(),
        'place': args.place,
        'path': rel,
        'kind': args.kind,
        'source': args.source,
        'url': url,
        'sha256': sha,
        'captured': args.captured or '',
        'added': str(date.today()),
        'useful': args.useful,
        'models': models,
        'not_for': not_for,
        'notes': args.notes or '',
    }
    enrich_spatial(row, wm=args.wm, at=at, bbox=bbox)
    append_manifest(row)
    print(json.dumps({k: row[k] for k in ('id', 'path', 'useful', 'wm_tiles', 'mc_tiles', 'bbox_mc')}, indent=2))
    return 0


def cmd_find(args: argparse.Namespace) -> int:
    """Find manifest rows by MC point, WM tile, place, and/or useful.

    @param args: CLI args
    @returns: exit code
    """
    rows = load_manifest()
    want_tiles = set()
    if args.xz:
        x, z = map(int, args.xz.split(','))
        want_tiles.add(mc_tile_id(x, z))
    if args.wm:
        # rows that list this wm tile
        pass

    out = []
    for r in rows:
        if args.place and r.get('place') != args.place:
            continue
        if args.useful and r.get('useful') != args.useful:
            continue
        if args.wm and args.wm not in (r.get('wm_tiles') or []):
            continue
        if want_tiles and not want_tiles.intersection(r.get('mc_tiles') or []):
            continue
        out.append(r)

    for r in out:
        print(f"{r.get('useful','?'):5} {r.get('path','')}  models={r.get('models')}  "
              f"wm={r.get('wm_tiles')}  mc_tiles={len(r.get('mc_tiles') or [])}  notes={r.get('notes','')[:60]}")
    print(f'# {len(out)} matches', file=sys.stderr)
    return 0


def cmd_list(args: argparse.Namespace) -> int:
    """Compact listing.

    @param args: CLI args
    @returns: exit code
    """
    rows = load_manifest()
    if args.place:
        rows = [r for r in rows if r.get('place') == args.place]
    for r in rows:
        print(f"{r.get('useful','?'):5} {r.get('place','?'):8} {r.get('path','')}")
    return 0


def cmd_backfill(_args: argparse.Namespace) -> int:
    """Recompute spatial fields on every existing line.

    @param _args: unused
    @returns: exit code
    """
    rows = load_manifest()
    for r in rows:
        # Photos without coords: leave mc_tiles empty unless place seed known
        enrich_spatial(r)
        if not r.get('mc_tiles') and r.get('place') == 'SO173SF':
            # postcode mean as weak point index for street photos
            enrich_spatial(r, at=to_mc(443197, 114953))
    save_manifest(rows)
    print(f'backfilled {len(rows)} rows -> {MANIFEST}')
    return 0


def main(argv: list[str] | None = None) -> int:
    """CLI entry.

    @param argv: optional argv
    @returns: exit code
    """
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest='cmd', required=True)

    a = sub.add_parser('add', help='append a reference file')
    a.add_argument('path')
    a.add_argument('--place', required=True)
    a.add_argument('--kind', required=True, choices=['aerial', 'street', 'facade', 'detail', 'map', 'other'])
    a.add_argument('--source', required=True)
    a.add_argument('--useful', required=True, choices=['yes', 'maybe', 'no'])
    a.add_argument('--models', default='')
    a.add_argument('--not-for', dest='not_for', default='private_interior')
    a.add_argument('--url', default='')
    a.add_argument('--wm', default=None, help='web-mercator z/x/y')
    a.add_argument('--at', default=None, help='MC x,z point')
    a.add_argument('--bbox', default=None, help='MC x0,z0,x1,z1')
    a.add_argument('--captured', default='')
    a.add_argument('--notes', default='')
    a.set_defaults(func=cmd_add)

    f = sub.add_parser('find', help='query by tile / place')
    f.add_argument('--xz', help='MC x,z')
    f.add_argument('--wm', help='web-mercator z/x/y')
    f.add_argument('--place')
    f.add_argument('--useful', choices=['yes', 'maybe', 'no'])
    f.set_defaults(func=cmd_find)

    l = sub.add_parser('list', help='compact list')
    l.add_argument('--place')
    l.set_defaults(func=cmd_list)

    b = sub.add_parser('backfill', help='add tile fields to existing rows')
    b.set_defaults(func=cmd_backfill)

    args = p.parse_args(argv)
    return args.func(args)


if __name__ == '__main__':
    raise SystemExit(main())
