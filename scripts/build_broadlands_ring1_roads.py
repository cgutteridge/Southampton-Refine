#!/usr/bin/env python3
"""Q-046: ring-1 main-road parcels around the Broadlands focus — carriageway, pavements
and kerbs at pristine Y (Composer, 12 Oct 2026).

Streets (cells 54..56, -45..-43): Mayfield Rd, Harrison Rd, Sirdar Rd, Sirdar Mews,
Portswood Rd, Thomas Lewis Way, Belgrave Rd. Broadlands Road was Q-044; rear lanes
and driveways were Q-045.

Rules: CRAFTSMANSHIP §3a — copy build_broadlands_rd_streetscape.py road_column logic;
no aerial survey. Geometry from the pristine Geocraft corridor; superseded ring-1
kerb/streetscape passes in modifies; cells owned by house builds, Q-044 streetscape
or Q-045 lanes are never written. Building edges rasterised into the corridor keep
their wall row (carpet fringe cleared only), as in Q-045 lanes.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'scripts'))

from coverage import LEFTOVER_TOP, load_area  # noqa: E402
from build_broadlands_rd_streetscape import (  # noqa: E402
    AIR, ASPHALT, GEO_STONE, KERB, N4, PAVE, STOCK_PAVE, STOCK_ROAD, Streetscape,
    _AIRS, _id, street_surface,
)
from site_kit import Plan, World, apply, built_cells, preview  # noqa: E402

NAME = 'broadlands_ring1_roads'
CFG = json.loads((ROOT / 'config/world.json').read_text())

ROAD_PARCELS = (
    'road:Belgrave Road@56,-43',
    'road:Harrison Road@55,-45', 'road:Harrison Road@56,-45',
    'road:Mayfield Road@54,-45', 'road:Mayfield Road@55,-44',
    'road:Mayfield Road@55,-45', 'road:Mayfield Road@56,-44',
    'road:Portswood Road@55,-43', 'road:Portswood Road@56,-43',
    'road:Portswood Road@56,-44',
    'road:Sirdar Mews@54,-43',
    'road:Sirdar Road@54,-43', 'road:Sirdar Road@55,-43',
    'road:Thomas Lewis Way@56,-43',
)

MODIFIES = (
    'portswood_ring1_streetscape_kerbs',
    'portswood_x_broadlands_streetscape_r0',
    'portswood_x_broadlands_streetscape_q013',
    'portswood_x_broadlands_streetscape_q013b',
    'portswood_x_broadlands_kerb_proof',
    'broadlands_facade_revert',
    'portswood_x_broadlands_terrace_facade_1',
    'portswood_x_broadlands_terrace_facade_1b',
    'portswood_x_broadlands_terrace_facade_2',
    'portswood_x_broadlands_terrace_facade_2b',
    'portswood_x_broadlands_terrace_facade_2c',
)

GRANITE = 'minecraft:granite'
GRASS = 'minecraft:grass_block'
VERGE = 'minecraft:grass_block[snowy=false]'
GROUND = (STOCK_ROAD, STOCK_PAVE, GEO_STONE, GRANITE, GRASS)


class Ring1Roads(Streetscape):
    """Plan the fourteen ring-1 road parcels column by column."""

    def __init__(self, plan: Plan):
        """@param plan: Plan to fill"""
        self.plan = plan
        self.pristine = World(CFG['pristine_region_path'])
        self.live = World()
        self.area = load_area('broadlands')
        self.owned = built_cells(exclude=set(MODIFIES) | {NAME})
        self.dug = self._lowest_modified()
        self._surf: dict = {}
        self.stats: dict = {}

    @staticmethod
    def _lowest_modified() -> dict:
        """Lowest y each superseded build wrote per column.

        @returns: {(x, z): lowest y}
        """
        low: dict = {}
        for name in MODIFIES:
            f = ROOT / f'verification/site/{name}-cells.json'
            if not f.exists():
                continue
            for k in json.loads(f.read_text()):
                x, y, z = (int(v) for v in k.split(','))
                low[(x, z)] = min(y, low.get((x, z), y))
        return low

    def keep_building_edge(self, x: int, z: int) -> bool:
        """Keep an unrebuilt Geocraft building edge column; drop only carpet fringe.

        @param x: MC x
        @param z: MC z
        @returns: False when no ground block was found under the structure
        """
        top, _b = self.surf(x, z)
        base = top - 1
        while base > 0 and _id(self.pristine.block(x, base, z)) not in GROUND:
            base -= 1
        if base <= 0:
            return False
        for yy in range(base + 1, LEFTOVER_TOP + 1):
            s = self.live.block(x, yy, z)
            if _id(s) in _AIRS:
                continue
            self.put(x, yy, z, AIR if _id(s).endswith('_carpet') else s)
        self.stats['building_edge_kept'] = self.stats.get('building_edge_kept', 0) + 1
        return True

    def road_column(self, x: int, z: int):
        """Carriageway, kerb or pavement for one road-parcel column.

        @param x: MC x
        @param z: MC z
        """
        y, b = self.surf(x, z)
        bid = _id(b)
        if bid.endswith('_carpet'):
            if not self.keep_building_edge(x, z):
                self.stats.setdefault('road_skipped', []).append((x, y, z, b))
            return
        if bid == GRASS and any(
            _id(self.pristine.block(x, yy, z)).endswith('_log') for yy in range(max(1, y - 4), y + 4)
        ):
            if self.put(x, y, z, VERGE):
                self.stats['under_tree'] = self.stats.get('under_tree', 0) + 1
            self.fill_below(x, y, z)
            self.clear_above(x, y, z)
            return
        if bid == GRANITE:
            b = STOCK_PAVE
        elif bid not in (STOCK_ROAD, STOCK_PAVE, GEO_STONE):
            if not self.keep_building_edge(x, z):
                self.stats.setdefault('road_skipped', []).append((x, y, z, b))
            return
        if b == STOCK_ROAD:
            kerb = any(self.surf(x + dx, z + dz)[1] != STOCK_ROAD for dx, dz in N4)
            state, key = (KERB, 'kerb') if kerb else (ASPHALT, 'asphalt')
        elif b == STOCK_PAVE:
            state, key = PAVE, 'pave'
        elif b == GEO_STONE:
            ys = [self.surf(x + dx, z + dz)[0] for dx, dz in N4
                  if self.surf(x + dx, z + dz)[1] in (STOCK_ROAD, STOCK_PAVE)]
            if ys and max(ys) < y:
                y = max(ys)
            state, key = PAVE, 'pave_from_stone'
        else:
            self.stats.setdefault('road_skipped', []).append((x, y, z, b))
            return
        if self.put(x, y, z, state):
            self.stats[key] = self.stats.get(key, 0) + 1
        self.fill_below(x, y, z)
        self.clear_above(x, y, z)

    def build(self) -> dict:
        """Plan every column of ROAD_PARCELS.

        @returns: stats dict (counts per surface, skipped columns)
        """
        for pid in ROAD_PARCELS:
            for x, z in sorted(self.area.parcels[pid]['set']):
                self.road_column(x, z)
        return self.stats


def build_plan() -> tuple[Plan, dict]:
    """@returns: (Plan, stats) for the Q-046 ring-1 road set"""
    plan = Plan(NAME)
    stats = Ring1Roads(plan).build()
    return plan, stats


def main():
    """CLI: preview + dry-run guards by default; --apply writes the live world."""
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--apply', action='store_true', help='write the live world (needs the lock)')
    args = ap.parse_args()
    plan, stats = build_plan()
    short = {k: (v if not isinstance(v, list) else f'{len(v)} e.g. {v[:4]}') for k, v in stats.items()}
    print(json.dumps(short, indent=1))
    preview(plan, ROOT / f'verification/site/{NAME}-preview.png', scale=2)
    apply(plan, dry=not args.apply, modifies=MODIFIES)


if __name__ == '__main__':
    main()
