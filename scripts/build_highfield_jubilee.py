#!/usr/bin/env python3
"""Jubilee Sports Complex (OSM 93729745): one clean rebuild (user, 2026-10-16).

Replaces the Jubilee part of highfield_library_b34_b18, its greeblies/restore/coping/cleanup patches and its 18-A entrance.

Evidence
  photo    portal 18-A (reference/portals, 800 px): a full-height glass curtain wall with dark mullions on a ~2 high red-brick plinth,
           the entrance in a projecting grey metal porch. Other faces: the long low brick box (commons-113513069), and the 2025
           extension in orange brick with deep glazed bays (commons-171520857).
  lidar    pristine Geocraft roof bands (campus.lidar_parts, merge 0): hall 64 and 62, ground 53. The extension post-dates the survey
           (lidar reads it as ground), so it is the rest of the OSM footprint: 2 storeys, roof 62.
  Google   z20 at 6243,-5495: white flat hall roof; beige flat extension roof with six tilted solar panels.

  python3 scripts/build_highfield_jubilee.py            # dry run + preview
  SITE_OWNER=... python3 scripts/build_highfield_jubilee.py --apply
"""
import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'scripts'))
from site_kit import Plan, World, apply, built_cells, preview  # noqa: E402
from campus import Campus, N4, Part, XZ, bbox, lidar_parts, roof_greeblies, way_cells  # noqa: E402
from entrances import entrances  # noqa: E402

NAME = 'highfield_jubilee'
WAY = '93729745'
OLD = {'highfield_library_b34_b18', 'highfield_library_b34_b18-greeblies', 'highfield_library_b34_b18-greeblies-restore',
       'highfield_library_b34_b18-greeblies-coping', 'highfield_library_b34_b18-greeblies-cleanup',
       'highfield_library_b34_b18-greeblies-yardclear', 'highfield_entrances_48_m44'}
KEEP = {'highfield_48_m44_trees'}
cells = way_cells(WAY)
HALL, HALL_INFO = lidar_parts(WAY, 'b18', merge=0, slab='white_concrete', wall='bricks', glass='glass', rows=(1,), pier=4)
G = HALL_INFO['ground']
hall = set().union(*(p.cells for p in HALL))
near = {(x + a, z + b) for x, z in hall for a in range(-2, 3) for b in range(-2, 3)} & cells       # lidar reads rim columns low
for q in near - hall:                                       # give each rim cell to the nearest hall band
    p = min(HALL, key=lambda pt: min(abs(q[0] - x) + abs(q[1] - z) for x, z in pt.cells))
    p.cells.add(q)
hall |= near - hall


def components(cs):
    seen, out = set(), []
    for q in cs:
        if q in seen:
            continue
        comp, stack = set(), [q]
        seen.add(q)
        while stack:
            c = stack.pop()
            comp.add(c)
            for dx, dz in N4:
                n = (c[0] + dx, c[1] + dz)
                if n in cs and n not in seen:
                    seen.add(n)
                    stack.append(n)
        out.append(comp)
    return out


EXT_CELLS = set().union(*[c for c in components(cells - hall) if len(c) >= 50])
EXT = Part('b18x', G, G + 9, G + 10, (G, G + 4), cells=EXT_CELLS, frame=XZ, wall='bricks', glass='glass', rows=(1, 2), pier=4,
           slab='mushroom_stem')
PARTS = HALL + [EXT]
BOX = bbox(PARTS, pad=3)
PANELS = [[(6253, -5480), (6257, -5481), (6258, -5478), (6254, -5477)], [(6268, -5487), (6274, -5488), (6274, -5485), (6269, -5484)],
          [(6257, -5466), (6265, -5468), (6267, -5465), (6258, -5462)], [(6261, -5457), (6269, -5460), (6270, -5457), (6262, -5454)],
          [(6265, -5450), (6273, -5452), (6274, -5447), (6265, -5445)], [(6275, -5473), (6283, -5476), (6284, -5472), (6276, -5470)],
          [(6279, -5465), (6287, -5468), (6288, -5464), (6279, -5462)], [(6282, -5457), (6291, -5460), (6291, -5456), (6283, -5452)]]
FEATURES = [('patch', q, 'blue_terracotta', 1) for q in PANELS]


class Jubilee(Campus):
    """East face of the hall: glass curtain wall with dark mullions on a 2 high brick plinth (portal photo 18-A)."""

    def wall_block(self, x, y, z, pt, ex):
        if pt.name.startswith('b18_') and any(d == (1, 0) for d in ex):
            if y - pt.base < 2 or y in pt.floors[:1]:
                return 'bricks'
            return 'black_concrete' if z % 4 == 0 else 'glass'
        return super().wall_block(x, y, z, pt, ex)


class PlanOverWorld:
    def __init__(self, plan, world):
        self.plan, self.world = plan, world

    def block(self, x, y, z):
        return self.plan.cells.get((x, y, z)) or self.world.block(x, y, z)


def build():
    c = Jubilee(NAME, PARTS, (WAY,), BOX, [], [], avoid_built=False, step_down_stairs=True, max_fill=2)
    plan = c.build(lambda cc: print('solar panels', roof_greeblies(cc, FEATURES)))
    w = World()
    notes = []
    ep = Plan(NAME)
    entrances(ep, PlanOverWorld(plan, w), cells, {'18-A': (6267, -5523)}, notes, double={'18-A'}, flat={'18-A'},
              style={'18-A': ('iron_door', 'gray_concrete')}, check_walls=False)
    plan.cells.update(ep.cells)
    col = [(x, y, z) for (x, z) in cells for y in range(G, 72)]
    old = {q for q, (b, _s) in built_cells(within=col).items() if b in OLD}
    clear = Plan(NAME)
    for q in old:
        clear.set(*q, 'minecraft:air')
    clear.cells.update(plan.cells)
    held = {q for q, (b, _s) in built_cells(within=clear.cells).items() if b in KEEP and clear.cells[q].endswith('air')}
    for q in held:
        del clear.cells[q]
    clear.signs, clear.entities = plan.signs, plan.entities
    return clear, notes


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--apply', action='store_true')
    a = ap.parse_args()
    plan, notes = build()
    print('ground', G, 'bands', HALL_INFO['bands'], 'hall cells', len(hall), 'extension cells', len(EXT_CELLS))
    print('\n'.join(notes))
    preview(plan, ROOT / f'verification/site/{NAME}-preview.png', scale=1)
    owners = {b for b, _s in built_cells(within=plan.cells).values()}
    mod = tuple(sorted((owners | OLD | {'highfield_48_m43_trees', 'highfield_49_m43_trees'}) - {NAME}))    # the porch wall may take a few leaf cells
    print('replaces blocks of', mod)
    apply(plan, dry=not a.apply, modifies=mod)
