#!/usr/bin/env python3
"""University of Southampton building entrances ("portals"): where the doors really are.

Source: https://maps.southampton.ac.uk/data/portals.json (university building-portal register). Each portal is one
entrance of one numbered university building, with the lat/lon of the ENTRANCE itself (not of the photo) and, for
about a third, a photo of it. Stored normalised in reference/portals/portals.json (committed: small, data not imagery).

  python3 scripts/portals.py fetch                      # re-download and rewrite the store (needs gdaltransform)
  python3 scripts/portals.py info                       # counts, how many fall inside the Geocraft map
  python3 scripts/portals.py cell 48,-44                # portals in a 128-block cell
  python3 scripts/portals.py bbox 6200,-5900,6330,-5800 [--pad 6]
  python3 scripts/portals.py building 32                # every entrance of university building 32
  python3 scripts/portals.py near 6240,-5850 [--radius 15]

Use (feature builds, `site/CRAFTSMANSHIP.txt` "ENTRANCES"): a portal is the best evidence for WHERE a door goes and
what it is called (Main, Rear, Lower ground entrance...). It does not say what the door looks like: for that open the
portal's photo (look-only, `rules/evidence-order.md`). cell_features.missing_features lists the portals of each
feature; Campus builds turn them into door anchors with door_specs().
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

SOURCE_URL = 'https://maps.southampton.ac.uk/data/portals.json'
STORE = ROOT / 'reference' / 'portals' / 'portals.json'
FOOTPRINT_REACH = 6      # blocks: an entrance this close to an OSM footprint belongs to that building
DOOR_REACH = 5           # blocks: Campus.door_specs ignores a portal further than this from a part cell


def normalise(raw: list) -> list:
    """Raw portals.json rows to one record per portal, with OSGB and Minecraft coordinates.

    The register repeats a portal once per photo; those rows merge into `images`. Coordinates are the entrance's.

    @param raw: parsed portals.json
    @returns: [{'id', 'building', 'label', 'lat', 'lon', 'e', 'n', 'x', 'z', 'in_map', 'images', 'uri'}] sorted by id
    """
    from geodetic import wgs84_batch_to_osgb
    by_id: dict = {}
    for r in raw:
        p = by_id.setdefault(r['id'], {'id': r['id'], 'building': str(r['building']), 'label': r['label'],
                                       'lat': r['lat'], 'lon': r['lon'], 'images': [], 'uri': r['uri']})
        if r['image'] and r['image'] not in p['images']:
            p['images'].append(r['image'])
    out = list(by_id.values())
    off = load_offsets()
    for p, (e, n) in zip(out, wgs84_batch_to_osgb([(p['lat'], p['lon']) for p in out])):
        p['e'], p['n'] = round(e, 1), round(n, 1)
        p['x'], p['z'] = to_mc(e, n, off)
        p['in_map'] = in_bounds(p['x'], p['z'], off)
    return sorted(out, key=lambda p: (_building_key(p['building']), p['id']))


def _building_key(b: str):
    digits = ''.join(c for c in b if c.isdigit())
    return int(digits) if digits else 10**6, b


def fetch(url: str = SOURCE_URL) -> list:
    """Download the register and rewrite the store.

    @param url: portals.json URL
    @returns: the normalised portals
    """
    with urllib.request.urlopen(url, timeout=60) as r:
        raw = json.load(r)
    portals = normalise(raw)
    STORE.parent.mkdir(parents=True, exist_ok=True)
    STORE.write_text(json.dumps({'source': url, 'count': len(portals), 'portals': portals}, indent=1) + '\n')
    load.cache_clear()
    return portals


@lru_cache(maxsize=1)
def load() -> list:
    """All stored portals ([] when the store is missing).

    @returns: normalised portals (see normalise)
    """
    try:
        return json.loads(STORE.read_text())['portals']
    except (OSError, ValueError, KeyError):
        return []


def in_bbox(x0: float, z0: float, x1: float, z1: float, pad: float = 0) -> list:
    """Portals inside an MC bbox grown by pad.

    @param x0: min X
    @param z0: min Z
    @param x1: max X
    @param z1: max Z
    @param pad: blocks of margin
    @returns: portals
    """
    return [p for p in load() if x0 - pad <= p['x'] <= x1 + pad and z0 - pad <= p['z'] <= z1 + pad]


def in_cell(tx: int, tz: int) -> list:
    """Portals in a 128-block cell.

    @param tx: cell X
    @param tz: cell Z
    @returns: portals
    """
    return in_bbox(tx * 128, tz * 128, tx * 128 + 127, tz * 128 + 127)


def building(num: str) -> list:
    """Every entrance of one university building number ("32", "2A", "63F").

    @param num: building number as the register writes it
    @returns: portals
    """
    return [p for p in load() if p['building'].upper() == str(num).upper()]


def near(x: float, z: float, radius: float = 15) -> list:
    """Portals within radius blocks of a point, nearest first.

    @param x: MC X
    @param z: MC Z
    @param radius: blocks
    @returns: [(distance, portal)]
    """
    hits = [(math.hypot(p['x'] - x, p['z'] - z), p) for p in load()]
    return sorted((h for h in hits if h[0] <= radius), key=lambda h: (h[0], h[1]['id']))


def _dist_to_ring(px: float, pz: float, ring) -> float:
    d = math.inf
    for (ax, az), (bx, bz) in zip(ring, ring[1:] + ring[:1]):
        dx, dz = bx - ax, bz - az
        t = 0 if dx == dz == 0 else max(0, min(1, ((px - ax) * dx + (pz - az) * dz) / (dx * dx + dz * dz)))
        d = min(d, math.hypot(px - (ax + t * dx), pz - (az + t * dz)))
    return d


def for_footprint(rings, reach: float = FOOTPRINT_REACH) -> list:
    """Portals on or within reach blocks of a building footprint (an entrance sits on its wall).

    @param rings: OSM rings [[(x, z), ...]] (outer first), as OSMIndex.buildings holds them
    @param reach: blocks outside the wall that still count
    @returns: portals, nearest the footprint first
    """
    xs = [x for x, _ in rings[0]]
    zs = [z for _, z in rings[0]]
    hits = []
    for p in in_bbox(min(xs), min(zs), max(xs), max(zs), reach):
        d = _dist_to_ring(p['x'], p['z'], rings[0])
        if d <= reach:
            hits.append((d, p['id'], p))
    return [p for _d, _i, p in sorted(hits, key=lambda h: h[:2])]


def describe(p: dict) -> str:
    """One line: id, name, block position, photo count.

    @param p: portal
    @returns: text
    """
    ph = f'{len(p["images"])} photo' + ('s' if len(p['images']) != 1 else '') if p['images'] else 'no photo'
    return f'{p["id"]} "{p["label"]}" at {p["x"]},{p["z"]} ({ph})'


def door_specs(cells, reach: float = DOOR_REACH, pname=None, base=0) -> list:
    """Campus `doors=` specs for the portals that sit against a build's footprint.

    Campus.doors puts the door on the exposed wall cell nearest each anchor, so a portal only needs to be near the
    build; one further than `reach` from every part cell belongs to another building and is skipped.

    @param cells: iterable of (x, z) wall/part cells of the build (e.g. Campus.part keys)
    @param reach: blocks between the portal and the nearest cell
    @param pname: part name to give every spec (None = any part, the base is then taken from the part)
    @param base: floor level handed on as the spec's f (ignored by Campus when pname is None)
    @returns: [(pname, x, z, base)] one per portal, in id order
    """
    cells = list(cells)
    if not cells:
        return []
    xs = [x for x, _ in cells]
    zs = [z for _, z in cells]
    cs = set(cells)
    out = []
    for p in sorted(in_bbox(min(xs), min(zs), max(xs), max(zs), reach), key=lambda q: q['id']):
        r = int(math.ceil(reach))
        if any((round(p['x']) + a, round(p['z']) + b) in cs and math.hypot(a, b) <= reach
               for a in range(-r, r + 1) for b in range(-r, r + 1)):
            out.append((pname, p['x'], p['z'], base))
    return out


def _print(ps: list) -> None:
    for p in ps:
        print(describe(p))
        for u in p['images']:
            print('    ' + u)
    print(f'{len(ps)} portal(s)')


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    sub = ap.add_subparsers(dest='cmd', required=True)
    sub.add_parser('fetch')
    sub.add_parser('info')
    sub.add_parser('cell').add_argument('cell')
    b = sub.add_parser('bbox')
    b.add_argument('bbox')
    b.add_argument('--pad', type=float, default=0)
    sub.add_parser('building').add_argument('number')
    n = sub.add_parser('near')
    n.add_argument('xz')
    n.add_argument('--radius', type=float, default=15)
    a = ap.parse_args(argv)
    if a.cmd == 'fetch':
        ps = fetch()
        print(f'{len(ps)} portals written to {STORE.relative_to(ROOT)}')
    elif a.cmd == 'info':
        ps = load()
        ins = [p for p in ps if p['in_map']]
        print(f'{len(ps)} portals, {len({p["building"] for p in ps})} buildings, {len(ins)} inside the Geocraft map, '
              f'{sum(1 for p in ps if p["images"])} with a photo')
    elif a.cmd == 'cell':
        _print(in_cell(*(int(v) for v in a.cell.split(','))))
    elif a.cmd == 'bbox':
        _print(in_bbox(*(float(v) for v in a.bbox.split(',')), pad=a.pad))
    elif a.cmd == 'building':
        _print(building(a.number))
    elif a.cmd == 'near':
        x, z = (float(v) for v in a.xz.split(','))
        for d, p in near(x, z, a.radius):
            print(f'{d:5.1f}  {describe(p)}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
