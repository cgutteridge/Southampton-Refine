#!/usr/bin/env python3
"""Q-135 (cell 47,-46): private covered bike shed, OSM w226141861 (amenity=bicycle_parking,
bicycle_parking=shed, capacity=27, access=private, building=yes; bbox 6052,-5802,6057,-5792).

Evidence
  OSM      way 226141861: 4-point rotated rectangle ~2 x 10 m, no height / levels tags.
  LIDAR    none usable (previous campus note: "no LIDAR height"); open-sided shed read as a flat
           canopy ~3 m clear (same type as the B35 bike shed 242322573).
  Not evidenced: roof/post material (aerial z18 blurry, colour not distinguishable) -> stone slab roof on iron-bar posts every 3rd edge cell.

  python3 scripts/build_highfield_bike_shed_w226141861.py            # preview + dry-run guards
  SITE_OWNER=... python3 scripts/build_highfield_bike_shed_w226141861.py --apply
"""
import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'scripts'))
from site_kit import Plan, World, apply, preview  # noqa: E402
from osm_footprints import OSMIndex, PRISTINE  # noqa: E402
from campus import inside, N4  # noqa: E402

NAME = 'highfield_bike_shed_w226141861'
WAY = '226141861'
H = 3
ROOF = 'smooth_stone_slab[type=bottom,waterlogged=false]'
POST = 'iron_bars'
FLOOR = 'light_gray_concrete'
AIR = ('air', 'cave_air', 'void_air')


def build():
    ring = next(r[0] for r, t in OSMIndex().buildings if t.get('osm_way_id') == WAY)
    w = World()
    xs, zs = [p[0] for p in ring], [p[1] for p in ring]
    cells = {(x, z) for x in range(int(min(xs)) - 1, int(max(xs)) + 2)
             for z in range(int(min(zs)) - 1, int(max(zs)) + 2) if inside(x + .5, z + .5, ring)}


    pw = World(PRISTINE)  # ground from the untouched Geocraft save (not this build's own blocks)

    def ground(x, z):
        for y in range(95, 40, -1):
            if (pw.block(x, y, z) or '').split('[')[0].replace('minecraft:', '') not in AIR + ('', 'light', 'oak_leaves', 'oak_log', 'birch_leaves', 'spruce_leaves', 'water'):
                return y
    # a stream/pond edge clips the footprint: do not build the shed over open water
    cells = {q for q in cells if (pw.block(q[0], 53, q[1]) or '').replace('minecraft:', '') .split('[')[0] != 'water'}
    gy = {q: ground(*q) for q in cells}
    base = max(gy.values())
    print('ground y per column', sorted(set(gy.values())))
    p = Plan(NAME)
    for (x, z), g in gy.items():
        for y in range(g, base + 1):
            p.set(x, y, z, FLOOR)
        edge = sum((x + dx, z + dz) in cells for dx, dz in N4) < 4
        for y in range(base + 1, base + H + 1):
            p.set(x, y, z, POST if edge and (x + z) % 3 == 0 else 'air')
        p.set(x, base + H, z, ROOF)
        for y in range(base + H + 1, base + H + 4):
            if (w.block(x, y, z) or '').split('[')[0].replace('minecraft:', '') not in AIR + ('',):
                p.set(x, y, z, 'air')
    return p, cells, base


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--apply', action='store_true')
    a = ap.parse_args()
    plan, cells, base = build()
    print('cells', len(cells), 'floor y', base, 'roof y', base + H)
    preview(plan, ROOT / f'verification/site/{NAME}-preview.png', scale=6)
    apply(plan, dry=not a.apply, modifies=[])
