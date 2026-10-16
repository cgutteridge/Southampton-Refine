"""Refine foliage palette, strip/replace helpers, and tree massing shared by campus + cell passes.

Static log + persistent leaves only — never saplings (see site/FOLIAGE.txt).
"""
from __future__ import annotations

import random
import sys
from typing import Iterable

from surface_probe import is_tree_or_plant_block, short_id, surface_y
from site_kit import Plan, World

# Canonical block short names / property patterns refine may place above ground surfaces.
LOG_SPECIES = frozenset({'oak', 'spruce', 'birch', 'jungle', 'acacia', 'dark_oak', 'mangrove', 'cherry'})
REFINE_PLANTS = frozenset({
    'short_grass', 'tall_grass', 'fern', 'flower', 'poppy', 'dandelion', 'daisy',
    'cornflower', 'allium', 'azure_bluet', 'oxeye_daisy', 'red_tulip', 'white_tulip',
    'blue_orchid', 'orange_tulip', 'pink_tulip', 'lily_of_the_valley', 'wither_rose',
    'sunflower', 'rose_bush', 'peony', 'lilac',
})
DEFAULT_LOG = 'oak_log'
DEFAULT_LEAVES = 'oak_leaves[persistent=true]'
# Small plants + saplings (for strip); logs/leaves handled in ``is_refine_foliage``.
REFINE_FOLIAGE = REFINE_PLANTS


def is_refine_foliage(block: str) -> bool:
    """Whether a block id is part of the refine foliage allowlist (strip/replace target).

    @param block: full or short block id
    @returns: True for refine-placed logs, persistent leaves, and small plants
    """
    if not block:
        return False
    raw = block if ':' in block.split('[')[0] else f'minecraft:{block}'
    short = short_id(raw)
    if 'sapling' in short:
        return True
    if short in REFINE_PLANTS:
        return True
    if '_log' in short:
        return True
    if 'leaves' in short:
        return 'persistent=true' in raw or 'persistent=true' in block
    return False


def should_strip_above_surface(block: str) -> bool:
    """Whether to clear this block during a foliage strip pass above the ground skin.

    @param block: full block id from World
    @returns: True for refine foliage and Geocraft procedural tree/plant junk
    """
    return is_refine_foliage(block) or is_tree_or_plant_block(block)


def should_strip_corridor_canopy(block: str) -> bool:
    """Whether to clear any tree/plant voxel above path/road surfaces (canopy overhang).

    Geocraft leaves often carry ``persistent=true`` and ``distance=*`` after decay;
    they must not be treated as intentional refine foliage on footways.

    @param block: full block id from World
    @returns: True for logs, leaves, saplings, and small plants
    """
    if not block or block.endswith('air'):
        return False
    short = short_id(block)
    if 'leaves' in short or '_log' in short or 'sapling' in short:
        return True
    return short in REFINE_PLANTS


def corridor_columns_in_cell(
    area_name: str,
    cell: tuple[int, int],
    *,
    margin: int = 0,
    kinds: frozenset[str] | None = None,
) -> set[tuple[int, int]]:
    """Path/road parcel columns in a coverage cell, expanded by ``margin`` blocks.

    @param area_name: coverage area key
    @param cell: (tx, tz)
    @param margin: Chebyshev padding on the cell bbox before intersecting parcels
    @param kinds: parcel kinds to include (default path + road)
    @returns: column set
    """
    from coverage import cell_bbox, load_area

    kind_set = kinds or frozenset({'path', 'road'})
    area = load_area(area_name)
    tx, tz = cell
    x0, z0, x1, z1 = cell_bbox(tx, tz, tx, tz)
    x0 -= margin
    z0 -= margin
    x1 += margin
    z1 += margin
    out: set[tuple[int, int]] = set()
    for p in area.parcels.values():
        if p['kind'] not in kind_set:
            continue
        for x, z in p['set']:
            if x0 <= x <= x1 and z0 <= z <= z1:
                out.add((x, z))
    return out


def strip_foliage_above_surface(
    plan: Plan,
    w: World,
    columns: Iterable[tuple[int, int]],
    *,
    keep_surface: bool = True,
    y_top: int = 120,
) -> int:
    """Plan ``air`` for foliage and tree junk strictly above each column's surface.

    @param plan: plan under construction
    @param w: live world reader
    @param columns: {(x, z)}
    @param keep_surface: when True, never change the surface block itself
    @param y_top: highest Y scanned
    @returns: number of cells planned
    """
    n = 0
    for x, z in columns:
        surf = surface_y(w, x, z, top=y_top)
        if not surf:
            continue
        y0, _top = surf
        start = y0 + 1 if keep_surface else y0
        for y in range(start, y_top + 1):
            b = w.block(x, y, z) or ''
            if b.endswith('air'):
                continue
            if not should_strip_above_surface(b):
                break
            plan.set(x, y, z, 'air')
            n += 1
    return n


def strip_corridor_canopy_overhang(
    plan: Plan,
    w: World,
    corridor_columns: Iterable[tuple[int, int]],
    *,
    y_top: int = 120,
) -> int:
    """Plan ``air`` for all canopy voxels above path/road columns (full column scan).

    Runs after zone feature merge so tidy cannot leave leaf blobs over footways.
    Uses the plan state when set, otherwise the live world.

    @param plan: plan under construction
    @param w: live world reader
    @param corridor_columns: footway/road columns (may extend outside the cell)
    @param y_top: highest Y scanned
    @returns: number of cells planned
    """
    n = 0
    for x, z in corridor_columns:
        surf = surface_y(w, x, z, top=y_top)
        if not surf:
            continue
        y0, _top = surf
        for y in range(y0 + 1, y_top + 1):
            planned = plan.get(x, y, z)
            if planned is not None:
                if planned == 'air':
                    continue
                b = planned if ':' in planned.split('[')[0] else f'minecraft:{planned}'
            else:
                b = w.block(x, y, z) or ''
            if b.endswith('air'):
                continue
            if not should_strip_corridor_canopy(b):
                continue
            plan.set(x, y, z, 'air')
            n += 1
    return n


def tree_voxels(
    x: int,
    z: int,
    ground_y: int,
    height: int,
    *,
    log_block: str = DEFAULT_LOG,
    leaves_block: str = DEFAULT_LEAVES,
    skip_xz: frozenset[tuple[int, int]] | None = None,
) -> dict[tuple[int, int, int], str]:
    """Static tree massing: trunk column + small persistent leaf blob.

    @param x: trunk column X
    @param z: trunk column Z
    @param ground_y: surface Y (log starts at ground_y + 1)
    @param height: trunk height in blocks (leaves cap above)
    @param log_block: trunk block id
    @param leaves_block: leaf block id (must be persistent)
    @param skip_xz: footprint columns that must not receive leaves
    @returns: {(x, y, z): block state}
    """
    skip = skip_xz or frozenset()
    out: dict[tuple[int, int, int], str] = {}
    h = height
    for i in range(1, h):
        out[(x, ground_y + i, z)] = log_block
    for a in range(-2, 3):
        for b in range(-2, 3):
            for dy in range(h - 2, h + 2):
                if abs(a) + abs(b) + max(0, dy - h) * 2 > 3 or (a == b == 0 and dy < h):
                    continue
                q = (x + a, z + b)
                if q in skip:
                    continue
                out[(x + a, ground_y + dy, z + b)] = leaves_block
    return out


def expand_tree(
    x: int,
    z: int,
    ground_y: int,
    *,
    height: int | None = None,
    species: str = 'oak',
    rng: random.Random | None = None,
    skip_xz: frozenset[tuple[int, int]] | None = None,
) -> dict[tuple[int, int, int], str]:
    """Place one aerial/OSM-scale tree (wrapper over ``tree_voxels``).

    @param x: anchor column X
    @param z: anchor column Z
    @param ground_y: lawn surface Y
    @param height: trunk height; random 5–7 when omitted
    @param species: log/leaves species prefix
    @param rng: random source for height
    @param skip_xz: columns that must not receive leaves (footprints)
    @returns: voxel map
    """
    rnd = rng or random.Random(0)
    h = height if height is not None else rnd.choice((5, 6, 6, 7))
    log_block = f'{species}_log' if species in LOG_SPECIES else DEFAULT_LOG
    leaves = f'{species}_leaves[persistent=true]' if species in LOG_SPECIES else DEFAULT_LEAVES
    return tree_voxels(x, z, ground_y, h, log_block=log_block, leaves_block=leaves, skip_xz=skip_xz)


def plan_tree(plan: Plan, voxels: dict[tuple[int, int, int], str]) -> int:
    """Copy a voxel map into a kit plan.

    @param plan: target plan
    @param voxels: {(x, y, z): block}
    @returns: cells written
    """
    for pos, st in voxels.items():
        plan.set(*pos, st)
    return len(voxels)


def affected_parcels(
    area_name: str,
    columns: Iterable[tuple[int, int]],
    *,
    margin: int = 0,
) -> list[str]:
    """Parcel ids whose column set intersects ``columns`` (optional bbox margin expansion).

    @param area_name: coverage area key
    @param columns: {(x, z)} planned or touched
    @param margin: expand each column to a Chebyshev square before lookup (unused when 0)
    @returns: sorted parcel ids
    """
    from coverage import load_area, parcels_intersecting_columns

    cols = set(columns)
    if margin:
        expanded = set()
        for x, z in cols:
            for dx in range(-margin, margin + 1):
                for dz in range(-margin, margin + 1):
                    expanded.add((x + dx, z + dz))
        cols = expanded
    return parcels_intersecting_columns(load_area(area_name), cols)


def is_canopy_block(block: str) -> bool:
    """Whether a block id counts as tree canopy massing (log or leaves).

    @param block: full or short block id
    @returns: True for logs and leaf blocks (any persistent flag)
    """
    short = short_id(block if ':' in block.split('[')[0] else f'minecraft:{block}')
    return '_log' in short or 'leaves' in short


def canopy_audit(
    plan: Plan,
    w: World,
    columns: Iterable[tuple[int, int]],
) -> dict[str, int]:
    """Compare live canopy above surface to planned strip (air) and replant (log/leaves).

    Used before ``build_cell_foliage.py --apply`` so a strip pass cannot silently
    clear Geocraft procedural canopy without enough static replant (Q-062 lesson).

    @param plan: foliage plan after strip + features
    @param w: live world reader
    @param columns: {(x, z)} parcel scope
    @returns: counts: removed_logs, removed_leaves, added_logs, added_leaves
    """
    cols = set(columns)
    removed_logs = removed_leaves = 0
    for (x, y, z), st in plan.cells.items():
        if st != 'air':
            continue
        live = short_id(w.block(x, y, z) or 'minecraft:air')
        if 'leaves' in live:
            removed_leaves += 1
        elif '_log' in live:
            removed_logs += 1
    added_logs = added_leaves = 0
    for (x, y, z), st in plan.cells.items():
        if (x, z) not in cols:
            continue
        short = short_id(st)
        if short == 'air':
            continue
        if 'leaves' in short:
            added_leaves += 1
        elif '_log' in short:
            added_logs += 1
    return {
        'removed_logs': removed_logs,
        'removed_leaves': removed_leaves,
        'added_logs': added_logs,
        'added_leaves': added_leaves,
    }


def format_canopy_audit(audit: dict[str, int], *, campus: bool) -> str:
    """Human-readable summary line for dry-run output.

    @param audit: ``canopy_audit`` result
    @param campus: HIGHFIELD grounds zones intersect the cell
    @returns: one line of text
    """
    rem = audit['removed_leaves'] + audit['removed_logs']
    add = audit['added_leaves'] + audit['added_logs']
    ratio = (add / rem) if rem else 1.0
    tag = 'campus' if campus else 'radial'
    return (
        f'canopy audit ({tag}): strip {audit["removed_leaves"]} leaves + '
        f'{audit["removed_logs"]} logs → replant {audit["added_leaves"]} leaves + '
        f'{audit["added_logs"]} logs (replant/strip={ratio:.2f})'
    )


def assert_canopy_replant_ok(
    audit: dict[str, int],
    *,
    campus: bool,
    accept_loss: bool,
    min_strip: int = 40,
) -> None:
    """Refuse apply when a large strip would leave lawns visually bare.

    @param audit: ``canopy_audit`` result
    @param campus: stricter ratio when ``build_highfield_grounds_cell`` zones apply
    @param accept_loss: user passed ``--accept-canopy-loss`` on the CLI
    @param min_strip: only enforce when at least this many canopy voxels would be aired
    @raises SystemExit: when replant is too sparse and ``accept_loss`` is False
    """
    rem_leaves = audit['removed_leaves']
    rem_total = rem_leaves + audit['removed_logs']
    if rem_total < min_strip:
        return
    added = audit['added_leaves'] + audit['added_logs']
    ratio = added / rem_total if rem_total else 1.0
    min_ratio = 0.55 if campus else 0.35
    if ratio >= min_ratio:
        return
    if accept_loss:
        print(
            f'WARNING: canopy replant/strip ratio {ratio:.2f} < {min_ratio} '
            f'(--accept-canopy-loss override)',
            file=sys.stderr,
        )
        return
    raise SystemExit(
        f'Foliage plan would strip {rem_total} canopy voxels but only replant {added} '
        f'(ratio {ratio:.2f}; need >={min_ratio} for {"campus" if campus else "radial"}). '
        f'Lawns will look bare. Dry-run preview + fix GroundsTidy/evidence, or pass '
        f'--accept-canopy-loss only after deliberate review. Restore: '
        f'restore_structure_backup.py <build> --apply',
    )


def plan_columns_xz(plan: Plan) -> set[tuple[int, int]]:
    """Horizontal columns touched by a plan.

    @param plan: kit plan
    @returns: {(x, z)}
    """
    return {(x, z) for x, _y, z in plan.cells}
