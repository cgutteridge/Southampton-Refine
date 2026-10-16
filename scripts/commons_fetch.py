#!/usr/bin/env python3
"""Wikimedia Commons geotagged photos near an MC point: list, fetch + log (with licence).

Most Highfield campus interiors-of-blocks have no KartaView (roads only); Commons carries
many Geograph uploads (CC BY-SA) of named campus buildings.

  python3 scripts/commons_fetch.py list --at 6435,-5543 [--radius-m 250] [--grep chem]
  python3 scripts/commons_fetch.py get 12345,67890 --place UNI --dir photos/highfield-campus

`list` prints pageid, distance, camera MC point (if geotagged) and title. `get` saves a
1280 px thumbnail as commons-<pageid>.jpg and appends a manifest row whose notes carry
title, author and licence (attribution travels with the file). Sheets: kartaview_fetch.py sheet.
"""
import argparse
import json
import re
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from script_env import ROOT  # noqa: E402
from kartaview_fetch import mc_to_ll, ll_to_mc  # noqa: E402

REF = ROOT / 'reference'
API = 'https://commons.wikimedia.org/w/api.php'
UA = {'User-Agent': 'SouthamptonRefine/commons_fetch (local build reference; University of Southampton)'}


def _get(params):
    url = API + '?' + urllib.parse.urlencode({**params, 'format': 'json'})
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=40) as r:
        return json.load(r)


def known():
    return {json.loads(l)['path'].rsplit('commons-', 1)[-1].split('.')[0]
            for l in (REF / 'manifest.jsonl').read_text().splitlines() if '"commons"' in l}


def cmd_list(a):
    x, z = map(int, a.at.split(','))
    lat, lon = mc_to_ll(x, z)
    rows = _get({'action': 'query', 'list': 'geosearch', 'gscoord': f'{lat}|{lon}',
                 'gsradius': min(a.radius_m, 10000), 'gslimit': 500, 'gsnamespace': 6})['query']['geosearch']
    if a.grep:
        rows = [r for r in rows if re.search(a.grep, r['title'], re.I)]
    pts = ll_to_mc([(r['lat'], r['lon']) for r in rows]) if rows else []
    have = known()
    for r, (cx, cz) in zip(rows, pts):
        print(f"{r['pageid']:>10}  d {r['dist']:5.0f}  cam {cx},{cz}  {r['title'][5:]}"
              f"{'  (on disk)' if str(r['pageid']) in have else ''}")


def cmd_get(a):
    have = known()
    d = REF / a.dir
    d.mkdir(parents=True, exist_ok=True)
    q = _get({'action': 'query', 'pageids': a.ids.replace(',', '|'), 'prop': 'imageinfo|coordinates',
              'iiprop': 'url|extmetadata', 'iiurlwidth': 1280})['query']['pages']
    for pid, pg in q.items():
        if pid in have:
            print('on disk', pid)
            continue
        ii = pg['imageinfo'][0]
        md = {k: re.sub('<[^>]+>', '', str(v.get('value', ''))).strip() for k, v in ii.get('extmetadata', {}).items()}
        out = d / f'commons-{pid}.jpg'
        for wait in (2, 10, 30, 60):                     # polite + retry on 429
            time.sleep(wait)
            try:
                with urllib.request.urlopen(urllib.request.Request(ii['thumburl'], headers=UA), timeout=60) as s:
                    out.write_bytes(s.read())
                break
            except urllib.error.HTTPError as e:
                if e.code != 429:
                    raise
        else:
            print('rate-limited, skipped', pid)
            continue
        c = (pg.get('coordinates') or [{}])[0]
        at = []
        if c.get('lat'):
            cx, cz = ll_to_mc([(c['lat'], c['lon'])])[0]
            at = ['--at', f'{cx},{cz}']
        notes = (f"{pg['title'][5:]} | {md.get('Artist', '?')[:60]} | {md.get('LicenseShortName', '?')}"
                 f" | {md.get('DateTimeOriginal', '')[:10]}" + (f' | {a.notes}' if a.notes else ''))
        subprocess.run([sys.executable, str(ROOT / 'scripts/ref_manifest.py'), 'add', str(out.relative_to(REF)),
                        '--place', a.place, '--kind', 'street', '--source', 'commons', '--useful', a.useful,
                        '--models', 'facade', '--url', ii['descriptionurl'], '--notes', notes, *at],
                       check=True, capture_output=True)
        print('got', pid, out.relative_to(ROOT), notes)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest='cmd', required=True)
    p = sub.add_parser('list')
    p.add_argument('--at', required=True)
    p.add_argument('--radius-m', type=int, default=250)
    p.add_argument('--grep', default='')
    p.set_defaults(f=cmd_list)
    p = sub.add_parser('get')
    p.add_argument('ids')
    p.add_argument('--place', required=True)
    p.add_argument('--dir', required=True)
    p.add_argument('--useful', default='maybe', choices=('yes', 'maybe', 'no'))
    p.add_argument('--notes', default='')
    p.set_defaults(f=cmd_get)
    a = ap.parse_args()
    a.f(a)


if __name__ == '__main__':
    main()
