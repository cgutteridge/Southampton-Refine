#!/usr/bin/env python3
"""Dry-run diff for the campus relight (sea lanterns -> invisible ceiling lights).

Regenerates a build's plan with the current generator and compares it with the cells that
build last applied (verification/site/<name>-cells.json). Prints counts of changed cells,
split into the expected lamp swaps, cells the plan no longer sets (already air / owned
elsewhere), and anything else (drift from the live world since the first apply).

With --apply-dry / --apply the regenerated plan is re-applied under the same build name
with the drift cells dropped, so they keep their current world state (e.g. a later grounds
build's surface) instead of being re-cut. --apply-dry runs only apply()'s guards.

  python3 scripts/relight_diff.py highfield_b37 [more names ...]
  python3 scripts/relight_diff.py --apply-dry highfield_b37
  SITE_OWNER=<owner> python3 scripts/relight_diff.py --apply highfield_b37
"""
import importlib
import json
import os
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'scripts'))
OUT = ROOT / 'verification/site'
HOUSE_GROUPS = ('chamberlain_rd_8_58', 'hartley_ave_17_31', 'university_rd_26_28')


def module_for(name):
    """Build script module name for a build name.

    @param name: build name as used in verification/site/<name>-cells.json
    @returns: importable module name under scripts/
    """
    return 'build_highfield_uni_houses' if name in HOUSE_GROUPS else f'build_{name}'


def plan_for(name):
    """Regenerate ``name``'s plan with the current generator (no apply).

    @param name: build name
    @returns: site_kit Plan
    """
    if name in HOUSE_GROUPS:
        os.environ['HOUSES'] = name
    mod = importlib.import_module(module_for(name))
    return mod.build()


def diff(name):
    """Compare the regenerated plan with the last applied cells of ``name``.

    @param name: build name
    @returns: dict with lamp (expected) and other (drift) change counters and samples
    """
    old = {tuple(int(v) for v in k.split(',')): s
           for k, s in json.loads((OUT / f'{name}-cells.json').read_text()).items()}
    plan = plan_for(name)
    new = plan.cells
    lamp, other, omitted, samples, drift = Counter(), Counter(), Counter(), [], []
    for q in set(old) | set(new):
        a, b = old.get(q), new.get(q)
        if a == b:
            continue
        key = f'{(a or "-").split("[")[0][10:]} -> {(b or "-").split("[")[0][10:]}'
        if 'sea_lantern' in (a or '') or 'minecraft:light' in (b or ''):
            lamp[key] += 1
        elif b is None:
            omitted[key] += 1           # no longer set: already air in the world / owned elsewhere
        else:
            other[key] += 1
            drift.append(q)
            if len(samples) < 8:
                samples.append((q, a, b))
    return dict(lamp=lamp, other=other, omitted=omitted, samples=samples, drift=drift, plan=plan,
                old=len(old), new=len(new))


def reapply(r, dry=True):
    """Re-apply the regenerated plan from ``diff()`` under its own build name, minus drift and
    minus cells a later build has since taken over (e.g. a grounds build's colonnade glazing),
    so that later work keeps its state.

    @param r: result of diff()
    @param dry: True = guards only (clashes, footprint), no world change
    @returns: apply() report (None when dry)
    """
    from site_kit import apply, built_cells
    plan = r['plan']
    for q in r['drift']:
        del plan.cells[q]
    owned = built_cells(exclude={plan.name})
    taken = [q for q, st in plan.cells.items() if q in owned and owned[q][1] != st]
    lamps = sum('minecraft:light' in plan.cells[q] for q in taken)
    for q in taken:
        del plan.cells[q]
    print(f'  dropped {len(r["drift"])} drift + {len(taken)} later-build cells ({lamps} of them lights)')
    return apply(plan, dry=dry)


if __name__ == '__main__':
    args = sys.argv[1:]
    mode = args.pop(0) if args and args[0] in ('--apply-dry', '--apply') else None
    for n in args:
        r = diff(n)
        print(f'== {n}: old {r["old"]} new {r["new"]} cells')
        print('  lamp :', dict(r['lamp'].most_common(6)))
        print('  omitted:', sum(r['omitted'].values()), dict(r['omitted'].most_common(3)))
        print('  other:', sum(r['other'].values()), dict(r['other'].most_common(6)))
        for s in r['samples']:
            print('   ', s)
        if mode:
            reapply(r, dry=mode == '--apply-dry')
