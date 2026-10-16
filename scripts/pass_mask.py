#!/usr/bin/env python3
"""Air-only pass masks for layered cell builds (site/HANDOFF-LAYERED-PASSES.txt §3).

A tree or decor pass only writes into air, so its undo is exact: every placed
position goes back to minecraft:air. A mask records those positions so the
undo does not need to remember the old blocks.

This module is pure data (no Minecraft). It builds, encodes, reads, verifies and
plans undo for a mask. It never writes to the world.

  from pass_mask import build_mask, write_mask, read_mask, plan_undo

Mask file: verification/site/masks/<pass>-<tx>_<tz>.mask.json
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
MASK_DIR = ROOT / 'verification' / 'site' / 'masks'
CELL_SIZE = 128
AIR = 'minecraft:air'
PASSES = ('trees', 'decor')
TREES_RULE = 'overhang-v1'   # trees: trunk's cell owns the tree, crowns overhang, tree-on-tree leaves merge (I-061)
OVERHANG_MARGIN = 12      # blocks past the cell edge a tree crown can reach; snapshots cover it

Pos = tuple[int, int, int]


def cell_bounds(tx: int, tz: int) -> tuple[int, int, int, int]:
    """Inclusive x/z bounds of a 128-block cell: (x0, z0, x1, z1)."""
    x0, z0 = tx * CELL_SIZE, tz * CELL_SIZE
    return x0, z0, x0 + CELL_SIZE - 1, z0 + CELL_SIZE - 1


def clip_to_cell(placements: dict[Pos, str], tx: int, tz: int) -> tuple[dict[Pos, str], int]:
    """Keep placements inside the cell's x/z bounds. Returns (kept, dropped_count)."""
    x0, z0, x1, z1 = cell_bounds(tx, tz)
    kept = {p: b for p, b in placements.items() if x0 <= p[0] <= x1 and z0 <= p[2] <= z1}
    return kept, len(placements) - len(kept)


def _digest(placed: list[tuple[int, int, int, str]]) -> str:
    """sha256 of the sorted (x, y, z, block) list, canonical JSON."""
    blob = json.dumps(placed, separators=(',', ':'))
    return hashlib.sha256(blob.encode('utf-8')).hexdigest()


def _sorted_placed(placements: dict[Pos, str]) -> list[tuple[int, int, int, str]]:
    return sorted((x, y, z, b) for (x, y, z), b in placements.items())


def _scan_order(bbox: list[int]):
    """Positions of bbox in the mask's order: x, then z, then y."""
    x0, y0, z0, x1, y1, z1 = bbox
    for x in range(x0, x1 + 1):
        for z in range(z0, z1 + 1):
            for y in range(y0, y1 + 1):
                yield x, y, z


def encode_runs(placements: dict[Pos, str], bbox: list[int]) -> tuple[list[str], list[list[int]]]:
    """Return (palette, runs) over bbox in x, z, y order. palette[0] is air."""
    palette = [AIR]
    index = {AIR: 0}
    runs: list[list[int]] = []
    for pos in _scan_order(bbox):
        block = placements.get(pos, AIR)
        if block not in index:
            index[block] = len(palette)
            palette.append(block)
        value = index[block]
        if runs and runs[-1][0] == value:
            runs[-1][1] += 1
        else:
            runs.append([value, 1])
    return palette, runs


def decode_runs(palette: list[str], runs: list[list[int]], bbox: list[int]) -> dict[Pos, str]:
    """Inverse of encode_runs. Returns only the non-air placements.

    Consumes ``runs`` (counts are decremented, as before) and raises IndexError if they run out early.
    """
    x0, y0, z0, x1, y1, z1 = bbox
    nx, nz, ny = x1 - x0 + 1, z1 - z0 + 1, y1 - y0 + 1
    volume = max(nx, 0) * max(nz, 0) * max(ny, 0)
    if sum(n for _v, n in runs) < volume:
        raise IndexError('mask runs end before the bbox does')
    values = np.repeat(np.array([v for v, _n in runs], dtype=np.int64), np.array([n for _v, n in runs], dtype=np.int64))[:volume]
    left = volume
    for r in runs:                                          # same consumption as the old one-cell-at-a-time loop
        take = min(r[1], left)
        r[1] -= take
        left -= take
    idx = np.nonzero(values)[0]                             # scan order is x, then z, then y
    xi, rem = np.divmod(idx, nz * ny)
    zi, yi = np.divmod(rem, ny)
    return {(int(x) + x0, int(y) + y0, int(z) + z0): palette[int(values[i])]
            for i, x, y, z in zip(idx.tolist(), xi.tolist(), yi.tolist(), zi.tolist())}


def _runs_copy(runs: list[list[int]]) -> list[list[int]]:
    return [[v, n] for v, n in runs]


def _box_of(placements: dict[Pos, str]) -> list[int]:
    xs = [p[0] for p in placements]
    ys = [p[1] for p in placements]
    zs = [p[2] for p in placements]
    return [min(xs), min(ys), min(zs), max(xs), max(ys), max(zs)]


def build_mask(
    pass_name: str,
    cell: tuple[int, int],
    plan_name: str,
    placements: dict[Pos, str],
    is_air,
    created: str | None = None,
) -> dict:
    """Build a mask for one pass on one cell.

    is_air(pos) -> bool is the plan-time air check. Any position that is not air
    in the live world stops the build, because the undo would not be exact.
    The mask records exactly what the planner gives it. A tree crown may overhang the cell edge
    (trees_layer.plan_cell); the planting cell's mask owns those blocks and undoes them.
    Decor clips itself to the cell before it gets here. outside_cell counts the overhang.
    """
    if pass_name not in PASSES:
        raise ValueError(f'pass must be one of {PASSES}, got {pass_name!r}')
    tx, tz = cell
    kept = placements
    outside = len(kept) - len(clip_to_cell(kept, tx, tz)[0])
    not_air = [p for p in kept if not is_air(p)]
    if not_air:
        raise ValueError(f'{len(not_air)} placement(s) not air at plan time, first {not_air[0]}')
    if not kept:
        bbox = [0, 0, 0, 0, 0, 0]
        offset = [0, 0, 0]
        size = [0, 0, 0]
    else:
        bbox = _box_of(kept)
        offset = bbox[:3]
        size = [bbox[3] - bbox[0] + 1, bbox[4] - bbox[1] + 1, bbox[5] - bbox[2] + 1]
    palette, runs = encode_runs(kept, bbox) if kept else ([AIR], [])
    mask = {
        'pass': pass_name,
        'cell': [tx, tz],
        'plan': plan_name,
        'created': created or datetime.now(timezone.utc).isoformat(timespec='seconds'),
        'bbox': bbox,
        'offset': offset,
        'size': size,
        'palette': palette,
        'data': runs,
        'count': len(kept),
        'outside_cell': outside,
        'sha256': _digest(_sorted_placed(kept)),
        'air_only': True,
    }
    if pass_name == 'trees':
        mask['rule'] = TREES_RULE
    return mask


def mask_path(pass_name: str, cell: tuple[int, int], mask_dir: Path = MASK_DIR) -> Path:
    tx, tz = cell
    return mask_dir / f'{pass_name}-{tx}_{tz}.mask.json'


def write_mask(mask: dict, mask_dir: Path = MASK_DIR) -> Path:
    tx, tz = mask['cell']
    path = mask_path(mask['pass'], (tx, tz), mask_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(mask, indent=2) + '\n', encoding='utf-8')
    return path


def read_mask(path: Path) -> dict:
    return json.loads(Path(path).read_text(encoding='utf-8'))


def trees_rule_current(cell: tuple[int, int], mask_dir: Path = MASK_DIR) -> bool:
    """Whether the cell's trees mask was written under the current overhang rule.

    The mask carries ``rule`` (TREES_RULE). Masks written under the overhang rule before the stamp
    existed carry ``outside_cell`` (and not the old clip counter ``dropped_outside_cell``), so they
    count as current. A missing or unreadable mask is not current: re-running trees writes one.
    """
    try:
        mask = read_mask(mask_path('trees', cell, mask_dir))
    except (OSError, json.JSONDecodeError):
        return False
    if mask.get('rule'):
        return mask['rule'] == TREES_RULE
    return 'outside_cell' in mask and 'dropped_outside_cell' not in mask


def mask_placements(mask: dict) -> dict[Pos, str]:
    """The placements a mask records, decoded from its runs."""
    if mask['count'] == 0:
        return {}
    return decode_runs(mask['palette'], _runs_copy(mask['data']), mask['bbox'])


def verify_integrity(mask: dict) -> bool:
    """Recompute the sha256 from the stored runs and compare with the stored digest."""
    placements = mask_placements(mask)
    if len(placements) != mask['count']:
        return False
    return _digest(_sorted_placed(placements)) == mask['sha256']


def shared_positions(mask: dict, mask_dir: Path = MASK_DIR) -> set[Pos]:
    """Positions of this mask that another mask file also lists (merged tree crowns).

    Undo leaves these in place: the other cell's mask still owns them.
    """
    mine = mask_placements(mask)
    own = mask_path(mask['pass'], tuple(mask['cell']), mask_dir)
    shared: set[Pos] = set()
    for path in sorted(mask_dir.glob('*.mask.json')) if mask_dir.exists() else ():
        if path != own:
            shared |= mine.keys() & mask_placements(read_mask(path)).keys()
    return shared


def plan_undo(mask: dict, live_block, shared: set[Pos] = frozenset()) -> tuple[list[Pos], list[tuple[Pos, str, str]]]:
    """Plan an undo without writing anything.

    live_block(pos) -> the block id now in the world at pos.
    Returns (positions_to_set_to_air, conflicts). conflicts are
    (pos, expected, live) where the live block differs from the mask.
    The caller must not write anything when conflicts is non-empty.
    """
    if not verify_integrity(mask):
        raise ValueError('mask integrity check failed; file does not match its sha256')
    conflicts: list[tuple[Pos, str, str]] = []
    to_air: list[Pos] = []
    for pos, expected in sorted(mask_placements(mask).items()):
        if pos in shared:
            continue
        live = live_block(pos)
        if live != expected:
            conflicts.append((pos, expected, live))
        else:
            to_air.append(pos)
    return to_air, conflicts


def masked_overlaps(planned: dict[Pos, str], mask: dict) -> list[Pos]:
    """Planned positions that land on a block this mask owns.

    A ground plan normally never does this. If it does, the mask must be undone
    before that plan applies (HANDOFF-LAYERED-PASSES §10). Sorted for stable output.
    """
    owned = mask_placements(mask)
    return sorted(p for p in planned if p in owned)
