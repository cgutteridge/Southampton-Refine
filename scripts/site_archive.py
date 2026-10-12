#!/usr/bin/env python3
"""Move finished records out of the live site/ files into site/archive/.

  python3 scripts/site_archive.py run [--dry-run] [--keep-reviews N]
  python3 scripts/site_archive.py next-id Q|I

Live files stay short so agents only read open work:

  site/QUEUE.txt    ``[x]`` items        -> site/archive/QUEUE-done.txt
  site/ISSUES.txt   done/fixed issues    -> site/archive/ISSUES-closed.txt
  site/REVIEWS.txt  all but last N dated -> site/archive/REVIEWS-archive.txt

Nothing is deleted. IDs, wording and order are kept, so
``grep -rn Q-017 site/`` still finds every record. Each archive is written
(atomically) before its live file is rewritten, and blocks already present in
the archive are not appended twice, so an interrupted run can be re-run.

``next-id`` scans live files and archives, so a new Q-/I- number is never
reused after its predecessor has been archived.
"""
from __future__ import annotations

import os
import re
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SITE = ROOT / 'site'
ARCHIVE_DIRNAME = 'archive'

DEFAULT_KEEP_REVIEWS = 10
CLOSED_ISSUE_STATUSES = frozenset({'done', 'fixed', 'closed', 'wontfix', 'dup', 'duplicate'})

QUEUE_ITEM_RE = re.compile(r'\[([ xX-])\]\s+(Q-\d+)\b')
ISSUE_HEAD_RE = re.compile(r'(I-\d+)\s+[HML]\s+\S+\s+(\w+)')
REVIEW_HEAD_RE = re.compile(r'20\d\d-\d\d-\d\d\b')
ID_RE = {'Q': re.compile(r'\bQ-(\d+)\b'), 'I': re.compile(r'\bI-(\d+)\b')}


@dataclass
class Block:
    """A run of lines from a site file.

    ``key`` is the record id (Q-nnn / I-nnn / review head line) or ``None``
    for free text (preamble, section headers) that always stays live.
    """

    lines: list[str]
    key: str | None = None
    archive: bool = False


@dataclass
class Spec:
    """How one live file maps to its archive."""

    live: str
    archive: str
    title: str
    pointer: str
    blocks: list[Block] = field(default_factory=list)


def _split(lines, is_head):
    """Split lines into blocks; a block starts at each line where ``is_head`` is true.

    Lines before the first head, and any later column-0 line that is not a
    head (e.g. a ``BACKLOG`` header or ``----`` rule), become free-text blocks.
    Indented and blank lines belong to the block above them.

    @param lines: file lines without newlines
    @param is_head: callable(line) -> key str or None
    @returns: list of Block
    """
    blocks = []
    cur = Block([])
    for line in lines:
        key = is_head(line)
        starts_free = (
            key is None and cur.key is not None and line[:1] not in ('', ' ', '\t')
        )
        if key is not None or starts_free:
            if cur.lines:
                blocks.append(cur)
            cur = Block([line], key=key)
            continue
        cur.lines.append(line)
    if cur.lines:
        blocks.append(cur)
    return blocks


def _split_reviews(lines):
    """Split REVIEWS.txt: each dated entry runs until the next dated line.

    TOKEN NOTES and other column-0 text after an entry stay with that entry.

    @param lines: file lines without newlines
    @returns: list of Block
    """
    blocks = []
    cur = Block([])
    for line in lines:
        if REVIEW_HEAD_RE.match(line):
            if cur.lines:
                blocks.append(cur)
            cur = Block([line], key=line.rstrip())
            continue
        cur.lines.append(line)
    if cur.lines:
        blocks.append(cur)
    return blocks


def _queue_head(line):
    """Return the Q-id when ``line`` opens a queue item, else None.

    @param line: one file line
    @returns: key string or None
    """
    m = QUEUE_ITEM_RE.match(line)
    return m.group(2) if m else None


def _issue_head(line):
    """Return the I-id when ``line`` opens an issue, else None.

    @param line: one file line
    @returns: key string or None
    """
    m = ISSUE_HEAD_RE.match(line) or re.match(r'(I-\d+)\b', line)
    return m.group(1) if m else None


def plan_queue(text):
    """Mark ``[x]`` queue items for archiving; ``[ ]`` and ``[-]`` stay live.

    @param text: QUEUE.txt contents
    @returns: list of Block
    """
    blocks = _split(text.splitlines(), _queue_head)
    for b in blocks:
        if b.key:
            m = QUEUE_ITEM_RE.match(b.lines[0])
            b.archive = m.group(1) in 'xX'
    return blocks


def plan_issues(text):
    """Mark issues whose status is done/fixed/closed for archiving.

    @param text: ISSUES.txt contents
    @returns: list of Block
    """
    blocks = _split(text.splitlines(), _issue_head)
    for b in blocks:
        if b.key:
            m = ISSUE_HEAD_RE.match(b.lines[0])
            b.archive = bool(m) and m.group(2).lower() in CLOSED_ISSUE_STATUSES
    return blocks


def plan_reviews(text, keep=DEFAULT_KEEP_REVIEWS):
    """Mark every dated review entry except the last ``keep`` for archiving.

    @param text: REVIEWS.txt contents
    @param keep: number of most recent entries to leave live (>= 0)
    @returns: list of Block
    """
    if keep < 0:
        raise ValueError('keep must be >= 0')
    blocks = _split_reviews(text.splitlines())
    dated = [b for b in blocks if b.key]
    for b in dated[: max(len(dated) - keep, 0)]:
        b.archive = True
    return blocks


def _tidy(lines):
    """Strip trailing blanks and collapse runs of blank lines to one.

    @param lines: list of lines
    @returns: new list of lines
    """
    out = []
    for line in lines:
        if not line.strip() and out and not out[-1].strip():
            continue
        out.append(line.rstrip() if not line.strip() else line)
    while out and not out[-1].strip():
        out.pop()
    return out


def _body(block):
    """Block text without trailing blank lines (used for archive dedupe).

    @param block: Block
    @returns: string
    """
    return '\n'.join(_tidy(block.lines))


def _atomic_write(path, text):
    """Write ``text`` to ``path`` via a temp file + rename in the same dir.

    @param path: Path
    @param text: full new contents
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f'.{path.name}.', suffix='.tmp')
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as fh:
            fh.write(text)
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


def _with_pointer(blocks, pointer):
    """Return live lines, adding the archive pointer to the preamble once.

    @param blocks: blocks that stay live
    @param pointer: one-line note naming the archive file
    @returns: list of lines
    """
    lines = [l for b in blocks for l in b.lines]
    if any(pointer in l for l in lines):
        return lines
    pre = blocks[0].lines if blocks and blocks[0].key is None else []
    insert_at = 0
    for i, line in enumerate(pre):
        if not line.strip():
            break
        insert_at = i + 1
    return lines[:insert_at] + [pointer] + lines[insert_at:]


def archive_file(spec, site=SITE, dry=False):
    """Move ``spec``'s archivable blocks from its live file into its archive.

    @param spec: Spec with ``blocks`` already planned
    @param site: site directory holding the live file and ``archive/``
    @param dry: report only; write nothing
    @returns: (moved_keys, skipped_duplicate_keys)
    """
    moving = [b for b in spec.blocks if b.archive]
    if not moving:
        return [], []
    arc_path = site / ARCHIVE_DIRNAME / spec.archive
    existing = arc_path.read_text(encoding='utf-8') if arc_path.exists() else ''
    new_bodies, moved, dupes = [], [], []
    for b in moving:
        body = _body(b)
        if body and body in existing:
            dupes.append(b.key)
            continue
        new_bodies.append(body)
        moved.append(b.key)
    if dry:
        return moved, dupes
    if new_bodies:
        head = existing.rstrip('\n') if existing else spec.title
        _atomic_write(arc_path, head + '\n\n' + '\n\n'.join(new_bodies) + '\n')
    live_blocks = [b for b in spec.blocks if not b.archive]
    live_lines = _tidy(_with_pointer(live_blocks, spec.pointer))
    _atomic_write(site / spec.live, '\n'.join(live_lines) + '\n')
    return moved, dupes


def build_specs(site=SITE, keep_reviews=DEFAULT_KEEP_REVIEWS):
    """Plan all three files; missing live files are skipped.

    @param site: site directory
    @param keep_reviews: dated review entries to leave live
    @returns: list of Spec with blocks planned
    """
    defs = [
        Spec('QUEUE.txt', 'QUEUE-done.txt',
             'SOUTHAMPTON REFINE — QUEUE (archived [x] items, oldest first)',
             'Done items: site/archive/QUEUE-done.txt (moved by scripts/site_archive.py).'),
        Spec('ISSUES.txt', 'ISSUES-closed.txt',
             'SOUTHAMPTON REFINE — ISSUES (archived done/fixed, oldest first)',
             'Closed issues: site/archive/ISSUES-closed.txt (scripts/site_archive.py).'),
        Spec('REVIEWS.txt', 'REVIEWS-archive.txt',
             'SOUTHAMPTON REFINE — REVIEWS (archived entries, oldest first)',
             'Older reviews: site/archive/REVIEWS-archive.txt (scripts/site_archive.py).'),
    ]
    planners = {
        'QUEUE.txt': plan_queue,
        'ISSUES.txt': plan_issues,
        'REVIEWS.txt': lambda t: plan_reviews(t, keep_reviews),
    }
    out = []
    for spec in defs:
        path = site / spec.live
        if not path.exists():
            continue
        spec.blocks = planners[spec.live](path.read_text(encoding='utf-8'))
        out.append(spec)
    return out


def run(site=SITE, dry=False, keep_reviews=DEFAULT_KEEP_REVIEWS, out=sys.stdout):
    """Archive finished records in every live site file.

    @param site: site directory
    @param dry: report only; write nothing
    @param keep_reviews: dated review entries to leave live
    @param out: stream for the report
    @returns: total number of blocks moved (or that would move when ``dry``)
    """
    total = 0
    for spec in build_specs(site, keep_reviews):
        moved, dupes = archive_file(spec, site, dry)
        total += len(moved)
        verb = 'would move' if dry else 'moved'
        label = ', '.join(k if not k.startswith('20') else k[:10] for k in moved)
        print(f'{spec.live}: {verb} {len(moved)} -> archive/{spec.archive}'
              + (f' ({label})' if moved and len(label) < 400 else ''), file=out)
        if dupes:
            print(f'  already archived, dropped from live: {len(dupes)}', file=out)
    return total


def next_id(prefix, site=SITE):
    """Next unused Q-/I- number across live files and archives.

    @param prefix: 'Q' or 'I'
    @param site: site directory
    @returns: id string, e.g. 'Q-043'
    """
    rx = ID_RE[prefix]
    live = 'QUEUE.txt' if prefix == 'Q' else 'ISSUES.txt'
    paths = [site / live, *sorted((site / ARCHIVE_DIRNAME).glob('*.txt'))]
    best = 0
    for p in paths:
        if p.exists():
            for m in rx.finditer(p.read_text(encoding='utf-8')):
                best = max(best, int(m.group(1)))
    return f'{prefix}-{best + 1:03d}'


def main(argv=None):
    """CLI entry point.

    @param argv: argument list (defaults to sys.argv[1:])
    @returns: exit code
    """
    argv = list(sys.argv[1:] if argv is None else argv)
    cmd = argv.pop(0) if argv else ''
    if cmd == 'run':
        keep = DEFAULT_KEEP_REVIEWS
        if '--keep-reviews' in argv:
            i = argv.index('--keep-reviews')
            try:
                keep = int(argv[i + 1])
            except (IndexError, ValueError):
                print('--keep-reviews needs an integer', file=sys.stderr)
                return 2
            if keep < 0:
                print('--keep-reviews must be >= 0', file=sys.stderr)
                return 2
        run(dry='--dry-run' in argv, keep_reviews=keep)
        return 0
    if cmd == 'next-id' and argv and argv[0] in ID_RE:
        print(next_id(argv[0]))
        return 0
    print(__doc__.strip(), file=sys.stderr)
    return 2


if __name__ == '__main__':
    sys.exit(main())
