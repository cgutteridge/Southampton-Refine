#!/usr/bin/env python3
"""Q-010: first Portswood Rd SW terrace façade from KartaView photo evidence.

Evidence: reference/photos/portswood-x-broadlands/kartaview-1471277657-seq5063417.jpg
(useful=yes; models facade/materials/openings). Real street: 2-storey red brick
terrace/semi with door + window rhythm. Geocraft mass here is low gray_terracotta
with no openings — raise street shell to a 2-storey eaves band and cut openings.

Street-only shell (depth 2); no invented private interiors. Avoids kit kerb cells.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'scripts'))

from site_kit import Plan, World, apply, bid, preview  # noqa: E402

NAME = 'portswood_x_broadlands_terrace_facade_1'
# Street-edge columns (max gray_terracotta X per Z) along Portswood SW frontage
# near the useful KartaView frame (camera ~X7071 Z-5531).
EDGE = [
    (7083, -5532),
    (7086, -5531),
    (7088, -5530),
    (7090, -5529),
    (7093, -5528),
]
# Ground / first / eaves relative to local pavement (~y26–27).
Y_PLINTH = 25
Y_GF = 26
Y_GF_TOP = 30
Y_FF = 31
Y_FF_TOP = 34
Y_EAVES = 35
Y_ROOF = 36
BRICK = 'minecraft:bricks'
PANE = 'minecraft:glass_pane'
AIR = 'minecraft:air'
# Facing street (+X / east toward Portswood Rd).
DOOR_L = 'minecraft:oak_door[facing=east,half=lower,hinge=left,open=false]'
DOOR_U = 'minecraft:oak_door[facing=east,half=upper,hinge=left,open=false]'
# Roof pitches toward street (east) and back (west).
STAIR_E = 'minecraft:brick_stairs[facing=east,half=bottom,shape=straight]'
STAIR_W = 'minecraft:brick_stairs[facing=west,half=bottom,shape=straight]'


def _kit_smooth_stone() -> set[tuple[int, int, int]]:
    """Return positions owned by prior kerb builds as smooth_stone (do not overwrite)."""
    out: set[tuple[int, int, int]] = set()
    for f in (ROOT / 'verification/site').glob('*-cells.json'):
        if 'facade' in f.name:
            continue
        import json
        for k, st in json.loads(f.read_text()).items():
            if bid(st) == 'minecraft:smooth_stone':
                x, y, z = (int(v) for v in k.split(','))
                out.add((x, y, z))
    return out


def build_plan() -> Plan:
    """Build the terrace façade plan from surveyed street-edge columns.

    @returns: Plan ready for preview / apply
    """
    plan = Plan(NAME)
    protect = _kit_smooth_stone()
    w = World()

    def set_if_free(x: int, y: int, z: int, st: str) -> None:
        if (x, y, z) in protect:
            return
        plan.set(x, y, z, st)

    # Column roles along the frontage (wall / window / door / window / wall).
    roles = ['wall', 'window', 'door', 'window', 'wall']

    for i, ((ex, z), role) in enumerate(zip(EDGE, roles)):
        # Depth-2 shell: street face + one block back (west).
        for depth, x in enumerate((ex, ex - 1)):
            # Clear air shaft above old low roof so eaves read clean from street.
            for y in range(Y_GF, Y_ROOF + 2):
                existing = bid(w.block(x, y, z))
                if existing == 'minecraft:smooth_stone' and (x, y, z) in protect:
                    continue
                # Keep road/pavement east of shell untouched (depth 0 only on building).
                if depth == 0 and existing in (
                    'minecraft:stone',
                    'minecraft:polished_diorite',
                    'minecraft:smooth_stone',
                ) and y <= Y_GF + 1 and x > ex:
                    continue
                set_if_free(x, y, z, AIR)

            # Plinth + walls
            for y in range(Y_PLINTH, Y_EAVES + 1):
                set_if_free(x, y, z, BRICK)

            if depth != 0:
                continue  # openings only on street face

            if role == 'door':
                set_if_free(x, Y_GF, z, DOOR_L)
                set_if_free(x, Y_GF + 1, z, DOOR_U)
                # First-floor window above door
                set_if_free(x, Y_FF + 1, z, PANE)
                set_if_free(x, Y_FF + 2, z, PANE)
            elif role == 'window':
                set_if_free(x, Y_GF + 2, z, PANE)
                set_if_free(x, Y_GF + 3, z, PANE)
                set_if_free(x, Y_FF + 1, z, PANE)
                set_if_free(x, Y_FF + 2, z, PANE)

        # Simple pitched roof strip over the unit (street + back)
        set_if_free(ex, Y_ROOF, z, STAIR_E)
        set_if_free(ex - 1, Y_ROOF, z, STAIR_W)
        # Fill one more depth for a readable ridge band without inventing rooms
        set_if_free(ex - 2, Y_EAVES, z, BRICK)
        set_if_free(ex - 2, Y_ROOF, z, STAIR_W)

    # Party-wall returns at ends (1 block along street) so the bay reads as a unit
    for ex, z in (EDGE[0], EDGE[-1]):
        for dz in (-1, 1):
            zz = z + dz
            if zz in {e[1] for e in EDGE}:
                continue
            for y in range(Y_PLINTH, Y_EAVES + 1):
                # only if currently building material / air above old mass
                cur = bid(w.block(ex, y, zz))
                if cur in (
                    'minecraft:gray_terracotta',
                    'minecraft:air',
                    'minecraft:bricks',
                    'minecraft:stone',
                ) and (ex, y, zz) not in protect:
                    # don't pave over road
                    if cur == 'minecraft:stone' and y <= Y_GF + 1:
                        side = bid(w.block(ex + 1, y, zz))
                        if side in ('minecraft:stone', 'minecraft:polished_diorite'):
                            continue
                    plan.set(ex, y, zz, BRICK)

    return plan


def main() -> None:
    """CLI: preview by default; ``--apply`` writes the live world.

    @returns: None
    """
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--apply', action='store_true', help='write live world (needs SITE_OWNER lock)')
    ap.add_argument('--dry', action='store_true', help='plan + clash check only')
    args = ap.parse_args()
    plan = build_plan()
    out = ROOT / 'verification/site' / f'{NAME}-preview.png'
    try:
        preview(plan, out)
        print('preview:', out)
    except Exception as e:  # matplotlib optional offline
        print('preview skipped:', e)
    print(f'{NAME}: {len(plan.cells)} cells; bounds {plan.bounds()}')
    if args.dry and not args.apply:
        apply(plan, dry=True)
        return
    if args.apply:
        apply(plan, dry=False)
    else:
        apply(plan, dry=True)


if __name__ == '__main__':
    main()
