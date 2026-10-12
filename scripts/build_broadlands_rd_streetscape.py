#!/usr/bin/env python3
"""Q-044: Broadlands Road streetscape — carriageway, both pavements, kerbs and the
rear lane w156591073 behind the north side, as whole coverage parcels (Claude, 12 Oct 2026).

Evidence
  OSM     Broadlands Road w24307056: residential, asphalt, sidewalk=both, 2 lanes.
          Rear lane w156591073: service=alley, surface=pebblestone.
  Aerial  hampshire-hub z18 mosaic (q044-aerial*.png): front boundary to front boundary
          ~14 rows in Z (~13 m across the 22° road), cars parked mostly on the south
          side, ~2 m footways both sides. Q-013 read the same mosaic as ~9-10 m
          kerb-to-kerb, which is the ring-1 / q013b layout kept here: two pavement rows,
          kerb in the outermost carriageway row, asphalt between. The lane is a light
          brown strip ~2.5-3 m wide with grass / planting at its edges.
  User    palette (Q-044, 12 Oct): gray_concrete carriageway, light_gray_concrete
          pavements, flush smooth_stone kerb row, lane gravel with coarse_dirt /
          dirt_path patches and grass verges.

Rules
  - Geometry comes from the PRISTINE Geocraft save: its corridor follows the OSM route
    (trusted) and the north-side terraces already set their front boundaries and rear
    fences against it (terrace.py pav_row / lane_row), so pavement and lane edges stay.
  - Every column of the eight parcels is written at the pristine street level, which is
    the level the terrace gates and paths were built to.
  - Unowned blocks above the new surface go (Geocraft road-label signs, orphaned fence
    posts left in the lane by earlier re-applies, raised Geocraft stone).
  - The bed under the surface is made solid again down to the lowest cell the superseded
    streetscape passes wrote (their trims left air pockets; gravel fell into one).
  - Cells owned by any build not in MODIFIES (the terraces' boundary walls, hedges,
    gates) are never written; those columns are already touched by their owners.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'scripts'))

from coverage import load_area, surface  # noqa: E402
from site_kit import Plan, World, apply, built_cells, preview  # noqa: E402

NAME = 'broadlands_rd_streetscape'
CFG = json.loads((ROOT / 'config/world.json').read_text())

ROAD_PARCELS = (
    'road:Broadlands Road@54,-44', 'road:Broadlands Road@55,-44',
    'road:Broadlands Road@55,-43', 'road:Broadlands Road@56,-43',
)
LANE_PARCELS = (
    'path:w156591073@54,-45', 'path:w156591073@54,-44',
    'path:w156591073@55,-44', 'path:w156591073@56,-44',
)
# Earlier streetscape passes on this ground, all superseded by this build, plus the I-009
# pavement façades and their revert (coverage.REVERTED): built_cells() drops a skipped
# build's air writes too, so the façades' bricks would otherwise still read as owned.
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

ASPHALT = 'minecraft:gray_concrete'
PAVE = 'minecraft:light_gray_concrete'
KERB = 'minecraft:smooth_stone'
GRAVEL = 'minecraft:gravel'
COARSE = 'minecraft:coarse_dirt'
DIRT_PATH = 'minecraft:dirt_path'
VERGE = 'minecraft:grass_block[snowy=false]'
AIR = 'minecraft:air'

STOCK_ROAD = 'minecraft:gray_terracotta'
STOCK_PAVE = 'minecraft:polished_diorite'
GEO_STONE = 'minecraft:stone'

# OSM w156591073 vertices in MC x, z (the west vertex 6466,-5834 is far outside the parcels).
LANE_LINE = ((6797.0, -5699.0), (7171.0, -5547.0))
LANE_HALF = 1.5         # aerial: ~3 m of worn surface; the rest of the parcel is verge
CLEAR_UP = 16           # blocks above the surface scanned for unowned leftovers
N4 = ((1, 0), (-1, 0), (0, 1), (0, -1))
_AIRS = ('minecraft:air', 'minecraft:cave_air', 'minecraft:void_air')


def _id(s: str | None) -> str:
    """Block id without properties.

    @param s: block state string or None
    @returns: e.g. 'minecraft:stone' ('minecraft:air' for None)
    """
    return (s or 'minecraft:air').split('[')[0]


def street_surface(world: World, x: int, z: int) -> tuple[int, str]:
    """Pristine street surface of a column, looking through Geocraft's road-label signs.

    @param world: World over the pristine save
    @param x: MC x
    @param z: MC z
    @returns: (y, block id) of the walkable street block
    """
    y, b = surface(world, x, z)
    while b.endswith('_sign'):
        y -= 1
        b = _id(world.block(x, y, z))
    return y, b


def lane_offset(x: float, z: float) -> float:
    """Perpendicular distance from (x, z) to the OSM centreline of lane w156591073.

    @param x: MC x (column centre)
    @param z: MC z (column centre)
    @returns: distance in blocks
    """
    (ax, az), (bx, bz) = LANE_LINE
    dx, dz = bx - ax, bz - az
    t = max(0.0, min(1.0, ((x - ax) * dx + (z - az) * dz) / (dx * dx + dz * dz)))
    return math.hypot(x - (ax + t * dx), z - (az + t * dz))


def lane_mix(x: int, z: int) -> str:
    """Deterministic pebble-lane surface: mostly gravel, patches of coarse dirt and worn path.

    @param x: MC x
    @param z: MC z
    @returns: block state
    """
    h = ((x * 73856093) ^ (z * 19349663)) % 100
    if h < 60:
        return GRAVEL
    if h < 88:
        return COARSE
    return DIRT_PATH


class Streetscape:
    """Plan the eight Broadlands Road / lane parcels column by column."""

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
        """Lowest y each superseded build wrote per column (their trims left air under the street).

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

    def fill_below(self, x: int, y: int, z: int):
        """Solid street bed from under the surface down to the lowest superseded write.

        @param x: MC x
        @param y: new surface y
        @param z: MC z
        """
        for yy in range(self.dug.get((x, z), y), y):
            self.put(x, yy, z, _id(self.pristine.block(x, yy, z)) if
                     _id(self.pristine.block(x, yy, z)) not in _AIRS else 'minecraft:dirt')

    def surf(self, x: int, z: int) -> tuple[int, str]:
        """Cached pristine street surface.

        @param x: MC x
        @param z: MC z
        @returns: (y, block id)
        """
        if (x, z) not in self._surf:
            self._surf[(x, z)] = street_surface(self.pristine, x, z)
        return self._surf[(x, z)]

    def put(self, x: int, y: int, z: int, state: str) -> bool:
        """Set a cell unless a protected (non-MODIFIES) build owns it.

        @param x: MC x
        @param y: MC y
        @param z: MC z
        @param state: block state
        @returns: whether the cell was planned
        """
        if (x, y, z) in self.owned:
            self.stats['protected'] = self.stats.get('protected', 0) + 1
            return False
        self.plan.set(x, y, z, state)
        return True

    def clear_above(self, x: int, y: int, z: int):
        """Air every unowned non-air live block in the CLEAR_UP blocks above the new surface.

        @param x: MC x
        @param y: new surface y
        @param z: MC z
        """
        for yy in range(y + 1, y + 1 + CLEAR_UP):
            if _id(self.live.block(x, yy, z)) in _AIRS:
                continue
            if self.put(x, yy, z, AIR):
                self.stats['cleared'] = self.stats.get('cleared', 0) + 1

    def road_column(self, x: int, z: int):
        """Carriageway, kerb or pavement for one road-parcel column.

        @param x: MC x
        @param z: MC z
        """
        y, b = self.surf(x, z)
        if b == STOCK_ROAD:
            kerb = any(self.surf(x + dx, z + dz)[1] != STOCK_ROAD for dx, dz in N4)
            state, key = (KERB, 'kerb') if kerb else (ASPHALT, 'asphalt')
        elif b == STOCK_PAVE:
            state, key = PAVE, 'pave'
        elif b == GEO_STONE:
            # Geocraft's garden band reaching into the corridor: back of the footway,
            # laid at the adjoining street level (raised stone above it goes).
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

    def lane_column(self, x: int, z: int):
        """Worn pebble surface down the lane centre, grass verge at its edges.

        @param x: MC x
        @param z: MC z
        """
        y, b = self.surf(x, z)
        if b not in (STOCK_ROAD, GEO_STONE):
            self.stats.setdefault('lane_skipped', []).append((x, y, z, b))
            return
        if lane_offset(x + 0.5, z + 0.5) <= LANE_HALF:
            state, key = lane_mix(x, z), 'lane'
        else:
            state, key = VERGE, 'verge'
        if self.put(x, y, z, state):
            self.stats[key] = self.stats.get(key, 0) + 1
        self.fill_below(x, y, z)
        self.clear_above(x, y, z)

    def build(self) -> dict:
        """Plan every column of the eight parcels.

        @returns: stats dict (counts per surface, skipped columns)
        """
        for pid in ROAD_PARCELS:
            for x, z in sorted(self.area.parcels[pid]['set']):
                self.road_column(x, z)
        for pid in LANE_PARCELS:
            for x, z in sorted(self.area.parcels[pid]['set']):
                self.lane_column(x, z)
        return self.stats


def build_plan() -> tuple[Plan, dict]:
    """@returns: (Plan, stats) for the whole Q-044 streetscape"""
    plan = Plan(NAME)
    stats = Streetscape(plan).build()
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
