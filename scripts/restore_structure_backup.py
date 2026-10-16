#!/usr/bin/env python3
"""Restore a site_kit apply backup structure into the live world.

Uses verification/site/<build>-backup.json written on first apply of that build.

  python3 scripts/restore_structure_backup.py highfield_48_m44_foliage
  SITE_OWNER=you python3 scripts/restore_structure_backup.py highfield_48_m44_foliage --apply
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'scripts'))

from mc_paced import Paced, box, D, xyz  # noqa: E402
from site_kit import OUT  # noqa: E402


def load_record(build: str) -> dict:
    """Read backup metadata for a build name.

    @param build: kit plan name
    @returns: parsed backup json
    """
    path = OUT / f'{build}-backup.json'
    if not path.exists():
        raise SystemExit(f'missing {path}')
    return json.loads(path.read_text())


def load_structure(name: str, origin, m=None) -> str:
    """Load a saved structure back into the world at ``origin`` and save the world.

    The caller holds the lock. Raises if the server reports a failure.

    @param name: structure id, e.g. southampton_refine:before_<plan>
    @param origin: [x, y, z] the structure was saved from
    @param m: optional Paced-like client (tests)
    @returns: the server's reply text
    """
    if m is None:
        m = Paced()
    res = m.text('structure_load_to_world', {'name': name, 'dimension': D, 'origin': xyz(origin),
                                             'rotation': 'none', 'mirror': 'none'})
    if any(w in res.lower() for w in ('error', 'fail', 'not found', 'unknown', 'no such')):
        raise SystemExit(f'structure load of {name} failed: {res}')
    m.call('server_save_all_worlds', {})
    return res


def restore(build: str, *, apply: bool) -> None:
    """Load ``before_<build>`` structure at the saved box origin.

    @param build: kit plan name
    @param apply: when False, print intent only
    """
    rec = load_record(build)
    name = rec['structure']
    origin = rec['from']
    lo, hi = rec['from'], rec['to']
    print(f'restore {name} at {origin} box {lo}..{hi}')
    if not apply:
        print('dry-run: pass --apply with SITE_OWNER lock held')
        return
    import site_lock

    site_lock.check()
    print(load_structure(name, origin))


if __name__ == '__main__':
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('build', help='plan name, e.g. highfield_48_m44_foliage')
    ap.add_argument('--apply', action='store_true')
    args = ap.parse_args()
    restore(args.build, apply=args.apply)
