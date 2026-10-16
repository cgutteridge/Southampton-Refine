#!/usr/bin/env python3
"""Fetch Southampton Tree Preservation Order (TPO) tree points for a map area.

The council TPO *map page* embeds a third-party ArcGIS Experience (Wigan BC);
authoritative Southampton geometry is published via planning.data.gov.uk and
GeoServer WFS (see reference/SOURCES.txt §G).

National tree.csv (org 318) has ~4.5k protected tree points with geometry but
tree-species is currently empty for Southampton — use reference/tpo/species-
overrides.jsonl to record species from TPO PDF schedules or local WFS columns.

  python3 scripts/tpo_fetch.py --at 5652,-2492 --radius-m 250 --place CHAMBERLAIN
  python3 scripts/tpo_fetch.py --bbox-mc 5600,-2520,5720,-2440 --out verification/site/tpo-chamberlain.json
  python3 scripts/tpo_fetch.py --bbox-wgs -1.405,50.935,-1.395,50.942 --dry-run
  python3 scripts/tpo_fetch.py --warm-cache          # download + build index once
  python3 scripts/tpo_fetch.py --refresh-cache       # force re-download

Requires: gdaltransform on PATH for WGS84→OSGB. Cached under reference/tpo/cache/
(gitignored).
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from script_env import ROOT  # noqa: E402
from osgb import load_offsets, to_mc, to_osgb  # noqa: E402

REF = ROOT / 'reference' / 'tpo'
CACHE_DIR = REF / 'cache'
CSV_CACHE = CACHE_DIR / 'planning-tree.csv'
CSV_META = CACHE_DIR / 'planning-tree.meta.json'
STH_INDEX = CACHE_DIR / 'southampton-trees.jsonl'
INDEX_META = CACHE_DIR / 'southampton-trees.meta.json'
SPECIES_OVERRIDES = REF / 'species-overrides.jsonl'
TREE_CSV_URL = 'https://files.planning.data.gov.uk/dataset/tree.csv'
SOUTHAMPTON_ORG_ENTITY = '318'
DEFAULT_CACHE_MAX_AGE_DAYS = 7
USER_AGENT = 'Southampton-Refine/tpo_fetch'

WFS_TREES = (
    'https://www.southampton.gov.uk/geoserver/Data/ows'
    '?service=WFS&version=1.0.0&request=GetFeature'
    '&typeName=Data:TPOS_TREES_DATA_EXT&outputFormat=application/json'
    '&srsName=EPSG:4326'
)
WFS_ZONES = (
    'https://www.southampton.gov.uk/geoserver/Data/ows'
    '?service=WFS&version=1.0.0&request=GetFeature'
    '&typeName=Data:TPOS_DATA_EXT&outputFormat=application/json'
    '&srsName=EPSG:4326'
)

POINT_RE = re.compile(
    r'POINT\s*\(\s*([-\d.]+)\s+([-\d.]+)\s*\)',
    re.IGNORECASE,
)

# Heuristic Minecraft crown for build scripts (not botanical truth).
SPECIES_CRAFT: dict[str, str] = {
    'oak': 'oak',
    'english oak': 'oak',
    'sessile oak': 'oak',
    'beech': 'oak',
    'ash': 'oak',
    'sycamore': 'birch',
    'maple': 'birch',
    'acer': 'birch',
    'birch': 'birch',
    'silver birch': 'birch',
    'cherry': 'birch',
    'prunus': 'birch',
    'apple': 'birch',
    'pear': 'birch',
    'cedar': 'spruce',
    'cedrus': 'spruce',
    'pine': 'spruce',
    'spruce': 'spruce',
    'yew': 'spruce',
    'holly': 'spruce',
    'walnut': 'oak',
    'lime': 'oak',
    'linden': 'oak',
    'horse chestnut': 'oak',
    'chestnut': 'oak',
    'willow': 'birch',
    'poplar': 'birch',
    'elm': 'oak',
}


def parse_wkt_point(wkt: str) -> tuple[float, float] | None:
    """Parse a WKT POINT (lon lat) in WGS84.

    @param wkt: e.g. ``POINT (-1.403580 50.941869)``
    @returns: (longitude, latitude) or None if unparseable
    """
    m = POINT_RE.search(wkt or '')
    if not m:
        return None
    return float(m.group(1)), float(m.group(2))


def wgs_to_mc(lon: float, lat: float) -> tuple[int, int]:
    """Convert WGS84 lon/lat to Minecraft X/Z via OSGB36.

    @param lon: longitude (degrees)
    @param lat: latitude (degrees)
    @returns: (x, z) block coordinates
    """
    return wgs_batch_to_mc([(lon, lat)])[0]


def wgs_batch_to_mc(points: list[tuple[float, float]]) -> list[tuple[int, int]]:
    """Convert many WGS84 points to Minecraft X/Z in one gdaltransform call.

    @param points: list of (lon, lat)
    @returns: list of (x, z) in the same order
    """
    if not points:
        return []
    inp = ''.join(f'{lon} {lat}\n' for lon, lat in points).encode()
    out = subprocess.run(
        ['gdaltransform', '-s_srs', 'EPSG:4326', '-t_srs', 'EPSG:27700'],
        input=inp,
        capture_output=True,
        check=True,
    )
    mc: list[tuple[int, int]] = []
    for line in out.stdout.decode().splitlines():
        parts = line.split()
        if len(parts) < 2:
            continue
        mc.append(to_mc(float(parts[0]), float(parts[1])))
    if len(mc) != len(points):
        raise RuntimeError(f'gdaltransform returned {len(mc)} points for {len(points)} inputs')
    return mc


def craft_for_species(species: str | None) -> str | None:
    """Map a free-text species label to a coarse Minecraft tree family.

    @param species: e.g. ``Beech``, ``English Oak``
    @returns: ``oak`` | ``birch`` | ``spruce`` or None if unknown/empty
    """
    if not species or not species.strip():
        return None
    key = species.strip().lower()
    if key in SPECIES_CRAFT:
        return SPECIES_CRAFT[key]
    for frag, craft in SPECIES_CRAFT.items():
        if frag in key:
            return craft
    return None


def load_species_overrides(path: Path = SPECIES_OVERRIDES) -> dict[str, str]:
    """Load manual species keyed by TPO tree reference.

    @param path: JSONL with ``reference`` and ``species`` per line
    @returns: reference → species text
    """
    if not path.is_file():
        return {}
    out: dict[str, str] = {}
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        row = json.loads(line)
        ref = (row.get('reference') or '').strip()
        sp = (row.get('species') or '').strip()
        if ref and sp:
            out[ref] = sp
    return out


def _in_wgs_bbox(lon: float, lat: float, bbox: tuple[float, float, float, float]) -> bool:
    lon0, lat0, lon1, lat1 = bbox
    return lon0 <= lon <= lon1 and lat0 <= lat <= lat1


def _in_mc_bbox(x: int, z: int, bbox: tuple[int, int, int, int]) -> bool:
    x0, z0, x1, z1 = bbox
    return x0 <= x <= x1 and z0 <= z <= z1


def resolve_bbox(args: argparse.Namespace) -> tuple[tuple[float, float, float, float], str]:
    """Resolve CLI area to WGS84 bbox and a short label.

    @param args: parsed CLI namespace
    @returns: ((lon0, lat0, lon1, lat1), label)
    """
    if args.bbox_wgs:
        parts = [float(p) for p in args.bbox_wgs.split(',')]
        if len(parts) != 4:
            raise SystemExit('--bbox-wgs needs lon0,lat0,lon1,lat1')
        return (parts[0], parts[1], parts[2], parts[3]), 'bbox-wgs'

    if args.bbox_mc:
        parts = [int(float(p)) for p in args.bbox_mc.split(',')]
        if len(parts) != 4:
            raise SystemExit('--bbox-mc needs x0,z0,x1,z1')
        x0, z0, x1, z1 = parts
        corners = [(x0, z0), (x1, z0), (x0, z1), (x1, z1)]
        lons, lats = [], []
        for x, z in corners:
            e, n = to_osgb(x, z)
            inp = f'{e} {n}\n'.encode()
            out = subprocess.run(
                ['gdaltransform', '-s_srs', 'EPSG:27700', '-t_srs', 'EPSG:4326'],
                input=inp,
                capture_output=True,
                check=True,
            )
            lon, lat = map(float, out.stdout.decode().strip().split())
            lons.append(lon)
            lats.append(lat)
        return (min(lons), min(lats), max(lons), max(lats)), 'bbox-mc'

    if args.at:
        x_s, z_s = args.at.split(',')
        x, z = int(float(x_s)), int(float(z_s))
        r = args.radius_m
        x0, z0, x1, z1 = int(x - r), int(z - r), int(x + r), int(z + r)
        ns = argparse.Namespace(bbox_mc=f'{x0},{z0},{x1},{z1}')
        return resolve_bbox(ns)

    raise SystemExit('need --at, --bbox-mc, or --bbox-wgs')


def _csv_file_key(path: Path) -> str:
    """Return a stable cache-invalidation key for a cached CSV file.

    @param path: path to the CSV on disk
    @returns: ``mtime:size`` string
    """
    st = path.stat()
    return f'{int(st.st_mtime)}:{st.st_size}'


def _read_json(path: Path) -> dict[str, Any]:
    """Load a JSON object from disk.

    @param path: file path
    @returns: parsed dict (empty if missing)
    """
    if not path.is_file():
        return {}
    return json.loads(path.read_text())


def download_planning_tree_csv(
    dest: Path = CSV_CACHE,
    url: str = TREE_CSV_URL,
) -> dict[str, Any]:
    """Download the national planning.data tree.csv into ``dest``.

    @param dest: output CSV path
    @param url: bulk dataset URL
    @returns: metadata dict (url, fetched_at, etag, size, sha256, …)
    """
    dest.parent.mkdir(parents=True, exist_ok=True)
    req = urllib.request.Request(url, headers={'User-Agent': USER_AGENT})
    with urllib.request.urlopen(req, timeout=300) as resp:
        data = resp.read()
    dest.write_bytes(data)
    digest = hashlib.sha256(data).hexdigest()
    meta: dict[str, Any] = {
        'url': url,
        'fetched_at': datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),
        'size': len(data),
        'sha256': digest,
        'etag': resp.headers.get('ETag'),
        'last_modified': resp.headers.get('Last-Modified'),
    }
    CSV_META.write_text(json.dumps(meta, indent=2) + '\n')
    return meta


def ensure_planning_tree_csv(
    force: bool = False,
    max_age_days: int = DEFAULT_CACHE_MAX_AGE_DAYS,
    url: str = TREE_CSV_URL,
) -> Path:
    """Return path to cached planning.data tree.csv, refreshing when stale.

    @param force: re-download even if cache looks fresh
    @param max_age_days: max age before automatic refresh
    @param url: bulk dataset URL
    @returns: path to local CSV cache
    """
    meta = _read_json(CSV_META)
    if CSV_CACHE.is_file() and not force:
        age_ok = True
        fetched = meta.get('fetched_at')
        if fetched:
            try:
                ts = datetime.strptime(fetched, '%Y-%m-%dT%H:%M:%SZ').replace(tzinfo=timezone.utc)
                age_ok = (datetime.now(timezone.utc) - ts).days < max_age_days
            except ValueError:
                age_ok = False
        else:
            age_ok = (time.time() - CSV_CACHE.stat().st_mtime) < max_age_days * 86400
        if age_ok:
            return CSV_CACHE
    print(f'downloading {url} → {CSV_CACHE}', file=sys.stderr)
    download_planning_tree_csv(CSV_CACHE, url)
    return CSV_CACHE


def _tree_record_from_row(
    row: dict[str, str],
    lon: float,
    lat: float,
    x: int,
    z: int,
) -> dict[str, Any]:
    """Build one indexed tree dict from CSV row and coordinates.

    @param row: CSV dict row
    @param lon: WGS84 longitude
    @param lat: WGS84 latitude
    @param x: Minecraft X
    @param z: Minecraft Z
    @returns: index record
    """
    return {
        'reference': row.get('reference') or '',
        'name': row.get('name') or '',
        'tree_preservation_order': row.get('tree-preservation-order') or '',
        'address_text': row.get('address-text') or '',
        'tree_species': (row.get('tree-species') or '').strip(),
        'entity': row.get('entity') or '',
        'lon': lon,
        'lat': lat,
        'x': x,
        'z': z,
    }


def build_southampton_index(
    csv_path: Path = CSV_CACHE,
    org_entity: str = SOUTHAMPTON_ORG_ENTITY,
    index_path: Path = STH_INDEX,
) -> int:
    """Build JSONL index of all Southampton TPO trees with MC coordinates.

    @param csv_path: cached national tree.csv
    @param org_entity: organisation-entity id (318 = Southampton)
    @param index_path: output JSONL path
    @returns: number of trees written
    """
    csv.field_size_limit(10**7)
    index_path.parent.mkdir(parents=True, exist_ok=True)
    pending_rows: list[dict[str, str]] = []
    pending_pts: list[tuple[float, float]] = []
    count = 0
    batch = 500

    def flush_batch(outfh) -> None:
        nonlocal count
        if not pending_rows:
            return
        mc_pts = wgs_batch_to_mc(pending_pts)
        for row, (lon, lat), (x, z) in zip(pending_rows, pending_pts, mc_pts, strict=True):
            rec = _tree_record_from_row(row, lon, lat, x, z)
            outfh.write(json.dumps(rec, separators=(',', ':')) + '\n')
            count += 1
        pending_rows.clear()
        pending_pts.clear()

    with csv_path.open(newline='', encoding='utf-8') as fh, index_path.open('w', encoding='utf-8') as out:
        for row in csv.DictReader(fh):
            if row.get('organisation-entity') != org_entity:
                continue
            pt = parse_wkt_point(row.get('point') or '')
            if not pt:
                continue
            pending_rows.append(row)
            pending_pts.append(pt)
            if len(pending_rows) >= batch:
                flush_batch(out)
        flush_batch(out)
    INDEX_META.write_text(
        json.dumps(
            {
                'csv_key': _csv_file_key(csv_path),
                'org_entity': org_entity,
                'count': count,
                'built_at': date.today().isoformat(),
            },
            indent=2,
        )
        + '\n'
    )
    return count


def ensure_southampton_index(
    csv_path: Path,
    force: bool = False,
    org_entity: str = SOUTHAMPTON_ORG_ENTITY,
) -> Path:
    """Return JSONL index path, rebuilding from CSV when the cache is stale.

    @param csv_path: cached national tree.csv
    @param force: rebuild even if index matches CSV
    @param org_entity: organisation-entity id
    @returns: path to southampton-trees.jsonl
    """
    key = _csv_file_key(csv_path)
    imeta = _read_json(INDEX_META)
    if (
        STH_INDEX.is_file()
        and not force
        and imeta.get('csv_key') == key
        and imeta.get('org_entity') == org_entity
    ):
        return STH_INDEX
    print(f'building Southampton index from {csv_path.name}…', file=sys.stderr)
    n = build_southampton_index(csv_path, org_entity=org_entity)
    print(f'  indexed {n} trees → {STH_INDEX}', file=sys.stderr)
    return STH_INDEX


def trees_in_bbox_from_index(
    bbox_wgs: tuple[float, float, float, float],
    index_path: Path = STH_INDEX,
) -> list[dict[str, Any]]:
    """Load TPO tree records whose WGS point falls inside ``bbox_wgs``.

    @param bbox_wgs: (lon0, lat0, lon1, lat1)
    @param index_path: southampton-trees.jsonl from ``ensure_southampton_index``
    @returns: tree property dicts (includes x, z)
    """
    out: list[dict[str, Any]] = []
    with index_path.open(encoding='utf-8') as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)
            lon, lat = float(rec['lon']), float(rec['lat'])
            if _in_wgs_bbox(lon, lat, bbox_wgs):
                out.append(rec)
    return out


def stream_planning_trees(
    bbox_wgs: tuple[float, float, float, float],
    org_entity: str = SOUTHAMPTON_ORG_ENTITY,
    csv_url: str = TREE_CSV_URL,
    refresh_cache: bool = False,
) -> list[dict[str, Any]]:
    """Return planning.data TPO trees in ``bbox_wgs`` using local cache + index.

    @param bbox_wgs: (lon0, lat0, lon1, lat1)
    @param org_entity: organisation-entity id (318 = Southampton)
    @param csv_url: bulk dataset URL (used when refreshing cache)
    @param refresh_cache: force CSV re-download and index rebuild
    @returns: list of feature property dicts with x/z added
    """
    csv_path = ensure_planning_tree_csv(force=refresh_cache, url=csv_url)
    index_path = ensure_southampton_index(csv_path, force=refresh_cache, org_entity=org_entity)
    return trees_in_bbox_from_index(bbox_wgs, index_path)


def warm_planning_cache(refresh: bool = False) -> None:
    """Download national CSV (if needed) and build the Southampton JSONL index.

    @param refresh: force re-download and index rebuild
    """
    csv_path = ensure_planning_tree_csv(force=refresh)
    ensure_southampton_index(csv_path, force=refresh)


def fetch_wfs_geojson(base_url: str, bbox_wgs: tuple[float, float, float, float]) -> dict[str, Any]:
    """GET GeoServer WFS JSON for a WGS84 bounding box (may be bot-blocked).

    @param base_url: WFS GetFeature URL without bbox filter
    @param bbox_wgs: (lon0, lat0, lon1, lat1)
    @returns: parsed GeoJSON FeatureCollection dict
    """
    lon0, lat0, lon1, lat1 = bbox_wgs
    bbox = f'{lon0},{lat0},{lon1},{lat1}'
    url = f'{base_url}&bbox={bbox},EPSG:4326'
    req = urllib.request.Request(url, headers={'User-Agent': USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            raw = resp.read()
    except urllib.error.HTTPError as exc:
        raise SystemExit(f'WFS HTTP {exc.code}: {exc.reason}') from exc
    if raw[:15].lower().startswith(b'<html'):
        raise SystemExit(
            'GeoServer returned HTML (often Incapsula). Run this script from a '
            'home network/browser session, or use --source planning (default).'
        )
    return json.loads(raw.decode('utf-8'))


def merge_species(
    trees: list[dict[str, Any]], overrides: dict[str, str]
) -> None:
    """Attach species and craft hints onto tree dicts in place.

    @param trees: feature property lists from stream_planning_trees
    @param overrides: reference → species from species-overrides.jsonl
    """
    for t in trees:
        ref = t.get('reference') or ''
        sp = t.get('tree_species') or overrides.get(ref) or ''
        t['tree_species'] = sp
        t['craft_tree'] = craft_for_species(sp)


def build_geojson(trees: list[dict[str, Any]]) -> dict[str, Any]:
    """Build a GeoJSON FeatureCollection from tree property dicts.

    @param trees: list with x, z, lon, lat and metadata
    @returns: GeoJSON dict
    """
    feats = []
    for t in trees:
        feats.append(
            {
                'type': 'Feature',
                'geometry': {'type': 'Point', 'coordinates': [t['lon'], t['lat']]},
                'properties': {k: v for k, v in t.items() if k not in ('lon', 'lat')},
            }
        )
    return {'type': 'FeatureCollection', 'features': feats}


def main(argv: list[str] | None = None) -> int:
    """CLI entry."""
    p = argparse.ArgumentParser(description=__doc__)
    g = p.add_mutually_exclusive_group(required=False)
    g.add_argument('--at', help='MC x,z centre (with --radius-m)')
    g.add_argument('--bbox-mc', help='MC bbox x0,z0,x1,z1')
    g.add_argument('--bbox-wgs', help='WGS84 bbox lon0,lat0,lon1,lat1')
    g.add_argument(
        '--warm-cache',
        action='store_true',
        help='Download CSV + build Southampton index only (no bbox query)',
    )
    p.add_argument('--radius-m', type=float, default=200.0, help='With --at (blocks)')
    p.add_argument(
        '--source',
        choices=('planning', 'geoserver'),
        default='planning',
        help='planning.data CSV (default) or council GeoServer WFS',
    )
    p.add_argument(
        '--refresh-cache',
        action='store_true',
        help='Force re-download of tree.csv and rebuild of local index',
    )
    p.add_argument('--place', help='Place id for default output path under reference/tpo/')
    p.add_argument('--out', type=Path, help='Output GeoJSON path')
    p.add_argument('--dry-run', action='store_true', help='Print counts only')
    args = p.parse_args(argv)

    load_offsets()

    if args.warm_cache:
        warm_planning_cache(refresh=args.refresh_cache)
        imeta = _read_json(INDEX_META)
        print(f"cache ready: {STH_INDEX} ({imeta.get('count', '?')} trees)")
        return 0

    if not (args.at or args.bbox_mc or args.bbox_wgs):
        raise SystemExit('need --at, --bbox-mc, --bbox-wgs, or --warm-cache')

    bbox_wgs, label = resolve_bbox(args)
    overrides = load_species_overrides()

    if args.source == 'geoserver':
        data = fetch_wfs_geojson(WFS_TREES, bbox_wgs)
        trees = []
        for feat in data.get('features') or []:
            geom = feat.get('geometry') or {}
            coords = geom.get('coordinates') or []
            if len(coords) < 2:
                continue
            lon, lat = float(coords[0]), float(coords[1])
            props = feat.get('properties') or {}
            x, z = wgs_to_mc(lon, lat)
            ref = str(props.get('reference') or props.get('REFERENCE') or '')
            sp = (
                props.get('tree-species')
                or props.get('TREE_SPECIES')
                or props.get('SPECIES')
                or props.get('DESCRIPTIO')
                or ''
            )
            if isinstance(sp, str):
                sp = sp.strip()
            trees.append(
                {
                    'reference': ref,
                    'name': str(props.get('name') or props.get('NAME') or ''),
                    'tree_preservation_order': str(
                        props.get('tree-preservation-order')
                        or props.get('TPO_REF')
                        or ''
                    ),
                    'address_text': str(props.get('address-text') or props.get('ADDRESS') or ''),
                    'tree_species': sp if isinstance(sp, str) else '',
                    'raw_properties': props,
                    'lon': lon,
                    'lat': lat,
                    'x': x,
                    'z': z,
                }
            )
    else:
        trees = stream_planning_trees(bbox_wgs, refresh_cache=args.refresh_cache)

    merge_species(trees, overrides)
    with_species = sum(1 for t in trees if t.get('tree_species'))
    with_craft = sum(1 for t in trees if t.get('craft_tree'))

    print(
        f'TPO trees in {label} ({bbox_wgs[0]:.5f},{bbox_wgs[1]:.5f}..'
        f'{bbox_wgs[2]:.5f},{bbox_wgs[3]:.5f}): {len(trees)}'
    )
    print(f'  with species (CSV + overrides): {with_species}')
    print(f'  with craft mapping: {with_craft}')

    if args.dry_run:
        return 0

    out = args.out
    if not out and args.place:
        REF.mkdir(parents=True, exist_ok=True)
        slug = re.sub(r'[^a-z0-9]+', '-', args.place.lower()).strip('-')
        out = REF / f'trees-{slug}.geojson'
    if not out:
        raise SystemExit('use --out or --place for output path')

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(build_geojson(trees), indent=2) + '\n')
    print(f'wrote {out}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
