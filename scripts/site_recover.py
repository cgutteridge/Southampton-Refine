#!/usr/bin/env python3
"""Recover aborted live runs: one mechanism for every pass (PROCESS.txt, lock / apply protocol).

site_kit.apply() records each live apply in site/cells/<tx>_<tz>-STAGES.json as 'applying'
(plan, owner, structure backup, region snapshot, planned-cells file) and 'applied' after the
readback. A run that dies in between leaves 'applying'. This tool resolves it.

  python3 scripts/site_recover.py status                  # read-only: stale lock, in-flight, rolled-back stages
  python3 scripts/site_recover.py recover 46,-43          # dry run: what it would do
  python3 scripts/site_recover.py recover 46,-43 --apply  # do it

Decision, per 'applying' stage (conservative: when unsure it reports and does nothing):
  * lock held and fresh (heartbeat < site_lock.STALE_MIN) -> refuse; the run may still be alive.
  * lock stale but owned by someone other than the stage's owner -> refuse (unsure).
  * flush the world, read the planned-cells file back from the region files (site_kit.readback):
      all planned blocks match -> stage 'applied' (recovered). An aborted mask undo also gets its
      bookkeeping finished (mask_undo.finish_undo).
      otherwise -> restore the structure saved for THIS apply (restore_structure_backup), verify
      the plan cells against the region snapshot when one was recorded, stage 'rolled-back' (not
      done, so the work reappears). Trees/decor re-applied after a mask undo: the structure taken
      before that undo is restored too (and the archived mask put back), so the cell is not left bare.
  * the stale lock is released only after a successful recovery and only when its owner is the
    owner recorded on the stage.
Cannot verify: sign text / entities (readback never did); a rollback with no region snapshot
recorded is reported 'unverified'; region-file snapshots are never copied back (server running).
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'scripts'))

import site_lock  # noqa: E402
import site_stages  # noqa: E402

OWNER = 'site-recover'


def _cells():
    for path in sorted(site_stages.CELLS.glob('*-STAGES.json')):
        a, _, b = path.name[:-len('-STAGES.json')].partition('_')
        try:
            yield (int(a), int(b)), json.loads(path.read_text()).get('stages', {})
        except (ValueError, OSError, json.JSONDecodeError):
            continue


def lock_state() -> dict:
    lk = site_lock.read()
    if not lk:
        return {'state': 'none', 'lock': None}
    age = (time.time() - lk['heartbeat']) / 60
    return {'state': 'fresh' if site_lock.fresh(lk) else 'stale', 'lock': lk, 'age_min': round(age)}


def status() -> dict:
    """Read-only: stale lock, in-flight ('applying') and rolled-back stages across all cells."""
    inflight, rolled = [], []
    for cell, stages in _cells():
        for key, e in stages.items():
            if isinstance(e, dict) and e.get('status') == 'applying':
                inflight.append({'cell': cell, 'stage': key, 'plan': e.get('plan'), 'owner': e.get('owner'),
                                 'started': e.get('started')})
            elif isinstance(e, dict) and e.get('status') == 'rolled-back':
                rolled.append({'cell': cell, 'stage': key, 'plan': e.get('plan')})
    return {'lock': lock_state(), 'in_flight': inflight, 'rolled_back': rolled}


def _flush():
    from mc_paced import Paced
    Paced().call('server_save_all_worlds', {})
    time.sleep(3)


def _load_planned(entry: dict):
    from site_kit import Plan
    rel = entry.get('planned')
    path = ROOT / rel if rel else None
    if not path or not path.exists():
        return None
    plan = Plan(entry.get('plan', 'recover'))
    for k, st in json.loads(path.read_text()).items():
        x, y, z = (int(v) for v in k.split(','))
        plan.cells[(x, y, z)] = st
    return plan


def _matches_snapshot(snapshot: str, positions, world_factory) -> int | None:
    """Mismatches between the live world and a region snapshot dir over positions (None: cannot read)."""
    from site_kit import World
    snap = Path(snapshot) if Path(snapshot).is_absolute() else ROOT / snapshot
    if not snap.is_dir() or not any(snap.glob('r.*.mca')):
        return None
    live, old = world_factory(), World(snap)
    return sum(1 for p in positions if live.block(*p) != old.block(*p))


def recover(cell, apply: bool = False, flush=None, world_factory=None, loader=None, snapshot_check=None) -> dict:
    """Resolve the 'applying' stage of one cell. Returns {'cell', 'action', 'detail'}.

    action: 'none' | 'applied' | 'rolled-back' | 'unsure' | 'failed' (prefixed 'would-' unless apply).
    flush / world_factory / loader / snapshot_check are injectable for tests.
    """
    import site_kit
    flush = flush or _flush
    world_factory = world_factory or site_kit.World
    cell = tuple(cell)
    stages = (site_stages.read(cell) or {}).get('stages', {})
    flying = site_stages.in_flight(stages)
    res = {'cell': list(cell), 'action': 'none', 'detail': []}
    say = res['detail'].append
    if not flying:
        say('no stage is in flight')
        return res
    if len(flying) > 1:
        res['action'] = 'unsure'
        say('several stages are in flight (' + ', '.join(k for k, _ in flying) + '); resolve by hand')
        return res
    key, e = flying[0]
    say(f'stage {key}: plan {e.get("plan")}, owner {e.get("owner")}, started {e.get("started")}')
    ls = lock_state()
    if ls['state'] == 'fresh':
        res['action'] = 'unsure'
        say(f'lock held by {ls["lock"]["owner"]} with a fresh heartbeat ({ls["age_min"]} min); the run may be '
            f'alive. Wait for it to go stale (> {site_lock.STALE_MIN} min) or ask the user. Nothing done.')
        return res
    if ls['state'] == 'stale' and (not e.get('owner') or ls['lock']['owner'] != e['owner']):
        res['action'] = 'unsure'
        say(f'stale lock belongs to {ls["lock"]["owner"]}, the in-flight stage to {e.get("owner")}: not the same run. Nothing done.')
        return res
    plan = _load_planned(e)
    if plan is None:
        res['action'] = 'unsure'
        say(f'planned-cells file {e.get("planned")} is missing: cannot compare the world. Nothing done.')
        return res
    try:
        flush()
    except Exception as exc:                              # noqa: BLE001
        res['action'] = 'unsure'
        say(f'could not flush the world ({exc}); reading stale region files would mislead. Nothing done.')
        return res
    rb = site_kit.readback(plan, world_factory())
    say(f'live world vs plan: {rb["planned"]} planned, {rb["mismatches"]} mismatches')
    prefix = '' if apply else 'would-'
    original_lock = ls['lock']

    def release_stale():
        if original_lock is not None:
            site_lock.LOCK.unlink(missing_ok=True)
            say('stale lock released (same owner as the in-flight stage)')

    if rb['mismatches'] == 0:
        res['action'] = prefix + 'applied'
        say("every planned block is in the world: stage -> 'applied' (recovered)")
        if apply:
            if e.get('kind') == 'undo':
                import mask_undo
                mask_undo.finish_undo(cell, e['pass'], e['plan'])
                say("mask undo bookkeeping finished (mask archived, stage '%s' -> 'undone')" % e['pass'])
            site_stages.finish(cell, key, 'applied', readback={k: rb[k] for k in ('planned', 'mismatches', 'checked')},
                               recovered=f'matched the plan after an aborted run ({time.strftime("%Y-%m-%d %H:%M:%S")})')
            release_stale()
        return res

    # --- roll back ---------------------------------------------------------------------------
    steps = []
    if not e.get('structure'):
        res['action'] = 'unsure'
        say('world differs from the plan and no structure backup is recorded for this apply. Nothing done.')
        return res
    steps.append(('apply', e['structure'], e.get('snapshot'), list(plan.cells)))
    prev = e.get('previous') or {}
    undo = prev.get('undo_snapshot') if key in ('trees', 'decor') and prev.get('status') == 'undone' else None
    if undo:
        if not undo.get('structure'):
            res['action'] = 'unsure'
            say('the pass was undone before this apply but the undo snapshot structure is not recorded. Nothing done.')
            return res
        positions = []
        if undo.get('planned') and (ROOT / undo['planned']).exists():
            positions = [tuple(int(v) for v in k.split(',')) for k in json.loads((ROOT / undo['planned']).read_text())]
        steps.append(('before-undo', undo['structure'], undo.get('snapshot'), positions))
    say('would restore: ' + ' then '.join(f'{n} {s["name"]}' for n, s, *_ in steps))
    if not apply:
        res['action'] = 'would-rolled-back'
        return res
    original = site_lock.read()
    verified = []
    try:
        site_lock.claim(OWNER, f'recover {cell[0]},{cell[1]} {e.get("plan")}')
        if loader is None:
            import restore_structure_backup
            loader = restore_structure_backup.load_structure
        for name, struct, snapshot, positions in steps:
            loader(struct['name'], struct['from'])
            flush()
            check = (snapshot_check or (lambda s, p: _matches_snapshot(s, p, world_factory)))
            bad = check(snapshot, positions) if snapshot and positions else None
            verified.append({'step': name, 'structure': struct['name'], 'snapshot': snapshot,
                             'verified': None if bad is None else bad == 0, 'mismatches_vs_snapshot': bad})
            say(f'restored {name}: {struct["name"]} ({"unverified: no readable snapshot" if bad is None else str(bad) + " mismatches vs snapshot"})')
            if bad:
                raise RuntimeError(f'{bad} blocks differ from snapshot {snapshot} after restoring {struct["name"]}')
    except (Exception, SystemExit) as exc:                # noqa: BLE001
        res['action'] = 'failed'
        say(f'rollback failed: {exc}. Stage stays "applying"; original lock restored. Report to the user.')
        if original:
            site_lock.LOCK.write_text(json.dumps(original, indent=1))
        else:
            site_lock.LOCK.unlink(missing_ok=True)
        return res
    if undo and undo.get('mask_backup') and Path(undo['mask_backup']).exists():
        from pass_mask import mask_path
        dest = mask_path(key, cell)
        shutil.copy2(undo['mask_backup'], dest)
        say(f'archived {key} mask put back at {dest}')
    site_stages.finish(cell, key, 'rolled-back', recovered={
        'at': time.strftime('%Y-%m-%d %H:%M:%S'), 'restored': verified,
        'used_undo_snapshot': undo['structure'] if undo else None})
    site_lock.LOCK.unlink(missing_ok=True)
    say('lock released; stage rolled-back (work reappears in cell_gaps)')
    res['action'] = 'rolled-back'
    return res


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    sub = ap.add_subparsers(dest='cmd', required=True)
    sub.add_parser('status', help='read-only')
    r = sub.add_parser('recover', help='resolve one cell')
    r.add_argument('cell', help='tx,tz')
    r.add_argument('--apply', action='store_true', help='LIVE: otherwise a dry run')
    a = ap.parse_args(argv)
    if a.cmd == 'status':
        st = status()
        lk = st['lock']
        print('lock:', 'none' if lk['state'] == 'none' else
              f'{lk["state"]} (owner {lk["lock"]["owner"]}, {lk["age_min"]} min since heartbeat, task: {lk["lock"].get("task")})')
        for f in st['in_flight']:
            print(f'in-flight: cell {f["cell"][0]},{f["cell"][1]} stage {f["stage"]} plan {f["plan"]} owner {f["owner"]} since {f["started"]}')
        for f in st['rolled_back']:
            print(f'rolled-back (needs re-run): cell {f["cell"][0]},{f["cell"][1]} stage {f["stage"]} plan {f["plan"]}')
        if not (st['in_flight'] or st['rolled_back'] or lk['state'] == 'stale'):
            print('clean')
        return 1 if (st['in_flight'] or lk['state'] == 'stale') else 0
    res = recover(tuple(int(v) for v in a.cell.split(',')), apply=a.apply)
    print(f'{res["cell"][0]},{res["cell"][1]}: {res["action"]}')
    for line in res['detail']:
        print('  ' + line)
    return 1 if res['action'] in ('unsure', 'failed') else 0


if __name__ == '__main__':
    sys.exit(main())
