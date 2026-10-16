#!/usr/bin/env python3
"""Single-builder lock for Southampton Refine.

Only the thread holding a fresh lock may change the live world. apply()
checks it (env SITE_OWNER must match) and refreshes the heartbeat. A lock
with no heartbeat for STALE_MIN minutes may be taken over.

  python3 scripts/site_lock.py status
  python3 scripts/site_lock.py claim <owner> "<queue item / task>"
  python3 scripts/site_lock.py release <owner>
Then run builds as:  SITE_OWNER=<owner> python3 scripts/<build>.py --apply
"""
import json
import os
import sys
import time
from pathlib import Path

LOCK = Path(__file__).resolve().parent.parent / 'site/LOCK.json'
STALE_MIN = 90


def read():
    """Return the lock dict, or None if unlocked.

    @returns: lock dict or None
    """
    return json.loads(LOCK.read_text()) if LOCK.exists() else None


def fresh(lk):
    """True if ``lk`` has a heartbeat newer than STALE_MIN minutes.

    @param lk: lock dict or None
    @returns: whether the lock is still held
    """
    return lk and time.time() - lk['heartbeat'] < STALE_MIN * 60


def check(owner=None):
    """Raise unless ``owner`` (default env SITE_OWNER) holds a fresh lock; refresh heartbeat.

    @param owner: lock owner id (defaults to SITE_OWNER)
    """
    owner = owner or os.environ.get('SITE_OWNER')
    lk = read()
    if not owner:
        raise SystemExit('Set SITE_OWNER=<owner> (claim first: scripts/site_lock.py claim <owner> "<task>")')
    if not fresh(lk) or lk['owner'] != owner:
        raise SystemExit(f'World lock not held by {owner}: {lk}')
    lk['heartbeat'] = time.time()
    lk['heartbeat_at'] = time.strftime('%Y-%m-%d %H:%M:%S')
    LOCK.write_text(json.dumps(lk, indent=1))


def claim(owner, task):
    """Write the lock for ``owner``; refuses while another owner's lock is fresh.

    @param owner: lock owner id
    @param task: what the lock is for
    """
    lk = read()
    if fresh(lk) and lk['owner'] != owner:
        raise SystemExit(f'Held by {lk["owner"]} since {lk["claimed_at"]} for: {lk["task"]}')
    now = time.time()
    LOCK.write_text(json.dumps({
        'owner': owner, 'task': task, 'claimed': now, 'heartbeat': now,
        'claimed_at': time.strftime('%Y-%m-%d %H:%M:%S'),
        'heartbeat_at': time.strftime('%Y-%m-%d %H:%M:%S'),
    }, indent=1))


def release(owner):
    """Remove the lock; refuses while another owner's lock is fresh.

    @param owner: lock owner id
    """
    lk = read()
    if lk and lk['owner'] != owner and fresh(lk):
        raise SystemExit(f'Not yours: {lk}')
    LOCK.unlink(missing_ok=True)


def main():
    """CLI: status | claim | release."""
    cmd = sys.argv[1] if len(sys.argv) > 1 else 'status'
    lk = read()
    if cmd == 'status':
        print(json.dumps(lk, indent=1) if lk else 'unlocked', '(fresh)' if fresh(lk) else '(stale/none)')
    elif cmd == 'claim':
        claim(sys.argv[2], ' '.join(sys.argv[3:]))
        print('claimed by', sys.argv[2])
    elif cmd == 'release':
        release(sys.argv[2])
        print('released')
    else:
        print(__doc__, file=sys.stderr)
        return 2
    return 0


if __name__ == '__main__':
    raise SystemExit(main() or 0)
