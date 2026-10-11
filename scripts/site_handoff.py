#!/usr/bin/env python3
"""Southampton Refine handoff helpers: next-chat starter, session end, Cursor hooks.

  python3 scripts/site_handoff.py next
  python3 scripts/site_handoff.py next --no-brief
  python3 scripts/site_handoff.py next --copy
  python3 scripts/site_handoff.py next --write
  python3 scripts/site_handoff.py end [Q-nnn]
  python3 scripts/site_handoff.py status
  python3 scripts/site_handoff.py hook-stop
  python3 scripts/site_handoff.py hook-start

Memory stays in site/ files. These commands prepare the next chat — they do
not claim the lock or apply builds.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SITE = ROOT / 'site'
QUEUE = SITE / 'QUEUE.txt'
HANDOFF = SITE / 'HANDOFF.txt'
PENDING = SITE / '.handoff-pending.json'
LOCK = SITE / 'LOCK.json'

CONTEXT_CEILING = '~250K tokens'


def _queue_items():
    """Parse QUEUE.txt into a list of dicts: id, open, text, lines.

    @returns: list of queue item dicts
    """
    items = []
    cur = None
    for line in QUEUE.read_text().splitlines():
        m = re.match(r'\[([ xX])\]\s+(Q-\d+)\s+(.*)', line)
        if m:
            if cur:
                items.append(cur)
            cur = {
                'open': m.group(1) == ' ',
                'id': m.group(2),
                'text': m.group(3).rstrip(),
                'lines': [m.group(3).rstrip()],
            }
            continue
        if cur and (line.startswith('           ') or line.startswith('\t')):
            bit = line.strip()
            if bit:
                cur['lines'].append(bit)
                cur['text'] = (cur['text'] + ' ' + bit).strip()
    if cur:
        items.append(cur)
    return items


def top_open():
    """Return the first open non-BACKLOG queue item, else first backlog, else None.

    @returns: queue item dict or None
    """
    backlog = None
    for it in _queue_items():
        if not it['open']:
            continue
        if 'BACKLOG' in it['text'].upper():
            if backlog is None:
                backlog = it
            continue
        return it
    return backlog


def lock_status():
    """Return lock dict or None; adds ``fresh`` bool when present.

    @returns: lock dict or None
    """
    if not LOCK.exists():
        return None
    try:
        lk = json.loads(LOCK.read_text())
    except (OSError, json.JSONDecodeError):
        return None
    age = time.time() - float(lk.get('heartbeat', 0))
    lk['fresh'] = age < 90 * 60
    return lk


def brief_hint(item):
    """Guess useful context file paths from the queue text.

    @param item: queue item dict
    @returns: list of hint strings
    """
    hints = [
        'site/QUEUE.txt (top open item)',
        'site/PROCESS.txt',
        'site/ISSUES.txt',
        'site/REVIEWS.txt',
        'site/PLACES.txt',
        'site/NOTES.txt',
        'config/world.json',
    ]
    t = item['text'].upper()
    if 'CIVIC' in t:
        hints.insert(1, 'site/PLACES.txt (CIVIC)')
    if 'OSGB' in t or 'COORD' in t:
        hints.insert(1, 'scripts/osgb.py / config/map-maker-offsets.json')
    return hints


def _open_issues():
    """Open/scheduled high-severity issues: (first line, optional detail).

    @returns: list of [line, ...] lists
    """
    out, cur = [], None
    path = SITE / 'ISSUES.txt'
    if not path.exists():
        return out
    for line in path.read_text().splitlines():
        m = re.match(r'(I-\d+)\s+([HML])\s+(\S+)\s+(open|sched\w*)\b', line)
        if m:
            cur = [line.rstrip()] if m.group(2) == 'H' else None
            if cur is not None:
                out.append(cur)
        elif re.match(r'I-\d+', line):
            cur = None
        elif cur is not None and len(cur) < 2 and line.strip():
            cur.append('      ' + line.strip())
    return out


def _last_reviews(n=3):
    """First line of the last ``n`` REVIEWS.txt entries.

    @param n: how many review heads to return
    @returns: list of lines
    """
    path = SITE / 'REVIEWS.txt'
    if not path.exists():
        return []
    heads = [l for l in path.read_text().splitlines() if re.match(r'20\d\d-', l)]
    return heads[-n:]


def _kit_api():
    """``site_kit`` public functions: signature + first docstring line.

    @returns: list of formatted lines
    """
    import ast
    tree = ast.parse((ROOT / 'scripts/site_kit.py').read_text())
    out = []
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.ClassDef)) and not node.name.startswith('_'):
            doc = (ast.get_docstring(node) or '').split('\n')[0][:80]
            if isinstance(node, ast.FunctionDef):
                sig = f'{node.name}({", ".join(a.arg for a in node.args.args)})'
            else:
                sig = f'class {node.name}'
            out.append(f'  {sig:42} {doc}'.rstrip())
    return out


def brief_text(item):
    """Focused session brief so a new chat need not cat every site file.

    @param item: queue item dict
    @returns: multi-line brief string
    """
    lk = lock_status()
    parts = [
        '', '=' * 72,
        f'SESSION BRIEF for {item["id"]} (generated; files are the source of truth)',
        '=' * 72,
        'lock: ' + ('free' if not lk else
                    f'{lk.get("owner")} ({"fresh" if lk.get("fresh") else "stale"}) - {lk.get("task")}'),
        '', 'QUEUE ITEM (full):',
    ] + [f'  {l}' for l in item['lines']]
    issues = _open_issues()
    parts += ['', 'OPEN HIGH ISSUES:']
    parts += [l for iss in issues for l in iss] or ['  (none)']
    parts += ['', 'LAST REVIEWS (first lines; site/REVIEWS.txt):'] + [
        f'  {l[:150]}' for l in _last_reviews()
    ]
    parts += ['', 'SITE_KIT API (scripts/site_kit.py; read a function body only when needed):'] + _kit_api()
    parts += [
        '', 'TOKEN RULES:',
        '- Read site/PROCESS.txt, then work from this brief. Grep / sed -n; do not cat whole files.',
        '- Accuracy only: match photos / aerial / survey. No fictional districts or whimsy.',
        '- Review views via the CONTACT SHEET; open a single full-size view only for detail.',
        '- Batch anything needing the user into ONE ask; do not poll.',
        f'- One queue item per chat. If context passes {CONTEXT_CEILING}, hand off with site_handoff.py end.',
    ]
    return '\n'.join(parts) + '\n'


def starter_text(item, owner_placeholder='<unique-owner>'):
    """Build the copy-paste boot prompt for one queue item.

    @param item: queue item dict
    @param owner_placeholder: text used in the claim line
    @returns: multi-line starter string
    """
    qid = item['id']
    summary = item['text']
    if len(summary) > 220:
        summary = summary[:217].rstrip() + '…'
    hints = '\n'.join(f'- {h}' for h in brief_hint(item))
    return f"""You are refining the Southampton Geocraft world in {ROOT}.

Read site/PROCESS.txt and follow it exactly. Accuracy to the real place only —
no regions, themes or whimsy. Use the SESSION BRIEF below
(from scripts/site_handoff.py next) instead of reading every site file.
Run: python3 scripts/site_lock.py status
If free: python3 scripts/site_lock.py claim {owner_placeholder} "{qid} …"
Then do {qid} from site/QUEUE.txt end to end (survey / plan → preview → apply
with SITE_OWNER=<you> → readback → walk → views → records).

Top open item:
  {qid}  {summary}

Context lives in files, not chat (grep / sed -n what you need):
{hints}

When the item is done: mark QUEUE [x], release the lock, run
  python3 scripts/site_handoff.py end {qid}
Then stop — open a new chat for the next item (do not chain phases here).
Needs: Minecraft open with Southampton2023 + Fabric MCP (F3+P), sole MCP client.
""".strip() + '\n'


def write_handoff_starter(item):
    """Replace the Q-nnn STARTER block in HANDOFF.txt with one for ``item``.

    @param item: open queue item dict
    @returns: path written
    """
    body = HANDOFF.read_text()
    block = (
        f'------------------------------------------------------------------------\n'
        f'{item["id"]} STARTER (copy into a fresh session)\n'
        f'------------------------------------------------------------------------\n'
        f'{starter_text(item)}\n'
    )
    pat = re.compile(
        r'------------------------------------------------------------------------\n'
        r'Q-\d+ STARTER \(copy into a fresh session\)\n'
        r'------------------------------------------------------------------------\n'
        r'.*?'
        r'(?=------------------------------------------------------------------------\nGENERIC BOOT PROMPT)',
        re.S,
    )
    if not pat.search(body):
        raise SystemExit('HANDOFF.txt missing Q-nnn STARTER block before GENERIC BOOT PROMPT')
    HANDOFF.write_text(pat.sub(block, body, count=1))
    return HANDOFF


def set_pending(done_id, next_item):
    """Arm the stop-hook nudge after a finished queue item.

    @param done_id: completed Q-nnn id (or None)
    @param next_item: next open item dict (or None)
    """
    payload = {
        'done': done_id,
        'next': next_item['id'] if next_item else None,
        'next_summary': (next_item['text'][:160] if next_item else None),
        'armed_at': time.strftime('%Y-%m-%d %H:%M:%S'),
        'armed_ts': time.time(),
    }
    PENDING.write_text(json.dumps(payload, indent=1) + '\n')


def clear_pending():
    """Remove the stop-hook nudge marker if present."""
    PENDING.unlink(missing_ok=True)


def read_pending():
    """Return pending handoff dict, or None.

    @returns: dict or None
    """
    if not PENDING.exists():
        return None
    try:
        return json.loads(PENDING.read_text())
    except (OSError, json.JSONDecodeError):
        return None


def copy_clipboard(text):
    """Copy ``text`` to the system clipboard when a known tool exists.

    @param text: string to copy
    @returns: name of tool used, or None
    """
    for cmd in (('pbcopy',), ('wl-copy',), ('xclip', '-selection', 'clipboard')):
        try:
            subprocess.run(cmd, input=text.encode(), check=True)
            return cmd[0]
        except (FileNotFoundError, subprocess.CalledProcessError):
            continue
    return None


def cmd_next(argv):
    """Print (and optionally copy/write) the boot prompt for the top open item.

    @param argv: remaining CLI args
    @returns: exit code
    """
    item = top_open()
    if not item:
        print('No open queue items in site/QUEUE.txt', file=sys.stderr)
        return 1
    text = starter_text(item)
    do_copy = '--copy' in argv
    if '--write' in argv or do_copy:
        write_handoff_starter(item)
    sys.stdout.write(text)
    if not text.endswith('\n'):
        sys.stdout.write('\n')
    if '--no-brief' not in argv:
        sys.stdout.write(brief_text(item))
    if do_copy:
        tool = copy_clipboard(text)
        print(f'# copied via {tool}' if tool else '# clipboard tool not found',
              file=sys.stderr)
    clear_pending()
    return 0


def cmd_end(argv):
    """Mark session end: refresh HANDOFF for the next item and arm the stop hook.

    @param argv: remaining CLI args
    @returns: exit code
    """
    done = None
    for a in argv:
        if re.fullmatch(r'Q-\d+', a):
            done = a
    items = _queue_items()
    if done is None:
        for it in reversed(items):
            if not it['open']:
                done = it['id']
                break
    nxt = top_open()
    if nxt:
        write_handoff_starter(nxt)
        print(f'HANDOFF.txt starter -> {nxt["id"]}')
    else:
        print('HANDOFF.txt unchanged (no open queue item)')
    set_pending(done, nxt)
    print(f'Armed stop-hook nudge (done={done}, next={nxt["id"] if nxt else None})')
    print('Open a new chat and paste:  python3 scripts/site_handoff.py next')
    lk = lock_status()
    if lk and lk.get('fresh'):
        print(f'NOTE: world lock still held by {lk["owner"]} — release before leaving.',
              file=sys.stderr)
    return 0


def cmd_status(_argv):
    """Print lock, top open queue item, and pending nudge.

    @param _argv: unused
    @returns: exit code
    """
    lk = lock_status()
    item = top_open()
    pend = read_pending()
    print('lock:', 'unlocked' if not lk else
          f'{lk.get("owner")} ({"fresh" if lk.get("fresh") else "stale"}) — {lk.get("task")}')
    print('top open:', f'{item["id"]}  {item["text"][:120]}' if item else '(none)')
    print('pending nudge:', json.dumps(pend) if pend else '(none)')
    return 0


def cmd_hook_stop(_argv):
    """Cursor ``stop`` hook: remind the agent to tell the user to hand off.

    @param _argv: unused
    @returns: exit code
    """
    try:
        payload = json.load(sys.stdin)
    except json.JSONDecodeError:
        payload = {}
    status = payload.get('status') or ''
    loop_count = int(payload.get('loop_count') or 0)
    pend = read_pending()
    out = {}
    if pend and status == 'completed' and loop_count == 0:
        nxt = pend.get('next') or (top_open() or {}).get('id') or 'the next QUEUE item'
        done = pend.get('done') or 'the finished item'
        out['followup_message'] = (
            f'Southampton Refine handoff: {done} is done. In one short message, tell the user '
            f'to open a NEW chat and run `python3 scripts/site_handoff.py next` (starter for {nxt}). '
            f'Do not start {nxt} in this thread. Then stop.'
        )
        clear_pending()
    sys.stdout.write(json.dumps(out) + '\n')
    return 0


def cmd_hook_start(_argv):
    """Cursor ``sessionStart`` hook: inject the top open queue item into context.

    @param _argv: unused
    @returns: exit code
    """
    try:
        json.load(sys.stdin)
    except json.JSONDecodeError:
        pass
    item = top_open()
    out = {}
    if item:
        summary = item['text'][:180].rstrip('.')
        out['additional_context'] = (
            f'Southampton Refine handoff: top open QUEUE item is {item["id"]} — {summary}. '
            f'Follow site/PROCESS.txt. Accuracy only (no fictional districts). '
            f'For the full boot prompt run `python3 scripts/site_handoff.py next`. '
            f'Prefer a fresh chat per queue item; files in site/ are the memory.'
        )
    sys.stdout.write(json.dumps(out) + '\n')
    return 0


def main(argv=None):
    """CLI entry: dispatch ``next`` / ``end`` / ``status`` / hook commands.

    @param argv: optional argv override
    @returns: exit code
    """
    argv = list(sys.argv[1:] if argv is None else argv)
    cmd = argv.pop(0) if argv else 'status'
    dispatch = {
        'next': cmd_next,
        'end': cmd_end,
        'status': cmd_status,
        'hook-stop': cmd_hook_stop,
        'hook-start': cmd_hook_start,
    }
    if cmd not in dispatch:
        print(__doc__, file=sys.stderr)
        return 2
    return dispatch[cmd](argv)


if __name__ == '__main__':
    raise SystemExit(main())
