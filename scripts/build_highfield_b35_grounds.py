#!/usr/bin/env python3
"""Q-024: grounds, roads and car parks around Building 35 (David Kiddle), Highfield campus.

Evidence
  OSM      amenity=parking polygons 146987889 (west, aisles 146987519/225775085),
           225506879 (south, under carport roof 146988290), 148269865, 148271081,
           148271080, 148271082 (street-side bays); service roads 1148011428 (north
           road), 93733742 / 1056414696 (east + south service), 225775079 (car park
           access), 6628877 / 245802748; footways 265695542 etc.; bike shed 242322573.
  aerial   reference/aerial/highfield-b35/mosaic-z18-3x3-centre-130056-87836.png
           (green = verge / planting, dark green = tree canopy, grey = paving)
  LIDAR    pristine Geocraft terrain Y (kept; single-cell spikes smoothed)

Surfaces: tarmac gray_concrete (``campus.TARMAC``), paving polished_diorite (project PAVE),
smooth_stone kerbs on road edges, white_concrete bay lines, grass + a few trees where
the aerial is green. Geocraft junk (brick fringe, carpet) above the ground is cleared.
Other buildings' footprints (+2) are left alone; their grounds wait for their own builds.
"""
import argparse
import json
import math
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'scripts'))
from campus import TARMAC  # noqa: E402
from site_kit import Plan, World, apply, preview  # noqa: E402
from osm_footprints import OSMIndex, PRISTINE  # noqa: E402
from coverage import LEFTOVER_TOP  # noqa: E402
from osgb import load_offsets, to_osgb  # noqa: E402
import build_highfield_b35 as B35  # noqa: E402

NAME = 'highfield_b35_grounds'
BOX = (6338, -5547, 6440, -5428)
REACH = 14                      # grounds = within this of B35, plus the car parks
ASPHALT, PAVE, KERB, LINE, GRASS = TARMAC, 'polished_diorite', 'smooth_stone', 'white_concrete', 'grass_block'
MOSAIC = ROOT / 'reference/aerial/highfield-b35/mosaic-z18-3x3-centre-130056-87836.png'
SRC = ROOT / 'verification/site/osm27700/highfield-b35-park-hw.geojson'

PARKING = {'146987889', '225506879', '148269865', '148271081', '148271080', '148271082'}
AISLES = {'146987519', '225775085', '225506877', '1170405960'}
ROADS = {'1148011428': 3.2, '1148011429': 3.2, '93733742': 2.4, '1056414696': 2.4,
         '225775079': 2.6, '6628877': 2.6, '245802748': 2.4, '9660160': 3.0, '1177230774': 2.6}
FOOTWAYS = {'265695542', '266839959', '371586379', '1147402500', '1263025771'}
CANOPY = '146988290'
BIKE_SHED = '242322573'
ROOF_SLAB = 'smooth_stone_slab[type=bottom,waterlogged=false]'


def load_osm():
    """Parking/grass/wood polygons and highway lines (EPSG:27700) → MC coords."""
    if not SRC.exists():
        pbf = ROOT / 'downloads/hampshire-latest.osm.pbf'
        spat = ['-spat', '-1.3975', '50.9325', '-1.3925', '50.9350']
        tmp = []
        for layer, where in (('multipolygons', "amenity IS NOT NULL OR landuse IS NOT NULL OR "
                              "\"natural\" IS NOT NULL OR building IS NOT NULL"),
                             ('lines', 'highway IS NOT NULL OR barrier IS NOT NULL')):
            out = SRC.with_suffix(f'.{layer}.geojson')
            out.unlink(missing_ok=True)
            subprocess.run(['ogr2ogr', '-f', 'GeoJSON', '-t_srs', 'EPSG:27700', str(out), str(pbf), layer,
                            *spat, '-where', where], check=True, capture_output=True)
            tmp.append(json.loads(out.read_text()))
            out.unlink()
        SRC.write_text(json.dumps({'type': 'FeatureCollection',
                                   'features': tmp[0]['features'] + tmp[1]['features']}))
    o = load_offsets()
    mc = lambda c: (c[0] - o['OFFSET_E'], o['OFFSET_N'] - c[1])
    polys, lines = {}, {}
    for f in json.loads(SRC.read_text())['features']:
        g, p = f['geometry'], f['properties']
        oid = p.get('osm_way_id') or p.get('osm_id')
        if g['type'] == 'LineString':
            lines[oid] = (p, [mc(c) for c in g['coordinates']])
        elif g['type'] in ('Polygon', 'MultiPolygon'):
            ring = (g['coordinates'][0] if g['type'] == 'MultiPolygon' else g['coordinates'])[0]
            polys[oid] = (p, [mc(c) for c in ring])
    return polys, lines


def inside(x, z, ring):
    c = False
    for (x1, z1), (x2, z2) in zip(ring, ring[1:] + ring[:1]):
        if (z1 > z) != (z2 > z) and x < x1 + (z - z1) * (x2 - x1) / (z2 - z1):
            c = not c
    return c


def seg_dist(p, line):
    best = (1e9, 0.0)
    acc = 0.0
    for a, b in zip(line, line[1:]):
        ax, az = a; bx, bz = b
        L2 = (bx - ax) ** 2 + (bz - az) ** 2 or 1e-9
        t = max(0, min(1, ((p[0] - ax) * (bx - ax) + (p[1] - az) * (bz - az)) / L2))
        d = math.hypot(p[0] - ax - t * (bx - ax), p[1] - az - t * (bz - az))
        if d < best[0]:
            best = (d, acc + t * math.sqrt(L2))
        acc += math.sqrt(L2)
    return best             # (distance, position along the line)


def aerial_colours(cells):
    """{(x, z): (r, g, b)} sampled from the z18 mosaic at each block centre."""
    import re
    from PIL import Image
    m = re.search(r'mosaic-z(\d+)-(\d+)x\d+-centre-(\d+)-(\d+)', MOSAIC.name)
    Z, h = int(m[1]), int(m[2]) // 2
    OXp, OYp = (int(m[3]) - h) * 256, (int(m[4]) - h) * 256
    img = Image.open(MOSAIC).convert('RGB')
    cells = list(cells)
    inp = ''.join('%f %f\n' % to_osgb(x + 0.5, z + 0.5) for x, z in cells)
    out = subprocess.run(['gdaltransform', '-s_srs', 'EPSG:27700', '-t_srs', 'EPSG:4326'],
                         input=inp.encode(), capture_output=True, check=True).stdout.decode().split('\n')
    res, n = {}, 2 ** Z * 256
    for (x, z), line in zip(cells, out):
        lon, lat = map(float, line.split()[:2])
        X = (lon + 180) / 360 * n - OXp
        Y = (1 - math.log(math.tan(math.radians(lat)) + 1 / math.cos(math.radians(lat))) / math.pi) / 2 * n - OYp
        px = [img.getpixel((int(X) + i, int(Y) + j)) for i in (0, 1) for j in (0, 1)]
        res[(x, z)] = tuple(sum(c[k] for c in px) // 4 for k in range(3))
    return res


class Grounds:
    def __init__(self):
        self.p = Plan(NAME)
        self.w = World()
        self.pristine = World(PRISTINE)
        self.b = B35.Build()                       # B35 parts + terrain helpers (no build)
        self.idx = self.b.idx
        self.polys, self.lines = load_osm()
        b35 = json.loads((ROOT / f'verification/site/{B35.NAME}-cells.json').read_text())
        self.b35_cols = {}
        for k, st in b35.items():
            x, y, z = map(int, k.split(','))
            if 'andesite' in st or 'stairs' in st or 'door' in st:
                self.b35_cols[(x, z)] = 'approach'
        other = self.b.other
        self.other2 = {(x + dx, z + dz) for x, z in other for dx in range(-2, 3) for dz in range(-2, 3)}
        self.other1 = {(x + dx, z + dz) for x, z in other for dx in range(-1, 2) for dz in range(-1, 2)}
        mass = set(self.b.part)
        x0, z0, x1, z1 = BOX
        near = {(x + dx, z + dz) for x, z in mass for dx in range(-REACH, REACH + 1, 1)
                for dz in range(-REACH, REACH + 1) if dx * dx + dz * dz <= REACH * REACH}
        parks = [r for oid, (p, r) in self.polys.items()
                 if oid in PARKING or oid in (CANOPY, BIKE_SHED)]
        self.scope = set()
        for x in range(x0, x1 + 1):
            for z in range(z0, z1 + 1):
                q = (x, z)
                if q in mass or q in self.b35_cols or q in other:
                    continue
                if q in near or any(inside(x + .5, z + .5, r) for r in parks):
                    self.scope.add(q)

    def classify(self):
        P = self.polys
        self.kind, self.mark = {}, set()
        col = aerial_colours(self.scope)
        self.tree_cells = set()
        for (x, z) in self.scope:
            c = (x + .5, z + .5)
            k = None
            for oid in PARKING:
                if oid in P and inside(*c, P[oid][1]):
                    k = 'park'
                    if self.bay_line(c, oid):
                        self.mark.add((x, z))
                    break
            if k is None:
                for oid, hw in ROADS.items():
                    if oid in self.lines and seg_dist(c, self.lines[oid][1])[0] <= hw:
                        k = 'road'
                        break
            if k is None:
                for oid in AISLES:
                    if oid in self.lines and seg_dist(c, self.lines[oid][1])[0] <= 2.6:
                        k = 'park'
                        break
            if k is None:
                for oid in FOOTWAYS:
                    if oid in self.lines and seg_dist(c, self.lines[oid][1])[0] <= 1.2:
                        k = 'pave'
                        break
            if k is None:
                r, g, b = col[(x, z)]
                wood = any(inside(*c, p[1]) for oid, p in P.items() if p[0].get('natural') == 'wood')
                grass = any(inside(*c, p[1]) for oid, p in P.items() if p[0].get('landuse') == 'grass')
                green = g > r + 15 and g > b + 15      # shadows here are dark teal (g-b ~8)
                if grass or green or wood:
                    k = 'grass'
                    if green and (r + g + b) < 200:
                        self.tree_cells.add((x, z))
                else:
                    k = 'pave'
            self.kind[(x, z)] = k

    def bay_line(self, c, oid):
        """White line every 3 blocks across the bays: aisle-relative where an aisle runs through
        the car park, otherwise along the polygon's long side."""
        best = None
        for a in AISLES:
            if a in self.lines:
                d, t = seg_dist(c, self.lines[a][1])
                if best is None or d < best[0]:
                    best = (d, t)
        if best and best[0] < 8 and oid in ('146987889', '225506879'):
            d, t = best
            return 3.0 <= d <= 7.5 and int(t) % 3 == 0
        ring = self.polys[oid][1]
        (ax, az), (bx, bz) = max(zip(ring, ring[1:]), key=lambda e: math.dist(*e))
        L = math.dist((ax, az), (bx, bz)) or 1
        t = ((c[0] - ax) * (bx - ax) + (c[1] - az) * (bz - az)) / L
        return int(math.floor(t)) % 3 == 0

    def ground(self, q):
        return self.b.outside_ground(*q)

    def surface(self):
        gy = {q: self.ground(q) for q in self.scope}
        # smooth single-cell spikes against same-kind neighbours (LIDAR noise on flat car parks)
        sm = {}
        for (x, z), y in gy.items():
            nb = [gy[(x + dx, z + dz)] for dx in (-1, 0, 1) for dz in (-1, 0, 1)
                  if (x + dx, z + dz) in gy and self.kind.get((x + dx, z + dz)) == self.kind[(x, z)]]
            nb.sort()
            med = nb[len(nb) // 2]
            sm[(x, z)] = med if abs(med - y) >= 1 and self.kind[(x, z)] in ('park', 'road') else y
        self.gy = sm
        for q in self.scope:
            x, z = q
            y = sm[q]
            k = self.kind[q]
            edge = q in self.other2
            if edge:
                # beside another (unprocessed) building: only resurface open columns
                above = self.w.block(x, y + 1, z) or 'minecraft:air'
                if q in self.other1 or not above.endswith('air'):
                    continue
            mat = {'park': ASPHALT, 'road': ASPHALT, 'pave': PAVE, 'grass': GRASS}[k]
            if k == 'park' and q in self.mark:
                mat = LINE
            if k == 'pave' and any(self.kind.get((x + dx, z + dz)) == 'road' for dx, dz in B35.N4):
                mat = KERB
            for yy in range(y - 2, y):
                self.p.set(x, yy, z, 'stone' if mat != GRASS else 'dirt')
            self.p.set(x, y, z, mat)
            if edge:
                continue
            for yy in range(y + 1, B35.CLEAR_TO + 1):
                b = self.w.block(x, yy, z) or 'minecraft:air'
                if not any(k2 in b for k2 in B35.KEEP):
                    self.p.set(x, yy, z, 'air')

    def trees(self):
        """Tree where the aerial canopy is dark green, one per 6x6 cell, not on hard surfaces."""
        placed = []
        for x, z in sorted(self.tree_cells):
            if self.kind[(x, z)] != 'grass' or (x, z) in self.other2:
                continue
            if any(abs(x - a) < 6 and abs(z - b) < 6 for a, b in placed):
                continue
            if any(self.w.block(x, yy, z) and '_log' in self.w.block(x, yy, z) for yy in range(40, 75)):
                continue
            placed.append((x, z))
            y = self.gy[(x, z)]
            for i in range(1, 6):
                self.p.set(x, y + i, z, 'oak_log')
            for dx in range(-2, 3):
                for dz in range(-2, 3):
                    for dy in range(4, 8):
                        if abs(dx) + abs(dz) + max(0, dy - 6) * 2 <= 3 and not (dx == dz == 0 and dy < 6):
                            q = (x + dx, z + dz)
                            if q in self.scope and q not in self.other2:
                                self.p.set(x + dx, y + dy, z + dz, 'oak_leaves[persistent=true]')
        self.placed_trees = placed

    def shelters(self):
        """Carport canopy (OSM roof 146988290, LIDAR top 56) and the covered bike shed."""
        # Flat canopies read from below: bottom slabs (not top slabs floating in air).
        specs = (
            (CANOPY, 4, ROOF_SLAB, 'stone_brick_wall', 5),
            (BIKE_SHED, 3, ROOF_SLAB, 'iron_bars', 1),
        )
        for oid, h, deck, post, post_stride in specs:
            ring = self.polys[oid][1]
            cells = {(x, z) for x in range(int(min(a for a, _ in ring)) - 1, int(max(a for a, _ in ring)) + 2)
                     for z in range(int(min(b for _, b in ring)) - 1, int(max(b for _, b in ring)) + 2)
                     if inside(x + .5, z + .5, ring)}
            base = max(self.gy.get(q, self.ground(q)) for q in cells)
            for x, z in cells:
                if (x, z) in self.b.part:
                    continue
                g = self.gy.get((x, z), self.ground((x, z)))
                for yy in range(g + 1, base + h):
                    if (x, yy, z) not in self.p.cells or self.p.cells[(x, yy, z)].endswith('air'):
                        self.p.set(x, yy, z, 'air')
                edge = sum((x + dx, z + dz) in cells for dx, dz in B35.N4) < 4
                if edge and (x + z) % post_stride == 0:
                    for yy in range(g + 1, base + h):
                        self.p.set(x, yy, z, post)
                self.p.set(x, base + h, z, deck)
                for yy in range(base + h + 1, LEFTOVER_TOP + 1):
                    lb = (self.w.block(x, yy, z) or '').split('[')[0]
                    pb = (self.pristine.block(x, yy, z) or '').split('[')[0]
                    if lb == pb and pb not in ('minecraft:air', 'minecraft:cave_air',
                                               'minecraft:void_air', 'minecraft:light'):
                        self.p.set(x, yy, z, 'air')

    def build(self):
        self.classify()
        self.surface()
        self.trees()
        self.shelters()
        return self.p


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--apply', action='store_true')
    a = ap.parse_args()
    g = Grounds()
    plan = g.build()
    from collections import Counter
    print('scope', len(g.scope), Counter(g.kind.values()), 'lines', len(g.mark), 'trees', g.placed_trees)
    preview(plan, ROOT / f'verification/site/{NAME}-preview.png', scale=3)
    print(json.dumps(plan.summary())[:600])
    plan.outside_footprint_ok = None
    apply(plan, dry=not a.apply, modifies=(B35.NAME,))
