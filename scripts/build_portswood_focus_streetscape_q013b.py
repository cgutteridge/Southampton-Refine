#!/usr/bin/env python3
"""Q-013b: Portswood carriageway trim + kerbs at the *visible* street surface.

q013 restored I-004 low-Y kerbs correctly but wrote the width trim on subsurface
Y (22–23). This build undoes those wrong-Y pave/kerb cells and trims the top
gray_terracotta band to ~10 m (aerial), re-kerbing edges. Modifies q013.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'scripts'))

from site_kit import Plan, World, apply, bid, preview  # noqa: E402

NAME = 'portswood_x_broadlands_streetscape_q013b'
MODIFIES = (
    'portswood_x_broadlands_streetscape_q013',
    'portswood_x_broadlands_streetscape_r0',
    'portswood_ring1_streetscape_kerbs',
    'portswood_x_broadlands_kerb_proof',
)

ROAD = 'minecraft:gray_terracotta'
PAVE = 'minecraft:polished_diorite'
KERB = 'minecraft:smooth_stone'
AIR = 'minecraft:air'
STREET = {ROAD, PAVE, KERB}

X0, X1 = 7065, 7135
Z_LO, Z_HI = -5565, -5495
TARGET_WIDTH = 10
Q013_CELLS = ROOT / 'verification/site/portswood_x_broadlands_streetscape_q013-cells.json'


def _top_street(w: World, x: int, z: int) -> tuple[int, str] | None:
    """Topmost street-surface block (road/pave/kerb) in a column.

    @param w: world
    @param x: X
    @param z: Z
    @returns: (y, block_id) or None
    """
    for y in range(40, 15, -1):
        b = bid(w.block(x, y, z) or '')
        if b in STREET:
            return y, b
        if b and b != AIR and b != 'minecraft:light':
            # Solid non-street (building / terrain) — no street surface here.
            return None
    return None


def _portswood_mid(x: int) -> float:
    """Expected Portswood centreline Z for column x (NW–SE diagonal).

    @param x: Minecraft X
    @returns: approximate centre Z
    """
    return -5520.0 + 0.40 * (x - 7097)


def _is_building_column(w: World, x: int, y: int, z: int) -> bool:
    """True if kit/Geocraft building mass occupies this street column.

    @param w: world
    @param x: X
    @param y: street surface Y
    @param z: Z
    @returns: whether to skip edits here
    """
    for yy in range(y, y + 10):
        b = bid(w.block(x, yy, z) or '')
        if b in ('minecraft:bricks', 'minecraft:brick_stairs') or (
            b and b.endswith('_door')
        ):
            return True
    return False


def build_plan() -> Plan:
    """Undo wrong-Y trim cells, then trim/re-kerb at top street Y.

    @returns: Plan
    """
    plan = Plan(NAME)
    w = World()

    # --- Undo q013 subsurface pave/kerb (keep I-004 gray_terracotta/air) ---
    if Q013_CELLS.exists():
        prev = json.loads(Q013_CELLS.read_text())
        for key, st in prev.items():
            x, y, z = map(int, key.split(','))
            if y >= 24:
                continue
            if st in (PAVE, KERB):
                plan.set(x, y, z, ROAD)
            elif st == AIR and bid(w.block(x, y - 1, z) or '') in (PAVE, KERB, ROAD):
                # air that sat above a wrong-Y kerb — leave air / ensure clear
                plan.set(x, y, z, AIR)

    # --- Top-surface Portswood trim ---
    for x in range(X0, X1 + 1):
        cols: list[tuple[int, int]] = []  # (z, y)
        for z in range(Z_LO, Z_HI + 1):
            top = _top_street(w, x, z)
            if top is None:
                continue
            y, _b = top
            # Keep only the Portswood band near the diagonal centreline.
            if abs(z - _portswood_mid(x)) > 12:
                continue
            cols.append((z, y))
        if len(cols) < 6:
            continue
        cols.sort()
        zs = [z for z, _y in cols]
        y_at = {z: y for z, y in cols}
        # Largest contiguous Z run.
        best: list[int] = []
        cur = [zs[0]]
        for z in zs[1:]:
            if z == cur[-1] + 1:
                cur.append(z)
            else:
                if len(cur) > len(best):
                    best = cur
                cur = [z]
        if len(cur) > len(best):
            best = cur
        if len(best) < 6:
            continue

        z0, z1 = best[0], best[-1]
        width = z1 - z0 + 1
        mid = (z0 + z1) / 2.0
        new0 = int(round(mid - (TARGET_WIDTH // 2) + 0.1))
        new1 = new0 + TARGET_WIDTH - 1
        new0 = max(new0, z0)
        new1 = min(new1, z1)
        if new1 - new0 + 1 < TARGET_WIDTH and width >= TARGET_WIDTH:
            if new0 == z0:
                new1 = min(z1, new0 + TARGET_WIDTH - 1)
            elif new1 == z1:
                new0 = max(z0, new1 - TARGET_WIDTH + 1)

        for z in best:
            y = y_at[z]
            if _is_building_column(w, x, y, z):
                continue
            if new0 < z < new1:
                plan.set(x, y, z, ROAD)
                if bid(w.block(x, y + 1, z) or '') == KERB:
                    plan.set(x, y + 1, z, AIR)
            elif z in (new0, new1):
                plan.set(x, y, z, KERB)
                plan.set(x, y + 1, z, AIR)
            else:
                plan.set(x, y, z, PAVE)
                if bid(w.block(x, y + 1, z) or '') == KERB:
                    plan.set(x, y + 1, z, AIR)

    # --- I-005: smooth_stone still kissing bricks at surface ---
    for x in range(X0, X1 + 1):
        for z in range(Z_LO, Z_HI + 1):
            top = _top_street(w, x, z)
            if top is None:
                continue
            y, b = top
            if b != KERB:
                continue
            nbrs = [
                bid(w.block(x + dx, y, z + dz) or '')
                for dx, dz in ((1, 0), (-1, 0), (0, 1), (0, -1))
            ]
            if not any(
                n == 'minecraft:bricks' or (n and n.endswith('_door')) for n in nbrs
            ):
                continue
            plan.set(x, y, z, ROAD if ROAD in nbrs else PAVE)
            plan.set(x, y + 1, z, AIR)

    return plan


def main() -> None:
    """CLI: preview / dry / apply Q-013b surface trim.

    @returns: None
    """
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--apply', action='store_true')
    ap.add_argument('--dry', action='store_true')
    args = ap.parse_args()
    plan = build_plan()
    out = ROOT / 'verification/site' / f'{NAME}-preview.png'
    try:
        preview(plan, out)
        print('preview:', out)
    except Exception as e:
        print('preview skipped:', e)
    # Sanity: most street edits should be at y>=24
    ys = [y for (_x, y, _z) in plan.cells]
    surf = sum(1 for y in ys if y >= 24)
    print(f'{NAME}: {len(plan.cells)} cells; bounds {plan.bounds()}; y>=24: {surf}')
    if surf < 100:
        raise SystemExit('refusing apply: too few surface cells — check Y detection')
    apply(plan, dry=not args.apply, modifies=MODIFIES)


if __name__ == '__main__':
    main()
