#!/usr/bin/env python3
"""Entrances of the other 48,-44 buildings from the portal register (user, 2026-10-16): the rule is in scripts/entrances.py.

  18-A Jubilee Sports Complex "Main" (way 93729745)   38-D Staff Club "Prayer Room" (relation 2139045)
  40-A West Building "Main", 40-B "Stags" (way 34391673)
(42-x are scripts/build_highfield_susu_entrances.py; 57-A is in scripts/build_highfield_su_retail.py.)

  python3 scripts/build_highfield_entrances_48_m44.py            # dry run + printout
  SITE_OWNER=... python3 scripts/build_highfield_entrances_48_m44.py --apply
"""
import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'scripts'))
import portals  # noqa: E402
from site_kit import Plan, World, apply, built_cells, preview  # noqa: E402
from campus import way_cells  # noqa: E402
from entrances import entrances  # noqa: E402

NAME = 'highfield_entrances_48_m44'
BUILDINGS = {'18': '93729745', '38': '2139045', '40': '34391673'}      # university building number -> OSM way
DOUBLE = {'18-A', '40-A'}                       # the Main entrances


def build():
    w = World()
    plan, notes = Plan(NAME), []
    for p in portals.in_cell(48, -44):
        b = p['building']
        if b not in BUILDINGS:
            continue
        entrances(plan, w, way_cells(BUILDINGS[b]), {p['id']: (p['x'], p['z'])}, notes, double=DOUBLE)
    return plan, notes


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--apply', action='store_true')
    a = ap.parse_args()
    plan, notes = build()
    print('\n'.join(notes))
    mod = tuple(sorted({b for b, _s in built_cells(within=plan.cells).values()} - {NAME}))
    print('changes cells of', mod)
    preview(plan, ROOT / f'verification/site/{NAME}-preview.png', scale=2)
    apply(plan, dry=not a.apply, modifies=mod)
