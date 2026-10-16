#!/usr/bin/env python3
"""Q-081 (cell 48,-46): public toilet block, OSM w1482280003 (amenity=toilets, building=yes;
bbox 6217,-5812,6223,-5806).

Evidence
  OSM      way 1482280003: 4-point rotated rectangle ~6 x 5 m, no height / levels tags.
  LIDAR    flat (ground 56 = DSM 56): no height. Single-storey utility block, 3 clear + slab roof.
  Aerial   none covers this column (annotated crop black) -> no roof/colour evidence.
  Not evidenced: wall material, door side -> brick walls, flat slab roof, one door on the south face.

  python3 scripts/build_highfield_toilets_w1482280003.py            # preview + dry-run guards
  SITE_OWNER=... python3 scripts/build_highfield_toilets_w1482280003.py --apply
"""
import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'scripts'))
from site_kit import Plan, World, apply, preview  # noqa: E402
from osm_footprints import OSMIndex  # noqa: E402
from campus import inside, N4  # noqa: E402

NAME = 'highfield_toilets_w1482280003'
WAY = '1482280003'
H = 3
WALL = 'bricks'
ROOF = 'smooth_stone_slab[type=bottom,waterlogged=false]'
FLOOR = 'light_gray_concrete'
AIR = ('air', 'cave_air', 'void_air')


def build():
    ring = next(r[0] for r, t in OSMIndex().buildings if t.get('osm_way_id') == WAY)
    w = World()
    xs, zs = [p[0] for p in ring], [p[1] for p in ring]
    cells = {(x, z) for x in range(int(min(xs)) - 1, int(max(xs)) + 2)
             for z in range(int(min(zs)) - 1, int(max(zs)) + 2) if inside(x + .5, z + .5, ring)}

    def ground(x, z):
        for y in range(95, 40, -1):
            b = (w.block(x, y, z) or '').split('[')[0].replace('minecraft:', '')
            if b not in AIR + ('', 'light', 'bricks', 'spruce_door', 'smooth_stone_slab'):
                return y
    gy = {q: ground(*q) for q in cells}
    base = max(gy.values())
    zmax = max(z for _, z in cells)
    south = sorted(x for x, z in cells if z == zmax)
    door_x = south[len(south) // 2]
    p = Plan(NAME)
    for (x, z), g in gy.items():
        for y in range(g, base + 1):
            p.set(x, y, z, FLOOR)
        edge = sum((x + dx, z + dz) in cells for dx, dz in N4) < 4
        for y in range(base + 1, base + H):
            p.set(x, y, z, WALL if edge else 'air')
        p.set(x, base + H, z, ROOF)
        for y in range(base + H + 1, base + H + 4):
            if (w.block(x, y, z) or '').split('[')[0].replace('minecraft:', '') not in AIR + ('',):
                p.set(x, y, z, 'air')
    p.set(door_x, base + 1, zmax, 'spruce_door[facing=south,half=lower,hinge=left,open=false]')
    p.set(door_x, base + 2, zmax, 'spruce_door[facing=south,half=upper,hinge=left,open=false]')
    return p, cells, base


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--apply', action='store_true')
    a = ap.parse_args()
    plan, cells, base = build()
    print('cells', len(cells), 'floor y', base, 'roof y', base + H)
    preview(plan, ROOT / f'verification/site/{NAME}-preview.png', scale=6)
    apply(plan, dry=not a.apply)
