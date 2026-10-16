#!/usr/bin/env python3
"""Stage 5a: strip Geocraft above-ground features across one whole cell (dry-run by default).

Plans air for every tree / plant / junk block directly above each column's surface, for
every column inside the cell (no margin, so neighbours are not written). Records the stage
in site/cells/<tx>_<tz>-STAGES.json so a later pass can see what has been applied.

  python3 scripts/strip_cell_above_ground.py --cell 48,-45            # dry-run + preview
  SITE_OWNER=<lock-owner> python3 scripts/strip_cell_above_ground.py --cell 48,-45 --apply
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'scripts'))



def parse_cell(raw: str) -> tuple[int, int]:
    """Parse ``tx,tz``."""
    a, b = raw.split(',')
    return int(a), int(b)

from foliage import strip_foliage_above_surface  # noqa: E402
from site_kit import OUT, Plan, World, apply, preview  # noqa: E402

STAGE = 'above-ground-strip'


def cell_columns(cell: tuple[int, int]) -> list[tuple[int, int]]:
    """Every (x, z) column inside one 128-block coverage cell.

    @param cell: (tx, tz)
    @returns: list of columns
    """
    x0, z0 = cell[0] * 128, cell[1] * 128
    return [(x, z) for x in range(x0, x0 + 128) for z in range(z0, z0 + 128)]


def stage_record(cell: tuple[int, int], status: str, plan_name: str, cells: int) -> Path:
    """Write or update the per-cell stage record.

    @param cell: (tx, tz)
    @param status: planned | applied
    @param plan_name: plan name used for the stage
    @param cells: blocks planned
    @returns: path written
    """
    path = ROOT / 'site/cells' / f'{cell[0]}_{cell[1]}-STAGES.json'
    rec = json.loads(path.read_text()) if path.exists() else {'cell': f'{cell[0]},{cell[1]}', 'stages': {}}
    rec['stages'][STAGE] = {'status': status, 'plan': plan_name, 'blocks': cells}
    path.write_text(json.dumps(rec, indent=2) + '\n')
    return path


if __name__ == '__main__':
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--cell', required=True)
    ap.add_argument('--apply', action='store_true')
    args = ap.parse_args()
    cell = parse_cell(args.cell)
    name = f'highfield_{cell[0]}_m{abs(cell[1])}_stripabove'
    plan = Plan(name)
    w = World()
    n = strip_foliage_above_surface(plan, w, cell_columns(cell))
    print(f'{name}: columns {len(cell_columns(cell))} blocks to strip {n} cells {len(plan.cells)}')
    preview(plan, ROOT / f'verification/site/{name}-preview.png', scale=2)
    apply(plan, dry=not args.apply, modifies=())
    if args.apply:
        stage_record(cell, 'applied', name, n)
    else:
        print('stage record not written (dry-run)')
