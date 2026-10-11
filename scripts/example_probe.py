#!/usr/bin/env python3
"""Offline probe: print ground block under a place without editing the world.

  python3 scripts/example_probe.py civic
  python3 scripts/example_probe.py 5652 -2492
"""
from __future__ import annotations

import sys

from osgb import to_mc
from site_kit import World

PLACES = {
    'civic': (441900, 112100),
    'oldtown': (441900, 111700),
}


def main(argv: list[str] | None = None) -> int:
    """Print top solid block at a named place or MC X Z.

    @param argv: CLI args
    @returns: exit code
    """
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv:
        print(__doc__, file=sys.stderr)
        return 2
    if argv[0] in PLACES:
        e, n = PLACES[argv[0]]
        x, z = to_mc(e, n)
        label = f'{argv[0]} OSGB E{e} N{n}'
    else:
        x, z = int(argv[0]), int(argv[1])
        label = f'MC X{x} Z{z}'
    w = World()
    y = w.ground(x, z, top=200, bottom=0)
    st = w.block(x, y, z)
    print(f'{label} -> MC ({x}, {y}, {z})  top={st}')
    for dy in range(1, 8):
        print(f'  +{dy}: {w.block(x, y + dy, z)}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
