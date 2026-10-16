#!/usr/bin/env python3
"""Google satellite tiles for one cell or one spot: a look-only sheet with the MC grid drawn on it.

Always look at this for every cell (cell_sources family ``google``): it is often clearer than the university
aerial. Same status as the Street View thumbnails (reference/SOURCES.txt): an unofficial plain-image endpoint,
viewed in the browser pane, never downloaded, hashed, committed or looped over many cells.

``sheet`` writes a local HTML page whose <img> tags load straight from Google in the browser (nothing is saved
here). The page shows the tiles seamlessly, the bbox outline, and a MC block grid every 10 blocks (x green, z
cyan, labelled) so a position on the picture reads straight off as a block coordinate.

  python3 scripts/google_aerial.py sheet --cell 49,-42            # whole cell, z19
  python3 scripts/google_aerial.py sheet --at 6379,-5277          # around a building, z20, radius 30 blocks
  python3 scripts/google_aerial.py sheet --at 6379,-5277 --radius 60 --zoom 19
  python3 scripts/google_aerial.py url --at 6379,-5277 --zoom 19  # the single tile URL

Sheet: instance/google-aerial/<name>.html (gitignored). Open it as file://... in the browser pane.
After looking, record it once:  cell_sources.py --cell TX,TZ --record google --result found --note "what it shows"
"""
from __future__ import annotations

import argparse
import html
import math
import sys
from pathlib import Path

from script_env import ROOT  # noqa: E402

from coverage import cell_bbox  # noqa: E402
from geodetic import osgb_batch_to_wgs84  # noqa: E402
from osgb import to_osgb  # noqa: E402

BASE = 'https://mt1.google.com/vt/lyrs=s'
SHEETS = ROOT / 'instance' / 'google-aerial'
TILE = 256
MAX_TILES = 6                       # per side: one cell at z19 is 3-4; keeps the request count small (ToS)
GRID = 10                           # MC blocks between grid lines


def tile_float(lat: float, lon: float, zoom: int) -> tuple[float, float]:
    """Web-mercator tile coordinate (fractional) of a point.

    @param lat: latitude
    @param lon: longitude
    @param zoom: zoom level
    @returns: (x, y) in tiles; the integer part is the tile index
    """
    n = 2 ** zoom
    return ((lon + 180) / 360 * n,
            (1 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2 * n)


def mc_to_tile(points: list[tuple[float, float]], zoom: int) -> list[tuple[float, float]]:
    """Fractional tile coordinates of MC (x, z) points.

    @param points: MC (x, z) pairs
    @param zoom: zoom level
    @returns: one (tile_x, tile_y) per point
    """
    return [tile_float(lat, lon, zoom) for lat, lon in osgb_batch_to_wgs84([to_osgb(x, z) for x, z in points])]


def tile_url(x: int, y: int, zoom: int) -> str:
    """Satellite tile URL (open in a browser; do not download).

    @param x: tile x
    @param y: tile y
    @param zoom: zoom level
    @returns: URL
    """
    return f'{BASE}&x={x}&y={y}&z={zoom}'


def tile_range(bbox: tuple[int, int, int, int], zoom: int) -> tuple[int, int, int, int]:
    """Tile indices (x0, y0, x1, y1, inclusive) covering an MC bbox.

    @param bbox: MC x0, z0, x1, z1
    @param zoom: zoom level
    @returns: tile index box
    @raises ValueError: when the box needs more than MAX_TILES tiles a side
    """
    x0, z0, x1, z1 = bbox
    pts = mc_to_tile([(x0, z0), (x1, z0), (x0, z1), (x1, z1)], zoom)
    tx0, tx1 = int(min(p[0] for p in pts)), int(max(p[0] for p in pts))
    ty0, ty1 = int(min(p[1] for p in pts)), int(max(p[1] for p in pts))
    if tx1 - tx0 + 1 > MAX_TILES or ty1 - ty0 + 1 > MAX_TILES:
        raise ValueError(f'{tx1 - tx0 + 1}x{ty1 - ty0 + 1} tiles at z{zoom}: lower --zoom or --radius (max {MAX_TILES} a side)')
    return tx0, ty0, tx1, ty1


def grid_lines(bbox: tuple[int, int, int, int]) -> list[dict]:
    """MC grid lines every GRID blocks inside a bbox, as endpoint pairs.

    @param bbox: MC x0, z0, x1, z1
    @returns: [{axis, value, a: (x, z), b: (x, z)}] for x lines then z lines
    """
    x0, z0, x1, z1 = bbox
    out = [{'axis': 'x', 'value': v, 'a': (v, z0), 'b': (v, z1)} for v in range(-(-x0 // GRID) * GRID, x1 + 1, GRID)]
    out += [{'axis': 'z', 'value': v, 'a': (x0, v), 'b': (x1, v)} for v in range(-(-z0 // GRID) * GRID, z1 + 1, GRID)]
    return out


def sheet_html(bbox: tuple[int, int, int, int], zoom: int, title: str, scale: float = 2.0) -> str:
    """The sheet page: seamless tiles, the bbox outline and the labelled MC grid.

    @param bbox: MC x0, z0, x1, z1 to outline (tiles cover it and a margin)
    @param zoom: zoom level
    @param title: heading text
    @param scale: on-screen size of one 256 px tile, as a multiple
    @returns: HTML text
    """
    tx0, ty0, tx1, ty1 = tile_range(bbox, zoom)
    s = TILE * scale
    imgs = ''.join(
        f'<img src="{tile_url(x, y, zoom)}" style="left:{(x - tx0) * s}px;top:{(y - ty0) * s}px;width:{s}px;height:{s}px">'
        for y in range(ty0, ty1 + 1) for x in range(tx0, tx1 + 1))
    x0, z0, x1, z1 = bbox
    lines = grid_lines(bbox)
    ends = [p for ln in lines for p in (ln['a'], ln['b'])] + [(x0, z0), (x1, z0), (x1, z1), (x0, z1)]
    px = [((fx - tx0) * s, (fy - ty0) * s) for fx, fy in mc_to_tile(ends, zoom)]
    svg = ''
    for i, ln in enumerate(lines):
        (ax, ay), (bx, by) = px[2 * i], px[2 * i + 1]
        col = '#3f6' if ln['axis'] == 'x' else '#3cf'
        svg += (f'<line x1="{ax:.1f}" y1="{ay:.1f}" x2="{bx:.1f}" y2="{by:.1f}" stroke="{col}" stroke-opacity=".55" stroke-width="1"/>'
                f'<text x="{ax + 2:.1f}" y="{ay + 11:.1f}" fill="{col}" font-size="11">{ln["axis"]}{ln["value"]}</text>')
    c = px[-4:]
    svg += '<polygon points="' + ' '.join(f'{x:.1f},{y:.1f}' for x, y in (c[0], c[1], c[2], c[3])) + '" fill="none" stroke="#f33" stroke-width="2"/>'
    w, h = (tx1 - tx0 + 1) * s, (ty1 - ty0 + 1) * s
    return (f'<!doctype html><meta charset=utf-8><title>{html.escape(title)}</title>'
            f'<style>body{{font:13px system-ui;margin:10px;background:#111;color:#ddd}}'
            f'#m{{position:relative;width:{w}px;height:{h}px}}#m img{{position:absolute;display:block}}'
            f'#m svg{{position:absolute;left:0;top:0}}</style>'
            f'<h3>{html.escape(title)}</h3><p>Google satellite z{zoom}, look-only (not saved). Red = bbox {x0},{z0}..{x1},{z1}; '
            f'grid every {GRID} blocks.</p><div id=m>{imgs}<svg width="{w}" height="{h}">{svg}</svg></div>')


def write_sheet(name: str, bbox: tuple[int, int, int, int], zoom: int, title: str, scale: float) -> Path:
    """Write the sheet under instance/google-aerial/.

    @param name: file stem
    @param bbox: MC bbox
    @param zoom: zoom level
    @param title: heading text
    @param scale: tile display scale
    @returns: path
    """
    SHEETS.mkdir(parents=True, exist_ok=True)
    out = SHEETS / f'{name}.html'
    out.write_text(sheet_html(bbox, zoom, title, scale))
    return out


def _bbox(a: argparse.Namespace) -> tuple[tuple[int, int, int, int], str, int]:
    """Resolve --cell / --at into (bbox, file stem, default zoom).

    @param a: parsed args
    @returns: (bbox, name, zoom)
    """
    if a.cell:
        tx, tz = (int(v) for v in a.cell.split(','))
        return cell_bbox(tx, tz, tx, tz), f'{tx}_{tz}', a.zoom or 19
    x, z = (int(v) for v in a.at.split(','))
    r = a.radius
    return (x - r, z - r, x + r, z + r), f'at_{x}_{z}', a.zoom or 20


def main() -> int:
    """CLI entry point.

    @returns: exit code
    """
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('cmd', choices=('sheet', 'url'))
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument('--cell', help='tx,tz')
    g.add_argument('--at', help='MC x,z')
    ap.add_argument('--radius', type=int, default=30, help='blocks either side of --at (default 30)')
    ap.add_argument('--zoom', type=int, help='default 19 for a cell, 20 for --at')
    ap.add_argument('--scale', type=float, default=2.0, help='on-screen size of a tile as a multiple of 256 px')
    a = ap.parse_args()
    bbox, name, zoom = _bbox(a)
    if a.cmd == 'url':
        cx, cz = (bbox[0] + bbox[2]) // 2, (bbox[1] + bbox[3]) // 2
        fx, fy = mc_to_tile([(cx, cz)], zoom)[0]
        print(tile_url(int(fx), int(fy), zoom))
        return 0
    try:
        path = write_sheet(name, bbox, zoom, f'Google aerial {name} z{zoom}', a.scale)
    except ValueError as e:
        print(e, file=sys.stderr)
        return 2
    tx0, ty0, tx1, ty1 = tile_range(bbox, zoom)
    print(f'{(tx1 - tx0 + 1) * (ty1 - ty0 + 1)} tiles at z{zoom}, bbox {bbox}')
    print(f'Open in the browser pane: file://{path}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
