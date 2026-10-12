#!/usr/bin/env python3
"""Q-013: fix Portswood × Broadlands kerbs + Portswood carriageway width.

Evidence (aerial mosaic + KartaView): Portswood asphalt ~9–10 m; Geocraft
diagonal band is ~13 blocks perpendicular. Trim to 10, re-kerb edges, restore
I-004 low-Y ring1 kerbs from structure backup (were gray_terracotta).
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'scripts'))

from site_kit import Plan, World, apply, bid, preview  # noqa: E402

NAME = 'portswood_x_broadlands_streetscape_q013'
MODIFIES = (
    'portswood_x_broadlands_streetscape_r0',
    'portswood_ring1_streetscape_kerbs',
    'portswood_x_broadlands_kerb_proof',
)

ROAD = 'minecraft:gray_terracotta'
PAVE = 'minecraft:polished_diorite'
KERB = 'minecraft:smooth_stone'
AIR = 'minecraft:air'
BRICK = 'minecraft:bricks'

# Focus corridor along Portswood (NW–SE diagonal through junction).
X0, X1 = 7065, 7135
TARGET_WIDTH = 10  # aerial asphalt ~9–10 m; 1 MC = 1 m
LOWY_RESTORE = ROOT / 'verification/site/q013-lowy-restore.json'


def _road_z_span(w: World, x: int) -> tuple[int, int, int] | None:
    """Largest contiguous gray_terracotta Z-span at column x near the focus.

    @param w: read-only world
    @param x: Minecraft X
    @returns: (z0, z1, y_surface) inclusive, or None
    """
    found: list[tuple[int, int]] = []
    for z in range(-5580, -5480):
        for y in range(22, 30):
            if bid(w.block(x, y, z) or '') == ROAD:
                found.append((z, y))
                break
    if not found:
        return None
    zs = [z for z, _y in found]
    y_at = {z: y for z, y in found}
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
        return None
    y = Counter(y_at[z] for z in best).most_common(1)[0][0]
    return best[0], best[-1], y


def _is_building(w: World, x: int, y: int, z: int) -> bool:
    """True if this column reads as Geocraft / kit building mass (do not pave).

    @param w: world
    @param x: X
    @param y: Y sample
    @param z: Z
    @returns: whether to leave the column alone for road edits
    """
    for yy in range(y, y + 8):
        b = bid(w.block(x, yy, z) or '')
        if b in (BRICK, 'minecraft:brick_stairs') or b.endswith('_door'):
            return True
    return False


def build_plan() -> Plan:
    """Build restore + Portswood trim/re-kerb plan for the focus corridor.

    @returns: Plan ready for preview/apply
    """
    plan = Plan(NAME)
    w = World()

    # --- I-004: restore low-Y ring1 kerbs from pre-kerb structure snapshot ---
    lowy = json.loads(LOWY_RESTORE.read_text())
    for key, st in lowy.items():
        x, y, z = map(int, key.split(','))
        plan.set(x, y, z, st)

    # --- Portswood width + kerbs in focus corridor ---
    for x in range(X0, X1 + 1):
        span = _road_z_span(w, x)
        if span is None:
            continue
        z0, z1, y = span
        width = z1 - z0 + 1
        mid = (z0 + z1) / 2.0
        # Keep TARGET_WIDTH centred on the existing band.
        half_lo = TARGET_WIDTH // 2
        half_hi = TARGET_WIDTH - half_lo
        new0 = int(round(mid - half_lo + 0.1))
        new1 = new0 + TARGET_WIDTH - 1
        # Do not expand beyond the existing Geocraft band.
        new0 = max(new0, z0)
        new1 = min(new1, z1)
        if new1 - new0 + 1 < TARGET_WIDTH and width >= TARGET_WIDTH:
            # Shift to fit inside old span.
            if new0 == z0:
                new1 = min(z1, new0 + TARGET_WIDTH - 1)
            elif new1 == z1:
                new0 = max(z0, new1 - TARGET_WIDTH + 1)

        for z in range(z0, z1 + 1):
            if _is_building(w, x, y, z):
                continue
            if new0 < z < new1:
                plan.set(x, y, z, ROAD)
            elif z in (new0, new1):
                plan.set(x, y, z, KERB)
                plan.set(x, y + 1, z, AIR)
            else:
                # Oversized margin → pavement (matches Geocraft sidewalk material).
                plan.set(x, y, z, PAVE)
            if bid(w.block(x, y + 1, z) or '') == KERB and z not in (new0, new1):
                plan.set(x, y + 1, z, AIR)

    # --- I-005 remnants: live smooth_stone abutting bricks in focus ---
    for x in range(X0, X1 + 1):
        for z in range(-5560, -5495):
            for y in range(24, 32):
                if bid(w.block(x, y, z) or '') != KERB:
                    continue
                nbrs = [
                    bid(w.block(x + dx, y, z + dz) or '')
                    for dx, dz in ((1, 0), (-1, 0), (0, 1), (0, -1))
                ]
                if not any(n == BRICK or n.endswith('_door') for n in nbrs):
                    continue
                # Prefer road if neighbour road, else pavement.
                if ROAD in nbrs:
                    plan.set(x, y, z, ROAD)
                else:
                    plan.set(x, y, z, PAVE)
                if bid(w.block(x, y + 1, z) or '') == AIR or True:
                    plan.set(x, y + 1, z, AIR)

    return plan


def main() -> None:
    """CLI: preview / dry / apply Q-013 streetscape cleanup.

    @returns: None
    """
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--apply', action='store_true')
    ap.add_argument('--dry', action='store_true')
    args = ap.parse_args()
    if not LOWY_RESTORE.exists():
        raise SystemExit(f'missing {LOWY_RESTORE}; regenerate from ring1 backup NBT')
    plan = build_plan()
    out = ROOT / 'verification/site' / f'{NAME}-preview.png'
    try:
        preview(plan, out)
        print('preview:', out)
    except Exception as e:
        print('preview skipped:', e)
    print(f'{NAME}: {len(plan.cells)} cells; bounds {plan.bounds()}')
    apply(plan, dry=not args.apply, modifies=MODIFIES)


if __name__ == '__main__':
    main()
