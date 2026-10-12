#!/usr/bin/env python3
"""Broadlands Rd: side passage between terraces (no. 24 | no. 26).

Aerial: ~1.4 m gap between the #24 and #26 roofs, running back to the gardens.
The gap follows the same 1:3 plot stair as the two terraces (Q-041), so it is
the open columns between their end lines rather than a fixed x. Stray pavement
slabs at 7098/7103 y27 were Cursor 'steps' onto the pavement; pristine is air
there.
"""
import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'scripts'))
from site_kit import Plan, apply  # noqa: E402
from build_broadlands_rd_26_36 import HOUSES as HOUSES_26, pav_row, lane_row  # noqa: E402
from build_broadlands_rd_14_24 import HOUSES as HOUSES_14  # noqa: E402
from terrace import BROADLANDS_N_SLOPE, passage_xs  # noqa: E402

NAME = 'broadlands_rd_passage_24_26'


def build():
    """Gravel alley between the 26 and 24 plot lines, plus two stale pavement slabs cleared."""
    p = Plan(NAME)
    h26, h24 = HOUSES_26[-1], HOUSES_14[0]
    for z in range(-5520, -5595, -1):
        for x in passage_xs(z, h26.pe, h26.f - 11, h24.pw, h24.f - 11, BROADLANDS_N_SLOPE):
            try:
                if not (lane_row(x) < z < pav_row(x)):
                    continue
            except SystemExit:
                continue
            for y in range(23, 26):
                p.set(x, y, z, 'dirt')
            p.set(x, 26, z, 'gravel')
            for y in range(27, 43):
                p.set(x, y, z, 'air')
    for x, zs in ((7098, (-5526, -5525, -5524)), (7103, (-5524, -5523, -5522))):
        for z in zs:
            p.set(x, 27, z, 'air')
    return p


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--apply', action='store_true')
    a = ap.parse_args()
    apply(build(), dry=not a.apply, modifies=('broadlands_rd_20_22', 'broadlands_rd_24_26',
                                              'broadlands_rd_28_30', 'broadlands_rd_28_30_b',
                                              'broadlands_rd_26_36', 'broadlands_rd_14_24'))
