#!/usr/bin/env python3
"""OSGB36 ↔ Minecraft coordinates for the Southampton2023 Geocraft world.

Offsets come from config/map-maker-offsets.json (extracted from the world's
map-maker-status.json). Convention used by Geocraft for this save:

  minecraft_x = easting  - OFFSET_E
  minecraft_z = -(northing - OFFSET_N)     # north is −Z
  easting     = OFFSET_E + minecraft_x
  northing    = OFFSET_N - minecraft_z

  python3 scripts/osgb.py to-mc 441900 112100
  python3 scripts/osgb.py to-osgb 5652 -2492
  python3 scripts/osgb.py info
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OFFSETS = ROOT / 'config/map-maker-offsets.json'


def load_offsets(path: Path = OFFSETS) -> dict:
    """Load GRID offsets from config.

    @param path: JSON path with OFFSET_E / OFFSET_N and bounds
    @returns: offset dict
    """
    data = json.loads(path.read_text())
    for key in ('OFFSET_E', 'OFFSET_N'):
        if key not in data:
            raise SystemExit(f'{path} missing {key}')
    return data


def to_mc(easting: float, northing: float, offsets: dict | None = None) -> tuple[int, int]:
    """Convert OSGB easting/northing to Minecraft X/Z (integer blocks).

    @param easting: OSGB36 easting (metres)
    @param northing: OSGB36 northing (metres)
    @param offsets: optional offset dict (loads config if omitted)
    @returns: (x, z)
    """
    o = offsets or load_offsets()
    x = int(round(easting - o['OFFSET_E']))
    z = int(round(-(northing - o['OFFSET_N'])))
    return x, z


def to_osgb(x: float, z: float, offsets: dict | None = None) -> tuple[float, float]:
    """Convert Minecraft X/Z to OSGB easting/northing.

    @param x: Minecraft X
    @param z: Minecraft Z
    @param offsets: optional offset dict (loads config if omitted)
    @returns: (easting, northing)
    """
    o = offsets or load_offsets()
    easting = o['OFFSET_E'] + x
    northing = o['OFFSET_N'] - z
    return float(easting), float(northing)


def in_bounds(x: int, z: int, offsets: dict | None = None) -> bool:
    """True if (x, z) lies inside the Geocraft map rectangle.

    @param x: Minecraft X
    @param z: Minecraft Z
    @param offsets: optional offset dict
    @returns: whether the point is inside WEST..EAST, SOUTH..NORTH
    """
    o = offsets or load_offsets()
    return o['WEST'] <= x <= o['EAST'] and o['SOUTH'] <= z <= o['NORTH']


def main(argv: list[str] | None = None) -> int:
    """CLI: info | to-mc E N | to-osgb X Z."""
    argv = list(sys.argv[1:] if argv is None else argv)
    o = load_offsets()
    if not argv or argv[0] == 'info':
        print(json.dumps({
            'grid': o.get('GRID'),
            'OFFSET_E': o['OFFSET_E'],
            'OFFSET_N': o['OFFSET_N'],
            'bounds_mc': {
                'west': o['WEST'], 'east': o['EAST'],
                'south': o['SOUTH'], 'north': o['NORTH'],
            },
            'sea_level': o.get('SEA_LEVEL'),
            'elevation': o.get('ELEVATION_PLUGIN'),
        }, indent=2))
        return 0
    cmd = argv[0]
    if cmd == 'to-mc' and len(argv) == 3:
        e, n = float(argv[1]), float(argv[2])
        x, z = to_mc(e, n, o)
        print(f'OSGB E{e:.1f} N{n:.1f}  ->  MC X{x} Z{z}'
              f'  ({"in" if in_bounds(x, z, o) else "OUT OF"} bounds)')
        return 0
    if cmd == 'to-osgb' and len(argv) == 3:
        x, z = float(argv[1]), float(argv[2])
        e, n = to_osgb(x, z, o)
        print(f'MC X{x:.0f} Z{z:.0f}  ->  OSGB E{e:.1f} N{n:.1f}'
              f'  ({"in" if in_bounds(int(x), int(z), o) else "OUT OF"} bounds)')
        return 0
    print(__doc__, file=sys.stderr)
    return 2


if __name__ == '__main__':
    raise SystemExit(main())
