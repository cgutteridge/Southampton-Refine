#!/usr/bin/env python3
"""Q-045: ring-1 rear lanes, driveways and car-park aisles around the Broadlands focus, as whole
coverage parcels (Claude, 12 Oct 2026).

Rules of thumb (CRAFTSMANSHIP §3a), with the surface chosen by OSM tag (user, Q-045):
  asphalt    service=driveway / parking_aisle (untagged surface, flats and store car parks
             off Harrison Road and Portswood Road) and surface=asphalt service ways:
             gray_concrete over the whole parcel, no kerb, no verge.
  alley      service=alley, surface=asphalt (w116387635, width=2): gray_concrete within 1 of
             the OSM centreline, grass verge on the rest.
  gravel     service=alley, untagged or dirt (w176648868, w176648867): the §3a gravel /
             coarse_dirt / dirt_path mix within 1.5 of the centreline, grass verge on the rest.
  footpath   highway=path, surface=dirt (w140004021): coarse_dirt / dirt_path within 1 of the
             line, grass on the rest.
Aerial sanity check (hampshire-hub z18 5x5 mosaic-z18-5x5-centre-130063-87835, overlay
verification/site/q045/aerial-lanes.png): the driveways and the parking aisle read as grey
paved ground round the flats and the store; the alleys are narrow strips behind gardens.

Geometry, as Q-044: Geocraft's corridor (OSM route, trusted) at the PRISTINE surface Y; Geocraft
stone inside a parcel is laid at the adjoining street Y; the bed is re-solidified down to the
lowest cell any superseded streetscape pass wrote; unowned blocks above are cleared.
Kept on purpose (written unchanged so signoff sees them as deliberate):
  - Geocraft building edges: columns whose pristine top is not ground (carpet roof over brick,
    one plank shed) are the outer wall row of an unrebuilt Geocraft building rasterised one
    block into the lane. Clearing them would hole that building, so the wall stays and only
    its carpet fringe goes; no lane surface is laid there.
  - Trees: canopy at least CANOPY_CLEAR above the surface and standing trunks (the aerial
    shows canopies over the lanes); grass stays under a trunk. Leaves lower than that sit on
    the lane (stubs of Geocraft trees buried under the east loop of w176441832) and go.
Cells owned by any build not in MODIFIES (house builds, the Q-044 streetscape) are never written.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'scripts'))

from coverage import LEFTOVER_TOP, load_area, osm_ref  # noqa: E402
from osm_footprints import OSMIndex  # noqa: E402
from site_kit import Plan, World, apply, built_cells, preview  # noqa: E402
from build_broadlands_rd_streetscape import (  # noqa: E402
    AIR, ASPHALT, COARSE, DIRT_PATH, GEO_STONE, STOCK_PAVE, STOCK_ROAD, VERGE, N4, _AIRS, _id,
    lane_mix, street_surface,
)

NAME = 'broadlands_ring1_lanes'
CFG = json.loads((ROOT / 'config/world.json').read_text())

# OSM way -> (surface class, half-width of the worn strip; None = whole parcel).
WAYS = {
    'w177807843': ('asphalt', None), 'w177807844': ('asphalt', None),
    'w177807845': ('asphalt', None), 'w177963540': ('asphalt', None),
    'w178001287': ('asphalt', None), 'w178001288': ('asphalt', None),
    'w178001289': ('asphalt', None), 'w178209829': ('asphalt', None),
    'w178209830': ('asphalt', None), 'w271816493': ('asphalt', None),
    'w820869320': ('asphalt', None), 'w820869321': ('asphalt', None),
    'w1039703270': ('asphalt', None), 'w1039703271': ('asphalt', None),
    'w176441832': ('asphalt', None), 'w1021988335': ('asphalt', None),
    'w116387635': ('alley', 1.0),
    'w176648868': ('gravel', 1.5), 'w176648867': ('gravel', 1.5),
    'w140004021': ('footpath', 1.0),
}
PARCELS = (
    'path:w1021988335@56,-44', 'path:w1039703270@56,-43', 'path:w1039703271@56,-43',
    'path:w116387635@55,-43', 'path:w116387635@55,-44', 'path:w116387635@56,-44',
    'path:w140004021@56,-45', 'path:w176441832@56,-43', 'path:w176441832@56,-44',
    'path:w176648867@55,-43', 'path:w176648868@54,-43', 'path:w177807843@55,-43',
    'path:w177807844@55,-43', 'path:w177807845@55,-43', 'path:w177963540@55,-45',
    'path:w177963540@56,-45', 'path:w178001287@55,-45', 'path:w178001288@55,-45',
    'path:w178001288@56,-45', 'path:w178001289@55,-45', 'path:w178209829@56,-45',
    'path:w178209830@56,-45', 'path:w271816493@55,-45', 'path:w820869320@56,-43',
    'path:w820869321@56,-43',
)
# Superseded streetscape passes on this ground plus the I-009 façades and their revert
# (built_cells() drops a skipped build's air writes too; see Q-044 TOKEN NOTES).
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
GROUND = (STOCK_ROAD, STOCK_PAVE, GEO_STONE, GRANITE, GRASS)
CANOPY_CLEAR = 3        # lowest height above the surface at which overhanging leaves stay


def path_mix(x: int, z: int) -> str:
    """Deterministic dirt-footpath surface: half coarse dirt, half worn path.

    @param x: MC x
    @param z: MC z
    @returns: block state
    """
    return COARSE if ((x * 73856093) ^ (z * 19349663)) % 100 < 50 else DIRT_PATH


def line_offset(pts: list, x: float, z: float) -> float:
    """Distance from (x, z) to the nearest segment of a polyline.

    @param pts: [(x, z), ...] polyline vertices in MC coordinates
    @param x: MC x (column centre)
    @param z: MC z (column centre)
    @returns: distance in blocks
    """
    best = math.inf
    for (ax, az), (bx, bz) in zip(pts, pts[1:]):
        dx, dz = bx - ax, bz - az
        L = dx * dx + dz * dz
        t = 0.0 if L == 0 else max(0.0, min(1.0, ((x - ax) * dx + (z - az) * dz) / L))
        best = min(best, math.hypot(x - (ax + t * dx), z - (az + t * dz)))
    return best


def way_lines() -> dict:
    """OSM centrelines of the WAYS.

    @returns: {way ref: [(x, z), ...]}
    """
    idx = OSMIndex()
    lines = {}
    for (_n, _hw, pts), p in zip(idx.streets, idx.street_props):
        ref = osm_ref(p)
        if ref in WAYS:
            lines[ref] = pts
    missing = set(WAYS) - set(lines)
    if missing:
        raise SystemExit(f'OSM ways not found: {sorted(missing)}')
    return lines


class Lanes:
    """Plan every column of the ring-1 lane / driveway parcels."""

    def __init__(self, plan: Plan):
        """@param plan: Plan to fill"""
        self.plan = plan
        self.pristine = World(CFG['pristine_region_path'])
        self.live = World()
        self.area = load_area('broadlands')
        self.owned = built_cells(exclude=set(MODIFIES) | {NAME})
        self.dug = self._lowest_modified()
        self.lines = way_lines()
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

    def count(self, key: str):
        """@param key: stats counter to bump"""
        self.stats[key] = self.stats.get(key, 0) + 1

    def surf(self, x: int, z: int) -> tuple[int, str]:
        """Cached pristine street surface (through Geocraft road-label signs).

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
            self.count('protected')
            return False
        self.plan.set(x, y, z, state)
        return True

    def fill_below(self, x: int, y: int, z: int):
        """Solid bed from under the surface down to the lowest superseded write.

        @param x: MC x
        @param y: new surface y
        @param z: MC z
        """
        for yy in range(self.dug.get((x, z), y), y):
            b = _id(self.pristine.block(x, yy, z))
            self.put(x, yy, z, b if b not in _AIRS else 'minecraft:dirt')

    def clear_above(self, x: int, y: int, z: int):
        """Air unowned live blocks above the surface up to LEFTOVER_TOP; trunks and high canopy stay.

        @param x: MC x
        @param y: new surface y
        @param z: MC z
        """
        for yy in range(y + 1, LEFTOVER_TOP + 1):
            s = self.live.block(x, yy, z)
            if _id(s) in _AIRS:
                continue
            if _id(s).endswith('_log') or (_id(s).endswith('_leaves') and yy >= y + CANOPY_CLEAR):
                if self.put(x, yy, z, s):
                    self.count('tree_kept')
            elif self.put(x, yy, z, AIR):
                self.count('cleared')

    def keep_building_edge(self, x: int, z: int) -> bool:
        """Write an unrebuilt Geocraft building's edge column unchanged, minus its carpet fringe.

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
        self.count('building_edge_kept')
        return True

    def column(self, pid: str, x: int, z: int):
        """Surface for one parcel column by its way's class.

        @param pid: parcel id (path:<way>@tx,tz)
        @param x: MC x
        @param z: MC z
        """
        way = pid.split(':')[1].split('@')[0]
        cls, half = WAYS[way]
        y, b = self.surf(x, z)
        if b not in GROUND:
            if not self.keep_building_edge(x, z):
                self.stats.setdefault('skipped', []).append((x, y, z, b))
            return
        if b == GEO_STONE:
            ys = [self.surf(x + dx, z + dz)[0] for dx, dz in N4
                  if self.surf(x + dx, z + dz)[1] in (STOCK_ROAD, STOCK_PAVE, GRANITE)]
            if ys and max(ys) < y:
                y = max(ys)
        strip = half is None or line_offset(self.lines[way], x + 0.5, z + 0.5) <= half
        trunk = _id(self.live.block(x, y + 1, z)).endswith('_log')
        if trunk:
            state, key = GRASS + '[snowy=false]', 'under_tree'
        elif not strip:
            state, key = VERGE, 'verge'
        elif cls in ('asphalt', 'alley'):
            state, key = ASPHALT, cls
        elif cls == 'gravel':
            state, key = lane_mix(x, z), 'gravel'
        else:
            state, key = path_mix(x, z), 'footpath'
        if self.put(x, y, z, state):
            self.count(key)
        self.fill_below(x, y, z)
        self.clear_above(x, y, z)

    def build(self) -> dict:
        """Plan every column of PARCELS.

        @returns: stats dict (counts per surface, skipped columns)
        """
        for pid in PARCELS:
            for x, z in sorted(self.area.parcels[pid]['set']):
                self.column(pid, x, z)
        return self.stats


def build_plan() -> tuple[Plan, dict]:
    """@returns: (Plan, stats) for the whole Q-045 lane set"""
    plan = Plan(NAME)
    stats = Lanes(plan).build()
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
