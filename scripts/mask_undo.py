#!/usr/bin/env python3
"""Undo one tree or decor pass from its mask — HANDOFF-LAYERED-PASSES §3.

Trees and decor only ever place into air, so the undo is exact: every masked position goes
back to air. Steps: integrity check, conflict check against the live world (any position that
no longer holds the masked block stops the undo with nothing written), then one air plan.

  python3 scripts/mask_undo.py --cell 48,-44 --pass trees            # dry run
  SITE_OWNER=<owner> python3 scripts/mask_undo.py --cell 48,-44 --pass trees --apply

Undo order is the reverse of the pass order: decor first, then trees.
On a clean readback the mask file is archived (masks/undone/) and the stage is marked 'undone'.
Any failure raises (fail-closed); see site_recover.py for an aborted run.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from script_env import ROOT  # noqa: E402

from ground_layer import bare, ignored_builds, plan_name  # noqa: E402
from pass_mask import OVERHANG_MARGIN, PASSES, mask_path, mask_placements, read_mask, shared_positions, verify_integrity  # noqa: E402
from site_kit import Plan, World, apply, same  # noqa: E402


def finish_undo(cell: tuple[int, int], pass_name: str, name: str, mask_dir: Path | None = None) -> None:
    """Bookkeeping after a clean undo: archive the mask, mark the pass stage 'undone'. Idempotent.

    The mask moves to <mask_dir>/undone/ (not deleted) and the stage keeps ``undo_snapshot`` (the
    structure saved by the undo's own apply), so site_recover.py can put the trees/decor back if the
    re-apply after the undo aborts. Shared with recovery of an aborted undo.
    """
    import shutil

    import site_stages

    path = mask_path(pass_name, cell, mask_dir) if mask_dir else mask_path(pass_name, cell)
    backup = path.parent / 'undone' / f'{name}.mask.json'
    if path.exists():
        backup.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, backup)
        path.unlink()
    data = site_stages.read(cell) or {'cell': f'{cell[0]},{cell[1]}', 'stages': {}}
    undo = data['stages'].get(f'{pass_name}-undo', {})
    entry = data['stages'].get(pass_name, {})
    entry.update({'status': 'undone', 'note': f'undone from mask via {name}; re-run the {pass_name} pass after ground',
                  'undo_snapshot': {'plan': name, 'structure': undo.get('structure'), 'snapshot': undo.get('snapshot'),
                                    'planned': undo.get('planned'),
                                    'mask_backup': str(backup) if backup.exists() else None}})
    entry.pop('mask', None)
    data['stages'][pass_name] = entry
    site_stages.write(cell, data)


def run(cell: tuple[int, int], pass_name: str, live: bool) -> int:
    """Plan (and with ``live`` apply) the undo. Returns 0 on success.

    Fail-closed: a conflict, a failed flush, or a readback mismatch raises SystemExit instead of
    returning, so a calling script cannot carry on and overwrite the mask. After a mismatch the
    stage '<pass>-undo' stays 'applying' (site_recover.py).
    """
    tx, tz = cell
    path = mask_path(pass_name, cell)
    if not path.exists():
        print(f'no {pass_name} mask for {tx},{tz} at {path.relative_to(ROOT)}: nothing to undo')
        return 0
    mask = read_mask(path)
    try:
        from mc_paced import Paced
        Paced().call('server_save_all_worlds', {})
    except Exception as exc:                              # noqa: BLE001
        if live:
            raise SystemExit(f'could not flush the world before reading it (stale reads give false conflicts): {exc}')
        print(f'  (could not flush the world before reading: {exc})')
    world = World()
    if not verify_integrity(mask):
        raise SystemExit('mask integrity check failed; file does not match its sha256')
    to_air, conflicts = [], []
    shared = shared_positions(mask)          # a crown merged with another cell's: that mask still owns it
    for pos, expected in sorted(mask_placements(mask).items()):
        if pos in shared:
            continue
        live_block = world.block(*pos)
        if live_block and same(expected, live_block):
            to_air.append(pos)
        else:
            conflicts.append((pos, expected, bare(live_block)))
    print(f'{pass_name} {tx},{tz}: mask {mask["count"]} blocks, undo {len(to_air)}, left (shared with another mask) {len(shared)}, conflicts {len(conflicts)}')
    for pos, want, got in conflicts[:10]:
        print(f'  CONFLICT {pos}: mask says {want}, live is {got}')
    if conflicts:
        raise SystemExit(f'STOP: {len(conflicts)} position(s) differ from the mask; nothing written, mask kept.')
    name = plan_name(tx, tz, f'{pass_name}_undo')
    plan = Plan(name)
    for pos in to_air:
        plan.set(*pos, 'air')
    owner_plan = mask['plan']
    mods = (owner_plan,) + tuple(ignored_builds(cell))
    if not live:
        apply(plan, dry=True, modifies=mods)
        return 0
    if not os.environ.get('SITE_OWNER'):
        raise SystemExit('SITE_OWNER is not set; claim the lock first (scripts/site_lock.py claim <owner> ...)')
    import subprocess
    from ground_layer import cell_bbox_str
    subprocess.run([sys.executable, str(ROOT / 'scripts/region_backup.py'), 'snap',
                    '--bbox', cell_bbox_str(cell, OVERHANG_MARGIN), '--name', name], check=True)
    rb = apply(plan, modifies=mods, stage=f'{pass_name}-undo', cell=cell, strict=True,
               meta={'kind': 'undo', 'pass': pass_name})
    print(f'readback: {rb["planned"]} planned, {rb["mismatches"]} mismatches')
    finish_undo(cell, pass_name, name)
    print(f'{pass_name} undone; mask archived')
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--cell', required=True)
    ap.add_argument('--pass', dest='pass_name', required=True, choices=PASSES)
    ap.add_argument('--apply', action='store_true', help='LIVE: needs SITE_OWNER + claimed lock')
    a = ap.parse_args()
    return run(tuple(int(v) for v in a.cell.split(',')), a.pass_name, a.apply)


if __name__ == '__main__':
    sys.exit(main())
