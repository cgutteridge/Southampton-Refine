#!/usr/bin/env python3
"""Layered trees pass for one 128² cell — HANDOFF-LAYERED-PASSES §1 (pass 3), §2, §3.

Crowns are read from the z19 aerial (a 4x6 mosaic that covers the whole cell) by texture
plus greenness, not colour alone: sunlit crowns here are the same hue as the lawn.
Trees go only where the live block is air (or a grass stem / flower, as in §10), so the
mask undo is exact. A crown voxel that is not air (roof, wall, a neighbour's block) is
dropped; the tree is skipped if too much of it would be dropped or the trunk is blocked.
A tree belongs to the cell its trunk is in (the trunk is always in-cell); its crown may overhang into
neighbours' columns where the block is air or a leaf of a neighbour's trees mask (crowns merge), recorded
in this cell's mask. It never overwrites any other block. Undo skips blocks another mask also lists.
Writes a trees mask (§3) only after a clean readback.

  python3 scripts/trees_layer.py --cell 48,-44            # dry run + crown review image
  SITE_OWNER=<owner> python3 scripts/trees_layer.py --cell 48,-44 --apply
"""
from __future__ import annotations

import argparse
import json
import math
import random
import re
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'scripts'))

from ground_layer import plan_name as ground_plan_name, bare, cell_bbox_str, ignored_builds, is_air, load_masked_positions  # noqa: E402
from surface_probe import short_id, surface_y  # noqa: E402
from pass_mask import OVERHANG_MARGIN, build_mask, cell_bounds, clip_to_cell, write_mask  # noqa: E402
from plant_cell_canopy import MOSAIC_TILE0, RNG_SEED, bush_voxels, mosaic_px, tree_voxels  # noqa: E402
from site_kit import Plan, World, built_cells  # noqa: E402

MOSAIC = ROOT / 'reference/aerial/highfield-z19/mosaic-z19-18x17-260101-175662-eastext6.png'
LAYER_PLAN = re.compile(r'^highfield_\d+_m\d+_(ground|trees|decor|foliage|stripabove|edge_grass|podium_flatten)$')
LAWN_SURFACES = frozenset({'grass_block', 'dirt', 'podzol', 'coarse_dirt', 'moss_block'})
# Hard ground a tree can stand in: the real pavement has a soil pit under the trunk that the aerial
# never shows (user, 2026-10-14); the trunk hides the paving block, so nothing is placed below it.
# Tarmac, water, stairs/slabs and structure blocks stay out.
PAVED_SURFACES = frozenset({'light_gray_concrete', 'polished_granite', 'gravel'})
# Hard-surface rule (2026-10-15 dense-tree redo): trunks stand on lawn only, never on paving, gravel or tarmac.
TREES_ON_PAVING = False
KEEP_FRACTION = 0.7        # a crown that loses more than this to non-air is skipped
MIN_CROWN_R = 1.8          # below this a blob is a bush, not a tree
MAX_CROWN_R = 7.0
DENSITY_MIN = 0.55
# Dense-cover fill (I-059): in woodland the individual-crown detector finds a fraction of the crowns
# (shaded, brown-olive or dark canopy fails the lawn-green test), so area cover is read with a looser
# test and filled at a spacing that matches it. Planting still goes through plan_cell's rules.
COVER_MIN = 0.6            # local cover fraction below which nothing is filled (light canopy unchanged)
COVER_FULL = 0.9           # at or above this every fill site gets a tree
FILL_SPACING = 5           # jittered grid pitch of the fill (crowns here are 5-7 blocks across)
FILL_RADII = (2.5, 3.0, 3.0, 3.5, 4.0, 4.5)   # height variance: round 4-6 below 3.5, plane 8-9 above


class _InCell:
    """Membership test: is a position's x/z inside the cell."""

    def __init__(self, x0: int, z0: int, x1: int, z1: int):
        self.box = (x0, z0, x1, z1)

    def __contains__(self, p) -> bool:
        x0, z0, x1, z1 = self.box
        return x0 <= p[0] <= x1 and z0 <= p[2] <= z1


def may_plant(live: str | None, block: str, owner: str | None) -> bool:
    """The one placement rule: air, or a leaf onto a leaf that another cell's trees mask owns (crowns merge).

    owner is the mask owning the position ('trees 46,-44'), or None. Anything else is never overwritten.
    """
    if owner is None:
        return is_air(live)
    return owner.startswith('trees ') and 'leaves' in bare(live) and 'leaves' in block


def plan_name(tx: int, tz: int) -> str:
    """Build name, e.g. highfield_48_m44_trees."""
    return f"highfield_{tx}_{'m' if tz < 0 else ''}{abs(tz)}_trees"


def _box(a: np.ndarray, k: int) -> np.ndarray:
    """Mean over a k×k window (edge padded)."""
    pad = np.pad(a, k // 2, mode='edge')
    h, w = a.shape
    return sum(pad[i:i + h, j:j + w] for i in range(k) for j in range(k)) / (k * k)


def canopy_pixels(img_path: Path = MOSAIC) -> np.ndarray:
    """Boolean canopy mask over the mosaic: texture + greenness, then a morphological closing."""
    from PIL import Image

    a = np.asarray(Image.open(img_path).convert('RGB')).astype(float) / 255
    r, g = a[..., 0], a[..., 1]
    mx, mn = a.max(2), a.min(2)
    d = mx - mn
    s = np.where(mx > 0, d / np.maximum(mx, 1e-9), 0)
    h = np.zeros_like(mx)
    m = d > 0
    b = a[..., 2]
    idx = m & (mx == r)
    h[idx] = ((g - b)[idx] / d[idx]) % 6
    idx = m & (mx == g)
    h[idx] = ((b - r)[idx] / d[idx]) + 2
    idx = m & (mx == b)
    h[idx] = ((r - g)[idx] / d[idx]) + 4
    h *= 60
    lum = a.mean(2)
    mu = _box(lum, 7)
    sd = np.sqrt(np.maximum(_box(lum ** 2, 7) - mu ** 2, 0))
    # z18-filled pixels (gap in the z19 mosaic) are upsampled and smooth: no texture bar and a teal-shifted hue range there
    fm = img_path.with_name(img_path.stem + '-mask.png')
    filled = np.asarray(Image.open(fm).convert('L')) > 0 if fm.exists() else np.zeros(sd.shape, bool)
    mask = (sd >= np.where(filled, 0.0, 0.035)) & (g >= r * 0.93) & (s >= 0.14) & (mx <= 0.85) & (h >= 38) & (h <= np.where(filled, 200, 140))
    dil = _box(mask.astype(float), 9) > 1e-6
    return _box(dil.astype(float), 9) > 0.999


def cover_pixels(img_path: Path = MOSAIC) -> np.ndarray:
    """Boolean vegetation-cover mask: any saturated, not-bright, green-to-olive pixel (no texture test).

    Wider than canopy_pixels on purpose: shaded woodland is dark, olive or brownish (g < r) and smooth at
    this resolution, so the crown test rejects most of it. Roofs (red, g << r), paving and tarmac (low
    saturation) and bright surfaces stay out.
    """
    from PIL import Image

    a = np.asarray(Image.open(img_path).convert('RGB')).astype(float) / 255
    r, g, b = a[..., 0], a[..., 1], a[..., 2]
    mx, mn = a.max(2), a.min(2)
    s = np.where(mx > 0, (mx - mn) / np.maximum(mx, 1e-9), 0)
    mask = (s >= 0.22) & (mx <= 0.62) & (g > b + 0.02) & (g >= r * 0.8)
    return _box(_box(mask.astype(float), 5), 5) > 0.5


def cover_grid(cell: tuple[int, int], mask: np.ndarray | None = None) -> np.ndarray:
    """128×128 [x - x0, z - z0] = fraction of cover pixels in a ~7-block window around the column."""
    tx, tz = cell
    x0, z0 = tx * 128, tz * 128
    pix = mosaic_px([(x, z) for x in range(x0, x0 + 128) for z in range(z0, z0 + 128)])
    mask = cover_pixels() if mask is None else mask
    dens = _box(mask.astype(float), 35)
    grid = np.zeros((128, 128))
    for (x, z), (px, py) in pix.items():
        ix, iy = int(px), int(py)
        if 0 <= ix < dens.shape[1] and 0 <= iy < dens.shape[0]:
            grid[x - x0, z - z0] = dens[iy, ix]
    return grid


def fill_dense(cover: np.ndarray, crowns: list[tuple[int, int, float]], seed: int = 0) -> list[tuple[int, int, float]]:
    """Extra crowns (dx, dz, r) so dense cover gets trees at a density that follows the cover fraction.

    A jittered grid at FILL_SPACING; a site is used with probability rising from 0 at COVER_MIN to 1 at
    COVER_FULL, and not within an existing crown. Deterministic for a given cell.
    """
    rnd = random.Random(RNG_SEED + seed)
    ii, jj = np.mgrid[0:128, 0:128]
    taken = np.zeros((128, 128), bool)
    for ci, cj, cr in crowns:
        taken |= (ii - ci) ** 2 + (jj - cj) ** 2 <= (cr * 0.75 + 1.5) ** 2
    extra = []
    for gi in range(0, 128, FILL_SPACING):
        for gj in range(0, 128, FILL_SPACING):
            i = min(127, max(0, gi + rnd.randint(-1, 1) + FILL_SPACING // 2))
            j = min(127, max(0, gj + rnd.randint(-1, 1) + FILL_SPACING // 2))
            p = (cover[i, j] - COVER_MIN) / (COVER_FULL - COVER_MIN)
            if rnd.random() >= p or taken[i, j]:    # rnd drawn first so sites do not shift with neighbours
                continue
            r = rnd.choice(FILL_RADII)
            extra.append((i, j, r))
            taken |= (ii - i) ** 2 + (jj - j) ** 2 <= (r * 0.75) ** 2
    return extra


def canopy_grid(cell: tuple[int, int]) -> np.ndarray:
    """128×128 array [x - x0, z - z0] = fraction of canopy pixels around that column."""
    tx, tz = cell
    x0, z0 = tx * 128, tz * 128
    cols = [(x, z) for x in range(x0, x0 + 128) for z in range(z0, z0 + 128)]
    pix = mosaic_px(cols)
    mask = canopy_pixels()
    dens = _box(mask.astype(float), 5)
    grid = np.zeros((128, 128))
    for (x, z), (px, py) in pix.items():
        ix, iy = int(px), int(py)
        if 0 <= ix < dens.shape[1] and 0 <= iy < dens.shape[0]:
            grid[x - x0, z - z0] = dens[iy, ix]
    return grid


def find_crowns(grid: np.ndarray) -> list[tuple[int, int, float]]:
    """Greedy crown packing: (dx, dz, radius) in cell-local columns, densest first."""
    smooth = _box(grid, 5)
    order = sorted(((smooth[i, j], i, j) for i in range(128) for j in range(128)
                    if smooth[i, j] >= DENSITY_MIN and grid[i, j] >= 0.5), reverse=True)
    used = np.zeros((128, 128), bool)
    ii, jj = np.mgrid[0:128, 0:128]
    crowns = []
    for _v, i, j in order:
        if used[i, j]:
            continue
        r = 1.0
        while r < MAX_CROWN_R:
            disc = (ii - i) ** 2 + (jj - j) ** 2 <= (r + 0.5) ** 2
            if grid[disc].mean() < 0.6:
                break
            r += 0.5
        r = min(MAX_CROWN_R, r)
        if r < 1.5:
            continue
        crowns.append((i, j, r))
        used |= (ii - i) ** 2 + (jj - j) ** 2 <= (r * 0.75) ** 2
    return crowns


EXTRA_CROWNS = ROOT / 'reference/trees-extra-crowns.json'


def extra_crowns(cell: tuple[int, int], path: Path | None = None) -> list[tuple[int, int, float]]:
    """Crowns the z19 mosaic cannot show, from reference/trees-extra-crowns.json: {"tx,tz": [{"x","z","r","evidence"}]}.

    Each entry is a tree read from other imagery (registered user aerial + LIDAR dome) where the mosaic shows no
    canopy. They are cell-local (dx, dz, r) like detected crowns and go through exactly the same planting rules
    (lawn surface, trunk in cell, air only, mask); only the OSM-footprint 'feature zone' skip is waived, because
    these sit where an OSM roof way was found to be a tree (I-055).
    """
    path = path or EXTRA_CROWNS
    if not path.exists():
        return []
    x0, z0 = cell[0] * 128, cell[1] * 128
    out = []
    for e in json.loads(path.read_text()).get(f'{cell[0]},{cell[1]}', []):
        i, j = int(e['x']) - x0, int(e['z']) - z0
        if 0 <= i < 128 and 0 <= j < 128:
            out.append((i, j, float(e['r'])))
    return out


def voxels_for(x: int, z: int, gy: int, r: float) -> dict:
    """Voxels for one crown: bush for small ones, plane/round tree otherwise."""
    rnd = random.Random(RNG_SEED + x * 31 + z)
    if r < MIN_CROWN_R + 0.2:
        return bush_voxels(x, z, gy)
    if r >= 6:
        h, style = rnd.choice((12, 13, 14)), 'plane'
    elif r >= 3.5:
        h, style = rnd.choice((8, 9)), 'plane'
    else:
        h, style = rnd.choice((4, 5, 6)), 'round'
    vox = tree_voxels(x, z, gy, height=h, style=style, rng=random.Random(RNG_SEED + x * 31 + z))
    # tree_voxels mottles plane trunks with birch patches; here trunks are plain oak (user, 2026-10-14)
    return {p: ('oak_log' if b == 'birch_log' else b) for p, b in vox.items()}


def plan_cell(cell: tuple[int, int], plan: Plan, world: World):
    """Plan the trees. Returns (placements, report)."""
    tx, tz = cell
    x0, z0 = tx * 128, tz * 128
    bx0, bz0, bx1, bz1 = cell_bounds(tx, tz)
    cell_xz = _InCell(bx0, bz0, bx1, bz1)
    grid = canopy_grid(cell)
    crowns = find_crowns(grid)
    n_detected = len(crowns)
    crowns = crowns + fill_dense(cover_grid(cell), crowns, seed=tx * 1000 + tz)
    extra = {(x0 + i, z0 + j) for i, j, _r in extra_crowns(cell)}
    crowns = crowns + [c for c in extra_crowns(cell) if not any((c[0] - ci) ** 2 + (c[1] - cj) ** 2 <= (cr * 0.75) ** 2
                                                                for ci, cj, cr in crowns)]
    owned = set(built_cells(exclude=ignored_builds(cell)))
    # Feature zones are the columns the ground layer did not surface (building footprints, structure
    # builds, bridges). A tree-phase tree is never rooted in one; a feature's own build may plant inside it.
    ground_file = ROOT / 'verification/site' / f"{ground_plan_name(tx, tz, 'ground')}-cells.json"
    ground_cols = ({tuple(map(int, k.split(',')))[::2] for k in json.loads(ground_file.read_text())}
                   if ground_file.exists() else None)
    masked = load_masked_positions()
    placed: dict[tuple[int, int, int], str] = {}
    report = {'candidates': len(crowns), 'detected': n_detected, 'trees': [], 'skipped': []}
    from osm_footprints import OSMIndex
    fp = {q for q in OSMIndex().cells() if x0 - 2 <= q[0] <= x0 + 129 and z0 - 2 <= q[1] <= z0 + 129}
    for i, j, r in crowns:
        x, z = x0 + i, z0 + j
        surf = surface_y(world, x, z)
        if (x, z) not in extra and ((x, z) in fp or (ground_cols is not None and (x, z) not in ground_cols)):
            report['skipped'].append((x, z, r, 'feature zone'))      # no tree-phase tree is rooted in a feature
            continue
        if not surf or surf[1] not in (LAWN_SURFACES | PAVED_SURFACES if TREES_ON_PAVING else LAWN_SURFACES):
            report['skipped'].append((x, z, r, f'surface {surf[1] if surf else None}'))
            continue
        gy = surf[0]
        vox = voxels_for(x, z, gy, r)
        kept = {p: b for p, b in vox.items()
                if may_plant(world.block(*p), b, masked.get(p)) and p not in owned and p not in placed}
        trunk = [p for p, b in vox.items() if 'log' in b]
        if any(p not in kept or p not in cell_xz for p in trunk):
            report['skipped'].append((x, z, r, 'trunk blocked'))
            continue
        if len(kept) < KEEP_FRACTION * len(vox):
            report['skipped'].append((x, z, r, f'{len(vox) - len(kept)} of {len(vox)} voxels blocked'))
            continue
        placed.update(kept)
        report['trees'].append((x, z, r, 'bush' if r < MIN_CROWN_R + 0.2 else 'tree'))
    for p, b in placed.items():
        plan.set(*p, b)
    report['overhang'] = sum(1 for p in placed if p not in cell_xz)
    return placed, report


def review_image(cell: tuple[int, int], report: dict, out: Path) -> None:
    """Planned crowns drawn over the aerial crop, for the visual check."""
    from PIL import Image, ImageDraw

    tx, tz = cell
    x0, z0 = tx * 128, tz * 128
    pts = [(x0, z0), (x0 + 127, z0), (x0, z0 + 127), (x0 + 127, z0 + 127)]
    px = mosaic_px(pts)
    xs, ys = [v[0] for v in px.values()], [v[1] for v in px.values()]
    X0, Y0, X1, Y1 = int(min(xs)) - 4, int(min(ys)) - 4, int(max(xs)) + 4, int(max(ys)) + 4
    img = Image.open(MOSAIC).convert('RGB').crop((X0, Y0, X1, Y1))
    scale = 2
    img = img.resize((img.width * scale, img.height * scale))
    d = ImageDraw.Draw(img)
    cols = [(x, z) for x, z, *_ in report['trees']] + [(x, z) for x, z, *_ in report['skipped']]
    pm = mosaic_px(cols) if cols else {}
    ppb = (px[pts[1]][0] - px[pts[0]][0]) / 127
    for x, z, r, kind in report['trees']:
        cx, cy = (pm[(x, z)][0] - X0) * scale, (pm[(x, z)][1] - Y0) * scale
        rr = r * ppb * scale
        d.ellipse((cx - rr, cy - rr, cx + rr, cy + rr), outline=(255, 0, 255) if kind == 'tree' else (0, 255, 255), width=3)
    for x, z, r, why in report['skipped']:
        cx, cy = (pm[(x, z)][0] - X0) * scale, (pm[(x, z)][1] - Y0) * scale
        d.ellipse((cx - 5, cy - 5, cx + 5, cy + 5), outline=(255, 0, 0), width=2)
    out.parent.mkdir(parents=True, exist_ok=True)
    img.save(out)


def run(cell: tuple[int, int]) -> int:
    """Dry run: plan, run the kit's guards, write the review image. Never writes the world."""
    from site_kit import apply, preview

    tx, tz = cell
    name = plan_name(tx, tz)
    plan = Plan(name)
    world = World()
    placed, rep = plan_cell(cell, plan, world)
    print(f'{name}: crowns found {rep["detected"]} + dense fill {rep["candidates"] - rep["detected"]}  planted {len(rep["trees"])} '
          f'({sum(1 for t in rep["trees"] if t[3] == "tree")} trees, '
          f'{sum(1 for t in rep["trees"] if t[3] == "bush")} bushes)  skipped {len(rep["skipped"])}  '
          f'blocks {len(placed)}  overhang past cell edge {rep["overhang"]}')
    for x, z, r, why in rep['skipped'][:25]:
        print(f'  skipped ({x},{z}) r{r:.1f}: {why}')
    img = ROOT / f'verification/site/{name}-crowns.png'
    review_image(cell, rep, img)
    print(f'  review image: {img.relative_to(ROOT)}  (magenta tree, cyan bush, red skipped)')
    (ROOT / f'verification/site/{name}-plan.json').write_text(json.dumps(
        {'trees': rep['trees'], 'skipped': rep['skipped'], 'blocks': len(placed)}, indent=1))
    preview(plan, ROOT / f'verification/site/{name}-preview.png', scale=2)
    apply(plan, dry=True, modifies=ignored_builds(cell))
    return 0


def apply_cell(cell: tuple[int, int]) -> int:
    """Live apply: lock + snapshot first, re-plan from the live world, readback, then the mask."""
    import os
    import subprocess
    from site_kit import apply, readback

    if not os.environ.get('SITE_OWNER'):
        raise SystemExit('SITE_OWNER is not set; claim the lock first (scripts/site_lock.py claim <owner> ...)')
    tx, tz = cell
    name = plan_name(tx, tz)
    plan = Plan(name)
    world = World()
    placed, rep = plan_cell(cell, plan, world)
    if not placed:
        raise SystemExit('nothing to plant; check the dry run')
    # air-only is asserted now, from the same world the plan was read from, and again here
    mask = build_mask('trees', cell, name, placed,
                      lambda p: is_air(world.block(*p)) or 'leaves' in bare(world.block(*p)))   # leaf-on-leaf merge
    print(f'{name}: {len(placed)} blocks, {len(rep["trees"])} crowns')
    subprocess.run([sys.executable, str(ROOT / 'scripts/region_backup.py'), 'snap',
                    '--bbox', cell_bbox_str(cell, OVERHANG_MARGIN), '--name', name], check=True)
    apply(plan, modifies=ignored_builds(cell), stage='trees', cell=cell)   # records 'applying' first, 'applied' after readback
    rb = readback(plan)
    print(f'readback: {rb["planned"]} planned, {rb["mismatches"]} mismatches')
    stage = ROOT / f'site/cells/{tx}_{tz}-STAGES.json'
    data = json.loads(stage.read_text()) if stage.exists() else {'cell': f'{tx},{tz}', 'stages': {}}
    ok = rb['mismatches'] == 0
    entry = {'status': 'applied' if ok else 'applied-with-mismatches', 'plan': name,
             'blocks': len(placed), 'crowns': len(rep['trees']), 'readback': rb}
    if ok:
        entry['mask'] = str(write_mask(mask).relative_to(ROOT))
    data['stages']['trees'] = entry
    stage.write_text(json.dumps(data, indent=2) + '\n', encoding='utf-8')
    return 0 if ok else 1


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--cell', required=True, help='tx,tz e.g. 48,-44')
    ap.add_argument('--apply', action='store_true', help='LIVE: needs SITE_OWNER + claimed lock')
    a = ap.parse_args()
    cell = tuple(int(v) for v in a.cell.split(','))
    return apply_cell(cell) if a.apply else run(cell)


if __name__ == '__main__':
    sys.exit(main())
