#!/usr/bin/env python3
"""University of Southampton building register: a picture and the university's own outline of each building.

Source: https://maps.soton.ac.uk/data/buildings.json (the campus-map data behind maps.southampton.ac.uk). One row per
numbered university building: id (the building number, "42", "2A"), label, a centre lat/lon, 247 of 370 with a photo of the
building, 232 with a footprint polygon. Stored normalised in reference/buildings/buildings.json (committed: data, not
imagery), with Minecraft X/Z for the centre and every ring point. Same shape as scripts/portals.py (entrances), which it
works beside.

  python3 scripts/buildings.py fetch                     # re-download and rewrite the store (needs gdaltransform)
  python3 scripts/buildings.py info                      # counts, how many fall inside the Geocraft map
  python3 scripts/buildings.py cell 48,-44               # buildings with their centre in a 128-block cell
  python3 scripts/buildings.py bbox 6200,-5900,6330,-5800 [--pad 6]
  python3 scripts/buildings.py building 42               # one building (number as the register writes it)
  python3 scripts/buildings.py near 6240,-5850 [--radius 30]
  python3 scripts/buildings.py download [--size 800]     # every photo -> reference/photos/buildings/<id>.jpg (gitignored)

Photos: the register links 200 px thumbnails; photos()/image_url() give the same picture at PHOTO_SIZE (800 px wide).

Use (`rules/evidence-order.md`, `site/CRAFTSMANSHIP.txt` "BUILDING PICTURES"): the photo is a street-level view of the
whole building, the best source for walls, openings, storeys and roof edge where no Street View frame exists; look-only,
look at it once and write down what it shows. The outline is the university's own footprint: use it to cross-check the OSM
polygon (a wing OSM lacks, a wrong corner). It is not authority over lidar for heights. cell_features.missing_features
lists the pictures on each feature's footprint.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
import urllib.request
from functools import lru_cache

from script_env import ROOT  # noqa: E402

from osgb import in_bounds, load_offsets, to_mc  # noqa: E402
from portals import PHOTO_SIZE, PHOTO_SIZES, _building_key, image_url  # noqa: E402

SOURCE_URL = 'https://maps.soton.ac.uk/data/buildings.json'
STORE = ROOT / 'reference' / 'buildings' / 'buildings.json'
PHOTO_DIR = ROOT / 'reference' / 'photos' / 'buildings'
MANIFEST = ROOT / 'reference' / 'manifest.jsonl'


def normalise(raw: list) -> list:
    """Raw buildings.json rows to one record per building, with OSGB and Minecraft coordinates.

    @param raw: parsed buildings.json
    @returns: [{'id', 'label', 'lat', 'lon', 'x', 'z', 'in_map', 'image', 'uri', 'rings'}] sorted by building number;
              `rings` = [[[x, z], ...]] in Minecraft coordinates ([] when the register has no outline)
    """
    from geodetic import wgs84_batch_to_osgb
    off = load_offsets()
    pts = [(r['lat'], r['lon']) for r in raw]
    flat = [(lat, lon) for r in raw for ring in (r.get('polygon') or []) for lat, lon in ring]
    both = wgs84_batch_to_osgb(pts + flat)
    cen, ringpts = both[:len(pts)], iter(both[len(pts):])
    out = []
    for r, (e, n) in zip(raw, cen):
        x, z = to_mc(e, n, off)
        rings = [[list(to_mc(*next(ringpts), off)) for _ in ring] for ring in (r.get('polygon') or [])]
        out.append({'id': str(r['id']), 'label': r['label'], 'lat': r['lat'], 'lon': r['lon'], 'x': x, 'z': z,
                    'in_map': in_bounds(x, z, off), 'image': r.get('image') or '', 'uri': r.get('uri', ''),
                    'rings': rings})
    return sorted(out, key=lambda b: (_building_key(b['id']), b['id']))


def fetch(url: str = SOURCE_URL) -> list:
    """Download the register and rewrite the store.

    @param url: buildings.json URL
    @returns: the normalised buildings
    """
    with urllib.request.urlopen(url, timeout=60) as r:
        raw = json.load(r)
    bs = normalise(raw)
    STORE.parent.mkdir(parents=True, exist_ok=True)
    STORE.write_text(json.dumps({'source': url, 'count': len(bs), 'buildings': bs}, separators=(',', ':')) + '\n')
    load.cache_clear()
    return bs


@lru_cache(maxsize=1)
def load() -> list:
    """All stored buildings ([] when the store is missing).

    @returns: normalised buildings (see normalise)
    """
    try:
        return json.loads(STORE.read_text())['buildings']
    except (OSError, ValueError, KeyError):
        return []


def in_bbox(x0: float, z0: float, x1: float, z1: float, pad: float = 0) -> list:
    """Buildings whose centre is inside an MC bbox grown by pad.

    @param x0: min X
    @param z0: min Z
    @param x1: max X
    @param z1: max Z
    @param pad: blocks of margin
    @returns: buildings
    """
    return [b for b in load() if x0 - pad <= b['x'] <= x1 + pad and z0 - pad <= b['z'] <= z1 + pad]


def in_cell(tx: int, tz: int) -> list:
    """Buildings with their centre in a 128-block cell.

    @param tx: cell X
    @param tz: cell Z
    @returns: buildings
    """
    return in_bbox(tx * 128, tz * 128, tx * 128 + 127, tz * 128 + 127)


def building(num: str) -> list:
    """One university building by number ("32", "2A", "63F"); a list so callers treat it like the other lookups.

    @param num: building number as the register writes it
    @returns: [building] or []
    """
    return [b for b in load() if b['id'].upper() == str(num).upper()]


def near(x: float, z: float, radius: float = 30) -> list:
    """Buildings whose centre is within radius blocks of a point, nearest first.

    @param x: MC X
    @param z: MC Z
    @param radius: blocks
    @returns: [(distance, building)]
    """
    hits = [(math.hypot(b['x'] - x, b['z'] - z), b) for b in load()]
    return sorted((h for h in hits if h[0] <= radius), key=lambda h: (h[0], h[1]['id']))


def _inside(px: float, pz: float, ring) -> bool:
    hit = False
    for (ax, az), (bx, bz) in zip(ring, ring[1:] + ring[:1]):
        if (az > pz) != (bz > pz) and px < (bx - ax) * (pz - az) / (bz - az) + ax:
            hit = not hit
    return hit


def for_footprint(rings) -> list:
    """University buildings that an OSM footprint is: the register's centre lies inside the OSM outline, or the OSM
    outline's centre lies inside the register's outline.

    @param rings: OSM rings [[(x, z), ...]] (outer first), as OSMIndex.buildings holds them
    @returns: buildings, nearest centre first
    """
    outer = [tuple(p) for p in rings[0]]
    xs = [x for x, _ in outer]
    zs = [z for _, z in outer]
    cx, cz = sum(xs) / len(xs), sum(zs) / len(zs)
    hits = []
    for b in in_bbox(min(xs), min(zs), max(xs), max(zs), 40):
        mine = _inside(b['x'], b['z'], outer) or any(_inside(cx, cz, [tuple(p) for p in ring]) for ring in b['rings'][:1])
        if mine:
            hits.append((math.hypot(b['x'] - cx, b['z'] - cz), b['id'], b))
    return [b for _d, _i, b in sorted(hits, key=lambda h: h[:2])]


def photos(b: dict, size: int = PHOTO_SIZE) -> list:
    """A building's photo URL at the working width.

    @param b: building
    @param size: width in px
    @returns: [URL] or []
    """
    return [image_url(b['image'], size)] if b['image'] else []


def describe(b: dict) -> str:
    """One line: number, name, block position, photo and outline.

    @param b: building
    @returns: text
    """
    return (f'{b["id"]} "{b["label"]}" at {b["x"]},{b["z"]} ({"photo" if b["image"] else "no photo"}, '
            f'{"outline" if b["rings"] else "no outline"})')


def download(size: int = PHOTO_SIZE) -> tuple:
    """Save every building photo at one width under reference/photos/buildings/ and log each in the manifest.

    Files are <building number>.jpg. Existing files are kept, so a rerun only fetches what is missing. Images stay
    gitignored (reference/photos/**); the manifest lines are committed.

    @param size: width in px (one of PHOTO_SIZES)
    @returns: (saved, already there, failed [(url, error)])
    """
    import datetime
    import hashlib
    PHOTO_DIR.mkdir(parents=True, exist_ok=True)
    logged = {json.loads(ln).get('id') for ln in MANIFEST.read_text().splitlines() if ln.strip()}
    today = datetime.date.today().isoformat()
    saved = have = 0
    failed = []
    for b in load():
        for url in photos(b, size):
            path = PHOTO_DIR / f'{b["id"]}.jpg'
            if not path.exists():
                try:
                    with urllib.request.urlopen(url, timeout=60) as r:
                        data = r.read()
                except OSError as e:
                    failed.append((url, str(e)))
                    continue
                path.write_bytes(data)
                saved += 1
            else:
                have += 1
            mid = f'building-{b["id"].lower()}-{size}'
            if mid not in logged:
                line = {'id': mid, 'place': 'UOS_CAMPUSES', 'path': f'photos/buildings/{path.name}', 'kind': 'facade',
                        'source': 'uos-buildings', 'url': url, 'sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
                        'captured': '', 'added': today, 'useful': 'yes', 'models': ['facade', 'storeys', 'roof'],
                        'not_for': ['private_interior'],
                        'notes': f'building {b["id"]} "{b["label"]}" at {b["x"]},{b["z"]}; {size}px'}
                with MANIFEST.open('a') as f:
                    f.write(json.dumps(line, separators=(',', ':')) + '\n')
    return saved, have, failed


def _print(bs: list) -> None:
    for b in bs:
        print(describe(b))
        for u in photos(b):
            print('    ' + u)
    print(f'{len(bs)} building(s)')


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    sub = ap.add_subparsers(dest='cmd', required=True)
    sub.add_parser('fetch')
    sub.add_parser('info')
    sub.add_parser('cell').add_argument('cell')
    bb = sub.add_parser('bbox')
    bb.add_argument('bbox')
    bb.add_argument('--pad', type=float, default=0)
    sub.add_parser('building').add_argument('number')
    n = sub.add_parser('near')
    n.add_argument('xz')
    n.add_argument('--radius', type=float, default=30)
    d = sub.add_parser('download')
    d.add_argument('--size', type=int, default=PHOTO_SIZE, choices=PHOTO_SIZES)
    a = ap.parse_args(argv)
    if a.cmd == 'download':
        saved, have, failed = download(a.size)
        print(f'{saved} saved, {have} already there, {len(failed)} failed -> {PHOTO_DIR.relative_to(ROOT)}')
        for u, e in failed:
            print(f'  FAILED {u}: {e}')
        return 1 if failed else 0
    if a.cmd == 'fetch':
        bs = fetch()
        print(f'{len(bs)} buildings written to {STORE.relative_to(ROOT)}')
    elif a.cmd == 'info':
        bs = load()
        print(f'{len(bs)} buildings, {sum(1 for b in bs if b["in_map"])} inside the Geocraft map, '
              f'{sum(1 for b in bs if b["image"])} with a photo, {sum(1 for b in bs if b["rings"])} with an outline')
    elif a.cmd == 'cell':
        _print(in_cell(*(int(v) for v in a.cell.split(','))))
    elif a.cmd == 'bbox':
        _print(in_bbox(*(float(v) for v in a.bbox.split(',')), pad=a.pad))
    elif a.cmd == 'building':
        _print(building(a.number))
    elif a.cmd == 'near':
        x, z = (float(v) for v in a.xz.split(','))
        for dist, b in near(x, z, a.radius):
            print(f'{dist:5.1f}  {describe(b)}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
