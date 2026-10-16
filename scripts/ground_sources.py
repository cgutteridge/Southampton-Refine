#!/usr/bin/env python3
"""Evidence for the ground layer: what is on the ground in a 128² cell.

Two sources, both read-only, neither tied to any one place:

  OSM    every ``*-mp / *-ln / *-pt`` extract in verification/site/osm27700 (EPSG:27700),
         projected to Minecraft columns. Roads, paths and areas become surface kinds.
  AERIAL the z19 mosaic, sampled per column. Colour says lawn / brick paving / light
         paving / shade-or-canopy. It only fills columns OSM does not describe.

Nothing here reads the Minecraft world, an earlier ground pass, a zone, or a campus polygon.

Kinds (the vocabulary the ground layer works in):
  grass  tarmac  paving  brick  gravel  dirt  water
"""
from __future__ import annotations

import json
import math
import subprocess
from collections import Counter
from pathlib import Path

import numpy as np

from ref_manifest import load_manifest, mc_tile_id

ROOT = Path(__file__).resolve().parent.parent
OSM_DIR = ROOT / 'verification' / 'site' / 'osm27700'
MOSAIC = ROOT / 'reference/aerial/highfield-z19/mosaic-z19-18x17-260101-175662-eastext6.png'
NO_DATA_LUM = 0.01                   # window mean below this is a blank mosaic pixel (pure black), not ground
MOSAIC_TILE0 = (260101, 175662)      # z19 tile x,y of the mosaic's top-left corner
ZOOM, TILE = 19, 256

# OSM surface=* → ground kind. 'paving' is split brick / light by the aerial.
SURFACE_KIND = {
    'asphalt': 'tarmac', 'paved': 'paving', 'paving_stones': 'paving', 'concrete': 'paving',
    'concrete:plates': 'paving', 'sett': 'brick', 'bricks': 'brick', 'cobblestone': 'brick',
    'gravel': 'gravel', 'fine_gravel': 'gravel', 'compacted': 'gravel', 'unpaved': 'gravel',
    'dirt': 'dirt', 'ground': 'dirt', 'earth': 'dirt', 'grass': 'grass', 'pebblestone': 'gravel',
}
# Priority: a higher number wins where two features cover one column.
PRI = {'wood': 20, 'grass': 30, 'pedestrian': 40, 'parking': 50, 'path': 60, 'service': 70, 'road': 90}
ROAD_CLASSES = ('motorway', 'trunk', 'primary', 'secondary', 'tertiary', 'unclassified', 'residential')
LANE_WIDTH = 3.0                      # metres ≈ blocks, one traffic lane
DEFAULT_LANES = 2
SERVICE_WIDTH = {'driveway': 3.0, 'parking_aisle': 5.0, 'alley': 3.5}
PATH_WIDTH = {'footway': 2.0, 'cycleway': 2.5, 'path': 1.6, 'pedestrian': 3.0, 'bridleway': 2.0, 'track': 3.0}
MARGIN = 4                            # columns of evidence kept outside the cell, for filters


def tags_of(props: dict) -> dict:
    """Merge ogr's ``other_tags`` hstore string into the plain property dict."""
    t = dict(props)
    for kv in (props.get('other_tags') or '').split('","'):
        if '=>' in kv:
            k, v = kv.split('=>', 1)
            t.setdefault(k.strip('"'), v.strip('"'))
    return t


def _coords(c):
    """Flatten any GeoJSON coordinate nesting to (E, N) pairs."""
    if isinstance(c[0], (int, float)):
        yield c[0], c[1]
    else:
        for s in c:
            yield from _coords(s)


def seg_dist(px: float, pz: float, a, b) -> tuple[float, float]:
    """Distance from a point to segment a-b, and the distance along it."""
    (ax, az), (bx, bz) = a, b
    l2 = (bx - ax) ** 2 + (bz - az) ** 2 or 1e-9
    t = max(0.0, min(1.0, ((px - ax) * (bx - ax) + (pz - az) * (bz - az)) / l2))
    return math.hypot(px - ax - t * (bx - ax), pz - az - t * (bz - az)), t * math.sqrt(l2)


def line_cells(pts, half: float) -> dict:
    """{(x, z): (distance, along)} for columns whose centre is within ``half`` of a polyline."""
    out, acc = {}, 0.0
    for a, b in zip(pts, pts[1:]):
        for x in range(math.floor(min(a[0], b[0]) - half) - 1, math.ceil(max(a[0], b[0]) + half) + 1):
            for z in range(math.floor(min(a[1], b[1]) - half) - 1, math.ceil(max(a[1], b[1]) + half) + 1):
                d, t = seg_dist(x + .5, z + .5, a, b)
                if d <= half and ((x, z) not in out or d < out[(x, z)][0]):
                    out[(x, z)] = (d, acc + t)
        acc += math.dist(a, b)
    return out


def inside(px: float, pz: float, ring) -> bool:
    """Even-odd point-in-polygon."""
    c = False
    for (ax, az), (bx, bz) in zip(ring, ring[1:] + ring[:1]):
        if (az > pz) != (bz > pz) and px < ax + (pz - az) * (bx - ax) / (bz - az):
            c = not c
    return c


def _inside_grid(px, pz, ring):
    """``inside`` over numpy arrays of centres: same even-odd test, same float expression, so same answer."""
    c = np.zeros(px.shape, dtype=bool)
    with np.errstate(divide='ignore', invalid='ignore'):
        for (ax, az), (bx, bz) in zip(ring, ring[1:] + ring[:1]):
            if az == bz:
                continue                                   # horizontal edge never crosses: (az > pz) == (bz > pz)
            c ^= ((az > pz) != (bz > pz)) & (px < ax + (pz - az) * (bx - ax) / (bz - az))
    return c


def poly_cells(rings_list) -> set:
    """Columns inside polygons given as [[outer, hole, ...], ...] (MC coordinates)."""
    out = set()
    for rings in rings_list:
        o = rings[0]
        x0, x1 = math.floor(min(p[0] for p in o)), math.ceil(max(p[0] for p in o))
        z0, z1 = math.floor(min(p[1] for p in o)), math.ceil(max(p[1] for p in o))
        xs, zs = np.meshgrid(np.arange(x0, x1 + 1), np.arange(z0, z1 + 1), indexing='ij')
        hit = _inside_grid(xs + .5, zs + .5, o)
        for h in rings[1:]:
            hit &= ~_inside_grid(xs + .5, zs + .5, h)
        ix, iz = np.nonzero(hit)
        out.update(zip((ix + x0).tolist(), (iz + z0).tolist()))
    return out


def cell_box(cell: tuple[int, int], margin: int = 0) -> tuple[int, int, int, int]:
    """Inclusive x0, z0, x1, z1 of a 128² cell, grown by ``margin``."""
    x0, z0 = cell[0] * 128, cell[1] * 128
    return x0 - margin, z0 - margin, x0 + 127 + margin, z0 + 127 + margin


# --- OSM ---------------------------------------------------------------------------------
def load_osm(cell: tuple[int, int], margin: int = MARGIN + 8) -> list[tuple[dict, str, list]]:
    """OSM features touching the cell: [(tags, 'poly'|'line'|'point', geometry in MC)].

    poly geometry is [[outer, hole, ...], ...]; line is [(x, z), ...]; point is (x, z).
    Duplicates across extracts (same osm id and tags) are dropped.
    """
    from osgb import load_offsets
    o = load_offsets()
    mc = lambda c: (c[0] - o['OFFSET_E'], o['OFFSET_N'] - c[1])
    x0, z0, x1, z1 = cell_box(cell, margin)
    seen, out = set(), []
    for path in sorted(OSM_DIR.glob('*-mp.geojson')) + sorted(OSM_DIR.glob('*-ln.geojson')) + \
            sorted(OSM_DIR.glob('*-pt.geojson')):
        for f in json.loads(path.read_text())['features']:
            g = f.get('geometry')
            if not g:
                continue
            pts = [mc(c) for c in _coords(g['coordinates'])]
            if not any(x0 <= x <= x1 and z0 <= z <= z1 for x, z in pts):
                continue
            t = tags_of(f['properties'])
            key = (t.get('osm_id') or t.get('osm_way_id'), json.dumps(g['coordinates'])[:80])
            if key in seen:
                continue
            seen.add(key)
            if g['type'] in ('Polygon', 'MultiPolygon'):
                polys = [g['coordinates']] if g['type'] == 'Polygon' else g['coordinates']
                out.append((t, 'poly', [[[mc(c[:2]) for c in r] for r in poly] for poly in polys]))
            elif g['type'] in ('LineString', 'MultiLineString'):
                lines = [g['coordinates']] if g['type'] == 'LineString' else g['coordinates']
                for ln in lines:
                    out.append((t, 'line', [mc(c[:2]) for c in ln]))
            elif g['type'] == 'Point':
                out.append((t, 'point', mc(g['coordinates'][:2])))
    for cx, cz, pts, tags in SUPPLEMENT_ROADS:
        if (cx, cz) == tuple(cell):
            out.append((dict(tags), 'line', list(pts)))
    return out


# Real carriageways missing from the OSM clips (aerial + the existing road surface show them).
# (cell tx, tz, centreline in MC, tags). Added so the ground pass lays tarmac, not paving.
SUPPLEMENT_ROADS = [
    (50, -42, [(6396, -5294), (6460, -5266), (6500, -5248), (6531, -5235)],
     {'highway': 'residential', 'surface': 'asphalt', 'name': 'road S of Welbeck Ave houses (unmapped in OSM clip)',
      'width': '9'}),
    (49, -42, [(6350, -5322), (6351, -5314), (6355, -5297), (6360, -5282), (6365, -5263), (6370, -5246)],
     {'highway': 'residential', 'surface': 'asphalt', 'name': 'University Rd south of the junction (unmapped in OSM clip)',
      'width': '9'}),
    (49, -42, [(6352, -5322), (6362, -5316), (6372, -5311), (6385, -5304), (6399, -5298)],
     {'highway': 'residential', 'surface': 'asphalt', 'name': 'road E from the junction toward Welbeck Ave (unmapped in OSM clip)',
      'width': '9'}),
]


def road_width(t: dict) -> float:
    """Carriageway width in blocks from tags: width=*, else lanes (+ painted cycle lanes)."""
    if t.get('width'):
        try:
            return float(t['width'].split()[0])
        except ValueError:
            pass
    hw = t.get('highway')
    if hw == 'service':
        return SERVICE_WIDTH.get(t.get('service'), 4.0)
    if hw == 'track':
        return 3.0
    try:
        lanes = int(t.get('lanes', DEFAULT_LANES))
    except ValueError:
        lanes = DEFAULT_LANES
    w = LANE_WIDTH * lanes
    if t.get('cycleway:both') == 'lane' or t.get('cycleway') == 'lane':
        try:
            w += 2 * float(t.get('cycleway:width', 1.5))
        except ValueError:
            w += 3.0
    return w


class OSMGround:
    """OSM rasterised to one kind + priority per column, plus road/barrier extras."""

    def __init__(self, cell: tuple[int, int]):
        self.cell = cell
        self.kind: dict = {}          # (x, z) -> kind from OSM
        self.pri: dict = {}
        self.feat: dict = {}          # (x, z) -> id of the mapped line (path/road) that put the kind there
        self._fid = 0
        self.road: set = set()        # public carriageway columns (kerb candidates)
        self.marks: set = set()       # centre-line dash columns
        self.water: set = set()
        self.bridge: set = set()      # columns under a mapped bridge/tunnel: not ours to surface
        self.hedge: set = set()
        self.wall: set = set()
        self.fence: set = set()
        self.soft: set = set()        # mapped parking polygon: the aerial may show it is really lawn
        self.trees: list = []
        self._load(load_osm(cell))

    def _put(self, cells, kind: str, pri: int, feat: int | None = None) -> None:
        x0, z0, x1, z1 = cell_box(self.cell, MARGIN)
        for q in cells:
            if x0 <= q[0] <= x1 and z0 <= q[1] <= z1 and pri >= self.pri.get(q, -1):
                self.kind[q], self.pri[q] = kind, pri
                if feat is None:
                    self.feat.pop(q, None)
                else:
                    self.feat[q] = feat

    def _load(self, feats) -> None:
        for t, geom, g in feats:
            if geom == 'poly':
                self._poly(t, g)
            elif geom == 'line':
                self._line(t, g)
            elif t.get('natural') == 'tree':
                self.trees.append((int(math.floor(g[0])), int(math.floor(g[1]))))

    def _poly(self, t: dict, polys) -> None:
        if t.get('natural') == 'water':
            self.water |= poly_cells(polys)
        elif t.get('highway') == 'pedestrian' or t.get('area:highway'):
            self._put(poly_cells(polys), SURFACE_KIND.get(t.get('surface'), 'paving'), PRI['pedestrian'])
        elif t.get('amenity') == 'parking' and t.get('parking') not in ('underground', 'multi-storey'):
            cs = poly_cells(polys)
            self._put(cs, 'tarmac', PRI['parking'])
            self.soft |= {q for q in cs if self.pri.get(q) == PRI['parking']}
        elif t.get('amenity') == 'bicycle_parking':
            self._put(poly_cells(polys), 'paving', PRI['pedestrian'])
        elif t.get('landuse') in ('grass', 'meadow', 'flowerbed', 'recreation_ground') or \
                t.get('leisure') in ('garden', 'park'):
            self._put(poly_cells(polys), 'grass', PRI['grass'])
        elif t.get('natural') in ('wood', 'scrub') or t.get('landuse') == 'forest':
            self._put(poly_cells(polys), 'grass', PRI['wood'])
        if t.get('barrier') == 'hedge':
            for rings in polys:
                self.hedge |= set(line_cells(rings[0], 0.6))

    def _line(self, t: dict, pts) -> None:
        hw, b = t.get('highway'), t.get('barrier')
        if t.get('waterway') in ('stream', 'river', 'canal', 'ditch'):
            if t.get('tunnel') == 'yes' or t.get('level', '0').startswith('-'):
                return
            self.water |= set(line_cells(pts, 0.8))
            return
        if hw and (t.get('bridge') in ('yes', 'viaduct') or t.get('tunnel') == 'yes' or
                   t.get('layer', '0') not in ('0', '')):
            self.bridge |= set(line_cells(pts, max(1.5, road_width(t) / 2 if hw in ROAD_CLASSES else 1.5)))
            return
        if hw in ROAD_CLASSES or hw == 'service' or hw == 'track':
            half = road_width(t) / 2
            cells = line_cells(pts, half)
            kind = SURFACE_KIND.get(t.get('surface'), 'tarmac')
            pri = PRI['service'] if hw in ('service', 'track') else PRI['road']
            self._put(cells, kind, pri)
            if hw in ROAD_CLASSES and kind == 'tarmac':
                self.road |= set(cells)
                if half >= 3 and t.get('oneway') != 'yes':
                    self.marks |= {q for q, (d, a) in cells.items() if d <= 0.5 and int(a) % 6 < 3}
        elif hw in PATH_WIDTH:
            self._fid += 1
            self._put(line_cells(pts, PATH_WIDTH[hw] / 2),
                      SURFACE_KIND.get(t.get('surface'), 'tarmac' if hw == 'cycleway' else 'paving'), PRI['path'],
                      self._fid)
        elif hw == 'steps':
            self.bridge |= set(line_cells(pts, 1.2))          # stairs are structure, not surface
        elif b == 'hedge':
            self.hedge |= set(line_cells(pts, 0.6))
        elif b in ('wall', 'retaining_wall'):
            self.wall |= set(line_cells(pts, 0.5))
        elif b in ('fence', 'railings', 'guard_rail'):
            self.fence |= set(line_cells(pts, 0.5))


# --- aerial ------------------------------------------------------------------------------
def mosaic_px(pts: list[tuple[int, int]]) -> dict:
    """Mosaic pixel (X, Y) of each MC column centre, one gdaltransform call."""
    from osgb import to_osgb
    inp = ''.join('%f %f\n' % to_osgb(x + 0.5, z + 0.5) for x, z in pts)
    lines = [ln for ln in subprocess.run(
        ['gdaltransform', '-s_srs', 'EPSG:27700', '-t_srs', 'EPSG:4326'],
        input=inp.encode(), capture_output=True, check=True, timeout=300).stdout.decode().split('\n') if ln.strip()]
    n = 2 ** ZOOM * TILE
    res = {}
    for p, ln in zip(pts, lines):
        lon, lat = map(float, ln.split()[:2])
        res[p] = ((lon + 180) / 360 * n - MOSAIC_TILE0[0] * TILE,
                  (1 - math.log(math.tan(math.radians(lat)) + 1 / math.cos(math.radians(lat))) / math.pi) / 2 * n
                  - MOSAIC_TILE0[1] * TILE)
    return res


class RegRGB(tuple):
    """A colour sampled from a registered user aerial (Google 3D render), not the z19 mosaic.

    Same 0..1 RGB triple, but ``aerial_class`` reads it with the registered-source thresholds.
    """
    __slots__ = ()


AERIAL_USER_GLOB = 'reference/aerial/**/*.registration.json'
REG_HALF_BLOCKS = 0.5                # sample window half-width in blocks (median, so render speckle drops out)
REG_EDGE_BLOCKS = 3.0                # skip columns this close to the image edge (Google watermark, attribution, UI chrome)


def registered_aerials() -> list[dict]:
    """Every registered user aerial found by globbing reference/aerial/**/*.registration.json.

    Drop a new screenshot and its registration beside the others and it is used with no code change.
    Each: ``{'name', 'A' (2x3), 'im' (HxWx3 float 0..1), 'ppb' (px per block)}``.
    """
    from PIL import Image
    out = []
    for rp in sorted(ROOT.glob(AERIAL_USER_GLOB)):
        try:
            reg = json.loads(rp.read_text())
            A = np.array(reg['A'], float)
            im = np.asarray(Image.open(ROOT / 'reference' / reg['image']).convert('RGB')).astype(float) / 255
        except (OSError, KeyError, ValueError):
            continue
        out.append({'name': rp.name, 'A': A, 'im': im, 'ppb': float(np.hypot(A[0, 0], A[1, 0]))})
    return out


def registered_rgb(pts: list[tuple[int, int]], sources: list[dict] | None = None) -> dict:
    """RegRGB per column covered by a registered user aerial (median of a ~1-block window).

    Columns whose window leaves the image, or is (near-)black no-data, are skipped so the mosaic
    can fill them. Earlier sources in ``sources`` (sorted by name) win over later ones.
    """
    out: dict = {}
    for src in (registered_aerials() if sources is None else sources):
        im, A, ppb = src['im'], src['A'], src['ppb']
        h = max(2, int(round(REG_HALF_BLOCKS * ppb)))
        edge = REG_EDGE_BLOCKS * ppb
        H, W = im.shape[:2]
        for p in pts:
            if p in out:
                continue
            u, v = A @ [p[0] + 0.5, p[1] + 0.5, 1]
            if not (edge + h <= u < W - edge - h and edge + h <= v < H - edge - h):
                continue
            u, v = int(u), int(v)
            win = np.median(im[v - h:v + h + 1, u - h:u + h + 1].reshape(-1, 3), axis=0)
            if win.mean() < NO_DATA_LUM * 5:             # blank / black padding
                continue
            out[p] = RegRGB(float(c) for c in win)
    return out


def aerial_rgb(cell: tuple[int, int], margin: int = MARGIN) -> dict:
    """Colour (0..1) per column: registered user aerials where one covers it, else the z19 mosaic.

    The mosaic gives a 5x5 pixel mean; registered columns are RegRGB (see ``aerial_class``).
    """
    from PIL import Image
    im = np.asarray(Image.open(MOSAIC).convert('RGB')).astype(float) / 255
    x0, z0, x1, z1 = cell_box(cell, margin)
    pts = [(x, z) for x in range(x0, x1 + 1) for z in range(z0, z1 + 1)]
    out = {}
    for p, (X, Y) in mosaic_px(pts).items():
        X, Y = int(X), int(Y)
        if 2 <= X < im.shape[1] - 2 and 2 <= Y < im.shape[0] - 2:
            win = tuple(im[Y - 2:Y + 3, X - 2:X + 3].reshape(-1, 3).mean(0))
            if sum(win) / 3 < NO_DATA_LUM:       # blank tile / outside coverage, not dark paving (I-042, I-057)
                continue
            out[p] = win
    out.update(registered_rgb(pts))                      # sharper, truer colour wins where it exists
    return out


def hsv(rgb) -> tuple[float, float, float]:
    """(hue°, saturation, mean luminance) of a 0..1 RGB triple."""
    r, g, b = rgb
    mx, mn = max(rgb), min(rgb)
    d = mx - mn
    h = 0.0
    if d > 0:
        h = (((g - b) / d) % 6 if mx == r else (b - r) / d + 2 if mx == g else (r - g) / d + 4) * 60
    return h, (d / mx if mx else 0.0), (r + g + b) / 3


def _registered_class(h: float, s: float, lum: float) -> str:
    """Class of a registered user aerial colour (Google 3D render: true colour, neutral paving, blue roofs).

    Calibrated on cell 47,-45 against the strip beside Building 2 and the promenade: lawn there is
    green (hue 80-165, s 0.24-0.36, lum 0.25-0.55, dark under shade) where the sun-bleached mosaic
    shows khaki, paving is neutral or cream (hue 15-60, s <= 0.12) and block paving is pink (hue <= 12 or >= 330; salmon s 0.25-0.30, pale s 0.09-0.14).
    Blue-violet colour is a leaning roof or its shadow (the ground is unseen), so it counts as shade.
    """
    if s >= 0.15 and 190 <= h <= 300:
        return 'shade'
    if s >= 0.17 and 31 <= h <= 170:
        return 'lawn'
    if s >= 0.20 and (h < 31 or h >= 330):
        return 'brick'
    if s >= 0.085 and (h >= 330 or h <= 12):              # pale pink block paving; cream/tan (hue 15-60) stays paving
        return 'brick'
    return 'light' if lum >= 0.45 else 'dark'


def aerial_class(rgb) -> str:
    """Colour → shade | lawn | brick | light | dark. A RegRGB (registered user aerial) uses its own thresholds.

    The aerial here is low-saturation and sun-bleached, so lawn is khaki, not green:
    hue (olive-yellow vs orange-red) separates lawn from brick paving, saturation separates
    both from neutral paving, and dark + saturated is shade or canopy (ground unseen).
    """
    h, s, lum = hsv(rgb)
    if isinstance(rgb, RegRGB):
        return _registered_class(h, s, lum)
    if lum < 0.50 and s >= 0.22:
        return 'shade'
    if s >= 0.13 and 31 <= h <= 110:
        return 'lawn'
    if s >= 0.14 and h < 31:
        return 'brick'
    return 'light' if lum >= 0.45 else 'dark'


def majority(grid: dict, free: set, passes: int = 2, need: int = 5) -> dict:
    """3×3 majority filter over ``free`` columns so single-pixel speckle does not become blocks."""
    cur = dict(grid)
    for _ in range(passes):
        new = {}
        for q in free:
            c = Counter(cur.get((q[0] + a, q[1] + b)) for a in (-1, 0, 1) for b in (-1, 0, 1))
            c.pop(None, None)
            k, n = c.most_common(1)[0] if c else (cur.get(q), 0)
            new[q] = k if n >= need else cur.get(q)
        cur.update(new)
    return cur


# --- reference manifest ---------------------------------------------------------------------
def mc_tile_for_cell(tx: int, tz: int, size: int = 128) -> str:
    """Sparse manifest tile id for a coverage cell index.

    @param tx: cell X index (same as coverage tx)
    @param tz: cell Z index
    @param size: tile size in blocks
    @returns: e.g. ``128:48:-44``
    """
    # Cell tx,tz maps to world tile index (origin at cell corner)
    x0 = tx * size
    z0 = tz * size
    return mc_tile_id(x0 + size // 2, z0 + size // 2, size)


def references_for_cell(
    tx: int,
    tz: int,
    *,
    useful_only: bool = True,
) -> list[dict]:
    """Manifest rows whose ``mc_tiles`` overlap this coverage cell.

    @param tx: cell X
    @param tz: cell Z
    @param useful_only: omit ``useful=no`` rows
    @returns: matching manifest rows (may be empty)
    """
    tile = mc_tile_for_cell(tx, tz)
    rows = load_manifest()
    out: list[dict] = []
    for r in rows:
        if useful_only and r.get('useful') == 'no':
            continue
        if tile not in (r.get('mc_tiles') or []):
            continue
        out.append(r)
    return out
