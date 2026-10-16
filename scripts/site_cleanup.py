#!/usr/bin/env python3
"""Find and remove files that will not be used again. Policy: site/CLEANUP.txt.

  python3 scripts/site_cleanup.py report            # read-only: what each class would free
  python3 scripts/site_cleanup.py due               # exit 0 + one line if a cleanup is due, else exit 1
  python3 scripts/site_cleanup.py apply             # the SAFE classes only (expired / regenerable)
  python3 scripts/site_cleanup.py apply --class reference-junk    # judged classes: name them
  python3 scripts/site_cleanup.py log               # the cleanup log

Classes
  SAFE (apply with no class name): region-snaps, views, screenshots, cells-cache, audits
  JUDGED (apply only when named): reference-junk
  REPORT-ONLY (never deleted here): reference-unlogged, build-scripts

Never touched: instance/saves, backups/pristine-geocraft, backups/*.tar.gz, verification/site/*-cells.json
and *-backup.json (the build records and their undo), reference files judged useful yes/maybe, site/archive.

Every apply appends to site/CLEANUP-LOG.txt. Reference junk keeps its manifest row (useful=no, removed date,
reason, url, sha256) so nothing is fetched twice.
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

from script_env import ROOT

SITE = ROOT / 'site'
LOG = SITE / 'CLEANUP-LOG.txt'
MANIFEST = ROOT / 'reference' / 'manifest.jsonl'

KEEP_SNAPS = 5            # newest region snaps kept (site/PROCESS.txt §2a)
BUILD_DAYS = 14           # a build script untouched this long and imported nowhere is a retire candidate
VIEW_DAYS = 7             # verification/site/views older than this and named in no live site file
SHOT_DAYS = 7             # instance/screenshots
KEEP_AUDITS = 10          # newest files kept in verification/site/audits and verification/site/patrol
DUE_DAYS = 7              # a cleanup is due when the last logged apply is this old ...
DUE_BYTES = 1 << 30       # ... or the SAFE classes could free this much
BLANK_STDDEV = 3.0        # grey-level spread below this on a 64px thumbnail = blank / uniform image

SAFE = ('region-snaps', 'views', 'screenshots', 'cells-cache', 'audits')
JUDGED = ('reference-junk',)
REPORT_ONLY = ('reference-unlogged', 'build-scripts')


@dataclass
class Item:
    """One thing that would be removed."""
    path: Path
    reason: str
    size: int = 0
    extra: dict = field(default_factory=dict)


def size_of(p: Path) -> int:
    """Bytes in a file or directory tree."""
    if p.is_file():
        return p.stat().st_size
    return sum(f.stat().st_size for f in p.rglob('*') if f.is_file())


def mb(n: int) -> str:
    return f'{n / 2**20:,.0f} MB'


def open_work_text() -> str:
    """Text of the open ISSUES and QUEUE files only: what can still need an old snap."""
    return '\n'.join((SITE / n).read_text(errors='replace') for n in ('ISSUES.txt', 'QUEUE.txt') if (SITE / n).exists())


def live_site_text() -> str:
    """Text of the live site/*.txt and *.md files (not site/archive): what open work can still mention."""
    return '\n'.join(p.read_text(errors='replace') for p in SITE.glob('*') if p.suffix in ('.txt', '.md'))


def _old(p: Path, days: float, now: float) -> bool:
    return now - p.stat().st_mtime > days * 86400


# ---------------------------------------------------------------- SAFE classes

def plan_region_snaps(keep: int = KEEP_SNAPS, text: str | None = None) -> list[Item]:
    """Region snaps beyond the newest ``keep``, except the newest snap of any name open ISSUES/QUEUE items mention."""
    root = ROOT / 'backups' / 'regions'
    if not root.exists():
        return []
    text = (open_work_text() if text is None else text).lower()
    dirs = sorted((d for d in root.iterdir() if d.is_dir()), reverse=True)
    out, held = [], set()
    for d in dirs[keep:]:
        label = re.sub(r'^\d{4}-\d\d-\d\d-\d{6}-?', '', d.name)
        if label and label.lower() in text and label not in held:
            held.add(label)
            continue
        out.append(Item(d, f'snap beyond newest {keep}', size_of(d)))
    return out


def plan_views(days: float = VIEW_DAYS, now: float | None = None, text: str | None = None) -> list[Item]:
    """View PNGs older than ``days`` that no live site file names (site_views.py regenerates them)."""
    root = ROOT / 'verification' / 'site' / 'views'
    if not root.exists():
        return []
    now = time.time() if now is None else now
    text = live_site_text() if text is None else text
    return [Item(p, f'view older than {days:g} days, not named in live site files', p.stat().st_size)
            for p in sorted(root.glob('*.png')) if _old(p, days, now) and p.name not in text]


def plan_screenshots(days: float = SHOT_DAYS, now: float | None = None) -> list[Item]:
    """instance/screenshots older than ``days``."""
    root = ROOT / 'instance' / 'screenshots'
    if not root.exists():
        return []
    now = time.time() if now is None else now
    return [Item(p, f'screenshot older than {days:g} days', p.stat().st_size)
            for p in sorted(root.iterdir()) if p.is_file() and _old(p, days, now)]


def plan_cells_cache() -> list[Item]:
    """Pickles in backups/cells-cache whose *-cells.json source no longer exists."""
    root = ROOT / 'backups' / 'cells-cache'
    if not root.exists():
        return []
    src = ROOT / 'verification' / 'site'
    return [Item(p, 'source cells.json gone', p.stat().st_size)
            for p in sorted(root.glob('*-cells.json.pkl')) if not (src / p.name[:-4]).exists()]


def plan_audits(keep: int = KEEP_AUDITS) -> list[Item]:
    """Audit and patrol outputs beyond the newest ``keep`` in each folder."""
    out = []
    for sub in ('audits', 'patrol'):
        d = ROOT / 'verification' / 'site' / sub
        if d.exists():
            files = sorted((f for f in d.iterdir() if f.is_file()), key=lambda f: f.stat().st_mtime, reverse=True)
            out += [Item(f, f'{sub} output beyond newest {keep}', f.stat().st_size) for f in files[keep:]]
    return out


# ---------------------------------------------------------------- reference

def _blank(path: Path) -> str:
    """Why an image has no usable data ('' if it has some). Needs Pillow; silently '' without it."""
    try:
        from PIL import Image, ImageStat
        with Image.open(path) as im:
            im.load()
            if im.mode in ('RGBA', 'LA') and im.getchannel('A').getextrema()[1] < 8:
                return 'fully transparent'
            sd = max(ImageStat.Stat(im.convert('L').resize((64, 64))).stddev)
    except Exception:
        return ''
    return 'blank / single colour' if sd < BLANK_STDDEV else ''


def _manifest() -> list[dict]:
    from ref_manifest import load_manifest
    return load_manifest(MANIFEST)


def plan_reference_junk(rows: list[dict] | None = None, check_blank: bool = True) -> list[Item]:
    """Reference files judged useful=no, or blank with no data; their manifest rows stay as tombstones."""
    rows = _manifest() if rows is None else rows
    ref = ROOT / 'reference'
    out = []
    for r in rows:
        p = ref / r.get('path', '')
        if r.get('removed') or not p.is_file():
            continue
        if r.get('useful') == 'no':
            out.append(Item(p, 'judged useful=no: ' + (r.get('notes') or 'no note'), p.stat().st_size, {'id': r['id']}))
        elif check_blank and (why := _blank(p)):
            out.append(Item(p, 'no usable data: ' + why, p.stat().st_size, {'id': r['id']}))
    return out


def plan_reference_unlogged(rows: list[dict] | None = None) -> list[Item]:
    """Files under reference/aerial|photos|osm that the manifest does not list: log them or drop them."""
    rows = _manifest() if rows is None else rows
    known = {r.get('path') for r in rows}
    ref = ROOT / 'reference'
    out = []
    for sub in ('aerial', 'photos'):
        for p in sorted((ref / sub).rglob('*')) if (ref / sub).exists() else []:
            rel = str(p.relative_to(ref))
            if p.is_file() and not p.name.startswith('.') and rel not in known and p.suffix in ('.png', '.jpg', '.jpeg', '.tif', '.tiff', '.webp'):
                out.append(Item(p, 'not in reference/manifest.jsonl', p.stat().st_size))
    return out


# ---------------------------------------------------------------- build scripts

def plan_build_scripts(days: float = BUILD_DAYS, now: float | None = None) -> list[Item]:
    """build_<x>.py untouched for ``days`` and imported or named by no other script or test: retire candidates.

    A build script can still be re-run for a refinement, so this is a list for a human or agent to judge
    (tar to backups/retired-*.tar.gz as with the ground scripts, then git rm), never auto-removed.
    """
    scripts = ROOT / 'scripts'
    now = time.time() if now is None else now
    others = {p: p.read_text(errors='replace') for p in scripts.glob('*.py')}
    out = []
    for p in sorted(scripts.glob('build_*.py')):
        if _old(p, days, now) and not any(p.stem in t for q, t in others.items() if q != p):
            out.append(Item(p, f'untouched {days:g}+ days, referenced by no other script or test', p.stat().st_size))
    return out


PLANNERS = {
    'region-snaps': plan_region_snaps, 'views': plan_views, 'screenshots': plan_screenshots,
    'cells-cache': plan_cells_cache, 'audits': plan_audits,
    'reference-junk': plan_reference_junk, 'reference-unlogged': plan_reference_unlogged,
    'build-scripts': plan_build_scripts,
}


# ---------------------------------------------------------------- apply and log

def _log(lines: list[str]) -> None:
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open('a') as f:
        f.write('\n'.join(lines) + '\n')


def _tombstone(items: list[Item], today: str) -> None:
    """Mark the manifest rows of removed reference files: useful=no, removed date and reason, rest kept."""
    from ref_manifest import load_manifest, save_manifest
    why = {i.extra['id']: i.reason for i in items if 'id' in i.extra}
    rows = load_manifest(MANIFEST)
    for r in rows:
        if r.get('id') in why:
            r.update(useful='no', removed=today, removed_reason=why[r['id']])
    save_manifest(rows, MANIFEST)


def apply_class(name: str, items: list[Item], today: str | None = None) -> int:
    """Delete one class's items, write the log lines, return bytes freed."""
    today = today or time.strftime('%Y-%m-%d')
    freed = 0
    for i in items:
        shutil.rmtree(i.path) if i.path.is_dir() else i.path.unlink()
        freed += i.size
    if name == 'reference-junk':
        _tombstone(items, today)
    detail = [f'  {i.path.relative_to(ROOT)}  [{i.reason}]' for i in items] if name == 'reference-junk' else []
    _log([f'{today} {name}: removed {len(items)} ({mb(freed)})'] + detail)
    return freed


def last_cleanup() -> float | None:
    """Epoch of the last logged apply, or None."""
    if not LOG.exists():
        return None
    days = re.findall(r'^(\d{4}-\d\d-\d\d) ', LOG.read_text(), re.M)
    return time.mktime(time.strptime(days[-1], '%Y-%m-%d')) if days else None


def safe_reclaimable() -> int:
    return sum(i.size for c in SAFE for i in PLANNERS[c]())


def due_reason(now: float | None = None) -> str:
    """Why a cleanup is due ('' if not)."""
    now = time.time() if now is None else now
    last = last_cleanup()
    if last is None:
        return 'never cleaned'
    age = (now - last) / 86400
    if age >= DUE_DAYS:
        return f'last cleanup {age:.0f} days ago'
    if (n := safe_reclaimable()) >= DUE_BYTES:
        return f'{mb(n)} reclaimable'
    return ''


# ---------------------------------------------------------------- CLI

def cmd_report(_a) -> int:
    for group, names in (('SAFE (apply)', SAFE), ('JUDGED (apply --class)', JUDGED), ('REPORT-ONLY', REPORT_ONLY)):
        print(f'== {group}')
        for n in names:
            items = PLANNERS[n]()
            print(f'  {n:<20} {len(items):>5} items  {mb(sum(i.size for i in items)):>9}')
            for i in items[:3 if n in REPORT_ONLY + JUDGED else 0]:
                print(f'      {i.path.relative_to(ROOT)}  [{i.reason[:70]}]')
    last = last_cleanup()
    print('\nlast cleanup:', time.strftime('%Y-%m-%d', time.localtime(last)) if last else 'never')
    return 0


def cmd_due(_a) -> int:
    why = due_reason()
    if why:
        print(f'CLEANUP DUE ({why}): python3 scripts/site_cleanup.py report')
    return 0 if why else 1


def cmd_apply(a) -> int:
    names = a.cls or list(SAFE)
    bad = [n for n in names if n not in SAFE + JUDGED]
    if bad:
        print(f'cannot apply {bad}: report-only or unknown', file=sys.stderr)
        return 2
    total = 0
    for n in names:
        items = PLANNERS[n]()
        freed = apply_class(n, items)
        print(f'{n}: removed {len(items)} ({mb(freed)})')
        total += freed
    print(f'freed {mb(total)}')
    return 0


def cmd_log(_a) -> int:
    print(LOG.read_text() if LOG.exists() else 'no cleanups logged yet')
    return 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest='cmd', required=True)
    sub.add_parser('report').set_defaults(func=cmd_report)
    sub.add_parser('due').set_defaults(func=cmd_due)
    sub.add_parser('log').set_defaults(func=cmd_log)
    ap = sub.add_parser('apply')
    ap.add_argument('--class', dest='cls', action='append', metavar='NAME')
    ap.set_defaults(func=cmd_apply)
    a = p.parse_args(argv)
    return a.func(a)


if __name__ == '__main__':
    sys.exit(main())
