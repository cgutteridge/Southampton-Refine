#!/usr/bin/env python3
"""OSM building footprints + named streets in Minecraft coords — the frontage authority.

Reads every OSM clip under reference/osm/ (written by osm_extract.py, WGS84),
reprojects it once to OSGB (EPSG:27700, via ogr2ogr; cached under
verification/site/osm27700/) and converts to MC X/Z with osgb.py.

Why this exists (I-009, 11 Oct 2026): façade builds placed a brick front wall
on the pavement of Broadlands Road because the "street edge" was guessed from
surface blocks. Real houses sat ~6 blocks back behind front gardens. The
house front line comes from these footprints, not from block surveys.

  # which street am I on, where are the fronts, how deep are the gardens?
  python3 scripts/osm_footprints.py frontage --bbox 7040,-5560,7140,-5500
  python3 scripts/osm_footprints.py frontage --street "Broadlands Road" --bbox ...
  # audit cells (a build's archive, or every live kit-owned cell)
  python3 scripts/osm_footprints.py check --build <build_name>
  python3 scripts/osm_footprints.py check --all
  # first-guess property plots (house + front + back garden) for whole-property builds
  python3 scripts/osm_footprints.py plots --bbox 7040,-5560,7140,-5500

site_kit.apply() runs the same check on every plan (see guard()).
"""
from __future__ import annotations

import argparse
import json
import math
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'scripts'))
from osgb import load_offsets  # noqa: E402

OSM = ROOT / 'reference/osm'
CACHE = ROOT / 'verification/site/osm27700'
_CFG = json.loads((ROOT / 'config/world.json').read_text())
# Untouched Geocraft output: ground reference for "how high above the street is this?"
PRISTINE = Path(_CFG.get('pristine_region_path', ''))

# Blocks that may legitimately stand outside a building footprint and rise above
# the ground: garden walls/fences/hedges, trees, street furniture.
FURNITURE = ('_wall', '_fence', 'fence_gate', 'leaves', '_log', '_wood', 'lantern', 'iron_chain',
             'sign', 'banner', 'iron_bars', 'end_rod', 'torch', 'flower', 'bush', 'azalea',
             'sapling', 'grass', 'fern', 'vine', 'potted', 'flower_pot', 'hopper', 'cauldron',
             'lightning_rod', 'button', 'lever', 'composter', 'barrel', 'scaffolding')
AIRS = ('minecraft:air', 'minecraft:cave_air', 'minecraft:light', 'minecraft:void_air', 'minecraft:water')
MAX_RISE = 2      # front zone (street side of the house line): boundary walls/hedges only
BACK_RISE = 4     # back gardens: sheds / outbuildings up to ~4 blocks (cite the aerial)
MARGIN = 2        # footprint dilation (projection + raster error is ~1-2 blocks)


def _projected(src: Path) -> Path:
    """Return a cached EPSG:27700 copy of one WGS84 GeoJSON clip."""
    CACHE.mkdir(parents=True, exist_ok=True)
    dst = CACHE / (src.parent.name + '__' + src.name)
    if not dst.exists() or dst.stat().st_mtime < src.stat().st_mtime:
        dst.unlink(missing_ok=True)
        subprocess.run(['ogr2ogr', '-f', 'GeoJSON', '-t_srs', 'EPSG:27700', str(dst), str(src)],
                       check=True, capture_output=True)
    return dst


class OSMIndex:
    """All buildings and named highways from reference/osm, in MC float coords."""

    def __init__(self, root: Path = OSM):
        o = load_offsets()
        mc = lambda c: (c[0] - o['OFFSET_E'], o['OFFSET_N'] - c[1])
        self.buildings = []   # (rings[[(x,z)...]], props)
        self.streets = []     # (name, highway, [(x,z)...])
        self.street_props = []  # OSM properties of each self.streets entry (same order)
        self.areas = []       # (rings, props) of every non-building polygon (landuse/leisure/amenity/...)
        self.extents = []     # (x0, z0, x1, z1) per clip — where OSM was actually checked
        seen = set()
        for src in sorted(root.glob('*/*.geojson')):
            d = json.loads(_projected(src).read_text())
            xs, zs = [], []
            for f in d['features']:
                g, p = f['geometry'], f['properties']
                if not g:
                    continue
                key = (p.get('osm_id'), p.get('osm_way_id'), g['type'])
                if key in seen:
                    continue
                seen.add(key)
                if g['type'] in ('Polygon', 'MultiPolygon'):
                    polys = [g['coordinates']] if g['type'] == 'Polygon' else g['coordinates']
                    for poly in polys:
                        rings = [[mc(c) for c in r] for r in poly]
                        if p.get('building'):
                            self.buildings.append((rings, p))
                            xs += [x for x, _ in rings[0]]; zs += [z for _, z in rings[0]]
                        else:
                            self.areas.append((rings, p))
                elif g['type'] == 'LineString' and p.get('highway'):
                    self.streets.append((p.get('name'), p['highway'], [mc(c) for c in g['coordinates']]))
                    self.street_props.append(p)
            if xs:
                self.extents.append((min(xs), min(zs), max(xs), max(zs)))
        self._cells = None

    # --- footprint raster ---------------------------------------------------
    def cells(self) -> dict:
        """{(x, z): building index} for every block whose centre is inside a footprint."""
        if self._cells is None:
            self._cells = {}
            for i, (rings, _p) in enumerate(self.buildings):
                xs = [x for x, _ in rings[0]]; zs = [z for _, z in rings[0]]
                for x in range(math.floor(min(xs)), math.ceil(max(xs)) + 1):
                    for z in range(math.floor(min(zs)), math.ceil(max(zs)) + 1):
                        if _inside(x + 0.5, z + 0.5, rings):
                            self._cells[(x, z)] = i
        return self._cells

    def near_footprint(self, x: int, z: int, margin: int = MARGIN) -> bool:
        c = self.cells()
        return any((x + dx, z + dz) in c for dx in range(-margin, margin + 1)
                   for dz in range(-margin, margin + 1))

    def covered(self, x: int, z: int) -> bool:
        """True if (x, z) lies inside an OSM clip we actually have (else the check is blind)."""
        return any(x0 <= x <= x1 and z0 <= z <= z1 for x0, z0, x1, z1 in self.extents)

    def setback(self, i: int) -> float:
        """Distance from building i's closest vertex to the nearest named street centreline."""
        if not hasattr(self, '_sb'):
            self._sb = {}
        if i not in self._sb:
            ds = [self.nearest_street(x, z) for x, z in self.buildings[i][0][0]]
            self._sb[i] = min((d[0] for d in ds if d), default=math.inf)
        return self._sb[i]

    def front_zone(self, x: int, z: int, reach: float = 30) -> bool:
        """True if (x, z) is between a street and the house fronts beside it (front garden / pavement)."""
        s = self.nearest_street(x + 0.5, z + 0.5)
        if not s:
            return False
        near = [i for i, (r, _p) in enumerate(self.buildings)
                if any(abs(vx - x) < reach and abs(vz - z) < reach for vx, vz in r[0])]
        return bool(near) and s[0] < min(self.setback(i) for i in near) - 0.5

    # --- streets --------------------------------------------------------------
    def nearest_street(self, x: float, z: float, named_only: bool = True):
        """(distance, name, highway, foot_point) of the closest highway centreline."""
        best = None
        for name, hw, pts in self.streets:
            if named_only and not name:
                continue
            for a, b in zip(pts, pts[1:]):
                d, foot = _seg_dist((x, z), a, b)
                if best is None or d < best[0]:
                    best = (d, name, hw, foot)
        return best


def _inside(x: float, z: float, rings) -> bool:
    """Even-odd point-in-polygon over outer ring + holes."""
    n = False
    for r in rings:
        for (x1, z1), (x2, z2) in zip(r, r[1:] + r[:1]):
            if (z1 > z) != (z2 > z) and x < (x2 - x1) * (z - z1) / (z2 - z1) + x1:
                n = not n
    return n


def _seg_dist(p, a, b):
    (px, pz), (ax, az), (bx, bz) = p, a, b
    dx, dz = bx - ax, bz - az
    t = 0 if dx == dz == 0 else max(0, min(1, ((px - ax) * dx + (pz - az) * dz) / (dx * dx + dz * dz)))
    foot = (ax + t * dx, az + t * dz)
    return math.dist(p, foot), foot


_HSTORE = re.compile(r'"((?:[^"\\]|\\.)*)"=>"((?:[^"\\]|\\.)*)"')


def osm_tags(p: dict) -> dict:
    """Flatten one ogr2ogr feature's properties: top-level columns plus the other_tags hstore.

    @param p: GeoJSON feature properties as written by osm_extract.py / ogr2ogr
    @returns: {key: value}; top-level columns win over duplicate other_tags keys
    """
    t = {k: v for k, v in p.items() if v not in (None, '') and k != 'other_tags'}
    for k, v in _HSTORE.findall(p.get('other_tags') or ''):
        t.setdefault(k.replace('\\"', '"'), v.replace('\\"', '"'))
    return t


def _addr(p) -> tuple[str, str]:
    tags = p.get('other_tags') or ''
    get = lambda k: (tags.split(f'"addr:{k}"=>"', 1)[1].split('"', 1)[0]
                     if f'"addr:{k}"=>"' in tags else '')
    return get('housenumber'), get('street')


# --- the guard used by site_kit.apply() ------------------------------------------
def guard(cells: dict, world=None, idx: OSMIndex | None = None) -> dict:
    """Find building-like blocks standing in front of / outside every OSM footprint.

    @param cells: {(x, y, z): state}
    @param world: site_kit.World for the ground reference (default: pristine Geocraft)
    Front zone (street side of the house line): max MAX_RISE. Back gardens: BACK_RISE.
    @returns: {'outside': {pos: [state, rise, zone, street, dist]}, 'blind': [pos...]}
    """
    from site_kit import World, bid
    idx = idx or OSMIndex()
    w = world or World(PRISTINE)
    ground = {}
    out, blind = {}, []
    for (x, y, z), st in cells.items():
        b = bid(st)
        if b in AIRS or any(k in b for k in FURNITURE):
            continue
        covered = idx.covered(x, z)
        if covered and idx.near_footprint(x, z):
            continue
        if (x, z) not in ground:
            ground[(x, z)] = w.ground(x, z, top=120, bottom=0)
        rise = y - ground[(x, z)]
        if rise <= MAX_RISE:
            continue          # kerbs, paving, low garden walls: fine anywhere
        if not covered:
            blind.append((x, y, z))
            continue
        front = idx.front_zone(x, z)
        if not front and rise <= BACK_RISE:
            continue          # back-garden shed / outbuilding height
        s = idx.nearest_street(x, z)
        out[(x, y, z)] = [st, rise, 'front' if front else 'back',
                          s[1] if s else None, round(s[0], 1) if s else None]
    return {'outside': out, 'blind': blind}


# --- CLI ------------------------------------------------------------------------
def frontage(args):
    from site_kit import World
    idx = OSMIndex()
    live = World()
    x0, z0, x1, z1 = map(int, args.bbox.split(','))
    rows = []
    for i, (rings, p) in enumerate(idx.buildings):
        cx = sum(x for x, _ in rings[0]) / len(rings[0]); cz = sum(z for _, z in rings[0]) / len(rings[0])
        if not (x0 <= cx <= x1 and z0 <= cz <= z1):
            continue
        num, street = _addr(p)
        if args.street and street != args.street:
            continue
        # the front is the footprint vertex closest to its own street (or the nearest named one)
        cands = [(idx.nearest_street(x, z), (x, z)) for x, z in rings[0]]
        if street:
            own = [(s, v) for s, v in ((_street_dist(idx, street, v), v) for _, v in cands) if s]
            cands = own or cands
        (d, sname, _hw, foot), front = min(cands, key=lambda c: c[0][0])
        # live block profile from the front wall back to the centreline
        n = max(1, int(math.ceil(d)))
        prof = []
        for k in range(1, n + 1):
            px = front[0] + (foot[0] - front[0]) * k / n; pz = front[1] + (foot[1] - front[1]) * k / n
            gx, gz = math.floor(px), math.floor(pz)
            y = live.ground(gx, gz, top=120, bottom=0)
            prof.append(live.block(gx, y, gz).split('[')[0][10:])
        rows.append((sname or '?', num or '-', round(d, 1), [round(front[0]), round(front[1])],
                     _runs(prof[::-1])))
    rows.sort(key=lambda r: (r[0], _numkey(r[1])))
    print('street | no. | front wall -> centreline (blocks) | front wall MC x,z | live surface centreline -> front')
    for r in rows:
        print(f'{r[0]} | {r[1]} | {r[2]} | {r[3]} | {r[4]}')
    print('\nRead: setback ≫ (carriageway half-width + pavement) means FRONT GARDENS between '
          'pavement and house. Build the house front at "front wall MC x,z", never at the kerb.')


STREET_SURFACE = ('gray_terracotta', 'polished_diorite', 'smooth_stone', 'andesite', 'gravel')


def street_surface(world, x: int, z: int) -> bool:
    """True if the top surface block of column (x, z) is a road / pavement block.

    @param world: site_kit.World to read (live save or pristine Geocraft)
    @param x: MC block x
    @param z: MC block z
    @returns: whether the surface block id is in STREET_SURFACE
    """
    y = world.ground(x, z, top=120, bottom=0)
    return (world.block(x, y, z) or '').split('[')[0][10:] in STREET_SURFACE


def grow_plots(seeds: dict, passable, reach: float = 45) -> dict:
    """Grow plots outwards from footprint cells: an approximate Euclidean Voronoi.

    Dijkstra keyed on straight-line distance to the seeding footprint cell, so plot sides
    run perpendicular to the street like real garden strips.

    @param seeds: {(x, z): owner} footprint cells that start growing at distance 0
    @param passable: callable(x, z) -> bool; False stops growth (street surface, other footprints)
    @param reach: max straight-line distance a plot may grow from its seeding cell
    @returns: {(x, z): owner} for every seed cell and every cell grown over
    """
    import heapq
    owner, heap = {}, []
    for (x, z), i in seeds.items():
        heapq.heappush(heap, (0.0, x, z, x, z, i))
    while heap:
        d, x, z, sx, sz, i = heapq.heappop(heap)
        if (x, z) in owner:
            continue
        owner[(x, z)] = i
        for dx in (-1, 0, 1):
            for dz in (-1, 0, 1):
                nx, nz = x + dx, z + dz
                if (dx or dz) and (nx, nz) not in owner and passable(nx, nz):
                    nd = math.hypot(nx - sx, nz - sz)
                    if nd <= reach:
                        heapq.heappush(heap, (nd, nx, nz, sx, sz, i))
    return owner


def plots(args):
    """First-guess property plots: grow every footprint outwards over garden ground
    (nearest house by straight-line distance) until it meets the street surface or a neighbour.
    Party walls -> plot sides, road -> front edge, meeting neighbour's garden -> back fence.
    A starting point only: move fences to what the aerial shows."""
    from site_kit import World, OUT
    idx = OSMIndex()
    live = World()
    x0, z0, x1, z1 = map(int, args.bbox.split(','))
    fp = idx.cells()
    seeds = {(x, z): i for (x, z), i in fp.items()
             if x0 - 60 <= x <= x1 + 60 and z0 - 60 <= z <= z1 + 60}
    surf = {}

    def passable(x, z):
        if (x, z) in fp:
            return False
        if (x, z) not in surf:
            surf[(x, z)] = street_surface(live, x, z)
        return not surf[(x, z)]
    owner = grow_plots(seeds, passable, args.reach)
    houses = {}
    for (x, z), i in owner.items():
        houses.setdefault(i, []).append((x, z))
    rep = {}
    for i, cs in houses.items():
        rings, p = idx.buildings[i]
        cx = sum(x for x, _ in rings[0]) / len(rings[0]); cz = sum(z for _, z in rings[0]) / len(rings[0])
        if not (x0 <= cx <= x1 and z0 <= cz <= z1):
            continue
        num, st = _addr(p)
        house = [c for c in cs if c in fp]
        front = [c for c in cs if c not in fp and idx.front_zone(*c)]
        rep[f'{st or "?"} {num or "#" + str(i)}'] = {
            'osm': p.get('osm_id') or p.get('osm_way_id'),
            'house_cells': len(house), 'front_garden_cells': len(front),
            'back_garden_cells': len(cs) - len(house) - len(front),
            'bbox': [min(x for x, _ in cs), min(z for _, z in cs), max(x for x, _ in cs), max(z for _, z in cs)],
            'cells': sorted([x, z] for x, z in cs)}
    out = OUT / f'plots-{x0}_{z0}_{x1}_{z1}.json'
    out.write_text(json.dumps(rep))
    for k, v in sorted(rep.items(), key=lambda kv: (kv[0].rsplit(' ', 1)[0], _numkey(kv[0].rsplit(' ', 1)[-1]))):
        print(f'{k}: house {v["house_cells"]}, front garden {v["front_garden_cells"]}, '
              f'back garden {v["back_garden_cells"]}, plot bbox {v["bbox"]}')
    print('cells per plot:', out)
    try:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        import numpy as np
        img = np.ones((z1 - z0 + 1, x1 - x0 + 1, 3))
        rng = np.random.default_rng(1)
        for k, v in rep.items():
            c = rng.uniform(0.35, 0.95, 3)
            for x, z in v['cells']:
                if x0 <= x <= x1 and z0 <= z <= z1:
                    img[z - z0, x - x0] = c * (0.6 if (x, z) in fp else 1)
        fig, ax = plt.subplots(figsize=(12, 12 * img.shape[0] / img.shape[1] + 1))
        ax.imshow(img, extent=(x0 - .5, x1 + .5, z1 + .5, z0 - .5), interpolation='nearest')
        for k, v in rep.items():
            b = v['bbox']
            ax.text((b[0] + b[2]) / 2, (b[1] + b[3]) / 2, k.rsplit(' ', 1)[-1], fontsize=7, ha='center')
        ax.set_title('first-guess plots (dark = OSM house footprint)')
        png = out.with_suffix('.png')
        plt.savefig(png, dpi=90)
        print('preview:', png)
    except ImportError:
        pass


def _street_dist(idx, name, v):
    best = None
    for n, hw, pts in idx.streets:
        if n != name:
            continue
        for a, b in zip(pts, pts[1:]):
            d, foot = _seg_dist(v, a, b)
            if best is None or d < best[0]:
                best = (d, n, hw, foot)
    return best


def _numkey(s):
    digits = ''.join(ch for ch in s if ch.isdigit())
    return (int(digits) if digits else 1 << 30, s)


def _runs(seq):
    out = []
    for s in seq:
        if out and out[-1][0] == s:
            out[-1][1] += 1
        else:
            out.append([s, 1])
    return ' '.join(f'{s}×{n}' for s, n in out)


def check(args):
    from site_kit import OUT, built_cells
    if args.all:
        cells = {q: st for q, (_n, st) in built_cells().items()}
        owner = {q: n for q, (n, _st) in built_cells().items()}
    else:
        f = OUT / f'{args.build}-cells.json'
        cells = {tuple(int(v) for v in k.split(',')): st for k, st in json.loads(f.read_text()).items()}
        owner = {q: args.build for q in cells}
    rep = guard(cells)
    by = {}
    for q, v in rep['outside'].items():
        by.setdefault(owner[q], []).append((q, v))
    for n, hits in sorted(by.items()):
        print(f'{n}: {len(hits)} building-like cells outside OSM footprints, e.g. {hits[:3]}')
    if rep['blind']:
        print(f'{len(rep["blind"])} cells outside every OSM clip (run osm_extract.py for the area), '
              f'e.g. {rep["blind"][:3]}')
    if not by and not rep['blind']:
        print('OK: no building-like cells outside OSM footprints')
    return 1 if by else 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest='cmd', required=True)
    f = sub.add_parser('frontage', help='per-house street, front line and garden profile')
    f.add_argument('--bbox', required=True, help='x0,z0,x1,z1 (MC) — building centroids inside')
    f.add_argument('--street', help='only houses whose addr:street matches')
    pl = sub.add_parser('plots', help='first-guess plot per house (house + front + back garden)')
    pl.add_argument('--bbox', required=True, help='x0,z0,x1,z1 (MC) — house centroids inside')
    pl.add_argument('--reach', type=int, default=45, help='max garden depth grown from a house')
    c = sub.add_parser('check', help='building-like cells outside OSM footprints')
    g = c.add_mutually_exclusive_group(required=True)
    g.add_argument('--build')
    g.add_argument('--all', action='store_true')
    a = ap.parse_args()
    if a.cmd == 'plots':
        return plots(a) or 0
    return frontage(a) or 0 if a.cmd == 'frontage' else check(a)


if __name__ == '__main__':
    sys.exit(main())
