#!/usr/bin/env python3
"""Fetch Southampton aer tiles and stitch an N×N mosaic (one Read, not nine).

Matches reference/LOGGING.txt naming and ref_manifest spatial index:

  reference/aerial/<dir>/mosaic-z{Z}-{N}x{N}-centre-{X}-{Y}.png

  python3 scripts/aerial_mosaic.py --wm 18/130062/87838 --place SO173SF \\
      --dir aerial/so17-3sf [--add]
  python3 scripts/aerial_mosaic.py --at 6949,-5345 --zoom 18 --place SO173SF \\
      --dir aerial/so17-3sf
  python3 scripts/aerial_mosaic.py --wm 18/130062/87838 --dir aerial/so17-3sf --dry-run

Default zoom 18 = Hampshire Hub (OGL). Zoom 19 = CCO (oblique / thinner).
Reuses local aer-zZ-X-Y.png tiles when present; does not keep newly fetched
singles unless --keep-tiles. Cap size at 5 (token budget).
"""
from __future__ import annotations

import argparse
import io
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

from PIL import Image

from script_env import ROOT  # noqa: E402
from geodetic import osgb_to_wgs84  # noqa: E402
from osgb import to_osgb  # noqa: E402
import ref_manifest  # noqa: E402
from ref_manifest import (  # noqa: E402
    deg2num,
    find_dup,
    load_manifest,
    parse_wm,
    sha256_file,
)
from ref_fetch_agent import fetch_bytes  # noqa: E402

REF = ROOT / 'reference'
TILE_URL = 'https://tiles.maps.southampton.ac.uk/aer/{z}/{x}/{y}.png'
REFERER = 'https://maps.southampton.ac.uk/'
USER_AGENT = 'SouthamptonRefine/aerial_mosaic (+local build reference)'
MAX_SIZE = 5
TILE_PX = 256


def mc_to_wm(x: int, z: int, zoom: int) -> tuple[int, int, int]:
    """Minecraft block → web-mercator tile containing that point.

    @param x: Minecraft X
    @param z: Minecraft Z
    @param zoom: WM zoom
    @returns: (z, xtile, ytile)
    """
    e, n = to_osgb(x, z)
    lat, lon = osgb_to_wgs84(e, n)
    tx, ty = deg2num(lat, lon, zoom)
    return zoom, tx, ty


def mosaic_offsets(size: int) -> list[tuple[int, int]]:
    """Return (dx, dy) offsets for an odd N×N mosaic centred on (0, 0).

    @param size: odd edge length (1, 3, 5)
    @returns: list of (dx, dy) in row-major order (dy outer for paste)
    """
    if size < 1 or size > MAX_SIZE or size % 2 == 0:
        raise ValueError(f'size must be odd 1..{MAX_SIZE}, got {size}')
    half = size // 2
    return [(dx, dy) for dy in range(-half, half + 1) for dx in range(-half, half + 1)]


def mosaic_wm_tiles(z: int, cx: int, cy: int, size: int) -> list[str]:
    """Sorted wm_tiles ids covering an N×N mosaic.

    @param z: zoom
    @param cx: centre tile X
    @param cy: centre tile Y
    @param size: odd edge
    @returns: sorted \"z/x/y\" strings
    """
    return sorted(f'{z}/{cx + dx}/{cy + dy}' for dx, dy in mosaic_offsets(size))


def tile_url(z: int, x: int, y: int) -> str:
    """Southampton aer tile URL.

    @param z: zoom
    @param x: tile X
    @param y: tile Y
    @returns: absolute URL
    """
    return TILE_URL.format(z=z, x=x, y=y)


def local_tile_path(out_dir: Path, z: int, x: int, y: int) -> Path:
    """Canonical on-disk name for a single aer tile under a place folder.

    @param out_dir: place aerial directory
    @param z: zoom
    @param x: tile X
    @param y: tile Y
    @returns: path
    """
    return out_dir / f'aer-z{z}-{x}-{y}.png'


def mosaic_path(out_dir: Path, z: int, cx: int, cy: int, size: int) -> Path:
    """Output mosaic path matching ref_manifest path regex.

    @param out_dir: place aerial directory
    @param z: zoom
    @param cx: centre X
    @param cy: centre Y
    @param size: odd edge
    @returns: path
    """
    return out_dir / f'mosaic-z{z}-{size}x{size}-centre-{cx}-{cy}.png'


def source_for_zoom(zoom: int) -> str:
    """Manifest source tag for a zoom level.

    @param zoom: WM zoom
    @returns: hampshire-hub or cco-z19
    """
    if zoom <= 18:
        return 'hampshire-hub'
    return 'cco-z19'


def fetch_tile(z: int, x: int, y: int, *, timeout: float = 30.0) -> bytes:
    """Download one aer tile PNG (direct, or optional localhost sidecar).

    Prefer running this script in a normal Terminal when mosaics are
    missing. Agent shells often cannot reach Hub; no per-handoff daemon.

    @param z: zoom
    @param x: tile X
    @param y: tile Y
    @param timeout: seconds
    @returns: PNG bytes
    """
    url = tile_url(z, x, y)
    data = fetch_bytes(
        url,
        {
            'User-Agent': USER_AGENT,
            'Referer': REFERER,
            'Accept': 'image/png,image/*;q=0.8,*/*;q=0.5',
        },
        timeout=timeout,
    )
    if len(data) < 100 or data[:8] != b'\x89PNG\r\n\x1a\n':
        raise RuntimeError(f'not a PNG from {url} ({len(data)} bytes)')
    return data


def load_tile_image(
    out_dir: Path,
    z: int,
    x: int,
    y: int,
    *,
    fetch: bool,
    keep_tiles: bool,
) -> Image.Image:
    """Load a tile from disk or network.

    @param out_dir: place aerial directory (for local reuse / optional keep)
    @param z: zoom
    @param x: tile X
    @param y: tile Y
    @param fetch: allow network download
    @param keep_tiles: write fetched singles as aer-zZ-X-Y.png
    @returns: RGB image
    """
    local = local_tile_path(out_dir, z, x, y)
    if local.is_file():
        return Image.open(local).convert('RGB')
    if not fetch:
        raise FileNotFoundError(f'missing local tile {local} (and --no-fetch)')
    data = fetch_tile(z, x, y)
    im = Image.open(io.BytesIO(data)).convert('RGB')
    if keep_tiles:
        out_dir.mkdir(parents=True, exist_ok=True)
        local.write_bytes(data)
    return im


def stitch_mosaic(
    out_dir: Path,
    z: int,
    cx: int,
    cy: int,
    size: int,
    *,
    fetch: bool = True,
    keep_tiles: bool = False,
    pause_s: float = 0.15,
) -> Image.Image:
    """Fetch/load tiles and paste into one RGB mosaic.

    @param out_dir: place aerial directory
    @param z: zoom
    @param cx: centre tile X
    @param cy: centre tile Y
    @param size: odd edge
    @param fetch: allow network
    @param keep_tiles: persist fetched singles
    @param pause_s: delay between network fetches
    @returns: stitched image (size*256 square)
    """
    half = size // 2
    sheet = Image.new('RGB', (size * TILE_PX, size * TILE_PX))
    fetched = 0
    for dy in range(-half, half + 1):
        for dx in range(-half, half + 1):
            tx, ty = cx + dx, cy + dy
            local = local_tile_path(out_dir, z, tx, ty)
            need_net = not local.is_file()
            if need_net and fetched and pause_s > 0:
                time.sleep(pause_s)
            im = load_tile_image(
                out_dir, z, tx, ty, fetch=fetch, keep_tiles=keep_tiles,
            )
            if need_net:
                fetched += 1
            if im.size != (TILE_PX, TILE_PX):
                im = im.resize((TILE_PX, TILE_PX), Image.Resampling.LANCZOS)
            sheet.paste(im, ((dx + half) * TILE_PX, (dy + half) * TILE_PX))
    return sheet


def resolve_centre(args: argparse.Namespace) -> tuple[int, int, int]:
    """Resolve (z, cx, cy) from CLI args.

    @param args: parsed args
    @returns: (zoom, centre_x, centre_y)
    """
    if args.wm:
        return parse_wm(args.wm)
    if args.at:
        x, z = map(int, args.at.split(','))
        return mc_to_wm(x, z, args.zoom)
    if args.osgb:
        e, n = map(float, args.osgb.split(','))
        lat, lon = osgb_to_wgs84(e, n)
        tx, ty = deg2num(lat, lon, args.zoom)
        return args.zoom, tx, ty
    raise SystemExit('need --wm, --at, or --osgb')


def place_dir(args: argparse.Namespace) -> Path:
    """Resolve output directory under reference/.

    @param args: CLI args with --dir or --place
    @returns: absolute path under reference/
    """
    if args.dir:
        rel = args.dir.strip().lstrip('/')
        if not rel.startswith('aerial/'):
            rel = f'aerial/{rel}'
        return REF / rel
    if args.place:
        return REF / 'aerial' / args.place.lower()
    raise SystemExit('need --dir or --place')


def manifest_has_mosaic(z: int, cx: int, cy: int, size: int) -> dict | None:
    """Return existing manifest row for this mosaic centre/size if any.

    @param z: zoom
    @param cx: centre X
    @param cy: centre Y
    @param size: edge
    @returns: row or None
    """
    needle = f'mosaic-z{z}-{size}x{size}-centre-{cx}-{cy}'
    for r in load_manifest():
        if needle in (r.get('path') or ''):
            return r
    return None


def cmd_build(args: argparse.Namespace) -> int:
    """Build (or dry-run) a mosaic.

    @param args: CLI args
    @returns: exit code
    """
    z, cx, cy = resolve_centre(args)
    size = args.size
    try:
        mosaic_offsets(size)
    except ValueError as e:
        print(e, file=sys.stderr)
        return 2

    out_dir = place_dir(args)
    out = mosaic_path(out_dir, z, cx, cy, size)
    tiles = mosaic_wm_tiles(z, cx, cy, size)
    centre_url = tile_url(z, cx, cy)
    source = source_for_zoom(z)

    print(f'centre  {z}/{cx}/{cy}')
    print(f'tiles   {len(tiles)}: {", ".join(tiles)}')
    print(f'out     {out.relative_to(REF)}')
    print(f'source  {source}')
    print(f'url     {centre_url}')

    if args.dry_run:
        for tid in tiles:
            zz, xx, yy = parse_wm(tid)
            local = local_tile_path(out_dir, zz, xx, yy)
            flag = 'local' if local.is_file() else ('fetch' if not args.no_fetch else 'MISSING')
            print(f'  {tid}  {flag}')
        return 0

    existing = manifest_has_mosaic(z, cx, cy, size)
    if existing and not args.force:
        print(
            f'already in manifest as {existing.get("id")} ({existing.get("path")}); '
            f'use --force to rebuild',
            file=sys.stderr,
        )
        return 1

    if out.is_file() and not args.force:
        print(f'exists: {out} (use --force)', file=sys.stderr)
        return 1

    if z == 19:
        print(
            'note: z19 is CCO (oblique / thinner coverage) — prefer z18 for general work',
            file=sys.stderr,
        )

    out_dir.mkdir(parents=True, exist_ok=True)
    try:
        sheet = stitch_mosaic(
            out_dir, z, cx, cy, size,
            fetch=not args.no_fetch,
            keep_tiles=args.keep_tiles,
        )
    except (FileNotFoundError, urllib.error.URLError, RuntimeError) as e:
        print(f'failed: {e}', file=sys.stderr)
        return 2

    sheet.save(out, optimize=True)
    sha = sha256_file(out)
    print(f'wrote   {out.relative_to(REF)}  {sheet.size[0]}x{sheet.size[1]}  sha256={sha[:12]}…')

    if args.add:
        if not args.place:
            print('--add requires --place', file=sys.stderr)
            return 2
        # refuse if sha/url already logged
        dup = find_dup(load_manifest(), centre_url if size == 1 else '', sha)
        if dup and not args.force:
            print(f'duplicate of {dup.get("id")} — mosaic written but not re-added', file=sys.stderr)
            return 1
        return ref_manifest.main([
            'add', str(out),
            '--place', args.place,
            '--kind', 'aerial',
            '--source', source,
            '--useful', args.useful,
            '--models', args.models,
            '--not-for', args.not_for,
            '--url', centre_url,
            '--wm', f'{z}/{cx}/{cy}',
            '--notes', args.notes or f'{size}x{size} mosaic centre {z}/{cx}/{cy}',
        ])

    print(
        'manifest not updated; to add:\n'
        f'  python3 scripts/ref_manifest.py add {out.relative_to(REF)} '
        f'--place {args.place or "PLACE"} --kind aerial --source {source} '
        f'--useful yes --models footprint,roof --url {centre_url} '
        f'--wm {z}/{cx}/{cy}'
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
    g.add_argument('--wm', help='centre web-mercator z/x/y')
    g.add_argument('--at', help='MC x,z point → centre tile at --zoom')
    g.add_argument('--osgb', help='OSGB easting,northing → centre tile at --zoom')
    p.add_argument('--zoom', type=int, default=18, help='WM zoom when using --at/--osgb (default 18)')
    p.add_argument('--size', type=int, default=3, help=f'odd N for N×N (default 3, max {MAX_SIZE})')
    p.add_argument('--place', help='PLACES.txt id (required for --add; default dir aerial/<place.lower()>)')
    p.add_argument('--dir', help='output dir under reference/ (e.g. aerial/so17-3sf)')
    p.add_argument('--dry-run', action='store_true', help='list tiles / paths only')
    p.add_argument('--no-fetch', action='store_true', help='only use local aer-zZ-X-Y.png tiles')
    p.add_argument('--keep-tiles', action='store_true', help='save fetched singles (usually skip)')
    p.add_argument('--force', action='store_true', help='overwrite existing mosaic / ignore manifest hit')
    p.add_argument('--add', action='store_true', help='append to manifest.jsonl after write')
    p.add_argument('--useful', default='yes', choices=['yes', 'maybe', 'no'])
    p.add_argument('--models', default='footprint,roof')
    p.add_argument('--not-for', dest='not_for', default='private_interior')
    p.add_argument('--notes', default='')
    args = p.parse_args(argv)
    if not args.dir and not args.place:
        p.error('need --dir or --place')
    return cmd_build(args)


if __name__ == '__main__':
    raise SystemExit(main())
