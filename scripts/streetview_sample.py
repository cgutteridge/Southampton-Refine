#!/usr/bin/env python3
"""Sample Street View frames for one 128×128 coverage cell and keep the useful ones.

Single-step method (reference/SOURCES.txt): the unofficial thumbnail URL takes
``ll=<lat>,<lon>`` and returns the nearest pano's frame, so no pano id lookup.

``sample`` writes a local HTML contact sheet whose <img> tags load straight from Google
in the browser (nothing is downloaded); you look and tick the useful frames. ``keep``
then saves ONLY those frames to reference/photos/streetview/<tx>_<tz>/<id>.jpg (local,
gitignored, per user decision 2026-10-14), logs each in reference/manifest.jsonl, and
records URL + params + note in a small committed JSON file.

  python3 scripts/streetview_sample.py sample --cell 48,-44            # 3×3 points × 4 yaws
  python3 scripts/streetview_sample.py sample --cell 48,-44 --grid 4 --yaws 0,90,180,270
  python3 scripts/streetview_sample.py keep --cell 48,-44 --ids g01-y90,g11-y180 --note "brick frontage"
  python3 scripts/streetview_sample.py show --cell 48,-44              # sheet of kept frames only
  python3 scripts/streetview_sample.py list --cell 48,-44

Sheet: instance/streetview/<tx>_<tz>-sheet.html (gitignored). Kept: site/cells/<tx>_<tz>-STREETVIEW.json.
Do not loop this over many cells/panos at once (ToS); keep grids small.
"""
from __future__ import annotations

import argparse
import html
import json
import re
import sys
import urllib.request
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'scripts'))

from coverage import cell_bbox  # noqa: E402
from geodetic import osgb_batch_to_wgs84  # noqa: E402
from osgb import to_osgb  # noqa: E402
from ref_manifest import REF, append_manifest, find_dup, load_manifest, sha256_file  # noqa: E402

BASE = 'https://streetviewpixels-pa.clients6.google.com/v1/thumbnail?cb_client=maps_sv.tactile'
SHEETS = ROOT / 'instance' / 'streetview'
CELLS = ROOT / 'site' / 'cells'
CITE = 'll-method, look-only'


def parse_cell(spec: str) -> tuple[int, int]:
    """Parse ``tx,tz`` cell indices.

    @param spec: comma-separated integers
    @returns: (tx, tz)
    """
    a, b = spec.split(',')
    return int(a), int(b)


def kept_path(tx: int, tz: int) -> Path:
    """Committed kept-frames file for a cell.

    @param tx: cell X index
    @param tz: cell Z index
    @returns: path under site/cells/
    """
    return CELLS / f'{tx}_{tz}-STREETVIEW.json'


def save_frame(tx: int, tz: int, f: dict, note: str) -> str:
    """Download one kept frame under reference/photos and log it in the manifest.

    @param tx: cell X index
    @param tz: cell Z index
    @param f: frame record (id, url, x, z, yaw)
    @param note: why it is useful
    @returns: path relative to reference/
    """
    dest = REF / 'photos' / 'streetview' / f'{tx}_{tz}' / f"{f['id']}.jpg"
    dest.parent.mkdir(parents=True, exist_ok=True)
    req = urllib.request.Request(f['url'], headers={'Referer': 'https://www.google.com/', 'User-Agent': 'Mozilla/5.0'})
    dest.write_bytes(urllib.request.urlopen(req, timeout=30).read())
    rel = str(dest.relative_to(REF))
    sha = sha256_file(dest)
    if not find_dup(load_manifest(), f['url'], sha):
        append_manifest({
            'id': re.sub(r'[^a-zA-Z0-9]+', '-', rel).strip('-').lower(),
            'place': f'CELL_{tx}_{tz}', 'path': rel, 'kind': 'street', 'source': 'google-streetview',
            'url': f['url'], 'sha256': sha, 'captured': '', 'added': str(date.today()), 'useful': 'yes',
            'models': ['facade', 'materials'], 'not_for': ['private_interior'],
            'notes': f"{note} (x{f['x']} z{f['z']} yaw {f['yaw']}; ll-method)"[:200],
            'mc_tiles': [], 'bbox_mc': [f['x'], f['z'], f['x'], f['z']],
        })
    return rel


def frame_url(lat: float, lon: float, yaw: int, w: int = 900, h: int = 600, pitch: int = 0) -> str:
    """Thumbnail URL for the nearest pano to lat/lon at a heading.

    @param lat: latitude
    @param lon: longitude
    @param yaw: heading in degrees (0 = north, 90 = east)
    @param w: image width
    @param h: image height
    @param pitch: pitch in degrees
    @returns: URL (open in a browser; do not download)
    """
    return f'{BASE}&w={w}&h={h}&pitch={pitch}&yaw={yaw}&ll={lat:.6f},{lon:.6f}'


def sample_points(tx: int, tz: int, grid: int) -> list[dict]:
    """Evenly spaced sample points inside a cell, with lat/lon.

    @param tx: cell X index
    @param tz: cell Z index
    @param grid: points per side (grid × grid, centred in equal sub-squares)
    @returns: list of {pid, x, z, lat, lon}
    """
    x0, z0, x1, z1 = cell_bbox(tx, tz, tx, tz)
    step_x, step_z = (x1 - x0 + 1) / grid, (z1 - z0 + 1) / grid
    pts = [(r, c, int(x0 + (c + 0.5) * step_x), int(z0 + (r + 0.5) * step_z))
           for r in range(grid) for c in range(grid)]
    en = [to_osgb(x, z) for _, _, x, z in pts]
    ll = osgb_batch_to_wgs84(en)
    return [{'pid': f'g{r}{c}', 'x': x, 'z': z, 'lat': lat, 'lon': lon}
            for (r, c, x, z), (lat, lon) in zip(pts, ll)]


def load_kept(tx: int, tz: int) -> list[dict]:
    """Read kept frames for a cell.

    @param tx: cell X index
    @param tz: cell Z index
    @returns: list of frame records (empty if none)
    """
    p = kept_path(tx, tz)
    return json.loads(p.read_text())['frames'] if p.exists() else []


def build_frames(tx: int, tz: int, grid: int, yaws: list[int]) -> list[dict]:
    """All candidate frames (points × yaws) for a cell.

    @param tx: cell X index
    @param tz: cell Z index
    @param grid: points per side
    @param yaws: headings to sample at each point
    @returns: list of frame records with id and url
    """
    return [{'id': f"{p['pid']}-y{y}", 'x': p['x'], 'z': p['z'], 'lat': round(p['lat'], 6),
             'lon': round(p['lon'], 6), 'yaw': y, 'url': frame_url(p['lat'], p['lon'], y)}
            for p in sample_points(tx, tz, grid) for y in yaws]


def write_sheet(tx: int, tz: int, frames: list[dict], title: str) -> Path:
    """Write a local HTML contact sheet with tick boxes and a ready-made keep command.

    @param tx: cell X index
    @param tz: cell Z index
    @param frames: frame records to show
    @param title: heading text
    @returns: path of the written sheet
    """
    SHEETS.mkdir(parents=True, exist_ok=True)
    cards = ''.join(
        f'<label class="c"><input type="checkbox" value="{html.escape(f["id"])}">'
        f'<img loading="lazy" src="{html.escape(f["url"].replace("w=900&h=600", "w=450&h=300"))}">'
        f'<span>{html.escape(f["id"])} · x{f["x"]} z{f["z"]} · yaw {f["yaw"]}</span></label>'
        for f in frames)
    page = f"""<!doctype html><meta charset=utf-8><title>{html.escape(title)}</title>
<style>body{{font:13px system-ui;margin:12px;background:#111;color:#ddd}}
.g{{display:grid;grid-template-columns:repeat(auto-fill,minmax(300px,1fr));gap:8px}}
.c{{display:block;background:#222;padding:4px;cursor:pointer}}.c img{{width:100%;display:block}}
.c:has(input:checked){{outline:3px solid #4c8}}pre{{background:#000;padding:8px;user-select:all}}</style>
<h3>{html.escape(title)}</h3><p>Tick the useful frames, then run the command below.</p>
<pre id=cmd></pre><div class=g>{cards}</div>
<script>
const cmd=document.getElementById('cmd'),bs=[...document.querySelectorAll('input')];
function up(){{cmd.textContent='python3 scripts/streetview_sample.py keep --cell {tx},{tz} --ids '+
bs.filter(b=>b.checked).map(b=>b.value).join(',')+' --note "..."'}}
bs.forEach(b=>b.onchange=up);up();
</script>"""
    out = SHEETS / f'{tx}_{tz}-sheet.html'
    out.write_text(page)
    return out


def cmd_sample(a: argparse.Namespace) -> int:
    """Build the contact sheet for a cell.

    @param a: parsed args
    @returns: exit code
    """
    tx, tz = parse_cell(a.cell)
    yaws = [int(y) for y in a.yaws.split(',')]
    frames = build_frames(tx, tz, a.grid, yaws)
    path = write_sheet(tx, tz, frames, f'Street View samples, cell {tx},{tz}')
    print(f'{len(frames)} frames ({a.grid}x{a.grid} points x {len(yaws)} yaws)')
    print(f'Open in the browser pane: file://{path}')
    return 0


def cmd_keep(a: argparse.Namespace) -> int:
    """Record chosen frames (by id) in the committed kept file. Re-derives from args so ids stay stable.

    @param a: parsed args
    @returns: exit code
    """
    tx, tz = parse_cell(a.cell)
    yaws = [int(y) for y in a.yaws.split(',')]
    by_id = {f['id']: f for f in build_frames(tx, tz, a.grid, yaws)}
    kept = {f['id']: f for f in load_kept(tx, tz)}
    for fid in [i for i in a.ids.split(',') if i]:
        if fid not in by_id:
            print(f'unknown id {fid} (use the same --grid/--yaws as sample)', file=sys.stderr)
            return 2
        path = save_frame(tx, tz, by_id[fid], a.note)
        kept[fid] = {**by_id[fid], 'note': a.note, 'kept': date.today().isoformat(), 'method': CITE, 'path': path}
    p = kept_path(tx, tz)
    p.write_text(json.dumps({'cell': f'{tx},{tz}', 'frames': list(kept.values())}, indent=1) + '\n')
    print(f'{len(kept)} kept frames -> {p.relative_to(ROOT)}')
    return 0


def cmd_show(a: argparse.Namespace) -> int:
    """Contact sheet of kept frames only.

    @param a: parsed args
    @returns: exit code
    """
    tx, tz = parse_cell(a.cell)
    frames = load_kept(tx, tz)
    if not frames:
        print('no kept frames')
        return 1
    print(f'file://{write_sheet(tx, tz, frames, f"Kept Street View frames, cell {tx},{tz}")}')
    return 0


def cmd_list(a: argparse.Namespace) -> int:
    """Print kept frames.

    @param a: parsed args
    @returns: exit code
    """
    tx, tz = parse_cell(a.cell)
    for f in load_kept(tx, tz):
        print(f"{f['id']}  x{f['x']} z{f['z']} yaw {f['yaw']}  {f['note']}\n  {f['url']}")
    return 0


def main() -> int:
    """CLI entry point.

    @returns: exit code
    """
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest='cmd', required=True)
    for name, fn in (('sample', cmd_sample), ('keep', cmd_keep), ('show', cmd_show), ('list', cmd_list)):
        p = sub.add_parser(name)
        p.add_argument('--cell', required=True)
        p.add_argument('--grid', type=int, default=3)
        p.add_argument('--yaws', default='0,90,180,270')
        if name == 'keep':
            p.add_argument('--ids', required=True)
            p.add_argument('--note', default='')
        p.set_defaults(fn=fn)
    a = ap.parse_args()
    return a.fn(a)


if __name__ == '__main__':
    raise SystemExit(main())
