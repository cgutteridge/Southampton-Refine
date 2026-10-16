#!/usr/bin/env python3
"""Remove the early (11-12 Oct) Broadlands Rd terrace house builds, back to pristine Geocraft.

User decision 2026-10-16: these were built before the layered-pass process; they come back as normal
house features when the radial ring reaches them. Streetscape, roads, lanes and kerbs stay.

Every cell any of REMOVED wrote is set to what stands there without them: the block of a kept build that
also owns the cell (site_kit.owned_in with exclude=removed), otherwise the pristine Geocraft block
(config/world.json pristine_region_path).

  .venv/bin/python scripts/remove_early_broadlands_houses.py houses|roads            # dry run
  SITE_OWNER=<owner> .venv/bin/python scripts/remove_early_broadlands_houses.py roads --apply
"""
from __future__ import annotations

import argparse
import json

from script_env import ROOT

from site_kit import Plan, World, apply, owned_in, _parse_cells_file, OUT  # noqa: E402

HOUSES = tuple(f'broadlands_rd_{n}' for n in ('2_12', '14_24', '20_22', '24_26', '26_36', '28_30', '28_30_b',
                                               '40_46', '48_54', '56_62', 'passage_24_26'))
# Road / kerb / track builds of the same early process in cells 54..56 x -45..-43 (user 2026-10-16: the layered
# ground pass handles roads and paths now). Later layered-pass builds (rd_155_165 and up) are not touched.
ROADS = ('broadlands_rd_streetscape', 'broadlands_ring1_lanes', 'broadlands_ring1_roads', 'broadlands_facade_revert',
         'portswood_ring1_streetscape_kerbs', 'portswood_x_broadlands_kerb_proof', 'portswood_x_broadlands_streetscape_q013',
         'portswood_x_broadlands_streetscape_q013b', 'portswood_x_broadlands_streetscape_r0',
         'portswood_x_broadlands_terrace_facade_1', 'portswood_x_broadlands_terrace_facade_1b',
         'portswood_x_broadlands_terrace_facade_2', 'portswood_x_broadlands_terrace_facade_2b',
         'portswood_x_broadlands_terrace_facade_2c')
GROUPS = {'houses': HOUSES, 'roads': ROADS}


def build_plan(group, removed) -> Plan:
    cells = set()
    for n in removed:
        adds, air = _parse_cells_file(OUT / f'{n}-cells.json')
        cells |= set(adds) | set(air)
    kept = owned_in(cells, exclude=removed)
    pristine = World(json.loads((ROOT / 'config/world.json').read_text())['pristine_region_path'])
    plan = Plan(f'remove_early_broadlands_{group}')
    for p in sorted(cells):
        st = kept[p][1] if p in kept else pristine.block(*p)
        if st is None:
            raise SystemExit(f'pristine world has no chunk for {p}')
        plan.set(*p, st)
    print(f'{len(cells)} cells: {len(kept)} to a kept build, {len(cells) - len(kept)} to pristine Geocraft')
    return plan


if __name__ == '__main__':
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('group', choices=sorted(GROUPS))
    ap.add_argument('--apply', action='store_true')
    a = ap.parse_args()
    plan = build_plan(a.group, GROUPS[a.group])
    print(json.dumps(plan.summary()['materials']))
    apply(plan, dry=not a.apply, modifies=GROUPS[a.group])
