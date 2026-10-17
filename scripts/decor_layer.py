#!/usr/bin/env python3
"""Layered decor pass for one 128² cell — HANDOFF-LAYERED-PASSES §1 (pass 4), §2, §3.

Decor here means the OSM-mapped boundary features the grounds classifier already knows:
hedges, brick walls and iron-bar fences (barrier=hedge/wall/fence), on any ground except mapped road, path and water columns,
never across a path or beside a build. Site hoarding is left out (temporary, not sure).
Placed only where the live block is air (or a stem/flower, as in §10) and not owned by a
neighbour or by another mask, clipped to the cell. Then any wall or fence pieces of the same
type that one extra block could link (face to face, diagonal is disjoint) are joined, one
block per join, repeating until none remain; supported spots first, air/flowers only. Writes a decor mask (§3) only after a
clean readback.

  python3 scripts/decor_layer.py --cell 48,-44            # dry run
  SITE_OWNER=<owner> python3 scripts/decor_layer.py --cell 48,-44 --apply
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

from script_env import ROOT  # noqa: E402

from ground_layer import (BLOCK_KIND, bare, cell_bbox_str, cell_contains, ignored_builds, is_air,  # noqa: E402
                          load_masked_positions)
from pass_mask import build_mask, clip_to_cell, write_mask  # noqa: E402
from site_kit import Plan, World, built_cells, full  # noqa: E402


def plan_name(tx: int, tz: int) -> str:
    """Build name, e.g. highfield_48_m44_decor."""
    return f"highfield_{tx}_{'m' if tz < 0 else ''}{abs(tz)}_decor"


JOINABLE = ('brick_wall', 'iron_bars', 'spruce_fence')
NEIGHBOURS = ((1, 0, 0), (-1, 0, 0), (0, 1, 0), (0, -1, 0), (0, 0, 1), (0, 0, -1))
# Ground kinds the decor pass must not sit on or straddle (live surface, not only OSM way columns).
_CARRIAGE_KINDS = frozenset({'tarmac', 'paving', 'mark', 'kerb'})


def column_ground_kind(world: World, x: int, z: int) -> str | None:
    """Classified ground kind at the live surface of (x, z), or None if empty."""
    from surface_probe import surface_y

    top = surface_y(world, x, z)
    if not top:
        return None
    return BLOCK_KIND.get(top[1])


def on_carriageway(world: World, x: int, z: int) -> bool:
    """True when a hedge/fence column would sit on the road or within two blocks of carriageway."""
    kind = column_ground_kind(world, x, z)
    if kind in _CARRIAGE_KINDS:
        return True
    for dx in range(-2, 3):
        for dz in range(-2, 3):
            if dx == 0 and dz == 0:
                continue
            nk = column_ground_kind(world, x + dx, z + dz)
            if nk in ('tarmac', 'paving'):
                return True
    return False


def join_pieces(found: dict[tuple[int, int, int], str], live, can_place,
                present: dict[tuple[int, int, int], str] | None = None) -> dict[tuple[int, int, int], str]:
    """Extra blocks that link separate walls/fences of the same type, one block per join.

    Pieces touch only face to face (diagonal is disjoint). A candidate is an empty spot
    (`can_place(pos)`) with face neighbours in two or more different pieces of one type;
    live same-type blocks next to the plan count as pieces too (`live(pos)` -> block id), as
    do `present` blocks (planned spots where that type is already standing).
    Supported candidates (solid block below, or planned) go first, then the lowest x, y, z;
    each placement merges its pieces, so later candidates that would only duplicate that
    join are dropped, and the sweep repeats until nothing more joins.
    """
    added: dict[tuple[int, int, int], str] = {}
    for mat in JOINABLE:
        nodes = {p for p, b in found.items() if b == mat}
        nodes |= {p for p, b in (present or {}).items() if b == mat}
        for p in list(nodes):
            for d in NEIGHBOURS:
                q = (p[0] + d[0], p[1] + d[1], p[2] + d[2])
                if q not in found and bare(live(q)) == f'minecraft:{mat}':
                    nodes.add(q)
        parent = {p: p for p in nodes}

        def find(p):
            while parent[p] != p:
                parent[p] = parent[parent[p]]
                p = parent[p]
            return p

        for p in nodes:
            for d in NEIGHBOURS:
                q = (p[0] + d[0], p[1] + d[1], p[2] + d[2])
                if q in parent:
                    parent[find(p)] = find(q)
        while True:
            cands = {(p[0] + d[0], p[1] + d[1], p[2] + d[2]) for p in nodes for d in NEIGHBOURS} - nodes
            cands = [c for c in cands if can_place(c) and c not in found and c not in added]

            def supported(c):
                below = (c[0], c[1] - 1, c[2])
                return below in found or below in added or not is_air(live(below))
            cands.sort(key=lambda c: (not supported(c), c))
            placed = False
            for c in cands:
                roots = {find((c[0] + d[0], c[1] + d[1], c[2] + d[2]))
                         for d in NEIGHBOURS if (c[0] + d[0], c[1] + d[1], c[2] + d[2]) in parent}
                if len(roots) < 2:
                    continue
                added[c] = mat
                parent[c] = c
                nodes.add(c)
                for r in roots:
                    parent[r] = c
                placed = True
                break
            if not placed:
                break
    return added


def plan_cell(cell: tuple[int, int], plan: Plan, world: World):
    """Plan the OSM-mapped hedges, walls and fences. Returns (placements, stats).

    Soft ground only (the live surface is grass), never within a block of a building
    footprint or a structure build, only into air, clipped to the cell.
    """
    from ground_sources import OSMGround
    from osm_footprints import OSMIndex
    from surface_probe import surface_y

    owned = set(built_cells(exclude=ignored_builds(cell)))
    owned_cols = {(x, z) for x, _y, z in owned}
    masked = load_masked_positions()
    fp = set(OSMIndex().cells())
    near = fp | owned_cols
    near1 = {(x + a, z + b) for x, z in near for a in (-1, 0, 1) for b in (-1, 0, 1)}
    osm = OSMGround(cell)
    found: dict[tuple[int, int, int], str] = {}
    present: dict[tuple[int, int, int], str] = {}
    stats = Counter()
    from garden_sources import garden_barriers
    groups = [(osm.hedge, 'oak_leaves[persistent=true]', 2), (osm.wall, 'brick_wall', 1),
              (osm.fence, 'iron_bars', 1)]
    mapped = {q for g in groups for q in g[0]}
    by_kind: dict = {}
    for q, (_t, blk, gh) in garden_barriers(cell).items():     # derived per-parcel garden boundaries
        if q not in mapped:                                    # an OSM-mapped barrier wins
            by_kind.setdefault((blk, gh), set()).add(q)
    groups += [(cells, blk, gh) for (blk, gh), cells in sorted(by_kind.items())]
    stats['garden columns'] = sum(len(c) for c in by_kind.values())
    way = set(osm.road) | set(osm.feat) | set(osm.water)        # mapped road, path or water columns
    for cells, mat, h in groups:
        for q in sorted(cells):
            if not cell_contains(cell, *q) or q in near1:
                continue
            top = surface_y(world, *q)
            if top and top[1] == mat:
                present[(q[0], top[0], q[1])] = mat   # already standing: a piece for joining
            if not top or q in way:
                stats['on road/path/water'] += 1
                continue
            if on_carriageway(world, q[0], q[1]):
                stats['on carriageway'] += 1
                continue
            if top[1].endswith('_carpet'):      # structure top (roof/deck), not ground: posts would float
                stats['on carpet top'] += 1
                continue
            for i in range(1, h + 1):
                pos = (q[0], top[0] + i, q[1])
                if not is_air(world.block(*pos)):
                    stats['blocked_live'] += 1
                    if bare(world.block(*pos)) == f'minecraft:{mat}':
                        present[pos] = mat
                elif pos in owned or pos in masked:
                    stats['blocked_owned'] += 1
                else:
                    found[pos] = mat
    def can_place(pos):
        return (cell_contains(cell, pos[0], pos[2]) and (pos[0], pos[2]) not in near1
                and is_air(world.block(*pos)) and pos not in owned and pos not in masked)

    joins = join_pieces(found, lambda p: world.block(*p), can_place, present)
    found.update(joins)
    stats['joins'] = len(joins)
    clipped, dropped = clip_to_cell(found, *cell)
    for p, b in clipped.items():
        plan.set(*p, b)
    stats['dropped_outside_cell'] = dropped
    stats['blocks'] = len(clipped)
    return clipped, stats


def run(cell: tuple[int, int]) -> int:
    """Dry run: plan and run the kit's guards. Never writes the world."""
    from site_kit import apply, preview

    name = plan_name(*cell)
    plan = Plan(name)
    placed, stats = plan_cell(cell, plan, World())
    kinds = Counter(placed.values())
    print(f'{name}: {dict(stats)}')
    print(f'  by block: {dict(kinds)}')
    if placed:
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
    placed, stats = plan_cell(cell, plan, world)
    if not placed:
        raise SystemExit('nothing to place; check the dry run')
    mask = build_mask('decor', cell, name, placed, lambda p: is_air(world.block(*p)))
    print(f'{name}: {len(placed)} blocks')
    subprocess.run([sys.executable, str(ROOT / 'scripts/region_backup.py'), 'snap',
                    '--bbox', cell_bbox_str(cell), '--name', name], check=True)
    apply(plan, modifies=ignored_builds(cell), stage='decor', cell=cell)   # records 'applying' first, 'applied' after readback
    rb = readback(plan)
    print(f'readback: {rb["planned"]} planned, {rb["mismatches"]} mismatches')
    stage = ROOT / f'site/cells/{tx}_{tz}-STAGES.json'
    data = json.loads(stage.read_text()) if stage.exists() else {'cell': f'{tx},{tz}', 'stages': {}}
    ok = rb['mismatches'] == 0
    entry = {'status': 'applied' if ok else 'applied-with-mismatches', 'plan': name,
             'blocks': len(placed), 'readback': rb}
    if ok:
        entry['mask'] = str(write_mask(mask).relative_to(ROOT))
    data['stages']['decor'] = entry
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
