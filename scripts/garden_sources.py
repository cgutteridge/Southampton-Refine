#!/usr/bin/env python3
"""Garden boundary evidence for the decor layer: per-parcel fences, walls and hedges.

OSM maps few garden boundaries, so the decor layer would leave every house garden bare. This
module derives them, cheapest evidence first, and tags each segment with its source:

  1. PLOTS     each OSM house footprint grows to a first-guess plot (osm_footprints.grow_plots,
               approximate Voronoi, stops at street surface and neighbours).
  2. SEGMENTS  plot edge columns are classed by what lies beyond them:
                 front  street surface
                 side_front / side_back  neighbour plot, edge runs front-to-back, before / behind the house line
                 rear   neighbour plot, edge runs across the plot   (open edge: nothing, no evidence)
  3. CONVENTION  site/gardens/<street>.json says what each role is made of on that street
               (one Street View look per street run; per-house overrides by house number).
  4. AERIAL    a segment whose aerial colour is a continuous dark-green strip is a hedge, whatever
               the convention says (hedges are the one boundary the z19 aerial can see).

No convention for a street = no fence/wall (accuracy over invention); only aerial hedges show.
Reads OSM, the aerial and the live ground surface; never an earlier fence build.

  python3 scripts/garden_sources.py --cell 47,-43 [--bbox x0,z0,x1,z1]     # report + overlay PNG
"""
from __future__ import annotations

import argparse
import json
import math
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

from script_env import ROOT  # noqa: E402

GARDENS = ROOT / 'site' / 'gardens'
HEDGE_BLOCK = 'oak_leaves[persistent=true]'
DEFAULT_BLOCK = {'hedge': HEDGE_BLOCK, 'brick_wall': 'brick_wall', 'fence': 'spruce_fence',
                 'iron_bars': 'iron_bars'}
DEFAULT_HEIGHT = {'hedge': 2, 'brick_wall': 1, 'fence': 2, 'iron_bars': 1}
HEDGE_SHARE = 0.6        # share of a segment's columns that must read dark green to call it a hedge
PAVEMENT = 3.0           # blocks of footway between kerb and front boundary
SIDE_DEPTH = 40          # side boundaries only run this far behind the front line unless told


def slug(street: str) -> str:
    return re.sub(r'[^a-z0-9]+', '_', street.lower()).strip('_')


def load_convention(street: str) -> dict | None:
    p = GARDENS / f'{slug(street)}.json'
    return json.loads(p.read_text()) if p.exists() else None


def role_spec(conv: dict | None, number: str, role: str) -> dict | None:
    """Barrier spec for one role on one house: override, else street convention, else None."""
    if not conv:
        return None
    over = (conv.get('overrides') or {}).get(str(number), {})
    spec = over[role] if role in over else conv.get(role)
    if not spec or spec.get('type') in (None, 'none'):
        return None
    t = spec['type']
    return {'type': t, 'block': spec.get('block') or DEFAULT_BLOCK[t],
            'height': int(spec.get('height') or DEFAULT_HEIGHT[t]), 'depth': spec.get('depth')}


def plots_for(box: tuple[int, int, int, int], margin: int = 60):
    """Plots touching ``box``: ({cell: plot id}, {plot id: info}, set of street columns)."""
    from ground_sources import ROAD_CLASSES, line_cells, road_width
    from osm_footprints import OSMIndex, _addr, grow_plots

    x0, z0, x1, z1 = box
    idx = OSMIndex()
    fp = idx.cells()
    seeds = {q: i for q, i in fp.items() if x0 - margin <= q[0] <= x1 + margin and z0 - margin <= q[1] <= z1 + margin}
    # street = carriageway plus a pavement either side (the front boundary sits at its back edge)
    street: dict = {}
    for (name, hw, pts), props in zip(idx.streets, idx.street_props):
        if hw in ROAD_CLASSES and any(x0 - margin <= x <= x1 + margin and z0 - margin <= z <= z1 + margin
                                      for x, z in pts):
            for q in line_cells(pts, road_width(props) / 2 + PAVEMENT):
                street[q] = True

    def is_street(x, z):
        return street.get((x, z), False)

    owner = grow_plots(seeds, lambda x, z: (x, z) not in fp and not is_street(x, z))
    info = {}
    for i in set(owner.values()):
        rings, p = idx.buildings[i]
        cx = sum(x for x, _ in rings[0]) / len(rings[0])
        cz = sum(z for _, z in rings[0]) / len(rings[0])
        num, st = _addr(p)
        s = idx.nearest_street(cx, cz)
        info[i] = {'street': st or (s[1] if s else ''), 'number': num or '', 'centre': (cx, cz),
                   'foot': s[3] if s else None, 'osm': p.get('osm_id') or p.get('osm_way_id')}
    return owner, info, street, idx


def segments(owner: dict, info: dict, street: dict, idx, box) -> dict:
    """{(plot id, role): [cells]} for plot edge columns (outside footprints) inside ``box``."""
    x0, z0, x1, z1 = box
    fp = idx.cells()
    seg = defaultdict(list)
    for (x, z), i in owner.items():
        if (x, z) in fp or not (x0 <= x <= x1 and z0 <= z <= z1):
            continue
        meta = info[i]
        fx, fz = (meta['foot'] or (x, z))
        ax, az = meta['centre'][0] - fx, meta['centre'][1] - fz       # street -> house axis
        n = math.hypot(ax, az) or 1.0
        ax, az = ax / n, az / n
        for dx, dz in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            q = (x + dx, z + dz)
            if q in fp or owner.get(q) == i:
                continue
            if street.get(q):
                role = 'front'
            elif q in owner:
                if abs(dx * ax + dz * az) > math.sqrt(0.5):
                    role = 'rear'
                else:       # side: in front of the house line (front garden) or behind it
                    role = 'side_front' if ((x - fx) * ax + (z - fz) * az) < n - 6 else 'side_back'
            else:
                continue                                              # open edge: no evidence
            seg[(i, role)].append((x, z))
    return seg


def components(cells) -> list:
    """8-connected groups of columns."""
    left, out = set(cells), []
    while left:
        seed = left.pop()
        group, stack = [seed], [seed]
        while stack:
            x, z = stack.pop()
            for a in (-1, 0, 1):
                for b in (-1, 0, 1):
                    q = (x + a, z + b)
                    if q in left:
                        left.remove(q)
                        group.append(q)
                        stack.append(q)
        out.append(group)
    return out


def walk(group) -> list:
    """Order a group's columns along itself: start at an end, then always step to the nearest unvisited."""
    pts = set(group)
    near = lambda p: sum((p[0] + a, p[1] + b) in pts for a in (-1, 0, 1) for b in (-1, 0, 1) if a or b)
    cur = min(pts, key=lambda p: (near(p), p))
    path = [cur]
    pts.remove(cur)
    while pts:
        cur = min(pts, key=lambda p: ((p[0] - cur[0]) ** 2 + (p[1] - cur[1]) ** 2, p))
        path.append(cur)
        pts.remove(cur)
    return path


def simplify(path, tol: float = 1.2) -> list:
    """Douglas-Peucker: the few corner points a boundary really turns at."""
    if len(path) < 3:
        return list(path)
    (ax, az), (bx, bz) = path[0], path[-1]
    n = math.hypot(bx - ax, bz - az) or 1.0
    dist = [abs((bx - ax) * (az - z) - (ax - x) * (bz - az)) / n for x, z in path]
    k = max(range(len(path)), key=dist.__getitem__)
    if dist[k] <= tol:
        return [path[0], path[-1]]
    return simplify(path[:k + 1], tol)[:-1] + simplify(path[k:], tol)


def line4(a, b) -> list:
    """4-connected columns of the straight line a-b (every column the line crosses, no diagonal gaps)."""
    (x0, z0), (x1, z1) = a, b
    dx, dz = abs(x1 - x0), abs(z1 - z0)
    sx, sz = (1 if x1 > x0 else -1), (1 if z1 > z0 else -1)
    x, z, out = x0, z0, [(x0, z0)]
    ix = iz = 0
    while ix < dx or iz < dz:
        if (1 + 2 * ix) * dz == (1 + 2 * iz) * dx:      # exactly through a corner: step both
            x, z, ix, iz = x + sx, z + sz, ix + 1, iz + 1
            out.append((x - sx, z))
        elif (1 + 2 * ix) * dz < (1 + 2 * iz) * dx:
            x, ix = x + sx, ix + 1
        else:
            z, iz = z + sz, iz + 1
        out.append((x, z))
    return out


def straighten(cells) -> list:
    """Replace a rasterised plot edge by straight, 4-connected runs between its corner points."""
    out = []
    for g in components(cells):
        pts = simplify(walk(g)) if len(g) > 1 else g
        for a, b in zip(pts, pts[1:]):
            out += line4(a, b)
        if len(pts) == 1:
            out += pts
    return out


def hedge_share(cells: list, rgb: dict) -> float:
    """Share of the cells whose aerial colour is dark saturated green (hedge/shrub strip)."""
    from ground_sources import aerial_class
    seen = [aerial_class(rgb[q]) for q in cells if q in rgb]
    return (sum(1 for c in seen if c == 'shade') / len(seen)) if seen else 0.0


def garden_barriers(cell: tuple[int, int], rgb: dict | None = None, report: dict | None = None):
    """{(x, z): (type, block, height)} fence/wall/hedge columns for one cell, plus a report.

    ``rgb`` is the cell's aerial sampler output (ground_sources.aerial_rgb); fetched if omitted.
    """
    from ground_sources import aerial_rgb, cell_box

    box = cell_box(cell)
    rgb = rgb if rgb is not None else aerial_rgb(cell)
    owner, info, street, idx = plots_for(box)
    seg = segments(owner, info, street, idx, box)
    out, rep = {}, []
    for (i, role), cells in sorted(seg.items(), key=lambda kv: (info[kv[0][0]]['street'], kv[0][1])):
        meta = info[i]
        conv = load_convention(meta['street'])
        spec = role_spec(conv, meta['number'], role)
        near = [q for q in cells if math.hypot(q[0] - meta['centre'][0], q[1] - meta['centre'][1]) <= 30]
        share = hedge_share(near, rgb) if len(near) >= 4 else 0.0   # only the house's own garden
        src = 'convention' if spec else 'none'
        if share >= HEDGE_SHARE and len(cells) >= 4:
            spec, src = {'type': 'hedge', 'block': HEDGE_BLOCK, 'height': 2, 'depth': None}, 'aerial hedge'
        if spec and spec.get('depth') and role.startswith('side'):
            fx, fz = meta['foot'] or meta['centre']
            cells = [q for q in cells if math.hypot(q[0] - fx, q[1] - fz) <= spec['depth'] + 12]
        if spec:
            # a boundary between two plots is one line: the lower plot id keeps it (if it builds one)
            def twin(q):
                for a, b in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                    j = owner.get((q[0] + a, q[1] + b))
                    if j is not None and j < i and role != 'front' and \
                            role_spec(load_convention(info[j]['street']), info[j]['number'], role):
                        return True
                return False
            for q in straighten([q for q in cells if not twin(q)]):
                out[q] = (spec['type'], spec['block'], spec['height'])
        rep.append({'street': meta['street'], 'number': meta['number'], 'role': role,
                    'cells': len(cells), 'source': src, 'hedge_share': round(share, 2),
                    'type': spec['type'] if spec else None})
    if report is not None:
        report['segments'] = rep
    return out


def overlay(cell, barriers: dict, path: Path, rgb_cells=None) -> None:
    """Aerial crop of the cell with the barrier columns marked (fence cyan, wall red, hedge green)."""
    import numpy as np
    from PIL import Image
    from ground_sources import MOSAIC, cell_box, mosaic_px

    x0, z0, x1, z1 = cell_box(cell)
    k = 4
    keys = [(x, z) for x in range(x0, x1 + 2) for z in range(z0, z1 + 2)]
    # block corners (the sampler adds .5 to its input, so ask for x - .5)
    px = dict(zip(keys, mosaic_px([(x - .5, z - .5) for x, z in keys]).values()))
    im = np.asarray(Image.open(MOSAIC).convert('RGB'))
    W = (x1 - x0 + 1) * k
    H = (z1 - z0 + 1) * k
    out = np.zeros((H, W, 3), np.uint8)
    for a in range(W):
        for b in range(H):
            x, z = x0 + a / k, z0 + b / k
            xi, zi = int(math.floor(x)), int(math.floor(z))
            fx, fz = x - xi, z - zi
            p00, p10 = px[(xi, zi)], px[(xi + 1, zi)]
            p01, p11 = px[(xi, zi + 1)], px[(xi + 1, zi + 1)]
            X = (p00[0] * (1 - fx) + p10[0] * fx) * (1 - fz) + (p01[0] * (1 - fx) + p11[0] * fx) * fz
            Y = (p00[1] * (1 - fx) + p10[1] * fx) * (1 - fz) + (p01[1] * (1 - fx) + p11[1] * fx) * fz
            X, Y = int(X), int(Y)
            if 0 <= X < im.shape[1] and 0 <= Y < im.shape[0]:
                out[b, a] = im[Y, X]
    col = {'hedge': (40, 255, 40), 'brick_wall': (255, 40, 40), 'fence': (0, 220, 255),
           'iron_bars': (255, 0, 255)}
    for (x, z), (t, _b, _h) in barriers.items():
        a, b = (x - x0) * k, (z - z0) * k
        out[b + 1:b + k - 1, a + 1:a + k - 1] = col.get(t, (255, 255, 0))
    Image.fromarray(out).resize((W * 2, H * 2), Image.NEAREST).save(path)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--cell', required=True)
    ap.add_argument('--png', default='')
    a = ap.parse_args()
    cell = tuple(int(v) for v in a.cell.split(','))
    rep: dict = {}
    b = garden_barriers(cell, report=rep)
    by = Counter((r['street'], r['role'], r['source'], r['type']) for r in rep['segments'])
    for k, n in sorted(by.items(), key=str):
        print(n, k)
    print('barrier columns', len(b), dict(Counter(v[0] for v in b.values())))
    png = Path(a.png) if a.png else ROOT / f'verification/site/gardens_{cell[0]}_{cell[1]}.png'
    overlay(cell, b, png)
    print('overlay', png)
    return 0


if __name__ == '__main__':
    sys.exit(main())
