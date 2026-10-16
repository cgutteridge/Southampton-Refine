"""Stage state machine for live applies: site/cells/<tx>_<tz>-STAGES.json.

site_kit.apply() calls begin() before its first live block write (status 'applying') and
finish() after the readback ('applied' / 'applied-with-mismatches'). An aborted run therefore
leaves 'applying', which site_handoff.cell_gaps reports as 'in-flight: <plan>' and
site_recover.py can resolve (PROCESS.txt, lock / apply protocol).

An 'applying' entry records: plan, owner (SITE_OWNER), started, structure backup
{name, from, to}, region snapshot dir, the planned-cells file and any `meta` (kind 'undo' ...).
If the stage key already held an entry it is kept under 'previous' (recovery needs it when a mask
undo was followed by an aborted re-apply).
"""
from __future__ import annotations

import json
import os
import time
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CELLS = ROOT / 'site' / 'cells'
SNAPSHOTS = ROOT / 'backups' / 'regions'
CELL_SHIFT = 7                       # 128-block cells
SNAPSHOT_MAX_AGE_H = 3


def stage_path(cell, cells_dir: Path | None = None) -> Path:
    return (cells_dir or CELLS) / f'{cell[0]}_{cell[1]}-STAGES.json'


def read(cell) -> dict | None:
    try:
        return json.loads(stage_path(cell).read_text())
    except (OSError, json.JSONDecodeError):
        return None


def write(cell, data: dict) -> None:
    path = stage_path(cell)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + '\n', encoding='utf-8')


def primary_cell(positions) -> tuple[int, int]:
    """The cell holding most of the given (x, y, z) positions."""
    counts = Counter((x >> CELL_SHIFT, z >> CELL_SHIFT) for x, _y, z in positions)
    return counts.most_common(1)[0][0]


def latest_snapshot(name: str, now: float | None = None) -> str | None:
    """Newest region snapshot dir (backups/regions/<stamp>-<name>) younger than SNAPSHOT_MAX_AGE_H, repo-relative."""
    now = now or time.time()
    if not SNAPSHOTS.exists():
        return None
    for d in sorted(SNAPSHOTS.glob(f'*-{name}'), reverse=True):
        if d.is_dir() and now - d.stat().st_mtime < SNAPSHOT_MAX_AGE_H * 3600:
            try:
                return str(d.relative_to(ROOT))
            except ValueError:
                return str(d)
    return None


def begin(cell, key: str, plan: str, **fields) -> None:
    """Record stage ``key`` of ``cell`` as 'applying' (before any live block write)."""
    data = read(cell) or {'cell': f'{cell[0]},{cell[1]}', 'stages': {}}
    entry = {'status': 'applying', 'plan': plan, 'owner': os.environ.get('SITE_OWNER'),
             'started': time.strftime('%Y-%m-%d %H:%M:%S'), **fields}
    prev = data['stages'].get(key)
    if isinstance(prev, dict) and prev.get('status') != 'applying':
        entry['previous'] = {k: v for k, v in prev.items() if k != 'previous'}
    elif isinstance(prev, dict) and prev.get('previous'):
        entry['previous'] = prev['previous']       # a re-run of an aborted apply keeps the original prior state
    data['stages'][key] = entry
    write(cell, data)


def finish(cell, key: str, status: str, **fields) -> None:
    """Set the stage's final status (idempotent: a later hand-written entry simply replaces it)."""
    data = read(cell)
    if data is None or not isinstance(data['stages'].get(key), dict):
        return
    entry = data['stages'][key]
    entry.update({'status': status, 'finished': time.strftime('%Y-%m-%d %H:%M:%S'), **fields})
    entry.pop('previous', None)
    data['stages'][key] = entry
    write(cell, data)


def in_flight(stages: dict | None) -> list[tuple[str, dict]]:
    """Stages whose status is 'applying'."""
    return [(k, v) for k, v in (stages or {}).items() if isinstance(v, dict) and v.get('status') == 'applying']
