#!/usr/bin/env python3
"""KartaView street photos near an MC point: list, fetch + log, contact sheet (one Read).

API: https://api.openstreetcam.org/2.0/photo/ (no token; see reference/SOURCES.txt).

  python3 scripts/kartaview_fetch.py list --at 6435,-5543 --radius-m 80
  python3 scripts/kartaview_fetch.py get 1519868249,1519868121 --place UNI \
      --dir photos/highfield-campus [--notes "..."]
  python3 scripts/kartaview_fetch.py sheet photos/highfield-campus/kartaview-1.jpg,... out.png

`list` prints id, camera MC x,z, heading (deg, 0 = north = -Z), date and distance, nearest
first, one per sequence position so a pass along a road is easy to pick from. `get` skips
ids already in reference/manifest.jsonl, saves the processed JPEG and appends a manifest
row (camera MC point as --at). `sheet` tiles photos at 480 px wide with their id/heading.
"""
import argparse
import json
import math
import subprocess
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'scripts'))
from osgb import to_osgb, to_mc  # noqa: E402

REF = ROOT / 'reference'
API = 'https://api.openstreetcam.org/2.0/photo/'
UA = {'User-Agent': 'SouthamptonRefine/kartaview_fetch (+local build reference)'}


def _gdal(inp, s, t):
    out = subprocess.run(['gdaltransform', '-s_srs', s, '-t_srs', t], input=inp.encode(),
                         capture_output=True, check=True).stdout.decode().split('\n')
    return [tuple(map(float, l.split()[:2])) for l in out if l.strip()]


def mc_to_ll(x, z):
    e, n = to_osgb(x, z)
    lon, lat = _gdal(f'{e} {n}\n', 'EPSG:27700', 'EPSG:4326')[0]
    return lat, lon


def ll_to_mc(pairs):
    en = _gdal(''.join(f'{lon} {lat}\n' for lat, lon in pairs), 'EPSG:4326', 'EPSG:27700')
    return [to_mc(e, n) for e, n in en]


def _json(url):
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=40) as r:
        return json.load(r)


def query(x, z, radius):
    lat, lon = mc_to_ll(x, z)
    rows = _json(f'{API}?lat={lat}&lng={lon}&radius={min(radius, 200)}&itemsPerPage=100')['result']['data']
    pts = ll_to_mc([(float(r['lat']), float(r['lng'])) for r in rows])
    for r, (cx, cz) in zip(rows, pts):
        r['mc'] = (cx, cz)
        r['d'] = math.hypot(cx - x, cz - z)
    return sorted(rows, key=lambda r: r['d'])


def known():
    ids = set()
    for line in (REF / 'manifest.jsonl').read_text().splitlines():
        if '"kartaview"' in line:
            ids.add(json.loads(line)['path'].rsplit('kartaview-', 1)[-1].split('.')[0])
    return ids


def cmd_list(a):
    x, z = map(int, a.at.split(','))
    have = known()
    for r in query(x, z, a.radius_m)[:a.max]:
        cx, cz = r['mc']
        print(f"{r['id']:>11}  cam {cx},{cz}  head {float(r.get('heading') or 0):5.0f}  "
              f"{r['shotDate'][:10]}  d {r['d']:4.0f}{'  (on disk)' if r['id'] in have else ''}")


def cmd_get(a):
    have = known()
    d = REF / a.dir
    d.mkdir(parents=True, exist_ok=True)
    for pid in a.ids.split(','):
        if pid in have:
            print('on disk', pid)
            continue
        r = _json(f'{API}{pid}')['result']['data']
        cx, cz = ll_to_mc([(float(r['lat']), float(r['lng']))])[0]
        out = d / f'kartaview-{pid}.jpg'
        with urllib.request.urlopen(urllib.request.Request(r['fileurlProc'], headers=UA), timeout=60) as s:
            out.write_bytes(s.read())
        notes = f"cam {cx},{cz} head {float(r.get('heading') or 0):.0f}" + (f'; {a.notes}' if a.notes else '')
        subprocess.run([sys.executable, str(ROOT / 'scripts/ref_manifest.py'), 'add', str(out.relative_to(REF)),
                        '--place', a.place, '--kind', 'street', '--source', 'kartaview',
                        '--useful', a.useful, '--models', 'facade', '--at', f'{cx},{cz}',
                        '--url', f'https://kartaview.org/details/{pid}', '--notes', notes], check=True,
                       capture_output=True)
        print('got', pid, out.relative_to(ROOT), notes)


def cmd_sheet(a):
    from PIL import Image, ImageDraw
    paths = [REF / p if not Path(p).is_absolute() else Path(p) for p in a.paths.split(',')]
    W = 480
    ims = []
    for p in paths:
        im = Image.open(p).convert('RGB')
        im = im.resize((W, int(im.height * W / im.width)))
        ImageDraw.Draw(im).text((6, 6), p.stem.replace('kartaview-', ''), fill=(255, 255, 0))
        ims.append(im)
    cols = min(a.cols, len(ims))
    rows = math.ceil(len(ims) / cols)
    H = max(i.height for i in ims)
    sheet = Image.new('RGB', (cols * W, rows * H), 'black')
    for k, im in enumerate(ims):
        sheet.paste(im, ((k % cols) * W, (k // cols) * H))
    sheet.save(a.out)
    print('wrote', a.out, sheet.size)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest='cmd', required=True)
    p = sub.add_parser('list')
    p.add_argument('--at', required=True)
    p.add_argument('--radius-m', type=int, default=80)
    p.add_argument('--max', type=int, default=40)
    p.set_defaults(f=cmd_list)
    p = sub.add_parser('get')
    p.add_argument('ids')
    p.add_argument('--place', required=True)
    p.add_argument('--dir', required=True)
    p.add_argument('--useful', default='maybe', choices=('yes', 'maybe', 'no'))
    p.add_argument('--notes', default='')
    p.set_defaults(f=cmd_get)
    p = sub.add_parser('sheet')
    p.add_argument('paths')
    p.add_argument('out')
    p.add_argument('--cols', type=int, default=3)
    p.set_defaults(f=cmd_sheet)
    a = ap.parse_args()
    a.f(a)


if __name__ == '__main__':
    main()
