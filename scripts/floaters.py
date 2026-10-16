"""Offline floater / attachable glitch detection over saved region files."""
from __future__ import annotations

import re
from collections import deque
from typing import Callable

from site_kit import ATTACH, bid
from site_walk import solid

_FACING = {'north': (0, -1), 'south': (0, 1), 'east': (1, 0), 'west': (-1, 0)}
_AIR = frozenset({'minecraft:air', 'minecraft:cave_air', 'minecraft:void_air', 'minecraft:light'})
_NEIGH6 = ((1, 0, 0), (-1, 0, 0), (0, 1, 0), (0, -1, 0), (0, 0, 1), (0, 0, -1))
_SKIP_UNSUPPORTED = (
    'leaves', 'vine', 'ladder', 'scaffolding', 'chain', 'pane', 'torch', 'sign', 'button',
    'carpet', 'rail', 'door', 'trapdoor', 'sapling', 'grass', 'fern', 'flower', 'crop',
    'stem', 'mushroom', 'kelp', 'seagrass', 'coral', 'banner', 'rod', 'candle', 'campfire',
    'pressure_plate', 'tripwire', 'snow', 'ice',
)


def prop(st: str, key: str) -> str | None:
    """Read a block-state property value.

    @param st: block state string
    @param key: property name
    @returns: value or None
    """
    m = re.search(rf'{key}=(\w+)', st)
    return m.group(1) if m else None


def is_air(st: str | None) -> bool:
    """True for empty / non-structural air variants.

    @param st: block state or None
    @returns: whether the cell counts as air for volume stats
    """
    if st is None:
        return True
    return bid(st) in _AIR


def _short_name(st: str) -> str:
    return bid(st)[10:]


def _is_attachable_name(n: str) -> bool:
    return any(k in n for k in ATTACH)


def _is_leaves_name(n: str) -> bool:
    """@param n: block short name
    @returns: True for leaf blocks
    """
    return 'leaves' in n


def _is_log_name(n: str) -> bool:
    """@param n: block short name
    @returns: True for log blocks
    """
    return '_log' in n


def leaves_connected_to_log(
    block_at: Callable[[int, int, int], str | None],
    x: int,
    y: int,
    z: int,
    *,
    max_dist: int = 6,
) -> bool:
    """Whether a leaf block reaches a log through leaves/log within ``max_dist`` steps.

    @param block_at: ``(x, y, z) -> block state`` reader
    @param x: block X
    @param y: block Y
    @param z: block Z
    @param max_dist: BFS edge limit (Minecraft decay distance is 7)
    @returns: True if any log is reachable through foliage
    """
    start = block_at(x, y, z)
    if not start or not _is_leaves_name(_short_name(start)):
        return False
    seen: set[tuple[int, int, int]] = {(x, y, z)}
    q: deque[tuple[int, int, int, int]] = deque([(x, y, z, 0)])
    while q:
        cx, cy, cz, d = q.popleft()
        st = block_at(cx, cy, cz) or ''
        n = _short_name(st)
        if _is_log_name(n):
            return True
        if d >= max_dist:
            continue
        for dx, dy, dz in _NEIGH6:
            nx, ny, nz = cx + dx, cy + dy, cz + dz
            if (nx, ny, nz) in seen:
                continue
            ns = block_at(nx, ny, nz) or ''
            nn = _short_name(ns)
            if _is_leaves_name(nn) or _is_log_name(nn):
                seen.add((nx, ny, nz))
                q.append((nx, ny, nz, d + 1))
    return False


def floating_leaves(
    block_at: Callable[[int, int, int], str | None],
    x: int,
    y: int,
    z: int,
    st: str,
    *,
    owner: str | None = None,
    max_log_dist: int = 6,
) -> dict | None:
    """Leaf blocks with no nearby log (Geocraft canopy remnants, not hedges on walls).

    Hedges and single-layer leaves on brick/fence are kept (solid non-leaf support below).

    @param block_at: ``(x, y, z) -> block state`` reader
    @param x: block X
    @param y: block Y
    @param z: block Z
    @param st: block state at the position
    @param owner: optional build name for reports
    @param max_log_dist: log search radius through foliage
    @returns: finding dict or None
    """
    n = _short_name(st)
    if not _is_leaves_name(n):
        return None
    if leaves_connected_to_log(block_at, x, y, z, max_dist=max_log_dist):
        return None
    below = block_at(x, y - 1, z) or ''
    bn = _short_name(below)
    if solid(below) and not _is_leaves_name(bn):
        return None
    row: dict = {
        'kind': 'floating_leaves',
        'why': f'leaves with no log within {max_log_dist} blocks (no trunk)',
        'pos': [x, y, z],
        'block': n,
    }
    if owner:
        row['owner'] = owner
    return row


def _skip_structural_scan(n: str) -> bool:
    if not solid(f'minecraft:{n}' if ':' not in n else n.split('[')[0]):
        return True
    if _is_attachable_name(n):
        return True
    return any(k in n for k in _SKIP_UNSUPPORTED)


def cell_glitches(
    block_at: Callable[[int, int, int], str | None],
    x: int,
    y: int,
    z: int,
    st: str,
    *,
    owner: str | None = None,
) -> list[dict]:
    """Patrol-style attachable / door glitches at one position.

    @param block_at: ``(x, y, z) -> block state`` reader
    @param x: block X
    @param y: block Y
    @param z: block Z
    @param st: block state at the position
    @param owner: optional build name for reports
    @returns: list of finding dicts with keys ``kind``, ``why``, ``pos``, ``block``, optional ``owner``
    """
    n = _short_name(st)
    below = block_at(x, y - 1, z) or ''
    above = block_at(x, y + 1, z) or ''
    out: list[dict] = []

    def rec(kind: str, why: str) -> None:
        row: dict = {'kind': kind, 'why': why, 'pos': [x, y, z], 'block': n}
        if owner:
            row['owner'] = owner
        out.append(row)

    if n in ('lantern', 'soul_lantern'):
        if prop(st, 'hanging') == 'true' and not solid(above) and 'chain' not in above:
            rec('floating', 'hanging lantern with nothing above')
        if prop(st, 'hanging') == 'false' and not solid(below) and not below.split('[')[0].endswith(('_fence', '_wall')):
            rec('floating', 'standing lantern with nothing below')
    elif n.endswith('_wall_sign') or n.endswith('wall_torch'):
        f = prop(st, 'facing')
        if f in _FACING:
            dx, dz = _FACING[f]
            if not solid(block_at(x - dx, y, z - dz)):
                rec('floating', 'wall sign/torch with no block behind')
    elif (n.endswith('_sign') and 'hanging' not in n) or n == 'torch':
        if not solid(below) and not bid(below).endswith(('_fence', '_wall')):
            rec('floating', 'standing sign/torch with nothing below')
    elif n.endswith('_door'):
        half = prop(st, 'half')
        if half == 'lower' and not bid(above).endswith('_door'):
            rec('broken_bed_or_door', 'door lower half without upper')
        if half == 'upper' and not bid(below).endswith('_door'):
            rec('broken_bed_or_door', 'door upper half without lower')
        if half == 'lower':
            f = prop(st, 'facing')
            if f in _FACING:
                dx, dz = _FACING[f]

                def wall(b: str | None) -> bool:
                    return solid(b) and not bid(b or '').endswith('_trapdoor')

                a = wall(block_at(x + dx, y, z + dz)) or wall(block_at(x + dx, y + 1, z + dz))
                b = wall(block_at(x - dx, y, z - dz)) or wall(block_at(x - dx, y + 1, z - dz))
                if a or b:
                    rec('door_to_wall', 'door opens onto a solid block')
    elif n.endswith('_bed'):
        f, part = prop(st, 'facing'), prop(st, 'part')
        if f in _FACING:
            dx, dz = _FACING[f]
            ox, oz = (x + dx, z + dz) if part == 'foot' else (x - dx, z - dz)
            if not bid(block_at(ox, y, oz) or '').endswith('_bed'):
                rec('broken_bed_or_door', 'bed missing its other half')
    elif n in ('rail', 'powered_rail') or n.endswith('_carpet'):
        if not solid(below):
            rec('floating', f'{n} with nothing below')
    if (n.endswith(('_fence', '_wall')) or n == 'iron_bars') and 'gate' not in n:
        if ('_slab' in below and 'type=bottom' in below) or bid(below).endswith('_carpet'):
            rec('post_on_half_block', 'post floats over a half-height block')
    return out


def unsupported_mass(
    block_at: Callable[[int, int, int], str | None],
    x: int,
    y: int,
    z: int,
    st: str,
    *,
    y_min: int,
    depth: int = 10,
) -> dict | None:
    """Solid block with no solid support within ``depth`` blocks downward.

    Only looks straight down (fast heuristic). Stops at ``y_min``; hits there
    without finding support yield ``hit_scan_floor``.

    @param block_at: ``(x, y, z) -> block state`` reader
    @param x: block X
    @param y: block Y
    @param z: block Z
    @param st: block state at the position
    @param y_min: lowest Y included in the scan box (inclusive)
    @param depth: max blocks to search downward
    @returns: finding dict or None
    """
    if is_air(st):
        return None
    n = _short_name(st)
    if _skip_structural_scan(n):
        return None
    for dy in range(1, depth + 1):
        yb = y - dy
        if yb < y_min:
            return {
                'kind': 'unsupported',
                'why': f'no solid within {depth} blocks down (scan Y floor at y={y_min})',
                'pos': [x, y, z],
                'block': n,
                'hit_scan_floor': True,
            }
        if solid(block_at(x, yb, z)):
            return None
    return {
        'kind': 'unsupported',
        'why': f'no solid within {depth} blocks down',
        'pos': [x, y, z],
        'block': n,
        'hit_scan_floor': False,
    }


def scan_box(
    block_at: Callable[[int, int, int], str | None],
    x0: int,
    y0: int,
    z0: int,
    x1: int,
    y1: int,
    z1: int,
    *,
    depth: int = 10,
    attachables: bool = True,
    structural: bool = True,
    foliage: bool = True,
    max_log_dist: int = 6,
) -> dict:
    """Scan an axis-aligned box for air volume and floaters.

    @param block_at: ``(x, y, z) -> block state`` reader
    @param x0: min X (inclusive)
    @param y0: min Y (inclusive)
    @param z0: min Z (inclusive)
    @param x1: max X (inclusive)
    @param y1: max Y (inclusive)
    @param z1: max Z (inclusive)
    @param depth: downward search limit for unsupported mass
    @param attachables: run patrol-style attachable checks
    @param structural: run downward unsupported-mass checks
    @param foliage: detect leaf blocks with no log within ``max_log_dist``
    @param max_log_dist: foliage BFS limit for trunk search
    @returns: report dict with ``counts`` and ``findings`` grouped by kind
    """
    if x0 > x1:
        x0, x1 = x1, x0
    if y0 > y1:
        y0, y1 = y1, y0
    if z0 > z1:
        z0, z1 = z1, z0

    counts = {'air': 0, 'non_air': 0}
    by_kind: dict[str, list] = {}

    def add(row: dict) -> None:
        by_kind.setdefault(row['kind'], []).append(row)

    for x in range(x0, x1 + 1):
        for z in range(z0, z1 + 1):
            for y in range(y0, y1 + 1):
                st = block_at(x, y, z)
                if is_air(st):
                    counts['air'] += 1
                    continue
                counts['non_air'] += 1
                st = st or 'minecraft:air'
                if attachables:
                    for row in cell_glitches(block_at, x, y, z, st):
                        add(row)
                if foliage:
                    row = floating_leaves(block_at, x, y, z, st, max_log_dist=max_log_dist)
                    if row:
                        add(row)
                if structural:
                    row = unsupported_mass(block_at, x, y, z, st, y_min=y0, depth=depth)
                    if row:
                        add(row)

    return {
        'bbox': [x0, y0, z0, x1, y1, z1],
        'depth': depth,
        'counts': counts,
        'findings': by_kind,
        'totals': {k: len(v) for k, v in by_kind.items()},
    }
