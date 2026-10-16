#!/usr/bin/env python3
"""Students' Union Retail Centre B57 (OSM 33830236), Highfield: one clean rebuild (user, 2026-10-16: start it over).

Replaces the earlier lidar-band build (highfield_library_b34_b18 b57), its q052 massing and the follow-up patches. Kept simple:
one flat roof, one colour, two roof features.

Evidence
  OSM      way 33830236, building:levels 2.
  lidar    pristine Geocraft, this footprint: flat roof at 61 (282 cells; the 58/59 columns are the rim, lidar reads edges low),
           ground 54 -> 2 storeys.
  Google   z20 sheet at 6238,-5563: pale white flat roof, a long solar array on the north half, one small plant box at the east end.
  photo    reference/aerial/highfield-user/union-shop-front.webp (user, 2026-10-16), the front face: two storeys; glazed shopfront
           in dark frames under a bright blue "union shop" sign band across the right three quarters; a brick pier bay at the left end
           with a glazed door; white rendered upper storey with two dark-framed windows; red brick end walls; a deep flat roof
           cantilevered ~4 forward over the whole front on two grey steel posts (dark grey fascia, cream soffit).
  portal   57-A "Union Shop" at 6225,-5566 (no photo): the door position; faces out of the south-west long face.

  python3 scripts/build_highfield_su_retail.py            # preview + dry run
  SITE_OWNER=... python3 scripts/build_highfield_su_retail.py --apply
"""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'scripts'))
from site_kit import Plan, apply, built_cells, preview  # noqa: E402
from campus import Campus, Part, bbox, roof_greeblies, way_cells  # noqa: E402
from entrances import entrances  # noqa: E402

NAME = 'highfield_su_retail'
WAY = '33830236'
BASE, DECK = 54, 61
cells = way_cells(WAY)
PART = Part('b57', BASE, DECK, floors=(BASE, BASE + 3), cells=cells, wall='white_concrete', glass='glass',
            slab='calcite', rows=(1,), pier=3,      # 2x1 window pairs (facade rhythm rule), not tall slots
            ground=dict(wall='gray_concrete', glass='glass', pier=3, rows=(1, 2)))      # glazed shopfront: 2x2 panes, dark steel frames
BOX = bbox([PART], pad=3)
OLD_RETAIL = {'highfield_library_b34_b18', 'highfield_library_b34_b18-greeblies', 'highfield_library_b34_b18-retail-fill', 'highfield_q052_b57'}
KEEP = {'highfield_48_m44_trees'}
BAY_X = min(x for x, _ in cells) + 7       # the brick bay at the west end of the front
CANOPY = 4                                  # the roof overhangs the front by this many blocks
DOORS = []                                  # portal 57-A "Union Shop" (reference/portals): scripts/entrances.py, below
# roof features, measured off the Google sheet (see docstring): the solar array and the plant box
FEATURES = [
    ('patch', [(6234, -5573), (6250, -5567), (6249, -5564), (6234, -5570)], 'light_gray_concrete', 1),
    ('plinth', [(6254, -5564), (6256, -5564), (6256, -5562), (6254, -5562)], 1, 'light_gray_concrete'),
]


class Retail(Campus):
    """Per-face materials from the photo. The outline is a stepped diagonal, so most front cells are corners with two exposures and
    Campus's one-exposure window rule leaves them as plain wall: the front is designed here instead, for every south-facing cell.
    Front: dark steel plinth, two rows of glazing between steel posts every 6th cell, the sign band, white render with window pairs
    above; the brick bay at the west end. Everything else (end walls, back) is brick."""

    def wall_block(self, x, y, z, pt, ex):
        b = super().wall_block(x, y, z, pt, ex).replace('minecraft:', '')
        if not any(d == (0, 1) for d in ex):
            return 'bricks' if b in ('white_concrete', 'gray_concrete') else b
        rel = y - BASE
        if y in (pt.base, pt.deck):
            return b
        if x <= BAY_X and rel < 3:
            return 'bricks'                                                          # the brick pier bay with its glazed door
        if rel in (1, 2):
            return 'gray_concrete' if x % 6 == 0 else 'glass'                        # shopfront: glazing between steel posts
        if rel == 3:
            return 'light_blue_concrete' if x > BAY_X else 'bricks'                  # "union shop" sign band
        return 'glass' if (rel == 4 and x > BAY_X + 2 and x % 5 in (1, 2)) else 'white_concrete'      # white render, window pairs


def canopy(plan, plan_world):
    """The roof cantilevered over the front: slab rows out from every south-facing wall cell, a dark fascia, two steel posts."""
    front = sorted((x, z) for (x, z) in cells if (x, z + 1) not in cells)
    for x, z in front:
        for k in range(1, CANOPY + 1):
            q = (x, DECK, z + k)
            if (plan_world.block(*q) or 'minecraft:air').split('[')[0][10:] in ('air', 'cave_air'):        # never through a tree crown
                plan.set(x, DECK, z + k, 'light_gray_concrete')
                if k == CANOPY:
                    plan.set(x, DECK + 1, z + k, 'gray_concrete')
    for x, z in (front[0], front[-1]):
        for y in range(BASE + 1, DECK):
            plan.set(x, y, z + CANOPY, 'gray_concrete')


def make():
    return Retail(NAME, [PART], (WAY,), BOX, DOORS, [], avoid_built=False)


class PlanOverWorld:
    """block() of a plan where it has the cell, else of the live world."""

    def __init__(self, plan, world, ignore=()):
        self.plan, self.world, self.ignore = plan, world, set(ignore)

    def block(self, x, y, z):
        if (x, y, z) in self.ignore and (x, y, z) not in self.plan.cells:
            return 'minecraft:air'                  # this build's own cells from an earlier run: not part of the ground
        if (x, y, z) in self.plan.cells:
            return self.plan.cells[(x, y, z)]
        return self.world.block(x, y, z)


def build():
    c = make()
    from site_kit import OUT, World, _parse_cells_file
    live = World()
    try:
        oldown, _air = _parse_cells_file(OUT / f'{NAME}-cells.json')
    except (OSError, ValueError, KeyError):
        oldown = {}
    plan = c.build(lambda cc: print('roof features', roof_greeblies(cc, FEATURES)))
    ep, notes = Plan(NAME), []
    entrances(ep, PlanOverWorld(plan, World(), oldown), cells, {'57-A': (6225, -5566)}, notes, double={'57-A'},
              style={'57-A': ('iron_door', 'gray_concrete')}, check_walls=False)      # portal 57-A: the glazed door in the brick bay
    entrances(ep, PlanOverWorld(plan, World(), oldown), cells, {'57-shop': (6238, -5563)}, notes, wide={'57-shop'},
              style={'57-shop': (None, 'gray_concrete')}, check_walls=False)       # the shop's wide automatic doors (photo): an open 6-wide entrance
    plan.cells.update(ep.cells)
    canopy(plan, PlanOverWorld(plan, live, oldown))      # after the doors: the canopy must not count as the ground outside them
    OUTSIDE_OK = 'the roof cantilevers ~4 over the front on two steel posts: photo reference/aerial/highfield-user/union-shop-front.webp'
    print('\n'.join(notes))
    try:                                              # an earlier version of this build (Campus door, approach steps): put back what was under it
        prev = built_cells(exclude=(NAME,), within=list(oldown))
        for q in oldown:
            if q not in plan.cells:
                plan.set(*q, prev[q][1] if q in prev else 'minecraft:air')
    except (OSError, ValueError, KeyError):
        pass
    # clear what the earlier retail builds left standing on the footprint (and one cell round it) above the plaza, then the new
    # shell on top; trees and other builds' blocks are never cleared
    col = [(x + a, y, z + b) for x, z in cells for a in (-1, 0, 1) for b in (-1, 0, 1) for y in range(BASE + 1, DECK + 6)]
    old = {q for q, (b, _s) in built_cells(within=col).items() if b in OLD_RETAIL}
    clear = Plan(NAME)
    for q in old:
        clear.set(*q, 'minecraft:air')
    clear.cells.update(plan.cells)
    held = {q for q, (b, _s) in built_cells(within=clear.cells).items() if b in KEEP and clear.cells[q].endswith('air')}
    for q in held:
        del clear.cells[q]                                  # the new shell's air clearing must not cut a tree
    clear.signs, clear.entities = plan.signs, plan.entities
    clear.outside_footprint_ok = OUTSIDE_OK
    return clear, c


def owners(plan):
    return sorted({b for b, _s in built_cells(within=plan.cells).values()})


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--apply', action='store_true')
    a = ap.parse_args()
    plan, c = build()
    print('doors', c.door_cells, 'cells', len(plan.cells))
    mod = tuple(sorted((set(owners(plan)) | OLD_RETAIL) - {NAME} - KEEP))
    print('replaces blocks of', mod)
    preview(plan, ROOT / f'verification/site/{NAME}-preview.png', scale=2)
    apply(plan, dry=not a.apply, modifies=mod)
