#!/usr/bin/env python3
"""Revert the misplaced Broadlands Road "terrace façade" builds (Q-010/Q-012).

terrace_facade_1, _1b, _2, _2b, _2c put a brick street shell on the
pavement / carriageway edge of Broadlands Road. The real houses (OSM
footprints, 20-40 Broadlands Rd) stand ~6 blocks further back behind
front gardens. See site/ISSUES.txt I-009.

Every cell those builds touched is set back to its state just before the
first façade build that touched it, read from the sparse region snapshots:
  cells of facade_1/_1b -> backups/regions/...-Q-010 (before facade_1)
  all other cells       -> backups/regions/...-Q-012 (before facade_2)
The streetscape_q013/_q013b cells never overlapped façade_1, so the Q-012
snapshot already carries their values.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'scripts'))

from site_kit import Plan, World, apply, preview  # noqa: E402

NAME = 'broadlands_facade_revert'
PREFIX = 'portswood_x_broadlands_'
FIRST = ('terrace_facade_1', 'terrace_facade_1b')
LATER = ('terrace_facade_2', 'terrace_facade_2b', 'terrace_facade_2c')
MODIFIES = tuple(PREFIX + n for n in FIRST + LATER) + (
    PREFIX + 'streetscape_r0',
    PREFIX + 'streetscape_q013',
    PREFIX + 'streetscape_q013b',
)
SNAP = ROOT / 'backups/regions'
SNAP_Q010 = SNAP / '2026-10-11-163601-Q-010'
SNAP_Q012 = SNAP / '2026-10-11-174529-Q-012'


def cells(name: str) -> set[tuple[int, int, int]]:
    """Positions written by one archived build.

    @param name: build name without PREFIX
    @returns: set of (x, y, z)
    """
    f = ROOT / 'verification/site' / f'{PREFIX}{name}-cells.json'
    return {tuple(int(v) for v in k.split(',')) for k in json.loads(f.read_text())}


def build_plan() -> Plan:
    """Restore every façade-touched cell from the right snapshot.

    @returns: Plan
    """
    plan = Plan(NAME)
    early = set().union(*(cells(n) for n in FIRST))
    late = set().union(*(cells(n) for n in LATER)) - early
    for src, pos in ((World(SNAP_Q010), early), (World(SNAP_Q012), late)):
        for p in sorted(pos):
            st = src.block(*p)
            if st is None:
                raise SystemExit(f'snapshot has no chunk for {p}')
            plan.set(*p, st)
    return plan


def main() -> None:
    """CLI: preview / dry / apply.

    @returns: None
    """
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--apply', action='store_true')
    args = ap.parse_args()
    plan = build_plan()
    out = ROOT / 'verification/site' / f'{NAME}-preview.png'
    try:
        preview(plan, out)
        print('preview:', out)
    except Exception as e:
        print('preview skipped:', e)
    print(json.dumps(plan.summary()['materials']))
    apply(plan, dry=not args.apply, modifies=MODIFIES)


if __name__ == '__main__':
    main()
