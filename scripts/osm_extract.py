#!/usr/bin/env python3
"""Extract place-scoped OSM clips from a local Geofabrik PBF (no tile tree).

Uses GDAL/ogr2ogr (osmium-tool is optional; currently broken vs Homebrew
boost on this machine). One GeoJSON per extract under reference/osm/<place>/,
indexed via ref_manifest sparse mc_tiles — never folder-per-tile.

Default PBF: downloads/hampshire-latest.osm.pbf

  python3 scripts/osm_extract.py --at 7097,-5521 --radius-m 200 \\
      --layers buildings --place PORTSWOOD_X_BROADLANDS --add
  python3 scripts/osm_extract.py --bbox-mc 7040,-5568,7167,-5441 \\
      --layers buildings,highways --place PORTSWOOD_X_BROADLANDS
  python3 scripts/osm_extract.py --osgb 443345,115129 --radius-m 150 \\
      --layers buildings --place PORTSWOOD_X_BROADLANDS --dry-run
  python3 scripts/osm_extract.py --bbox-wgs -1.386,50.932,-1.383,50.935 \\
      --layers highways --dir osm/portswood-x-broadlands

Presets (--layers): buildings | highways | railway | waterway | water |
landuse | amenity | shops  (comma-separated). Use --gdal-layer + --where
for a custom GDAL OSM layer query.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

from script_env import ROOT  # noqa: E402
from geodetic import osgb_to_wgs84  # noqa: E402
from osgb import to_mc, to_osgb  # noqa: E402
import ref_manifest  # noqa: E402
from ref_manifest import (  # noqa: E402
    find_dup,
    load_manifest,
    mc_tiles_for_bbox,
    sha256_file,
)

REF = ROOT / 'reference'
DEFAULT_PBF = ROOT / 'downloads' / 'hampshire-latest.osm.pbf'
SOURCE_TAG = 'geofabrik-hampshire'
PBF_URL = (
    'https://download.geofabrik.de/europe/united-kingdom/england/'
    'hampshire-latest.osm.pbf'
)

# name → list of (gdal_layer, SQL WHERE, default model tags)
LAYER_PRESETS: dict[str, list[tuple[str, str, list[str]]]] = {
    'buildings': [
        (
            'multipolygons',
            "building IS NOT NULL AND building <> ''",
            ['footprint'],
        ),
    ],
    'highways': [
        (
            'lines',
            "highway IS NOT NULL AND highway <> ''",
            ['context'],
        ),
    ],
    'railway': [
        (
            'lines',
            "railway IS NOT NULL AND railway <> ''",
            ['context'],
        ),
    ],
    'waterway': [
        (
            'lines',
            "waterway IS NOT NULL AND waterway <> ''",
            ['landscape'],
        ),
    ],
    'water': [
        (
            'multipolygons',
            "natural = 'water'",
            ['landscape'],
        ),
    ],
    'landuse': [
        (
            'multipolygons',
            "landuse IS NOT NULL AND landuse <> ''",
            ['landscape'],
        ),
    ],
    'amenity': [
        (
            'points',
            "amenity IS NOT NULL AND amenity <> ''",
            ['context'],
        ),
        (
            'multipolygons',
            "amenity IS NOT NULL AND amenity <> ''",
            ['context'],
        ),
    ],
    'shops': [
        (
            'points',
            "shop IS NOT NULL AND shop <> ''",
            ['context'],
        ),
        (
            'multipolygons',
            "shop IS NOT NULL AND shop <> ''",
            ['context'],
        ),
    ],
}


def mc_bbox_to_wgs84_spat(
    x0: int, z0: int, x1: int, z1: int,
) -> tuple[float, float, float, float]:
    """Minecraft inclusive XZ bbox → ogr2ogr -spat lon_min lat_min lon_max lat_max.

    @param x0: min MC X
    @param z0: min MC Z
    @param x1: max MC X
    @param z1: max MC Z
    @returns: (lon_min, lat_min, lon_max, lat_max)
    """
    if x0 > x1:
        x0, x1 = x1, x0
    if z0 > z1:
        z0, z1 = z1, z0
    corners = [
        to_osgb(x0, z0),
        to_osgb(x1, z0),
        to_osgb(x0, z1),
        to_osgb(x1, z1),
    ]
    lats: list[float] = []
    lons: list[float] = []
    for e, n in corners:
        lat, lon = osgb_to_wgs84(e, n)
        lats.append(lat)
        lons.append(lon)
    return min(lons), min(lats), max(lons), max(lats)


def radius_bbox_mc(x: int, z: int, radius_m: float) -> tuple[int, int, int, int]:
    """Axis-aligned MC bbox for a metre radius around a block (Geocraft ≈ 1 m/block).

    @param x: centre MC X
    @param z: centre MC Z
    @param radius_m: half-edge in metres (blocks)
    @returns: inclusive (x0, z0, x1, z1)
    """
    r = max(1, int(round(radius_m)))
    return x - r, z - r, x + r, z + r


def cell_bbox_mc(x: int, z: int, size: int = 128) -> tuple[int, int, int, int]:
    """128² MC cell containing (x, z).

    @param x: MC X
    @param z: MC Z
    @param size: cell edge (default 128)
    @returns: inclusive (x0, z0, x1, z1)
    """
    import math

    tx = math.floor(x / size)
    tz = math.floor(z / size)
    return tx * size, tz * size, tx * size + size - 1, tz * size + size - 1


def resolve_bbox_mc(args: argparse.Namespace) -> tuple[int, int, int, int]:
    """Resolve CLI spatial args to an inclusive MC XZ bbox.

    @param args: parsed CLI
    @returns: (x0, z0, x1, z1)
    """
    if args.bbox_mc:
        parts = [int(p) for p in args.bbox_mc.split(',')]
        if len(parts) != 4:
            raise SystemExit('--bbox-mc needs x0,z0,x1,z1')
        x0, z0, x1, z1 = parts
        if x0 > x1:
            x0, x1 = x1, x0
        if z0 > z1:
            z0, z1 = z1, z0
        return x0, z0, x1, z1

    if args.bbox_wgs:
        parts = [float(p) for p in args.bbox_wgs.split(',')]
        if len(parts) != 4:
            raise SystemExit('--bbox-wgs needs lon0,lat0,lon1,lat1')
        lon0, lat0, lon1, lat1 = parts
        # convert four corners via OSGB for a safe MC hull
        from ref_manifest import wgs84_to_osgb

        corners = [
            wgs84_to_osgb(lat0, lon0),
            wgs84_to_osgb(lat0, lon1),
            wgs84_to_osgb(lat1, lon0),
            wgs84_to_osgb(lat1, lon1),
        ]
        mcs = [to_mc(e, n) for e, n in corners]
        xs = [c[0] for c in mcs]
        zs = [c[1] for c in mcs]
        return min(xs), min(zs), max(xs), max(zs)

    if args.at:
        x, z = (int(p) for p in args.at.split(','))
        if args.cell:
            return cell_bbox_mc(x, z)
        return radius_bbox_mc(x, z, args.radius_m)

    if args.osgb:
        e, n = (float(p) for p in args.osgb.split(','))
        x, z = to_mc(e, n)
        if args.cell:
            return cell_bbox_mc(x, z)
        return radius_bbox_mc(x, z, args.radius_m)

    raise SystemExit('need --at, --osgb, --bbox-mc, or --bbox-wgs')


def resolve_queries(
    args: argparse.Namespace,
) -> list[tuple[str, str, str, list[str]]]:
    """Expand --layers / custom flags into extract jobs.

    @param args: parsed CLI
    @returns: list of (label, gdal_layer, where_sql, models)
    """
    if args.gdal_layer:
        where = args.where or '1=1'
        label = args.gdal_layer
        models = [x for x in (args.models or 'context').split(',') if x]
        return [(label, args.gdal_layer, where, models)]

    names = [n.strip().lower() for n in (args.layers or 'buildings').split(',') if n.strip()]
    if not names:
        raise SystemExit('need --layers or --gdal-layer')
    jobs: list[tuple[str, str, str, list[str]]] = []
    for name in names:
        if name not in LAYER_PRESETS:
            known = ', '.join(sorted(LAYER_PRESETS))
            raise SystemExit(f'unknown layer preset {name!r} (known: {known})')
        for gdal_layer, where, models in LAYER_PRESETS[name]:
            jobs.append((name, gdal_layer, where, list(models)))
    return jobs


def place_dir(args: argparse.Namespace) -> Path:
    """Resolve output directory under reference/.

    @param args: CLI with --dir or --place
    @returns: absolute path under reference/
    """
    if args.dir:
        rel = args.dir.strip().lstrip('/')
        if not rel.startswith('osm/'):
            rel = f'osm/{rel}'
        return REF / rel
    if args.place:
        slug = re.sub(r'[^a-z0-9]+', '-', args.place.lower()).strip('-')
        return REF / 'osm' / slug
    raise SystemExit('need --dir or --place')


def out_filename(
    layers: list[str],
    bbox_mc: tuple[int, int, int, int],
    *,
    cell: bool,
    radius_m: float | None,
) -> str:
    """Stable GeoJSON basename for an extract.

    @param layers: preset / layer labels
    @param bbox_mc: inclusive MC bbox
    @param cell: whether extract is a full 128 cell
    @param radius_m: radius used when centred (else None)
    @returns: filename under the place folder
    """
    layer_part = '+'.join(layers)
    x0, z0, x1, z1 = bbox_mc
    if cell:
        return f'{layer_part}-cell-{x0}-{z0}.geojson'
    if radius_m is not None and x1 - x0 == z1 - z0:
        cx = (x0 + x1) // 2
        cz = (z0 + z1) // 2
        r = int(round(radius_m))
        return f'{layer_part}-r{r}m-at-{cx}-{cz}.geojson'
    return f'{layer_part}-bbox-{x0}-{z0}-{x1}-{z1}.geojson'


def run_ogr2ogr(
    pbf: Path,
    out: Path,
    gdal_layer: str,
    where: str,
    spat: tuple[float, float, float, float],
) -> None:
    """Run ogr2ogr OSM → GeoJSON for one layer/query.

    @param pbf: source .osm.pbf
    @param out: destination .geojson
    @param gdal_layer: GDAL OSM layer name
    @param where: SQL WHERE clause
    @param spat: lon_min, lat_min, lon_max, lat_max
    """
    lon0, lat0, lon1, lat1 = spat
    cmd = [
        'ogr2ogr',
        '-f', 'GeoJSON',
        str(out),
        str(pbf),
        gdal_layer,
        '-spat', str(lon0), str(lat0), str(lon1), str(lat1),
        '-where', where,
        '-lco', 'COORDINATE_PRECISION=7',
        '-lco', 'WRITE_BBOX=YES',
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        err = (proc.stderr or proc.stdout or '').strip()
        raise RuntimeError(f'ogr2ogr failed ({proc.returncode}): {err[:800]}')


def merge_geojson(
    parts: list[tuple[str, Path]],
    out: Path,
    *,
    meta: dict,
) -> int:
    """Merge GeoJSON FeatureCollections; tag each feature with osm_layer.

    @param parts: (layer_label, path) pairs
    @param out: combined output path
    @param meta: top-level properties under \"southampton_refine\"
    @returns: feature count
    """
    features: list[dict] = []
    for label, path in parts:
        if not path.is_file() or path.stat().st_size == 0:
            continue
        data = json.loads(path.read_text())
        for feat in data.get('features') or []:
            props = feat.setdefault('properties', {})
            props['osm_layer'] = label
            features.append(feat)
    doc = {
        'type': 'FeatureCollection',
        'name': out.stem,
        'southampton_refine': meta,
        'features': features,
    }
    out.write_text(json.dumps(doc, separators=(',', ':')))
    return len(features)


def default_models(jobs: list[tuple[str, str, str, list[str]]]) -> str:
    """Comma-joined unique model tags from jobs.

    @param jobs: extract jobs
    @returns: models CSV
    """
    seen: list[str] = []
    for *_rest, models in jobs:
        for m in models:
            if m not in seen:
                seen.append(m)
    return ','.join(seen) if seen else 'context'


def cmd_extract(args: argparse.Namespace) -> int:
    """Extract (or dry-run) a place-scoped OSM clip.

    @param args: CLI args
    @returns: exit code
    """
    pbf = Path(args.pbf)
    if not pbf.is_file():
        print(f'missing PBF: {pbf}', file=sys.stderr)
        print(
            f'Download Hampshire (~59 MB):\n'
            f'  curl -fL -o {DEFAULT_PBF} {PBF_URL}',
            file=sys.stderr,
        )
        return 2

    try:
        bbox_mc = resolve_bbox_mc(args)
        jobs = resolve_queries(args)
    except SystemExit as e:
        print(e, file=sys.stderr)
        return 2

    spat = mc_bbox_to_wgs84_spat(*bbox_mc)
    out_dir = place_dir(args)
    layer_labels = []
    for label, *_ in jobs:
        if label not in layer_labels:
            layer_labels.append(label)

    radius_for_name: float | None = None
    if args.at or args.osgb:
        if not args.cell and not args.bbox_mc and not args.bbox_wgs:
            radius_for_name = float(args.radius_m)

    out = out_dir / out_filename(
        layer_labels, bbox_mc, cell=bool(args.cell), radius_m=radius_for_name,
    )

    print(f'pbf     {pbf}')
    print(f'bbox_mc {bbox_mc[0]},{bbox_mc[1]} → {bbox_mc[2]},{bbox_mc[3]}')
    print(
        f'spat    {spat[0]:.6f},{spat[1]:.6f} → {spat[2]:.6f},{spat[3]:.6f}'
    )
    print(f'layers  {", ".join(layer_labels)}')
    print(f'out     {out.relative_to(REF)}')
    for label, gdal_layer, where, _models in jobs:
        print(f'  {label}: {gdal_layer} WHERE {where}')

    if args.dry_run:
        return 0

    if out.is_file() and not args.force:
        print(f'exists: {out} (use --force)', file=sys.stderr)
        return 1

    out_dir.mkdir(parents=True, exist_ok=True)
    meta = {
        'source': SOURCE_TAG,
        'pbf': str(pbf.relative_to(ROOT)) if pbf.is_relative_to(ROOT) else str(pbf),
        'pbf_url': PBF_URL,
        'bbox_mc': list(bbox_mc),
        'spat_wgs84': list(spat),
        'layers': layer_labels,
        'place': args.place or '',
    }

    with tempfile.TemporaryDirectory(prefix='osm_extract_') as tmp:
        tmp_path = Path(tmp)
        parts: list[tuple[str, Path]] = []
        try:
            for i, (label, gdal_layer, where, _models) in enumerate(jobs):
                part = tmp_path / f'part-{i}-{label}-{gdal_layer}.geojson'
                print(f'extract {label}/{gdal_layer} …', flush=True)
                run_ogr2ogr(pbf, part, gdal_layer, where, spat)
                parts.append((label, part))
        except (RuntimeError, subprocess.CalledProcessError, FileNotFoundError) as e:
            print(f'failed: {e}', file=sys.stderr)
            return 2
        count = merge_geojson(parts, out, meta=meta)

    sha = sha256_file(out)
    print(f'wrote   {out.relative_to(REF)}  features={count}  sha256={sha[:12]}…')
    print(f'mc_tiles {", ".join(mc_tiles_for_bbox(*bbox_mc))}')

    models = args.models or default_models(jobs)
    if args.add:
        if not args.place:
            print('--add requires --place', file=sys.stderr)
            return 2
        dup = find_dup(load_manifest(), '', sha)
        if dup and not args.force:
            print(
                f'duplicate of {dup.get("id")} — extract written but not re-added',
                file=sys.stderr,
            )
            return 1
        notes = args.notes or (
            f'OSM {",".join(layer_labels)} clip bbox_mc='
            f'{bbox_mc[0]},{bbox_mc[1]},{bbox_mc[2]},{bbox_mc[3]} '
            f'features={count}'
        )
        return ref_manifest.main([
            'add', str(out),
            '--place', args.place,
            '--kind', 'map',
            '--source', SOURCE_TAG,
            '--useful', args.useful,
            '--models', models,
            '--not-for', args.not_for,
            '--url', PBF_URL,
            '--bbox', f'{bbox_mc[0]},{bbox_mc[1]},{bbox_mc[2]},{bbox_mc[3]}',
            '--notes', notes,
        ])

    print(
        'manifest not updated; to add:\n'
        f'  python3 scripts/ref_manifest.py add {out.relative_to(REF)} '
        f'--place {args.place or "PLACE"} --kind map --source {SOURCE_TAG} '
        f'--useful yes --models {models} --url {PBF_URL} '
        f'--bbox {bbox_mc[0]},{bbox_mc[1]},{bbox_mc[2]},{bbox_mc[3]}'
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    """CLI entry.

    @param argv: optional argv (without program name)
    @returns: exit code
    """
    p = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument('--at', help='MC x,z centre (use with --radius-m or --cell)')
    g.add_argument('--osgb', help='OSGB easting,northing centre')
    g.add_argument('--bbox-mc', help='inclusive MC bbox x0,z0,x1,z1')
    g.add_argument('--bbox-wgs', help='WGS84 bbox lon0,lat0,lon1,lat1')

    p.add_argument(
        '--radius-m', type=float, default=200.0,
        help='half-edge metres/blocks around --at/--osgb (default 200)',
    )
    p.add_argument(
        '--cell', action='store_true',
        help='use the 128×128 MC cell containing --at/--osgb instead of radius',
    )
    p.add_argument(
        '--layers',
        default='buildings',
        help=(
            'comma presets: '
            + ','.join(sorted(LAYER_PRESETS))
            + ' (default buildings)'
        ),
    )
    p.add_argument(
        '--gdal-layer',
        help='custom GDAL OSM layer (points|lines|multipolygons|…); needs --where',
    )
    p.add_argument('--where', help='SQL WHERE for --gdal-layer (default 1=1)')
    p.add_argument(
        '--pbf', default=str(DEFAULT_PBF),
        help=f'source .osm.pbf (default {DEFAULT_PBF.relative_to(ROOT)})',
    )
    p.add_argument('--place', help='PLACES.txt id (required for --add)')
    p.add_argument('--dir', help='output dir under reference/ (e.g. osm/portswood-x-broadlands)')
    p.add_argument('--dry-run', action='store_true', help='print plan only')
    p.add_argument('--force', action='store_true', help='overwrite existing GeoJSON')
    p.add_argument('--add', action='store_true', help='append to manifest.jsonl after write')
    p.add_argument('--useful', default='yes', choices=['yes', 'maybe', 'no'])
    p.add_argument(
        '--models', default='',
        help='override manifest models (default from layer presets)',
    )
    p.add_argument('--not-for', dest='not_for', default='private_interior')
    p.add_argument('--notes', default='')
    args = p.parse_args(argv)
    if not args.dir and not args.place:
        p.error('need --dir or --place')
    if args.gdal_layer and args.layers != 'buildings' and args.layers:
        # allow --gdal-layer alone; ignore default layers if custom set
        pass
    if args.cell and args.bbox_mc:
        p.error('--cell conflicts with --bbox-mc')
    return cmd_extract(args)


if __name__ == '__main__':
    raise SystemExit(main())
