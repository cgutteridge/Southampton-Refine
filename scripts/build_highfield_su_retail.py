#!/usr/bin/env python3
"""Students' Union Retail Centre B57 (OSM 33830236), Highfield: one clean rebuild (user, 2026-10-16: start it over).

Replaces the earlier lidar-band build (highfield_library_b34_b18 b57), its q052 massing and the follow-up patches. Kept simple:
one flat roof, one colour, two roof features.

Evidence
  OSM      way 33830236, building:levels 2.
  lidar    pristine Geocraft, this footprint: flat roof at 61 (282 cells; the 58/59 columns are the rim, lidar reads edges low),
           ground 54 -> 2 storeys.
  Google   z20 sheet at 6238,-5563: pale white flat roof, a long solar array on the north half, one small plant box at the east end.
  photo    commons-24864637 (SUSU 2013 entrance): white panels with a glazed shopfront.

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
            ground=dict(wall='white_concrete', glass='glass', pier=3, rows=(1, 2)))     # glazed shopfront: 2x2 panes
BOX = bbox([PART], pad=3)
OLD_RETAIL = {'highfield_library_b34_b18', 'highfield_library_b34_b18-greeblies', 'highfield_library_b34_b18-retail-fill', 'highfield_q052_b57'}
KEEP = {'highfield_48_m44_trees'}
DOORS = []                                  # portal 57-A "Union Shop" (reference/portals): scripts/entrances.py, below
# roof features, measured off the Google sheet (see docstring): the solar array and the plant box
FEATURES = [
    ('patch', [(6234, -5573), (6250, -5567), (6249, -5564), (6234, -5570)], 'light_gray_concrete', 1),
    ('plinth', [(6254, -5564), (6256, -5564), (6256, -5562), (6254, -5562)], 1, 'light_gray_concrete'),
]


def make():
    return Campus(NAME, [PART], (WAY,), BOX, DOORS, [], avoid_built=False)


class PlanOverWorld:
    """block() of a plan where it has the cell, else of the live world."""

    def __init__(self, plan, world):
        self.plan, self.world = plan, world

    def block(self, x, y, z):
        return self.plan.cells.get((x, y, z)) or self.world.block(x, y, z)


def build():
    c = make()
    plan = c.build(lambda cc: print('roof features', roof_greeblies(cc, FEATURES)))
    from site_kit import OUT, World, _parse_cells_file
    ep, notes = Plan(NAME), []
    entrances(ep, PlanOverWorld(plan, World()), cells, {'57-A': (6225, -5566)}, notes, double={'57-A'}, flat={'57-A'},
              style={'57-A': ('iron_door', 'white_concrete')}, check_walls=False)      # Union Shop: glazed shop doors, white frame
    plan.cells.update(ep.cells)
    print('\n'.join(notes))
    try:                                              # an earlier version of this build (Campus door, approach steps): put back what was under it
        oldown, _air = _parse_cells_file(OUT / f'{NAME}-cells.json')
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
