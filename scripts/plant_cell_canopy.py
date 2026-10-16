#!/usr/bin/env python3
"""Plant aerial-driven trees and bushes on open/gap lawn in one coverage cell (z19 crown blobs).

Runs AFTER build_cell_foliage.py (strip + zone features). Crowns are read from the local
z19 mosaic (reference/aerial/highfield-z19/mosaic-z19-4x4-260107-175667.png), not z18:

  1. Canopy mask: green hue with enough saturation (lawn is low-saturation tan).
  2. Connected blobs of canopy pixels; each blob centroid is a tree anchor.
  3. Crown radius = blob radius in blocks (clamped), so large crowns get large trees.
  4. Very small blobs become a low bush clump instead.

Anchors must sit on a live grass_block lawn column, keep crown + CORRIDOR_PAD blocks
clear of path/road columns, and every planned voxel must be air or plant life, with no
voxel already owned by another build.

  python3 scripts/plant_cell_canopy.py --cell 48,-45 --mask-only   # mask overlay only
  python3 scripts/plant_cell_canopy.py --cell 48,-45               # dry-run + preview
  SITE_OWNER=<lock-owner> python3 scripts/plant_cell_canopy.py --cell 48,-45 --apply
"""
from __future__ import annotations

import argparse
import colorsys
import json
import math
import random
import subprocess
import sys
from collections import deque
from pathlib import Path

from script_env import ROOT  # noqa: E402

from foliage import corridor_columns_in_cell  # noqa: E402
from surface_probe import short_id, surface_y  # noqa: E402


from cellmath import parse_cell  # noqa: E402,F401
import cellmath  # noqa: E402


def parcels_in_cell(*_a, **_k):
    """Retired with build_cell_foliage.py; the parcel canopy pass no longer runs."""
    raise SystemExit('plant_cell_canopy parcel passes are retired; use trees_layer.py')


def columns_for_parcels(*_a, **_k):
    """Retired with the old ground tooling (ground_top_block); the parcel canopy pass no longer runs."""
    raise SystemExit('plant_cell_canopy parcel passes are retired; use trees_layer.py')
from osgb import to_osgb  # noqa: E402
from site_kit import OUT, Plan, World, apply, preview  # noqa: E402

DEFAULT_AREA = 'highfield'
MOSAIC = ROOT / 'reference/aerial/highfield-z19/mosaic-z19-18x17-260101-175662-eastext6.png'
MOSAIC_TILE0 = (260101, 175662)  # z19 tile x,y of the mosaic's top-left corner
ZOOM = 19
TILE = 256
HUE_LO, HUE_HI = 45 / 360, 110 / 360  # olive through green
SAT_MIN = 0.25
VAL_LO, VAL_HI = 0.15, 0.50  # crowns are darker than pale lawn
MIN_BLOB_PX = 14
CROWN_MIN, CROWN_MAX = 2.5, 9.0  # blocks
CORRIDOR_PAD = 1
LEAVES = 'oak_leaves[persistent=true]'
LOG = 'oak_log'
RNG_SEED = 48045
CANOPY_PLAN_PREFIX = 'highfield_48_m45_canopy'
CLEAR_OK_SHORT = frozenset({'air', 'cave_air', 'void_air'})
CLEAR_OK_WORDS = (
    'grass', 'fern', 'leaves', 'oak_log', 'poppy', 'dandelion', 'tulip', 'orchid', 'allium',
    'azure_bluet', 'oxeye_daisy', 'cornflower', 'lily_of_the_valley',
)


def is_canopy(rgb: tuple[int, int, int]) -> bool:
    """Green crown pixel: hue band with saturation, not pale lawn or pavement.

    @param rgb: aerial colour
    @returns: True for crown-coloured pixels
    """
    h, s, v = colorsys.rgb_to_hsv(*(c / 255 for c in rgb))
    return HUE_LO <= h <= HUE_HI and s >= SAT_MIN and VAL_LO <= v <= VAL_HI


def blobs_of(mask: set[tuple[int, int]]) -> list[list[tuple[int, int]]]:
    """4-connected components of mask pixels (BFS; no scipy in the venv).

    @param mask: set of (px, py)
    @returns: list of pixel lists, one per blob
    """
    seen: set[tuple[int, int]] = set()
    out = []
    for start in mask:
        if start in seen:
            continue
        comp = []
        q = deque([start])
        seen.add(start)
        while q:
            p = q.popleft()
            comp.append(p)
            x, y = p
            for n in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
                if n in mask and n not in seen:
                    seen.add(n)
                    q.append(n)
        out.append(comp)
    return out


def mosaic_px(pts: list[tuple[int, int]]) -> dict[tuple[int, int], tuple[float, float]]:
    """Map MC column centres to mosaic pixel coordinates (one gdaltransform call).

    @param pts: (x, z) columns
    @returns: {(x, z): (px, py)}
    """
    inp = ''.join('%f %f\n' % to_osgb(x + 0.5, z + 0.5) for x, z in pts)
    out = [
        ln for ln in subprocess.run(
            ['gdaltransform', '-s_srs', 'EPSG:27700', '-t_srs', 'EPSG:4326'],
            input=inp.encode(), capture_output=True, check=True, timeout=300,
        ).stdout.decode().split('\n') if ln.strip()
    ]
    n = 2 ** ZOOM * TILE
    res = {}
    for p, ln in zip(pts, out):
        lon, lat = map(float, ln.split()[:2])
        X = (lon + 180) / 360 * n - MOSAIC_TILE0[0] * TILE
        Y = (1 - math.log(math.tan(math.radians(lat)) + 1 / math.cos(math.radians(lat))) / math.pi) / 2 * n - MOSAIC_TILE0[1] * TILE
        res[p] = (X, Y)
    return res


def px_per_block(lat: float) -> float:
    """Mosaic pixels per Minecraft block (1 block ~ 1 m) at zoom 19.

    @param lat: latitude in degrees
    @returns: pixels per metre
    """
    return TILE * math.cos(math.radians(lat)) * 2 ** ZOOM / 40075016.7


def cell_bounds(cell: tuple[int, int]) -> tuple[int, int, int, int]:
    """MC block bounds (inclusive x0,z0 .. x1,z1) of a coverage cell."""
    return cellmath.bounds(cell)


def read_mask(cell: tuple[int, int]):
    """Canopy mask over the cell's columns, from the z19 mosaic.

    @param cell: (tx, tz)
    @returns: (image, {(x,z): (px,py)}, mask set of (px,py))
    """
    from PIL import Image

    img = Image.open(MOSAIC).convert('RGB')
    x0, z0, x1, z1 = cell_bounds(cell)
    cols = [(x, z) for x in range(x0, x1 + 1) for z in range(z0, z1 + 1)]
    pix = mosaic_px(cols)
    mask = set()
    for px, py in pix.values():
        ix, iy = int(px), int(py)
        if 0 <= ix < img.width and 0 <= iy < img.height and is_canopy(img.getpixel((ix, iy))):
            mask.add((ix, iy))
    return img, pix, mask


def crown_voxels(x: int, z: int, ground_y: int, trunk: int, r: float) -> dict[tuple[int, int, int], str]:
    """Trunk plus a rounded crown (sphere of radius r) on top.

    @param x: trunk X
    @param z: trunk Z
    @param ground_y: lawn surface Y
    @param trunk: trunk height in blocks
    @param r: crown radius in blocks
    @returns: voxel map
    """
    out: dict[tuple[int, int, int], str] = {}
    for i in range(1, trunk + 1):
        out[(x, ground_y + i, z)] = LOG
    cy = ground_y + trunk
    R = max(2, round(r))
    for dx in range(-R, R + 1):
        for dz in range(-R, R + 1):
            for dy in range(-R + 1, R):
                if dx * dx + dz * dz + dy * dy <= r * r + 0.5:
                    p = (x + dx, cy + dy, z + dz)
                    if p[1] <= ground_y:
                        continue
                    if p[1] > ground_y + trunk or (dx or dz):
                        out.setdefault(p, LEAVES)
    return out


SPECIES = {
    'oak': ('oak_log', 'oak_leaves[persistent=true]'),
    'birch': ('birch_log', 'birch_leaves[persistent=true]'),
    'spruce': ('spruce_log', 'spruce_leaves[persistent=true]'),
    'dark_oak': ('dark_oak_log', 'dark_oak_leaves[persistent=true]'),
    'cherry': ('cherry_log', 'cherry_leaves[persistent=true]'),
    'acacia': ('acacia_log', 'acacia_leaves[persistent=true]'),
}
PLANE_SPECIES = 'oak'  # leaves; trunk is mottled oak with birch patches (see tree_voxels)


def tree_voxels(x: int, z: int, ground_y: int, *, height: int | None = None,
                species: str | None = None, style: str | None = None,
                rng: random.Random | None = None) -> dict[tuple[int, int, int], str]:
    """Parameterised tree: height, species (optional), style.

    @param x: trunk X
    @param z: trunk Z
    @param ground_y: surface Y under the trunk
    @param height: trunk height in blocks; default picked by style
    @param species: key of SPECIES; default by style (oak round, birch plane)
    @param style: 'round' (sphere crown) or 'plane' (English plane: tall clean trunk, open
        irregular crown of overlapping lobes high up); default 'plane' when height >= 8
    @param rng: random source for lobes
    @returns: voxel map
    """
    rnd = rng or random.Random(x * 73856093 ^ z * 19349663)
    if style is None:
        style = 'plane' if (height is None or height >= 8) else 'round'
    if height is None:
        height = rnd.choice((9, 10, 11)) if style == 'plane' else rnd.choice((4, 5, 6))
    if species is None:
        species = PLANE_SPECIES if style == 'plane' else 'oak'
    log, leaves = SPECIES[species]
    out: dict[tuple[int, int, int], str] = {}
    for i in range(1, height + 1):
        block = log
        if style == 'plane' and species == PLANE_SPECIES:
            # plane bark is mottled: oak base with pale birch patches
            block = 'birch_log' if (i * 7 + x * 3 + z * 5) % 4 == 0 else 'oak_log'
        out[(x, ground_y + i, z)] = block
    if style == 'round':
        r = 3.0 if height <= 6 else 4.0
        cy = ground_y + height
        for dx in range(-4, 5):
            for dz in range(-4, 5):
                for dy in range(-3, 3):
                    if dx * dx + dz * dz + dy * dy <= r * r + 0.5 and (dx or dz or dy >= 0):
                        p = (x + dx, cy + dy, z + dz)
                        if p[1] > ground_y and p not in out:
                            out[p] = leaves
        return out
    # plane: crown high up, several overlapping lobes (irregular, open underneath)
    top = ground_y + height
    lobes = [(0, 0, 0, 3.2)]
    for _ in range(rnd.randint(4, 6)):
        ang = rnd.uniform(0, 6.283)
        dist = rnd.uniform(1.5, 3.8)
        lobes.append((round(dist * math.cos(ang)), round(dist * math.sin(ang)), rnd.randint(-1, 1), rnd.uniform(2.0, 3.0)))
    for lx, lz, ly, lr in lobes:
        for dx in range(-5, 6):
            for dz in range(-5, 6):
                for dy in range(-2, 3):
                    if (dx - lx) ** 2 + (dz - lz) ** 2 + (dy * 1.3) ** 2 <= lr * lr:
                        p = (x + dx, top + ly + dy, z + dz)
                        if p[1] > ground_y + height // 2 and p not in out:
                            out[p] = leaves
    return out


def bush_voxels(x: int, z: int, ground_y: int) -> dict[tuple[int, int, int], str]:
    """Low leaf clump on the lawn (no trunk).

    @param x: centre X
    @param z: centre Z
    @param ground_y: lawn surface Y
    @returns: voxel map
    """
    out = {(x, ground_y + 1, z): LEAVES, (x, ground_y + 2, z): LEAVES}
    for dx, dz in ((1, 0), (-1, 0), (0, 1), (0, -1)):
        out[(x + dx, ground_y + 1, z + dz)] = LEAVES
    return out


def volume_clear(w: World, voxels: dict, ground_y: int, taken: set) -> bool:
    """Every voxel above the lawn must be air or plant life and not owned by another build.

    @param w: live world reader
    @param voxels: planned voxels for one tree or bush
    @param ground_y: lawn surface Y
    @param taken: voxels owned by other builds
    @returns: True when the volume is free to plant into
    """
    for (x, y, z) in voxels:
        if y <= ground_y:
            continue
        if (x, y, z) in taken:
            return False
        s = short_id(w.block(x, y, z))
        if s in CLEAR_OK_SHORT or any(k in s for k in CLEAR_OK_WORDS):
            continue
        return False
    return True


def owned_cells() -> set:
    """Voxels already planned by other builds (every verification/site/*-cells.json).

    @returns: set of (x, y, z) owned elsewhere
    """
    taken = set()
    for f in (ROOT / 'verification/site').glob('*-cells.json'):
        if f.name.startswith(CANOPY_PLAN_PREFIX):
            continue
        for k in json.loads(f.read_text()):
            taken.add(tuple(int(v) for v in k.strip('()').split(',')))
    return taken


def near_corridor(x: int, z: int, corridors: set, reach: int) -> bool:
    """Whether any path/road column lies within reach (Chebyshev) of (x, z).

    @param x: column X
    @param z: column Z
    @param corridors: path/road columns
    @param reach: blocks to check around the anchor
    @returns: True when a footway or road is too close
    """
    return any(
        (x + dx, z + dz) in corridors
        for dx in range(-reach, reach + 1)
        for dz in range(-reach, reach + 1)
    )


# Hand-read crown centres from the gridded z19 crop (display px, 1994 wide view):
# x: 6144 at px 33, 14.8 px per block; z: -5760 at py 20, 14.87 px per block.
# (xd, yd, r_display). Filtered by lawn / corridor / volume checks at plan time.
HAND_CROWNS = [
    (880, 880, 110), (1010, 990, 110),        # big central crown
    (1290, 1050, 90), (1440, 1010, 100), (1600, 1060, 100),   # east mass
    (1540, 1250, 110), (1690, 1350, 110),     # south-east mass
    (1330, 1400, 75), (1245, 1355, 45), (1180, 1490, 55), (1120, 1620, 60),
    (1255, 1690, 110), (1095, 1720, 40), (1510, 1600, 40), (1690, 1700, 60), (1490, 1740, 40),
    (450, 800, 45), (520, 830, 35), (1100, 835, 40),   # west and north-west clumps
    (30, 1010, 70),                           # far-left edge cluster (left of lawn)
    (555, 600, 30), (650, 650, 35), (760, 690, 25), (560, 920, 25),  # paving-edge crowns left of lawn
]
DISP_X0, DISP_X_PER_BLOCK = 33, 14.8
DISP_Z0, DISP_Z_PER_BLOCK = 20, 14.87
DISP_TO_BLOCK_R = 1 / 14.8


def hand_anchors() -> list[tuple[int, int, float]]:
    """Convert hand-read crown centres to (x, z, radius_blocks) columns.

    @returns: list of anchors, radius clamped to the planter's crown range
    """
    out = []
    x0, _, _, _ = cell_bounds((48, -45))
    for xd, yd, rd in HAND_CROWNS:
        x = round(x0 + (xd - DISP_X0) / DISP_X_PER_BLOCK)
        z = round(-5760 + (yd - DISP_Z0) / DISP_Z_PER_BLOCK)
        r = min(CROWN_MAX, max(1.5, rd * DISP_TO_BLOCK_R))
        out.append((x, z, r))
    return out


def build_plan(area: str, cell: tuple[int, int], kinds: tuple[str, ...]):
    """Plan crowns for lawn columns in one cell.

    @param area: coverage area
    @param cell: (tx, tz)
    @param kinds: parcel kinds, e.g. open,gap
    @returns: (plan, trees list of (x, z, r), bushes list of (x, z), img, mask)
    """
    img, pix, mask = read_mask(cell)
    pids = parcels_in_cell(area, cell, kinds)
    lawn = columns_for_parcels(area, pids)
    corridors = set(corridor_columns_in_cell(area, cell, margin=0))
    ppm = px_per_block(50.9)
    # Blob per canopy pixel group; keep blobs whose centroid falls on lawn.
    px_to_cols: dict[tuple[int, int], list] = {}
    for (x, z), (px, py) in pix.items():
        px_to_cols.setdefault((int(px), int(py)), []).append((x, z))
    blobs = [b for b in blobs_of(mask) if len(b) >= MIN_BLOB_PX]
    rnd = random.Random(RNG_SEED)
    w = World()
    taken = owned_cells()
    plan = Plan(CANOPY_PLAN_PREFIX)
    trees, bushes = [], []
    for blob in sorted(blobs, key=len, reverse=True):
        cx = sum(p[0] for p in blob) / len(blob)
        cy = sum(p[1] for p in blob) / len(blob)
        # Nearest lawn column to the blob centroid.
        best = None
        for (x, z), (px, py) in pix.items():
            if (x, z) not in lawn:
                continue
            d = (px - cx) ** 2 + (py - cy) ** 2
            if best is None or d < best[0]:
                best = (d, (x, z))
        if best is None or best[0] > (ppm * 4) ** 2:
            continue
        x, z = best[1]
        surf = surface_y(w, x, z)
        if not surf or short_id(surf[1]) != 'grass_block':
            continue
        gy = surf[0]
        r_blocks = math.sqrt(len(blob) / math.pi) / ppm
        if r_blocks < 1.5:
            voxels = bush_voxels(x, z, gy)
            if near_corridor(x, z, corridors, 2) or any(max(abs(x - a), abs(z - b)) < 3 for a, b in bushes):
                continue
            if not volume_clear(w, voxels, gy, taken):
                continue
            bushes.append((x, z))
        else:
            r = min(CROWN_MAX, max(CROWN_MIN, r_blocks))
            trunk = rnd.choice((4, 5, 5, 6))
            if near_corridor(x, z, corridors, int(math.ceil(r)) + CORRIDOR_PAD):
                continue
            if any(max(abs(x - a), abs(z - b)) < (r + rr) * 0.8 for a, b, rr in trees):
                continue
            voxels = crown_voxels(x, z, gy, trunk, r)
            if not volume_clear(w, voxels, gy, taken):
                continue
            trees.append((x, z, r))
        for pos, st in voxels.items():
            plan.set(*pos, st)
    return plan, trees, bushes, img, mask, pix, lawn


def plan_hand(area: str, cell: tuple[int, int], kinds: tuple[str, ...]):
    """Plan hand-read crowns: lawn surface, corridor clearance, clear volume, no overlap.

    @param area: coverage area
    @param cell: (tx, tz)
    @param kinds: parcel kinds
    @returns: (plan, placed trees (x,z,r), placed bushes (x,z), skipped list of (x,z,why))
    """
    pids = parcels_in_cell(area, cell, kinds)
    lawn = columns_for_parcels(area, pids)
    corridors = set(corridor_columns_in_cell(area, cell, margin=0))
    w = World()
    taken = owned_cells()
    plan = Plan(CANOPY_PLAN_PREFIX)
    trees, bushes, skipped = [], [], []
    for x, z, r in hand_anchors():
        surf = surface_y(w, x, z)
        if not surf:
            skipped.append((x, z, 'no ground')); continue
        gy = surf[0]
        if r < 2.0:
            if any(max(abs(x - a), abs(z - b)) < 3 for a, b in bushes):
                skipped.append((x, z, 'bush spacing')); continue
            voxels = bush_voxels(x, z, gy)
            if not volume_clear(w, voxels, gy, taken):
                skipped.append((x, z, 'volume not clear')); continue
            bushes.append((x, z))
        else:
            if any(max(abs(x - a), abs(z - b)) < (r + rr) * 0.8 for a, b, rr in trees):
                skipped.append((x, z, 'overlaps tree')); continue
            rr_ = random.Random(RNG_SEED + x * 31 + z)
            if r >= 6:
                h_, st_ = rr_.choice((12, 13, 14)), 'plane'
            elif r >= 3.5:
                h_, st_ = rr_.choice((8, 9)), 'plane'
            else:
                h_, st_ = rr_.choice((4, 5, 6)), 'round'
            voxels = None
            for hh in range(h_, 5, -2):  # step down until the crown clears overhead structure
                cand = tree_voxels(x, z, gy, height=hh, style=st_, rng=random.Random(RNG_SEED + x * 31 + z))
                if volume_clear(w, cand, gy, taken):
                    voxels = cand; h_ = hh; break
            if voxels is None:
                skipped.append((x, z, 'volume not clear at any height')); continue
            trees.append((x, z, r))
        for pos, st in voxels.items():
            plan.set(*pos, st)
    return plan, trees, bushes, skipped


def write_mask_overlay(img, pix, mask, cell, out_png: Path):
    """Save the z19 crop with canopy pixels tinted, for review.

    @param img: mosaic image
    @param pix: {(x,z): (px,py)}
    @param mask: canopy pixel set
    @param cell: (tx, tz)
    @param out_png: destination
    """
    from PIL import Image

    xs = [p[0] for p in pix.values()]
    ys = [p[1] for p in pix.values()]
    x0, x1 = int(min(xs)) - 4, int(max(xs)) + 4
    y0, y1 = int(min(ys)) - 4, int(max(ys)) + 4
    crop = img.crop((x0, y0, x1, y1)).convert('RGBA')
    tint = Image.new('RGBA', crop.size, (0, 0, 0, 0))
    px = tint.load()
    for ix, iy in mask:
        if x0 <= ix < x1 and y0 <= iy < y1:
            px[ix - x0, iy - y0] = (255, 0, 255, 170)
    Image.alpha_composite(crop, tint).resize((crop.width * 3, crop.height * 3), Image.NEAREST).convert('RGB').save(out_png)


if __name__ == '__main__':
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--area', default=DEFAULT_AREA)
    ap.add_argument('--cell', required=True)
    ap.add_argument('--kinds', default='open,gap')
    ap.add_argument('--mask-only', action='store_true')
    ap.add_argument('--apply', action='store_true')
    ap.add_argument('--skip-preview', action='store_true')
    args = ap.parse_args()
    cell = parse_cell(args.cell)
    kinds = tuple(k.strip() for k in args.kinds.split(',') if k.strip())
    scratch = ROOT / 'verification/site'
    if args.mask_only:
        img, pix, mask = read_mask(cell)
        out = scratch / f'{CANOPY_PLAN_PREFIX}-mask.png'
        write_mask_overlay(img, pix, mask, cell, out)
        print(f'mask pixels {len(mask)} -> {out}')
        raise SystemExit(0)
    plan, trees, bushes, skipped = plan_hand(args.area, cell, kinds)
    print(f'{plan.name}: trees {len(trees)} bushes {len(bushes)} cells {len(plan.cells)}')
    for x, z, why in skipped:
        print(f'  skipped ({x},{z}): {why}')
    if not trees and not bushes:
        raise SystemExit('no canopy anchors found; check the mask overlay before applying')
    if not args.skip_preview:
        preview(plan, scratch / f'{plan.name}-preview.png', scale=2)
    backup = OUT / f'{plan.name}-backup.json'
    if args.apply and backup.exists():
        raise SystemExit(f'{backup.name} exists; restore it before re-applying')
    apply(plan, dry=not args.apply, modifies=())
