#!/usr/bin/env python3
"""Students' Union B42 (OSM 33830305): one clean rebuild from the portal photos, lidar and aerial (user, 2026-10-16).

Replaces highfield_susu_west's B42 part and every follow-up patch made on it (lower, membrane, greeblies, canopy fix, holes,
entrances). One script, no follow-ups.

Evidence
  photos   reference/portals 800 px, 42-A..D: black steel frames and glass at the ground floor (The Union, Piazz@soton, Latte's),
           black cladding above, white fascia bands, white board-marked concrete beside the Cafe opening, blue-grey glazing above.
  lidar    pristine Geocraft, roof levels by cell (campus.lidar_parts, merge 0): 60 main, 58 south block, 53 west wing; ground 48.
  Google   z20: pale grey flat roofs, the dark membrane roof is the 58 block, three extract-fan housings on the 60 roof.
  portals  scripts/build_highfield_susu_entrances.py (42-A..D), same plan merged here.

  python3 scripts/build_highfield_susu_b42.py            # dry run + preview
  SITE_OWNER=... python3 scripts/build_highfield_susu_b42.py --apply
"""
import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'scripts'))
from site_kit import Plan, World, apply, built_cells, preview  # noqa: E402
from campus import Campus, bbox, lidar_parts, roof_greeblies, way_cells  # noqa: E402
import build_highfield_susu_entrances as ent  # noqa: E402

NAME = 'highfield_susu_b42'
WAY = '33830305'
STYLE = dict(wall='black_concrete', glass='glass', rows=(1,), pier=3,
             ground=dict(wall='black_concrete', glass='glass', pier=3, rows=(1, 2)))      # glazed shopfront storey
OLD = {'highfield_susu_west', 'highfield_susu_west-lower', 'highfield_susu_west-greeblies', 'highfield_susu_west-membrane-spill',
       'highfield_susu_west-canopyfix', 'highfield_susu_west-doorframe', 'highfield_susu_west-holes', 'highfield_susu_west-trenchfix', 'highfield_susu_west-followups-reset',
       'highfield_susu_entrances', 'highfield_q054_micro', 'highfield_q054_micro-canopy-removed', 'highfield_q051_ur'}
KEEP = {'highfield_48_m44_trees'}
FANS = [('fan', 6183, -5546), ('fan', 6181, -5540), ('fan', 6178, -5535)]

cells = way_cells(WAY)
PARTS, INFO = lidar_parts(WAY, 'b42', merge=0, **STYLE)
for pt in PARTS:
    pt.slab = 'gray_concrete' if pt.deck == 58 else 'light_gray_concrete'        # the 58 block is the dark membrane roof
    if pt.deck == 62:
        pt.rows = ()                                                              # raised plant blocks: plain walls, no windows
BOX = bbox(PARTS, pad=3)


PLAZA_X0, PLAZA_Z1 = 6181, -5550          # the plaza frontage: north-facing walls east of the Cafe steps (portals 42-A/B/C photos)


class B42(Campus):
    """The plaza (north) frontage is glass in black steel frames (floor lines and mullions), as in the 42-A/B/C photos; 42-D (west,
    by the steps) shows white board-marked concrete, so every other face is white concrete. A stepped outline has north-facing
    steps on every side, so the frontage is picked by position, not by face alone."""

    def wall_block(self, x, y, z, pt, ex):
        b = super().wall_block(x, y, z, pt, ex)
        if b not in ('minecraft:black_concrete', 'black_concrete'):
            return b
        if any(d == (0, -1) for d in ex) and x >= PLAZA_X0 and z <= PLAZA_Z1:
            floors = set(pt.floors) | {pt.base, pt.deck}
            return 'black_concrete' if (y in floors or (x + z) % 3 == 0) else 'glass'
        return 'white_concrete'


class PlanOverWorld:
    """block() of a plan where it has the cell, else of the live world (entrance code reads the building it is cutting into)."""

    def __init__(self, plan, world):
        self.plan, self.world = plan, world

    def block(self, x, y, z):
        return self.plan.cells.get((x, y, z)) or self.world.block(x, y, z)


def build():
    c = B42(NAME, PARTS, (WAY,), BOX, [], [], avoid_built=False, step_down_stairs=True, max_fill=2)
    plan = c.build(lambda cc: print('fans', roof_greeblies(cc, FANS)))
    w = World()
    ep, notes = ent.build(PlanOverWorld(plan, w))                  # entrances 42-A..D on the new walls
    plan.cells.update(ep.cells)
    col = [(x, y, z) for (x, z) in cells for y in range(48, 72)]
    old = {q for q, (b, _s) in built_cells(within=col).items() if b in OLD}
    clear = Plan(NAME)
    for q in old:
        clear.set(*q, 'minecraft:air')
    clear.cells.update(plan.cells)
    held = {q for q, (b, _s) in built_cells(within=clear.cells).items() if b in KEEP and clear.cells[q].endswith('air')}
    for q in held:
        del clear.cells[q]
    clear.signs, clear.entities = plan.signs, plan.entities
    return clear, notes, c


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--apply', action='store_true')
    a = ap.parse_args()
    plan, notes, c = build()
    print('bands', INFO['bands'], 'ground', INFO['ground'])
    print('\n'.join(notes))
    preview(plan, ROOT / f'verification/site/{NAME}-preview.png', scale=1)
    owners = {b for b, _s in built_cells(within=plan.cells).values()}
    mod = tuple(sorted((owners | OLD | {'highfield_48_m44_ground', 'highfield_q050_opens'}) - {NAME} - KEEP))    # the flush door wall can take one ground cell
    print('replaces blocks of', mod)
    apply(plan, dry=not a.apply, modifies=mod)
