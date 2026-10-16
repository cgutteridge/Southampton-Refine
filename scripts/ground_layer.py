#!/usr/bin/env python3
"""Ground layer for one 128² cell — HANDOFF-LAYERED-PASSES §1 (pass 2) and §10.

Written from first principles. It knows nothing about any one place: no zones, no campus
polygon, no hand-placed rectangles, no earlier ground pass. Per column it asks three questions.

  WHAT is on the ground?  OSM tags first (roads, paths, car parks, pedestrian areas, grass,
                          wood), then the z19 aerial for anything OSM does not describe
                          (ground_sources.py). Shade and canopy hide the ground, so those
                          columns take the lawn/paving around them.
  HOW HIGH?               The existing LIDAR-derived surface Y (trusted: NOTES / geocraft-accuracy).
                          Only single-column ±1 spikes on hard surfaces are levelled.
  WHAT BLOCK?             One palette, from CRAFTSMANSHIP §3a: tarmac gray_concrete (centre dashes
                          white_concrete, public-road edge smooth_stone), light paving
                          light_gray_concrete, brick paving polished_granite, grass grass_block.

Then, per §10: the top block becomes the surface block, raised columns get dirt beneath, and
everything above the surface is cleared except blocks a neighbour owns or a tree/decor mask holds.

Columns this layer never touches: OSM building footprints, columns any structure build owns,
water and its bank, mapped bridges/steps, and anything outside the cell. Trees and decor are
separate later passes that write masks; a ground plan that lands on a masked position is a
conflict and does not apply (undo that mask first: scripts/mask_undo.py).

  python3 scripts/ground_layer.py --cell 48,-44                 # dry run + preview + kinds image
  SITE_OWNER=<owner> python3 scripts/ground_layer.py --cell 48,-44 --apply
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'scripts'))

from ground_sources import (OSMGround, PRI, RegRGB, aerial_class, aerial_rgb, cell_box,  # noqa: E402
                            line_cells, hsv, majority, MARGIN)
from cell_marker import is_marker_wool  # noqa: E402
from pass_mask import MASK_DIR, mask_placements, read_mask  # noqa: E402
from site_kit import Plan, World, built_cells, full  # noqa: E402
from surface_probe import (PLANTS, is_tree_or_plant_block, is_water, short_id,  # noqa: E402,F401
                           surface_y)

SCAN_TOP = 120          # highest y the clear step looks at (survey tops out near 110)
RAISE_FILL = 'dirt'
AIRS = frozenset({'minecraft:air', 'minecraft:cave_air', 'minecraft:void_air'})
STEM_OR_FLOWER = frozenset(full(p) for p in PLANTS)

# Palette (CRAFTSMANSHIP §3a). One block per kind; markings and kerbs are tarmac extras.
MATERIAL = {
    'grass': 'grass_block', 'tarmac': 'gray_concrete', 'paving': 'light_gray_concrete',
    'brick': 'polished_granite', 'gravel': 'gravel', 'dirt': 'coarse_dirt',
    'mark': 'white_concrete', 'kerb': 'smooth_stone',
}
BLOCK_KIND = {'gray_concrete': 'tarmac', 'light_gray_concrete': 'paving', 'polished_granite': 'brick',
              'grass_block': 'grass', 'gravel': 'gravel'}
STITCH_DEPTH = 2        # columns from a seam that copy the finished neighbour's surface
HARD = ('tarmac', 'paving', 'brick', 'gravel', 'dirt', 'mark', 'kerb')
FILL_REACH = 12         # how far shade/canopy columns look for ground around them
STRUCTURE_TOPS = ('stairs', 'slab', '_wall', '_fence', 'bars', 'planks', '_carpet')

# Earlier ground and foliage passes. Their blocks are what this layer replaces, so they are not
# owners. (Records of them stay in verification/site; only this ownership test forgets them.)
RETIRED_GROUND_PASSES = frozenset({
    'highfield_q050_opens', 'highfield_q050_clears', 'highfield_q051_ur', 'highfield_q053_paths',
    'highfield_q054_micro', 'highfield_q061_stragglers', 'highfield_q063_m45_edge',
})


def plan_name(tx: int, tz: int, layer: str = 'ground') -> str:
    """Build name, e.g. highfield_48_m44_ground."""
    return f"highfield_{tx}_{'m' if tz < 0 else ''}{abs(tz)}_{layer}"


def bare(block: str | None) -> str:
    """Block id without its [state] suffix."""
    return (block or 'minecraft:air').split('[')[0]


def is_air(block: str | None) -> bool:
    """Air for the ground step: includes flowers and grass stems (§10); grass BLOCK is not air."""
    return bare(block) in AIRS or bare(block) in STEM_OR_FLOWER


def cell_contains(cell: tuple[int, int], x: int, z: int) -> bool:
    """True if column (x, z) is inside the 128² cell."""
    x0, z0, x1, z1 = cell_box(cell)
    return x0 <= x <= x1 and z0 <= z <= z1


def cell_bbox_str(cell: tuple[int, int], margin: int = 0) -> str:
    """Region-backup bbox for the cell: x0,z0,x1,z1, grown by margin blocks (tree overhang)."""
    x0, z0, x1, z1 = cell_box(cell)
    return ','.join(str(v) for v in (x0 - margin, z0 - margin, x1 + margin, z1 + margin))


def ignored_builds(cell: tuple[int, int]) -> frozenset:
    """Builds that do not count as owners for this cell's ground pass.

    Earlier ground passes (retired), plus this cell's own layer plans: the old foliage pass and
    the ground/trees/decor plans that are being redone, and cell marker rings (wool ~30 m up, not
    ground: counting them left the cell's outer ring of columns unsurfaced). Another cell's trees
    stay owners.
    """
    own = {plan_name(*cell, layer) for layer in ('ground', 'trees', 'decor', 'foliage')}
    return RETIRED_GROUND_PASSES | own | {n for n in _all_build_names()
                                          if n.startswith(('highfield_grounds_', 'cell_marker_'))}


def _all_build_names() -> set:
    from site_kit import OUT
    return {f.name[:-len('-cells.json')] for f in OUT.glob('*-cells.json')}


def load_masked_positions() -> dict:
    """Every position owned by a tree or decor mask: {pos: 'pass tx,tz'}."""
    owned: dict = {}
    if MASK_DIR.exists():
        for path in sorted(MASK_DIR.glob('*.mask.json')):
            mask = read_mask(path)
            for pos in mask_placements(mask):
                owned[pos] = f"{mask['pass']} {mask['cell'][0]},{mask['cell'][1]}"
    return owned


# --- 1. which columns are ours -----------------------------------------------------------
def free_columns(cell: tuple[int, int], world: World, osm: OSMGround, fp: set, owned_cols: set):
    """Columns this layer may surface, with their live surface (y, block).

    Returns (live: {(x,z): (y, short block)}, skipped: Counter of reasons).
    """
    x0, z0, x1, z1 = cell_box(cell)
    live, skipped = {}, Counter()
    water = set(osm.water)
    probed = {}
    for x in range(x0 - 1, x1 + 2):
        for z in range(z0 - 1, z1 + 2):
            probed[(x, z)] = surface_y(world, x, z)
            if probed[(x, z)] and (is_water(f'minecraft:{probed[(x, z)][1]}') or
                                   'waterlogged=true' in (world.block(x, probed[(x, z)][0], z) or '')):
                water.add((x, z))
    bank = {(x + a, z + b) for x, z in water for a in (-1, 0, 1) for b in (-1, 0, 1)}
    for x in range(x0, x1 + 1):
        for z in range(z0, z1 + 1):
            q = (x, z)
            top = probed[q]
            if q in fp:
                skipped['building footprint'] += 1
            elif q in owned_cols:
                skipped['structure build'] += 1
            elif q in bank:
                skipped['water / bank'] += 1
            elif q in osm.bridge:
                skipped['bridge / steps'] += 1
            elif top is None:
                skipped['empty column'] += 1
            elif any(s in top[1] for s in STRUCTURE_TOPS):
                skipped[f'structure top {top[1]}'] += 1
            else:
                live[q] = top
    return live, skipped



PATH_KINDS = ('paving', 'brick', 'gravel', 'dirt', 'tarmac')
BRIDGE_REACH = 30       # longest shaded stretch a path is carried across, in blocks
BRIDGE_ANGLE = 0.82     # cos of the largest bend allowed between a path's two ends (~35°)


def _components(cells: set) -> list:
    """8-connected components of a set of columns."""
    left, out = set(cells), []
    while left:
        seed = left.pop()
        comp, todo = {seed}, [seed]
        while todo:
            q = todo.pop()
            for a in (-1, 0, 1):
                for b in (-1, 0, 1):
                    n = (q[0] + a, q[1] + b)
                    if n in left:
                        left.discard(n)
                        comp.add(n)
                        todo.append(n)
        out.append(comp)
    return out


def _path_ends(shade: set, kind: dict) -> list:
    """Where a seen path meets a shaded patch: (kind, entry point, unit direction into the shade, width).

    The direction is the principal axis of the path's visible cells near the entry, signed to point
    at the shade; the width is their spread across that axis.
    """
    ends = []
    border = {q for q in kind if kind[q] in PATH_KINDS and
              any((q[0] + a, q[1] + b) in shade for a in (-1, 0, 1) for b in (-1, 0, 1))}
    for grp in _components(border):
        k = Counter(kind[q] for q in grp).most_common(1)[0][0]
        cx = sum(q[0] for q in grp) / len(grp)
        cz = sum(q[1] for q in grp) / len(grp)
        near = [q for q in kind if kind[q] in PATH_KINDS and abs(q[0] - cx) <= 5 and abs(q[1] - cz) <= 5]
        if not near:  # curved/ring-shaped border group: centroid sits off the path
            near = list(grp)
        mx = sum(q[0] for q in near) / len(near)
        mz = sum(q[1] for q in near) / len(near)
        sxx = sum((q[0] - mx) ** 2 for q in near)
        szz = sum((q[1] - mz) ** 2 for q in near)
        sxz = sum((q[0] - mx) * (q[1] - mz) for q in near)
        ang = 0.5 * math.atan2(2 * sxz, sxx - szz)
        d = (math.cos(ang), math.sin(ang))
        sh = [q for q in shade if abs(q[0] - cx) <= 4 and abs(q[1] - cz) <= 4]
        if not sh:
            continue
        sx = sum(q[0] for q in sh) / len(sh) - cx
        sz = sum(q[1] for q in sh) / len(sh) - cz
        if d[0] * sx + d[1] * sz < 0:
            d = (-d[0], -d[1])
        perp = [(q[0] - cx) * -d[1] + (q[1] - cz) * d[0] for q in near]
        ends.append((k, (cx, cz), d, max(1.0, min(6.0, max(perp) - min(perp) + 1))))
    return ends


def bridge_paths(kind: dict, shade: set) -> dict:
    """Carry paths across shade: pair two path ends that face each other and fill the gap.

    Two ends pair when they are the same kind (or both hard), within reach, and the line between
    them stays within ~35° of both ends' direction, so a wide lawn between two unrelated
    paths is not bridged. Returns {column: kind} for the shaded columns the paths cross.
    """
    ends = _path_ends(shade, kind)
    out: dict = {}
    used: set = set()
    pairs = []
    for i, (ka, pa, da, wa) in enumerate(ends):
        for j in range(i + 1, len(ends)):
            kb, pb, db, wb = ends[j]
            v = (pb[0] - pa[0], pb[1] - pa[1])
            dist = math.hypot(*v)
            if not 2 <= dist <= BRIDGE_REACH:
                continue
            u = (v[0] / dist, v[1] / dist)
            ca = da[0] * u[0] + da[1] * u[1]
            cb = -(db[0] * u[0] + db[1] * u[1])
            if ca >= BRIDGE_ANGLE and cb >= BRIDGE_ANGLE:
                pairs.append((dist * (2 - ca - cb), i, j))
    for _score, i, j in sorted(pairs):
        if i in used or j in used:
            continue
        used |= {i, j}
        ka, pa, _da, wa = ends[i]
        kb, pb, _db, wb = ends[j]
        half = (wa + wb) / 4
        for q, (dist, along) in line_cells([pa, pb], half).items():
            if q in shade:
                out[q] = ka if along <= math.dist(pa, pb) / 2 else kb
    return out


MIN_PATCH = {'grass': 12, 'paving': 8, 'brick': 8, 'gravel': 8, 'dirt': 8, 'tarmac': 12}


def denoise(kind: dict, locked: set, how: Counter) -> dict:
    """Noise reduction: a small isolated patch of one kind takes the kind that surrounds it.

    Patches are 4-connected runs of one kind. One smaller than MIN_PATCH, that is not mapped tarmac
    (roads and car parks are real however small), is re-labelled to the most common kind on its
    border. Thin features survive because they are long: a 2-wide path is 8 columns after 4 blocks.
    Runs three times so a patch exposed by the first pass can still go.
    """
    out = dict(kind)
    for _ in range(3):
        changed = 0
        for k in MIN_PATCH:
            cols = {q for q, v in out.items() if v == k}
            left = set(cols)
            while left:
                seed = left.pop()
                comp, todo = {seed}, [seed]
                while todo:
                    q = todo.pop()
                    for n in ((q[0] + 1, q[1]), (q[0] - 1, q[1]), (q[0], q[1] + 1), (q[0], q[1] - 1)):
                        if n in left:
                            left.discard(n)
                            comp.add(n)
                            todo.append(n)
                if len(comp) >= MIN_PATCH[k] or comp & locked:
                    continue
                border = Counter(out[(q[0] + a, q[1] + b)] for q in comp for a in (-1, 0, 1) for b in (-1, 0, 1)
                                 if (q[0] + a, q[1] + b) in out and (q[0] + a, q[1] + b) not in comp)
                if border:
                    new = border.most_common(1)[0][0]
                    for q in comp:
                        out[q] = new
                    changed += len(comp)
        how['noise removed'] += changed
        if not changed:
            break
    return out


# --- 2. what is on the ground ------------------------------------------------------------
def classify(cell: tuple[int, int], live: dict, osm: OSMGround, rgb: dict,
             fp: set | None = None) -> tuple[dict, Counter]:
    """Surface kind per free column: OSM first, aerial where OSM is silent, fill under shade."""
    free = set(live)
    x0, z0, x1, z1 = cell_box(cell, MARGIN)
    aer = {q: aerial_class(c) for q, c in rgb.items() if x0 <= q[0] <= x1 and z0 <= q[1] <= z1}
    raw = aer
    aer = majority(aer, set(aer))
    kind, how = {}, Counter()
    soft_grass: set = set()                               # lawn guessed, not seen (orange far from paths, shade fill)
    for q in free:
        a = aer.get(q)
        ok = osm.kind.get(q)
        if ok and osm.pri[q] in (50, 70) and q in osm.soft and (a in ('lawn', 'brick', 'shade') or (
                a in ('light', 'dark') and q in rgb and hsv(rgb[q])[1] >= 0.07)):
            kind[q] = 'grass'                             # mapped car park, but the aerial shows open ground
            how['aerial lawn inside mapped car park'] += 1
        elif ok and osm.pri[q] == PRI['pedestrian'] and a == 'lawn' and isinstance(rgb.get(q), RegRGB):
            kind[q] = 'grass'                             # lawn strip/planter inside a mapped plaza, seen in a sharp registered aerial
            how['registered aerial lawn inside mapped plaza'] += 1
        elif ok and osm.pri[q] >= 40:                     # a mapped road, path, car park or plaza
            kind[q] = ok
            how['osm surface'] += 1
        elif a == 'lawn':
            kind[q] = 'grass'
            how['aerial lawn'] += 1
        elif a == 'brick':
            if any(osm.pri.get((q[0] + i, q[1] + j), 0) >= 40 for i in range(-4, 5) for j in range(-4, 5)):
                kind[q] = 'brick'
                how['aerial brick'] += 1
            else:                                         # orange far from any mapped path: shed roof / bed, not paving
                kind[q] = 'grass'
                soft_grass.add(q)
                how['aerial brick away from paths -> lawn'] += 1
        elif a in ('light', 'dark'):
            kind[q] = 'paving'
            how['aerial paving'] += 1
    # shade and canopy hide the ground. First carry the paths that go under it straight across,
    # with the colour of their visible ends; then what is left takes the nearest seen ground.
    shaded = {q for q in free if aer.get(q) == 'shade'}
    # Block paving vs plain paving: vote along the same mapped path (or plaza) over the columns where
    # pavement colour is actually visible. Canopy and lawn-coloured columns do not vote, so a path
    # that goes under a tree takes the colour of the path on either side of it.
    by_feat: dict = {}
    for q in free:
        if kind.get(q) == 'paving' and osm.pri.get(q, 0) >= 40:
            by_feat.setdefault(osm.feat.get(q), []).append(q)
    for f, cols in by_feat.items():
        votes = [(q, raw.get(q)) for q in (cols if f is not None else [])
                 if raw.get(q) in ('brick', 'light') and aer.get(q) in ('brick', 'light')]
        for q in cols:
            if f is None:
                near = sum(raw.get((q[0] + i, q[1] + j)) == 'brick' for i in (-1, 0, 1) for j in (-1, 0, 1))
                if near >= 3:
                    kind[q] = 'brick'
                continue
            near = [c for p, c in votes if abs(p[0] - q[0]) <= 8 and abs(p[1] - q[1]) <= 8]
            if near.count('brick') > near.count('light'):
                kind[q] = 'brick'
                if q in shaded or aer.get(q) not in ('brick', 'light'):
                    how['mapped path colour voted along its length'] += 1
    gap = free - set(kind)
    seen_kind = {q: k for q, k in kind.items() if q not in shaded}
    for q, k in bridge_paths(seen_kind, gap).items():
        kind[q] = k
        how['path carried across shade'] += 1
    seen = {q: k for q, k in kind.items()}
    for q in sorted(free - set(kind)):
        if osm.kind.get(q) == 'grass':                    # mapped lawn, hidden by canopy
            kind[q] = 'grass'
            how['osm grass (under shade)'] += 1
            continue
        best = None
        for r in range(1, FILL_REACH + 1):
            ring = [(q[0] + a, q[1] + b) for a in range(-r, r + 1) for b in range(-r, r + 1)
                    if max(abs(a), abs(b)) == r and (q[0] + a, q[1] + b) in seen]
            if ring:
                best = Counter(seen[p] for p in ring).most_common(1)[0][0]
                break
        near_path = any(osm.pri.get((q[0] + a, q[1] + b), 0) >= 40 for a in range(-3, 4) for b in range(-3, 4))
        if best in ('paving', 'brick') and not near_path:
            best = 'grass'                                # unseen ground away from any mapped path: lawn/bed
        kind[q] = best or 'grass'
        if best in (None, 'grass'):
            soft_grass.add(q)
        how['filled under shade'] += 1
    # A guessed lawn strip squeezed between a public road and a building front is pavement (shopfront
    # forecourts, shadowed by the buildings), not garden. Only guessed lawn is converted, never seen lawn.
    if fp:
        road = {q for q in osm.kind if osm.kind[q] == 'tarmac' and osm.pri.get(q, 0) >= 40}
        for q in soft_grass:
            if kind.get(q) == 'grass' and any((q[0] + a, q[1] + b) in road for a in range(-8, 9) for b in range(-8, 9)) \
                    and any((q[0] + a, q[1] + b) in fp for a in range(-4, 5) for b in range(-4, 5)):
                kind[q] = 'paving'
                how['guessed lawn between road and building -> paving'] += 1
    barrier = osm.hedge | osm.wall | osm.fence
    lawn_by_barrier = {q for q in kind if kind[q] == 'grass' and any(
        (q[0] + a, q[1] + b) in barrier for a in (-1, 0, 1) for b in (-1, 0, 1))}
    kind = denoise(kind, {q for q in kind if osm.pri.get(q, 0) >= 40 and osm.kind.get(q) == 'tarmac'}
                   | lawn_by_barrier, how)          # a hedge needs its strip of lawn: not noise
    # road furniture: dashed centre line, kerb along the public-road edge (dropped at crossings)
    out = dict(kind)
    for q in free:
        if q in osm.road and kind.get(q) == 'tarmac' and q in osm.marks:
            out[q] = 'mark'
    for q in free:
        if q in osm.road and kind.get(q) == 'tarmac':
            nb = [kind.get((q[0] + a, q[1] + b)) for a, b in ((1, 0), (-1, 0), (0, 1), (0, -1))]
            if any(k in ('grass', 'paving', 'brick') for k in nb) and not any(
                    (q[0] + a, q[1] + b) in osm.kind and osm.pri[(q[0] + a, q[1] + b)] in (60, 70)
                    for a, b in ((1, 0), (-1, 0), (0, 1), (0, -1))):
                out[q] = 'kerb'
    return out, how


# --- 3. how high -------------------------------------------------------------------------
def level_spikes(live: dict, kind: dict, fp: set) -> dict:
    """Surface Y per column. Only an isolated ±1 on a hard surface is levelled to its neighbours."""
    ys = {q: v[0] for q, v in live.items()}
    out = dict(ys)
    n = 0
    for q, y in ys.items():
        if kind[q] not in HARD or any((q[0] + a, q[1] + b) in fp for a in range(-2, 3) for b in range(-2, 3)):
            continue
        nb = [ys[(q[0] + a, q[1] + b)] for a in (-1, 0, 1) for b in (-1, 0, 1)
              if (a or b) and (q[0] + a, q[1] + b) in ys and kind.get((q[0] + a, q[1] + b)) in HARD]
        if len(nb) >= 6:
            med = sorted(nb)[len(nb) // 2]
            if abs(med - y) == 1 and sum(1 for v in nb if v == med) >= len(nb) - 1:
                out[q] = med
                n += 1
    out['_levelled'] = n
    return out


# --- 4. the plan -------------------------------------------------------------------------
def ground_done(cell: tuple[int, int]) -> bool:
    """True if the cell's STAGES file records a ground pass (its surface is the reference)."""
    path = ROOT / f'site/cells/{cell[0]}_{cell[1]}-STAGES.json'
    if not path.exists():
        return False
    stages = json.loads(path.read_text()).get('stages', {})
    return any(k in stages for k in ('ground', 'ground-layer'))


def stitch_seams(cell: tuple[int, int], kind: dict, world: World) -> int:
    """Make the outer columns continue the surface of a neighbour whose ground is already done.

    Each cell classifies its own edge, so a road or path can end at the seam. Where the next
    cell across a side has its ground done, the STITCH_DEPTH outer columns copy that neighbour's
    surface kind at the same lateral position (mark / kerb / dirt and water are left alone).
    Returns the number of columns changed.
    """
    x0, z0, x1, z1 = cell_box(cell)
    sides = (((-1, 0), x0, 'x'), ((1, 0), x1, 'x'), ((0, -1), z0, 'z'), ((0, 1), z1, 'z'))
    changed = 0
    for (dx, dz), edge, axis in sides:
        if not ground_done((cell[0] + dx, cell[1] + dz)):
            continue
        for q in [c for c in kind if (c[0] if axis == 'x' else c[1]) in
                  [edge - dx * d if axis == 'x' else edge - dz * d for d in range(STITCH_DEPTH)]]:
            if kind[q] in ('mark', 'kerb', 'dirt'):
                continue
            ref = (edge + dx, q[1]) if axis == 'x' else (q[0], edge + dz)
            top = surface_y(world, *ref)
            want = BLOCK_KIND.get(top[1]) if top else None
            if want and want != kind[q]:
                kind[q] = want
                changed += 1
    return changed


def plan_cell(cell: tuple[int, int], masked: dict, neighbour_owned: set, plan: Plan, world: World,
              evidence=None):
    """Plan the ground for one cell. Returns (stats, conflicts, kinds, skipped)."""
    from osm_footprints import OSMIndex

    ev = evidence or {}
    osm = ev.get('osm') or OSMGround(cell)
    rgb = ev.get('rgb') or aerial_rgb(cell)
    x0, z0, x1, z1 = cell_box(cell, 2)
    fp = {q for q in OSMIndex().cells() if x0 <= q[0] <= x1 and z0 <= q[1] <= z1}
    owned_cols = {(x, z) for x, _y, z in neighbour_owned}
    live, skipped = free_columns(cell, world, osm, fp, owned_cols)
    kind, how = classify(cell, live, osm, rgb, fp)
    how['seam stitched to finished neighbour'] = stitch_seams(cell, kind, world)
    ys = level_spikes(live, kind, fp)
    stats = Counter({'columns': len(live), 'levelled': ys.pop('_levelled')})
    stats.update({f'how: {k}': v for k, v in how.items()})
    conflicts = []
    for q in sorted(live):
        x, z = q
        old = live[q][0]
        gy = ys[q]
        k = kind[q]
        mat = MATERIAL[k]
        top = (x, gy, z)
        if top in masked:
            conflicts.append((top, mat, masked[top]))
        else:
            plan.set(x, gy, z, mat)
            stats['top'] += 1
        for y in range(old + 1, gy):                      # raised: solid under the new top
            pos = (x, y, z)
            if is_air(world.block(x, y, z)) and pos not in neighbour_owned:
                if pos in masked:
                    conflicts.append((pos, RAISE_FILL, masked[pos]))
                else:
                    plan.set(x, y, z, RAISE_FILL)
                    stats['raise'] += 1
        for y in range(gy + 1, SCAN_TOP + 1):             # above the surface: clear (§10)
            pos = (x, y, z)
            b = world.block(x, y, z)
            if bare(b) in AIRS or is_marker_wool(b):          # hazard-tape ring stays
                continue
            if pos in neighbour_owned:
                stats['kept_neighbour'] += 1
                continue
            if pos in masked:
                stats['kept_masked'] += 1
                continue
            if bare(b) in STEM_OR_FLOWER and y == gy + 1 and mat == 'grass_block':
                continue                                  # a flower or grass stem may stand on lawn
            plan.set(x, y, z, 'air')
            stats['clear'] += 1
    return stats, conflicts, kind, skipped


KIND_RGB = {'grass': (110, 180, 70), 'tarmac': (70, 70, 80), 'paving': (200, 200, 200),
            'brick': (190, 90, 60), 'gravel': (150, 140, 120), 'dirt': (120, 90, 60),
            'mark': (255, 255, 255), 'kerb': (255, 220, 60)}


def kinds_image(cell: tuple[int, int], kind: dict, out: Path, scale: int = 4) -> None:
    """Kinds map beside the aerial crop of the same cell, for the review."""
    import numpy as np
    from PIL import Image
    from ground_sources import MOSAIC, mosaic_px

    x0, z0, x1, z1 = cell_box(cell)
    img = np.full((128, 128, 3), 35, np.uint8)
    for (x, z), k in kind.items():
        img[z - z0, x - x0] = KIND_RGB[k]
    left = Image.fromarray(img).resize((128 * scale, 128 * scale), Image.NEAREST)
    px = mosaic_px([(x0, z0), (x1 + 1, z1 + 1)])
    (ax, ay), (bx, by) = px[(x0, z0)], px[(x1 + 1, z1 + 1)]
    right = Image.open(MOSAIC).convert('RGB').crop((int(ax), int(ay), int(bx), int(by))).resize(left.size)
    sheet = Image.new('RGB', (left.width * 2 + 8, left.height), (0, 0, 0))
    sheet.paste(left, (0, 0))
    sheet.paste(right, (left.width + 8, 0))
    out.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(out)


def _fresh_world(strict: bool = False) -> World:
    """Flush the server's chunks to disk, then read them: World reads the saved region files.

    ``strict`` (live apply): a failed flush raises, because planning from stale region files writes
    a wrong plan.
    """
    try:
        from mc_paced import Paced
        Paced().call('server_save_all_worlds', {})
    except Exception as exc:                              # noqa: BLE001
        if strict:
            raise SystemExit(f'could not flush the world before reading it: {exc}')
        print(f'  (could not flush the world before reading: {exc})')
    return World()


def run(cell: tuple[int, int], skip_preview: bool = False) -> int:
    """Dry-run one cell. Returns the number of conflicts (0 means it is safe to apply)."""
    tx, tz = cell
    name = plan_name(tx, tz)
    plan = Plan(name)
    world = _fresh_world()
    masked = load_masked_positions()
    neighbour_owned = set(built_cells(exclude=ignored_builds(cell)))
    stats, conflicts, kind, skipped = plan_cell(cell, masked, neighbour_owned, plan, world)
    changes = [p for p, b in plan.cells.items() if bare(world.block(*p)) != b]
    print(f'{name}: columns {stats["columns"]}  (levelled {stats["levelled"]})')
    print('  skipped: ' + ', '.join(f'{k} {v}' for k, v in skipped.most_common()))
    print('  evidence: ' + ', '.join(f'{k[5:]} {v}' for k, v in sorted(stats.items()) if k.startswith('how:')))
    print(f'  kinds: {dict(Counter(kind.values()).most_common())}')
    print(f'  top {stats["top"]}  raise {stats["raise"]}  clear {stats["clear"]}  '
          f'(kept: neighbour {stats["kept_neighbour"]}, masked {stats["kept_masked"]})')
    print(f'  planned cells {len(plan.cells)}  would change {len(changes)}')
    print(f'  mask positions known: {len(masked)}  conflicts: {len(conflicts)}')
    for pos, want, why in conflicts[:10]:
        print(f'    CONFLICT {pos}: wanted {want}, masked by {why}')
    if conflicts:
        print('  NOT SAFE TO APPLY: undo the listed mask first (scripts/mask_undo.py; HANDOFF-LAYERED §3, §10).')
    out = ROOT / f'verification/site/{name}-kinds.png'
    kinds_image(cell, kind, out)
    print(f'  kinds image: {out.relative_to(ROOT)}')
    if not skip_preview:
        from site_kit import preview
        pv = ROOT / f'verification/site/{name}-preview.png'
        preview(plan, pv, scale=2)
        print(f'  preview: {pv.relative_to(ROOT)}')
    return len(conflicts)


def apply_cell(cell: tuple[int, int]) -> int:
    """Live apply: lock held, region snapshot first, re-plan from the live world, readback.

    Returns 0 on a clean readback, otherwise 1.
    """
    import os
    import subprocess
    from site_kit import apply, readback

    if not os.environ.get('SITE_OWNER'):
        raise SystemExit('SITE_OWNER is not set; claim the lock first (scripts/site_lock.py claim <owner> ...)')
    tx, tz = cell
    name = plan_name(tx, tz)
    plan = Plan(name)
    world = _fresh_world(strict=True)
    masked = load_masked_positions()
    ignored = ignored_builds(cell)
    neighbour_owned = set(built_cells(exclude=ignored))
    stats, conflicts, kind, _skipped = plan_cell(cell, masked, neighbour_owned, plan, world)
    if conflicts:
        print(f'REFUSED: {len(conflicts)} mask conflict(s); undo the masks first (§3, §10)')
        return 1
    print(f'{name}: {len(plan.cells)} cells planned, stats {dict(stats)}')
    subprocess.run([sys.executable, str(ROOT / 'scripts/region_backup.py'), 'snap',
                    '--bbox', cell_bbox_str(cell), '--name', name], check=True)
    apply(plan, modifies=ignored, stage='ground-layer', cell=cell)   # records 'applying' first, 'applied' after readback
    rb = readback(plan)
    print(f'readback: {rb["planned"]} planned, {rb["mismatches"]} mismatches')
    stage = ROOT / f'site/cells/{tx}_{tz}-STAGES.json'
    data = json.loads(stage.read_text()) if stage.exists() else {'cell': f'{tx},{tz}', 'stages': {}}
    data['stages']['ground-layer'] = {
        'status': 'applied' if rb['mismatches'] == 0 else 'applied-with-mismatches',
        'plan': name, 'blocks': len(plan.cells), 'readback': rb,
        'note': 'first-principles ground (OSM + aerial); verify: patrol, visuals; trees and decor re-run after',
    }
    stage.write_text(json.dumps(data, indent=2) + '\n', encoding='utf-8')
    return 0 if rb['mismatches'] == 0 else 1


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--cell', required=True, help='tx,tz e.g. 48,-44')
    ap.add_argument('--skip-preview', action='store_true')
    ap.add_argument('--apply', action='store_true', help='LIVE: write to the world (needs SITE_OWNER + claimed lock)')
    a = ap.parse_args()
    cell = tuple(int(v) for v in a.cell.split(','))
    if a.apply:
        return apply_cell(cell)
    return 1 if run(cell, skip_preview=a.skip_preview) else 0


if __name__ == '__main__':
    sys.exit(main())
