#!/usr/bin/env python3
"""Walkability search over the saved world: can a player walk from A to B?

Feet cell passable if feet and head are non-solid and the block below is solid
(or a stair/slab). Steps of ±1 allowed where a stair/slab makes it walkable.

  python3 scripts/site_walk.py x,y,z x,y,z [box: x0,z0,x1,z1]
"""
import sys
from collections import deque

from site_kit import World

OPEN_EXACT = {
    'air', 'cave_air', 'light', 'water', 'lantern', 'soul_lantern', 'end_rod', 'iron_chain',
    'torch', 'wall_torch', 'rail', 'vine', 'short_grass', 'tall_grass', 'fern', 'large_fern',
    'moss_carpet', 'flower_pot', 'ladder', 'lever', 'tripwire',
}
OPEN_SUFFIX = (
    '_door', '_sign', '_button', '_carpet', '_torch', '_rail', '_pressure_plate', '_banner',
    '_sapling', '_tulip',
)
OPEN_PREFIX = ('potted_',)


def solid(b):
    """True if a player can stand on it / cannot walk through it.

    @param b: block state string or None
    @returns: whether the block is solid for walking
    """
    if b is None:
        return False
    n = b.split(':')[-1].split('[')[0]
    return not (n in OPEN_EXACT or n.endswith(OPEN_SUFFIX) or n.startswith(OPEN_PREFIX))


def walk(w, start, goal, box):
    """BFS walkability from start to goal inside an XZ box.

    @param w: site_kit.World
    @param start: (x,y,z) feet position
    @param goal: (x,y,z) feet position
    @param box: (x0, z0, x1, z1) inclusive search bounds
    @returns: path list, or None if unreachable
    """
    x0, z0, x1, z1 = box

    def ok(x, y, z):
        return (x0 <= x <= x1 and z0 <= z <= z1 and not solid(w.block(x, y, z))
                and not solid(w.block(x, y + 1, z)) and solid(w.block(x, y - 1, z)))

    seen = {start: None}
    q = deque([start])
    while q:
        c = q.popleft()
        if c == goal:
            path = []
            while c:
                path.append(c)
                c = seen[c]
            return path[::-1]
        x, y, z = c
        for dx, dz in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            for dy in (0, 1, -1):
                n = (x + dx, y + dy, z + dz)
                if n in seen or not ok(*n):
                    continue
                below_n = w.block(n[0], n[1] - 1, n[2]) or ''
                if dy == 1 and 'stairs' not in below_n and 'slab' not in below_n:
                    continue
                if dy == 1 and solid(w.block(x, y + 2, z)):
                    continue
                seen[n] = c
                q.append(n)
                break
    return None


if __name__ == '__main__':
    a = tuple(map(int, sys.argv[1].split(',')))
    b = tuple(map(int, sys.argv[2].split(',')))
    box = tuple(map(int, sys.argv[3].split(','))) if len(sys.argv) > 3 else (5600, -2600, 5750, -2400)
    p = walk(World(), a, b, box)
    if p:
        print(f'REACHABLE in {len(p)} steps', p[::max(1, len(p) // 12)])
    else:
        print('NOT REACHABLE', a, '->', b)
