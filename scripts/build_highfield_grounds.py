#!/usr/bin/env python3
"""Q-038: Highfield campus non-building land — every ground column inside the campus polygon
(OSM way 1170405958) that no earlier build owns and no OSM building covers.

Q-024..Q-037 built every campus building with a 3-cell envelope; the rest of the ground was
still Geocraft: bare stone where landuse=university had no finer tag, black wool on
pedestrian/cycle ways, granite on footways, default-width gray_terracotta roads.

Evidence
  OSM      hampshire-latest.osm.pbf clipped to the campus (EPSG:27700 cache
           verification/site/osm27700/highfield-campus-grounds-{mp,ln,pt}.geojson):
           roads / service / parking aisles, amenity=parking (+ bay lines), highway=pedestrian
           areas, footways / cycleways / steps by surface=*, landuse=grass, leisure=garden/park,
           natural=wood, landuse=flowerbed, barrier=hedge/wall/fence, natural=tree points
  aerial   reference/aerial/highfield-campus/mosaic-z18-8x8-centre-130055-87834.png: where OSM
           has no ground tag — green → lawn, red-brown → block paving, light grey → paving,
           dark grey → asphalt (lawn if Geocraft already had grass: shadow), dark green canopy
           → extra trees on lawns/woods
  LIDAR    heights kept: each column is re-topped at its live surface Y; only single-cell
           spikes on hard surfaces are smoothed (±1), never next to a build or a footprint

Left alone: water and its banks (1 ring), Geocraft carpet masses (I-026) + 2 ring, timber
bridges, Geocraft trees (logs/leaves are never touched), columns owned by any build.

  .venv/bin/python scripts/build_highfield_grounds.py --zone nw          # preview + dry-run guards
  SITE_OWNER=... .venv/bin/python scripts/build_highfield_grounds.py --zone nw --apply
Zones: 3x3 grid nw nc ne / mw mc me / sw sc se (X 5950|6150|6350|6550, Z -5990|-5786|-5582|-5370);
one build each: highfield_grounds_<zone>.
"""
import argparse
import json
import math
import random
import statistics
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'scripts'))
from site_kit import Plan, World, apply, preview, built_cells  # noqa: E402
from osm_footprints import OSMIndex, _projected  # noqa: E402
from osgb import load_offsets  # noqa: E402
from campus import aerial_rgb, inside, is_water, N4  # noqa: E402

SRC = ROOT / 'verification/site/osm27700/highfield-campus-grounds-{}.geojson'
CAMPUS = ROOT / 'reference/osm/highfield-campus/multipolygons-r600m-at-6250--5560.geojson'
# 3x3 grid (rows n/m/s by Z, columns w/c/e by X) so each kit backup box stays under ~2M blocks
ZONES = {f'{r}{c}': (x0, z0, x1, z1)
         for r, (z0, z1) in zip('nms', ((-5990, -5787), (-5786, -5583), (-5582, -5370)))
         for c, (x0, x1) in zip('wce', ((5950, 6149), (6150, 6349), (6350, 6550)))}

MAT = {'road': 'gray_terracotta', 'proad': 'polished_andesite', 'park': 'gray_terracotta', 'bay': 'white_concrete',
       'mark': 'white_concrete', 'pave': 'polished_diorite', 'kerb': 'smooth_stone',
       'asph': 'polished_andesite', 'brick': 'polished_granite', 'gravel': 'gravel',
       'dirt': 'coarse_dirt', 'site': 'coarse_dirt', 'grass': 'grass_block', 'flower': 'grass_block', 'wood': 'grass_block'}
HARD = ('road', 'proad', 'park', 'bay', 'mark', 'pave', 'kerb', 'asph', 'brick', 'gravel', 'dirt', 'site')
SOFT = ('grass', 'flower', 'wood')
# road half-widths (blocks) by highway=*; service by service=*
HALF = {'primary': 3.6, 'secondary': 3.6, 'tertiary': 3.2, 'residential': 3.0, 'unclassified': 3.0,
        'service': 2.4, 'track': 1.5}
SERVICE_HALF = {'parking_aisle': 2.6, 'driveway': 1.6, 'alley': 1.8}
PATH_HALF = {'footway': 1.0, 'cycleway': 1.3, 'steps': 1.0, 'path': 0.8, 'pedestrian': 1.6,
             'bridleway': 1.0, 'corridor': 0.0, 'elevator': 0.0}
PATH_SURF = {'asphalt': 'asph', 'paving_stones': 'pave', 'concrete': 'pave', 'paved': 'pave',
             'sett': 'brick', 'bricks': 'brick', 'fine_gravel': 'gravel', 'gravel': 'gravel',
             'compacted': 'gravel', 'dirt': 'dirt', 'ground': 'dirt', 'grass': 'grass', 'unpaved': 'gravel'}
# priority: higher wins where features overlap
PRI = {'site': 95, 'road': 90, 'path': 60, 'park': 50, 'plaza': 40, 'flower': 32, 'grass': 30, 'wood': 25}
PLANTS = ('short_grass', 'tall_grass', 'fern', 'flower', 'tulip', 'poppy', 'dandelion', 'daisy', 'bluet',
          'orchid', 'allium', 'cornflower', 'lily', 'bush', 'rose')
# surface car parks on the aerial with no OSM amenity=parking (cars visible): (x0, z0, x1, z1)
HAND_PARK = {'centenary_n': (6163, -5852, 6247, -5800)}     # S of Salisbury Rd round Centenary (I-026 D)
HOARDING = 'spruce_planks'
FLOWERS = ('poppy', 'dandelion', 'oxeye_daisy', 'cornflower', 'azure_bluet', 'red_tulip', 'white_tulip')


def tags(p):
    t = dict(p)
    for kv in (p.get('other_tags') or '').split('","'):
        if '=>' in kv:
            k, v = kv.split('=>', 1)
            t.setdefault(k.strip('"'), v.strip('"'))
    return t


def seg_dist(px, pz, a, b):
    (ax, az), (bx, bz) = a, b
    L2 = (bx - ax) ** 2 + (bz - az) ** 2 or 1e-9
    t = max(0.0, min(1.0, ((px - ax) * (bx - ax) + (pz - az) * (bz - az)) / L2))
    return math.hypot(px - ax - t * (bx - ax), pz - az - t * (bz - az)), t * math.sqrt(L2)


def line_cells(pts, half, pad=0.0):
    """{(x, z): (dist, along)} for cells whose centre is within half(+pad) of the polyline."""
    out, acc = {}, 0.0
    r = half + pad
    for a, b in zip(pts, pts[1:]):
        for x in range(math.floor(min(a[0], b[0]) - r) - 1, math.ceil(max(a[0], b[0]) + r) + 1):
            for z in range(math.floor(min(a[1], b[1]) - r) - 1, math.ceil(max(a[1], b[1]) + r) + 1):
                d, t = seg_dist(x + .5, z + .5, a, b)
                if d <= r and ((x, z) not in out or d < out[(x, z)][0]):
                    out[(x, z)] = (d, acc + t)
        acc += math.dist(a, b)
    return out


def poly_cells(polys):
    """Cells inside a MultiPolygon given as [[outer, inner...], ...] in MC coords."""
    out = set()
    for rings in polys:
        o = rings[0]
        for x in range(math.floor(min(p[0] for p in o)), math.ceil(max(p[0] for p in o)) + 1):
            for z in range(math.floor(min(p[1] for p in o)), math.ceil(max(p[1] for p in o)) + 1):
                c = (x + .5, z + .5)
                if inside(*c, o) and not any(inside(*c, h) for h in rings[1:]):
                    out.add((x, z))
    return out


class Grounds:
    def __init__(self, zone):
        self.zone = zone
        self.name = f'highfield_grounds_{zone}'
        self.p = Plan(self.name)
        self.w = World()
        o = load_offsets()
        self.mc = lambda c: (c[0] - o['OFFSET_E'], o['OFFSET_N'] - c[1])
        x0, z0, x1, z1 = ZONES[zone]
        d = json.loads(_projected(CAMPUS).read_text())
        ring = [self.mc(c) for c in next(f for f in d['features'] if f['properties'].get('osm_way_id') ==
                                         '1170405958')['geometry']['coordinates'][0][0]]
        self.campus = {(x, z) for x in range(x0, x1 + 1) for z in range(z0, z1 + 1) if inside(x + .5, z + .5, ring)}
        idx = OSMIndex()
        self.fp = set(idx.cells())
        owned = built_cells(exclude=(self.name,))
        self.ocols = {(x, z) for x, _y, z in owned}
        self.scope = self.campus - self.fp - self.ocols
        near = self.fp | self.ocols
        self.near2 = {(x + a, z + b) for x, z in near for a in range(-2, 3) for b in range(-2, 3)}
        self.near1 = {(x + a, z + b) for x, z in near for a in (-1, 0, 1) for b in (-1, 0, 1)}

    # --- live ground -------------------------------------------------------------------
    def survey(self):
        """Live surface per column; drop water + banks, carpet masses, bridges, odd spikes."""
        self.top, skip = {}, set()
        for x, z in self.scope:
            y = 110
            while y > 30:
                b = self.w.block(x, y, z) or 'minecraft:air'
                if is_water(b):
                    skip.add((x, z))
                    break
                if not (b.endswith('air') or 'leaves' in b or '_log' in b or any(k in b for k in PLANTS)):
                    break
                y -= 1
            if (x, z) in skip:
                continue
            if 'waterlogged=true' in b:
                skip.add((x, z))
            self.top[(x, z)] = (y, b.split('[')[0][10:])
        water = set(skip)
        skip |= {(x + a, z + c) for x, z in water for a in (-1, 0, 1) for c in (-1, 0, 1)}
        mass = {q for q, (y, b) in self.top.items() if b.endswith('_carpet')}
        skip |= {(x + a, z + c) for x, z in mass for a in range(-2, 3) for c in range(-2, 3)}
        skip |= {q for q, (y, b) in self.top.items() if b in ('spruce_planks', 'oak_planks') or 'slab' in b
                 or 'stairs' in b or b.endswith(('_wall', '_fence', 'bars'))}
        for (x, z), (y, b) in list(self.top.items()):
            nb = [self.top[(x + a, z + c)][0] for a in range(-6, 7, 2) for c in range(-6, 7, 2)
                  if (x + a, z + c) in self.top]
            if y > statistics.median(nb) + 2:
                skip.add((x, z))
        self.skipped = Counter()
        for q in skip & set(self.top):
            self.skipped[self.top[q][1]] += 1
            del self.top[q]
        self.cells = set(self.top)

    # --- OSM ---------------------------------------------------------------------------
    def load(self):
        self.kind, self.pri = {}, {}
        self.road_line, self.lines_mark, self.bays = {}, set(), set()
        self.hedge, self.wall, self.fence, self.hoard, self.trees_osm = set(), set(), set(), set(), []
        aisles = []

        def put(cells, k, pri):
            for q in cells:
                if q in self.cells and pri >= self.pri.get(q, -1):
                    self.kind[q], self.pri[q] = k, pri

        mp = json.loads(Path(str(SRC).format('mp')).read_text())['features']
        ln = json.loads(Path(str(SRC).format('ln')).read_text())['features']
        pt = json.loads(Path(str(SRC).format('pt')).read_text())['features']
        polys = []
        for f in mp:
            g = f['geometry']
            if not g:
                continue
            P = [g['coordinates']] if g['type'] == 'Polygon' else g['coordinates']
            polys.append((tags(f['properties']), [[[self.mc(c) for c in r] for r in poly] for poly in P]))
        for t, P in polys:
            if t.get('landuse') in ('grass', 'meadow') or t.get('leisure') in ('garden', 'park'):
                put(poly_cells(P), 'grass', PRI['grass'])
            elif t.get('landuse') == 'flowerbed':
                put(poly_cells(P), 'flower', PRI['flower'])
            elif t.get('natural') in ('wood', 'scrub') or t.get('landuse') == 'forest':
                put(poly_cells(P), 'wood', PRI['wood'])
            elif t.get('highway') == 'pedestrian' or t.get('area:highway') == 'pedestrian':
                k = PATH_SURF.get(t.get('surface'), 'plaza')
                put(poly_cells(P), k, PRI['plaza'])
            elif t.get('landuse') == 'construction':
                cs = poly_cells(P)
                put(cs, 'site', PRI['site'])
                for rings in P:
                    self.hoard |= set(line_cells(rings[0], 0.5))
            elif t.get('amenity') == 'parking' and t.get('parking') not in ('underground', 'multi-storey'):
                cs = poly_cells(P)
                put(cs, 'park', PRI['park'])
                self.park_polys = getattr(self, 'park_polys', []) + [(P[0][0], cs)]
            elif t.get('amenity') == 'bicycle_parking':
                put(poly_cells(P), 'pave', PRI['plaza'])
            if t.get('barrier') == 'hedge':
                for rings in P:
                    self.hedge |= set(line_cells(rings[0], 0.6))
        for f in ln:
            t = tags(f['properties'])
            pts = [self.mc(c) for c in f['geometry']['coordinates']]
            hw = t.get('highway')
            if hw in HALF:
                half = SERVICE_HALF.get(t.get('service'), HALF[hw]) if hw == 'service' else HALF[hw]
                if t.get('width'):
                    try:
                        half = float(t['width'].split()[0]) / 2
                    except ValueError:
                        pass
                cs = line_cells(pts, half)
                k = 'road' if PATH_SURF.get(t.get('surface'), 'asph') == 'asph' else \
                    'proad' if PATH_SURF[t['surface']] in ('pave', 'brick') else PATH_SURF[t['surface']]
                if hw == 'service' and t.get('service') == 'parking_aisle':
                    aisles.append(cs)
                put(cs, k, PRI['road'])
                if half >= 3 and k == 'road':
                    self.lines_mark |= {q for q, (d, a) in cs.items() if d <= 0.5 and int(a) % 6 < 3}
            elif hw in PATH_HALF and PATH_HALF[hw] > 0 and t.get('surface') != 'wood' and t.get('bridge') != 'yes' \
                    and t.get('tunnel') != 'yes' and t.get('layer', '0') in ('0', ''):
                default = 'asph' if hw == 'cycleway' else 'pave'
                put(line_cells(pts, PATH_HALF[hw]), PATH_SURF.get(t.get('surface'), default), PRI['path'])
            b = t.get('barrier')
            if b == 'hedge':
                self.hedge |= set(line_cells(pts, 0.6))
            elif b in ('wall', 'retaining_wall'):
                self.wall |= set(line_cells(pts, 0.5))
            elif b in ('fence', 'railings', 'guard_rail'):
                self.fence |= set(line_cells(pts, 0.5))
        for f in pt:
            t = tags(f['properties'])
            if t.get('natural') == 'tree':
                self.trees_osm.append(tuple(int(math.floor(v)) for v in self.mc(f['geometry']['coordinates'])))
        aisle = set().union(*aisles) if aisles else set()
        # bay lines: within 5.5 of the car park edge, every 3rd block along the nearest edge
        for ring, cs in getattr(self, 'park_polys', []):
            for q in cs:
                if q not in self.cells or self.kind.get(q) != 'park' or q in aisle:
                    continue
                best = min(seg_dist(q[0] + .5, q[1] + .5, a, b) + (i,) for i, (a, b) in enumerate(zip(ring, ring[1:])))
                if 0.5 < best[0] <= 5.5 and int(best[1]) % 3 == 0:
                    self.bays.add(q)

    # --- aerial fallback ---------------------------------------------------------------
    def fallback(self):
        rest = [q for q in self.cells if q not in self.kind]
        self.rgb = aerial_rgb(self.cells)
        guess = {}
        parks = [q for q, k in self.kind.items() if k == 'park']
        park_near = {(x + a, z + b) for x, z in parks for a in range(-6, 7) for b in range(-6, 7)}
        for q in rest:
            r, g, b = self.rgb.get(q, (128, 128, 128))
            was = self.top[q][1]
            if g > r + 8 and g > b + 4:
                k = 'grass'
            elif r > g + 18 and r > b + 25:
                k = 'brick'
            elif was in ('grass_block', 'dirt', 'coarse_dirt') and r + g + b < 300:
                k = 'grass'                     # shadow / canopy over a Geocraft lawn
            elif q in park_near or any(a <= q[0] <= c and b <= q[1] <= d for a, b, c, d in HAND_PARK.values()):
                k = 'park'                      # unmapped part of a car park
            else:
                k = 'pave'                      # aerial grey can't split asphalt from paving: courts
            guess[q] = k
        for _ in range(2):                      # majority filter: no speckle
            new = {}
            for (x, z), k in guess.items():
                c = Counter(guess.get((x + a, z + b)) or self.kind.get((x + a, z + b))
                            for a in (-1, 0, 1) for b in (-1, 0, 1))
                c.pop(None, None)
                new[(x, z)] = c.most_common(1)[0][0] if c.most_common(1)[0][1] >= 5 else k
            guess = new
        self.kind.update(guess)
        self.from_aerial = len(guess)
        for q, k in self.kind.items():
            if k == 'plaza':
                r, g, b = self.rgb.get(q, (128, 128, 128))
                self.kind[q] = 'brick' if r > g + 18 and r > b + 25 else 'pave'

    # --- surface -----------------------------------------------------------------------
    def surface(self):
        rnd = random.Random(38)
        y0 = {q: self.top[q][0] for q in self.cells}
        self.gy = {}
        for (x, z), y in y0.items():
            k = self.kind[(x, z)]
            if k in HARD and (x, z) not in self.near2:
                nb = sorted(y0[(x + a, z + b)] for a in (-1, 0, 1) for b in (-1, 0, 1) if (x + a, z + b) in y0
                            and self.kind.get((x + a, z + b)) in HARD)
                med = nb[len(nb) // 2]
                y = y + max(-1, min(1, med - y))
            self.gy[(x, z)] = y
        for (x, z), y in self.gy.items():
            k = self.kind[(x, z)]
            mat = MAT[k]
            if k == 'park' and (x, z) in self.bays:
                mat = MAT['bay']
            if k == 'road' and (x, z) in self.lines_mark:
                mat = MAT['mark']
            if k in ('pave', 'asph', 'brick') and any(self.kind.get((x + a, z + b)) in ('road', 'proad') for a, b in N4):
                mat = MAT['kerb']
            if k == 'site' and rnd.random() < 0.35:
                mat = rnd.choice(('gravel', 'dirt', 'stone'))
            if k == 'wood' and rnd.random() < 0.3:
                mat = rnd.choice(('podzol', 'coarse_dirt', 'grass_block'))
            old = y0[(x, z)]
            for yy in range(min(old, y) - 1, y):        # raise: solid under the new top
                self.p.set(x, yy, z, 'dirt' if k in SOFT else 'stone')
            for yy in range(y + 1, old + 1):           # lower: clear the old top
                self.p.set(x, yy, z, 'air')
            if self.top[(x, z)][1] != mat or y != old:
                self.p.set(x, y, z, mat)
            above = self.w.block(x, y + 1, z) or 'minecraft:air'
            if k in HARD and any(s in above for s in PLANTS):
                self.p.set(x, y + 1, z, 'air')
            if k == 'flower' and above.endswith('air') and rnd.random() < 0.5:
                self.p.set(x, y + 1, z, rnd.choice(FLOWERS))
            if k == 'wood' and above.endswith('air') and rnd.random() < 0.12:
                self.p.set(x, y + 1, z, 'fern')

    def barriers(self):
        """Hedges / walls / fences on soft ground only; never across a path or beside a build."""
        n = Counter()
        for q in self.hoard:                    # site hoarding: 2-high timber, kept off roads/paths
            if q in self.gy and self.kind[q] in ('site',) + SOFT and q not in self.near1:
                for i in (1, 2):
                    self.p.set(q[0], self.gy[q] + i, q[1], HOARDING)
                n[HOARDING] += 1
        for cells, mat, h in ((self.hedge, 'oak_leaves[persistent=true]', 2), (self.wall, 'brick_wall', 1),
                              (self.fence, 'iron_bars', 1)):
            for q in cells:
                if q not in self.gy or self.kind[q] not in SOFT or q in self.near1:
                    continue
                y = self.gy[q]
                if not (self.w.block(q[0], y + 1, q[1]) or 'minecraft:air').endswith('air') and \
                        (q[0], y + 1, q[1]) not in self.p.cells:
                    continue
                for i in range(1, h + 1):
                    self.p.set(q[0], y + i, q[1], mat)
                n[mat] += 1
        self.n_barrier = n

    def trees(self):
        """OSM tree points + dark-green aerial canopy on lawns/woods, where no Geocraft tree stands."""
        rnd = random.Random(1170405958)
        logs = set()
        for x, z in self.cells:
            y = self.gy[(x, z)]
            if any('_log' in (self.w.block(x, y + i, z) or '') for i in range(1, 8)):
                logs.add((x, z))
        cand = [(q, 4) for q in self.trees_osm]
        canopy = sorted(q for q in self.cells if self.kind[q] in SOFT and sum(self.rgb.get(q, (255,) * 3)) < 200
                        and self.rgb[q][1] >= self.rgb[q][0] and self.rgb[q][1] >= self.rgb[q][2])
        rnd.shuffle(canopy)
        cand += [(q, 7) for q in canopy]
        placed = []
        for (x, z), gap in cand:
            if (x, z) not in self.gy or self.kind[(x, z)] not in SOFT or (x, z) in self.near2:
                continue
            if any(abs(x - a) < gap and abs(z - b) < gap for a, b in placed) or \
                    any((x + a, z + b) in logs for a in range(-gap + 1, gap) for b in range(-gap + 1, gap)):
                continue
            y = self.gy[(x, z)]
            h = rnd.choice((5, 6, 6, 7))
            if any(not (self.w.block(x, y + i, z) or 'minecraft:air').endswith('air') for i in range(1, h + 3)):
                continue
            placed.append((x, z))
            for i in range(1, h):
                self.p.set(x, y + i, z, 'oak_log')
            for a in range(-2, 3):
                for b in range(-2, 3):
                    for dy in range(h - 2, h + 2):
                        if abs(a) + abs(b) + max(0, dy - h) * 2 > 3 or (a == b == 0 and dy < h):
                            continue
                        q = (x + a, z + b)
                        if q in self.ocols or q in self.fp:
                            continue
                        pos = (x + a, y + dy, z + b)
                        if pos in self.p.cells or (self.w.block(*pos) or 'minecraft:air').endswith('air'):
                            if pos not in self.p.cells or self.p.cells[pos].endswith('air'):
                                self.p.set(*pos, 'oak_leaves[persistent=true]')
        self.placed = placed

    def build(self):
        self.survey()
        self.load()
        self.fallback()
        self.surface()
        self.barriers()
        self.trees()
        return self.p


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--zone', required=True, choices=sorted(ZONES))
    ap.add_argument('--apply', action='store_true')
    a = ap.parse_args()
    g = Grounds(a.zone)
    plan = g.build()
    print(g.name, 'campus', len(g.campus), 'scope', len(g.scope), 'surfaced', len(g.cells),
          'skipped', dict(g.skipped.most_common(6)))
    print('kinds', dict(Counter(g.kind[q] for q in g.cells).most_common()), 'aerial-only', g.from_aerial)
    print('bays', len(g.bays & g.cells), 'marks', len(g.lines_mark & g.cells), 'barriers', dict(g.n_barrier),
          'trees', len(g.placed))
    out = ROOT / f'verification/site/{g.name}-preview.png'
    preview(plan, out, scale=2)
    plan.outside_footprint_ok = None
    apply(plan, dry=not a.apply)
