#!/usr/bin/env python3
"""Southampton Refine handoff helpers: next-chat starter, session end, agent hooks.

  python3 scripts/site_handoff.py next
  python3 scripts/site_handoff.py next --no-brief
  python3 scripts/site_handoff.py next --copy
  python3 scripts/site_handoff.py next --copy
  python3 scripts/site_handoff.py next --plan      (read-only: cells/items it would re-queue)
  python3 scripts/site_handoff.py end Q-nnn --summary "…" --view x,y,z[,lx,ly,lz]
  python3 scripts/site_handoff.py status
  python3 scripts/site_handoff.py hook-stop
  python3 scripts/site_handoff.py hook-start

Memory stays in site/ files. These commands prepare the next chat — they do
not claim the lock or apply builds. ``end`` ticks the item, releases the lock and arms the
nudge first (finish_item), then announces ready-for-handoff
aloud, prints the session summary, and moves the player in creative to view
the main change area.

Run ``end`` outside any command sandbox: a sandbox makes macOS ``say`` exit 0
with no audible output.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

from script_env import ROOT  # noqa: E402
SITE = ROOT / 'site'
QUEUE = SITE / 'QUEUE.txt'
HANDOFF = SITE / 'HANDOFF.txt'
PENDING = SITE / '.handoff-pending.json'
LOCK = SITE / 'LOCK.json'

from cell_sources import in_flight_cell, sources_path  # noqa: E402
from rules_context import format_rules_brief, format_starter_rules_line, plan_for_item  # noqa: E402

CONTEXT_CEILING = '~250K tokens'
SAY_PHRASE = 'ready for handoff'
NEXT_CHAT_CMD = 'python3 scripts/site_handoff.py next'
NEXT_CHAT_USER_MSG = (
    f'Follow the instructions given by running: {NEXT_CHAT_CMD}'
)
CHAIN_CEILING = '~100K tokens'
CHAIN_RULE = (
    'Chain rule: when an item is done and needs no user check (readback/patrol clean, '
    'nothing for human eyes, no "awaiting user visual check") and context is still small '
    f'(under {CHAIN_CEILING}), skip `end` and run `{NEXT_CHAT_CMD}` here to continue with '
    'the next item. Otherwise hand off with `end`.'
)
AUTO_START_RULE = (
    'Begin the top queue item immediately in this session: check lock, read '
    'only PROCESS slices + rule files under RULES READING in the SESSION BRIEF, '
    'then execute the item end-to-end. Do not ask the user whether to start — '
    f'running `{NEXT_CHAT_CMD}` (or receiving this starter) is their go-ahead.'
)
SANDBOX_SAY_HINT = (
    'A command sandbox mutes macOS `say` (exit 0, no audio).\n'
    'Re-run this exact command with the sandbox disabled.\n'
    'Pass --skip-say only if audio is truly unavailable.'
)


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


LAYER_STAGES = ('ground', 'trees', 'decor')
QUEUE_DONE = SITE / 'archive' / 'QUEUE-done.txt'
from cellmath import ORIGIN_CELL, ring_cells  # noqa: E402,F401


def _cell_stages(cell):
    path = SITE / 'cells' / f'{cell[0]}_{cell[1]}-STAGES.json'
    try:
        return json.loads(path.read_text()).get('stages', {})
    except (OSError, json.JSONDecodeError):
        return None


def residual_features(cell, idx=None):
    """Unrefined original Geocraft in a cell, packaged as queue features.

    Mapped buildings no feature build covers (cell_features.missing_features) plus any Geocraft
    lumps still standing (lump_scan: unmapped / outside-OSM-clip buildings, or mapped ones a build
    missed), minus recorded stages.lump_sweep.exceptions. One list, one meaning: what is left to refine.

    @param cell: (tx, tz)
    @param idx: optional shared OSMIndex
    @returns: [{'kind': 'building'|'houses'|'lumps', 'label', 'street', 'refs', 'bbox'}]
    """
    from cell_features import missing_features
    from lump_scan import lump_features, scan_cell
    from osm_footprints import OSMIndex
    tx, tz = cell
    try:
        idx = idx or OSMIndex()
        feats = missing_features(tx, tz, idx)
        lumps = scan_cell(tx, tz, idx=idx)
    except (OSError, ValueError, KeyError, SystemExit):
        return []
    taken = {r for f in feats for r in f['refs']}
    return feats + lump_features(lumps, taken, idx.streets)


def cell_gaps(cell, features=True):
    """What keeps a cell from being done.

    A cell is done when ground, trees and decor are applied, the trees mask follows the current
    overhang rule (pass_mask.TREES_RULE, I-061) and no unrefined original Geocraft is left
    (residual_features; recorded lump exceptions excepted).

    @param cell: (tx, tz)
    @param features: also compute residual_features (slow: reads the world and OSM)
    A stage left 'applying' (aborted run, site_stages) is never done: it is reported first as
    in_flight 'in-flight: <plan>' and recovered with scripts/site_recover.py.

    @returns: {'in_flight': ['in-flight: <plan>'], 'layers': [missing pass names], 'trees_stale': bool, 'features': [...]}
    """
    stages = _cell_stages(cell)
    in_flight = [f'in-flight: {v.get("plan", k)}' for k, v in (stages or {}).items()
                 if isinstance(v, dict) and v.get('status') == 'applying']
    ok = ('applied', 'verified')
    layers = [k for k in LAYER_STAGES
              if not any((stages or {}).get(n, {}).get('status') in ok
                         for n in ((k, 'ground-layer') if k == 'ground' else (k,)))]
    stale = False
    if 'trees' not in layers:
        from pass_mask import trees_rule_current
        stale = not trees_rule_current(cell)
    return {'in_flight': in_flight, 'layers': layers, 'trees_stale': stale,
            'features': residual_features(cell) if features else []}


def layers_done(cell):
    """True when the cell is done: layer passes applied, trees current, no unrefined Geocraft left.

    @param cell: (tx, tz)
    @returns: bool
    """
    g = cell_gaps(cell, features=False)
    if g.get('in_flight') or g['layers'] or g['trees_stale']:
        return False
    return not residual_features(cell)


def next_cell(max_ring=12):
    """First cell in ring order (centre, then rings outward) that is not done (see cell_gaps).

    @param max_ring: stop searching beyond this ring
    @returns: (tx, tz, ring) or None
    """
    for r in range(max_ring + 1):
        for cell in ring_cells(r):
            if not layers_done(cell):
                return cell[0], cell[1], r
    return None


def requeue_plan(max_ring=12):
    """Read-only: every started cell (has a STAGES file) that is not done, with its gaps (writes nothing).

    @param max_ring: stop searching beyond this ring
    @returns: [(tx, tz, ring, gaps)] in ring order
    """
    out = []
    for r in range(max_ring + 1):
        for cell in ring_cells(r):
            if _cell_stages(cell) is None:
                continue
            g = cell_gaps(cell)
            if not (g.get('in_flight') or g['layers'] or g['trees_stale'] or g['features']):
                continue
            out.append((cell[0], cell[1], r, g))
    return out


def _max_queue_number():
    n = 0
    for path in (QUEUE, QUEUE_DONE):
        if path.exists():
            for m in re.finditer(r'Q-(\d+)', path.read_text()):
                n = max(n, int(m.group(1)))
    return n


def _queue_block(qid, head, body):
    lines = [f'[ ] {qid}  {head}'] + [f'           {b}' for b in body]
    return '\n' + '\n'.join(lines) + '\n'


def advance_to_next_cell():
    """Queue the next cell that is not done: its unrefined Geocraft as feature items, then passes.

    Appends open items to QUEUE.txt (feature items above the layered-passes item, so the top open
    item is always a feature while any is missing). Features are mapped buildings no build covers
    plus residual Geocraft lumps (unmapped / outside-clip buildings too), packaged per street
    (residual_features). A finished cell regains items only for what is left: features, and a
    trees re-run when its trees mask predates the overhang rule.

    @returns: first new queue item dict, or None if every cell is done
    """
    nxt = next_cell()
    if not nxt:
        return None
    tx, tz, r = nxt
    gaps = cell_gaps((tx, tz))
    n = _max_queue_number()
    blocks, first = [], None
    if gaps.get('in_flight'):
        n += 1
        qid = f'Q-{n:03d}'
        first = qid
        blocks.append(_queue_block(qid, f'CELL {tx},{tz} (r={r}) RECOVER aborted run: {"; ".join(gaps["in_flight"])}.', [
            f'A stage is left "applying" (aborted apply). Run scripts/site_recover.py status, then',
            f'site_recover.py recover {tx},{tz} (dry run) and --apply; report to the user if it is unsure.',
        ]))
    for f in gaps['features']:
        n += 1
        qid = f'Q-{n:03d}'
        first = first or qid
        x0, z0, x1, z1 = (int(v) for v in f['bbox'])
        lump = f['kind'] == 'lumps'
        blocks.append(_queue_block(qid, f'CELL {tx},{tz} (r={r}) FEATURE {f["label"]}. RULES: {"campus" if f["kind"] == "building" else "property"}.', [
            f'Major feature, pass 1 of the cell (HANDOFF-LAYERED-PASSES §1, §4): own build, region',
            f'snapshot + origin fingerprint before apply. bbox {x0},{z0},{x1},{z1}; OSM {",".join(f["refs"][:8])}'
            + (' …' if len(f['refs']) > 8 else '') + '.',
            'Houses: one build for the whole run on the street (shared frontage, roofs, party walls).',
            'House only: no gardens. Lawn is GROUND; trees/shrubs TREES; fences, sheds, planting DECOR.',
            'Use scripts/house_build.py: write site/builds/<name>.json (copy the nearest spec; ways, roofs, front), do not copy a build script.',
        ] + ([
            'Original Geocraft still standing here (lump_scan). Not in OSM or outside its clip: trace the',
            'footprint from the aerial, record source + year (PROCESS.txt 2d-i). Residual after the build must',
            'be 0, or record an exception in the STAGES file (stages.lump_sweep.exceptions).',
        ] if lump else [f'Not covered by any feature build. Auto-queued; before the {tx},{tz} layered passes.'])
          + ([f'First item of a new cell: cell_marker.py --status (must be clean), then --raise {tx},{tz}.'] if not blocks else [])))
    if gaps['layers']:
        n += 1
        qid = f'Q-{n:03d}'
        first = first or qid
        blocks.append(_queue_block(qid, f'CELL {tx},{tz} (r={r}) layered passes: ground, trees, decor. RULES: ground.', [
            'Auto-queued: next in north-centre-then-clockwise order. The cell marker',
            f'(project focus, site/CURRENT-CELL.json) must be up: cell_marker.py --raise {tx},{tz} if not already.',
            'Check neighbour edges; cell_sources --write; mask_undo trees/decor if masks exist;',
            'dry run, check kinds + crowns against the aerial; apply with SITE_OWNER;',
            f'patrol sweep; update site/cells/{tx}_{tz}-STAGES.json;',
            'Done = no unrefined Geocraft left: feature items above cover it; unmapped buildings are built too (PROCESS.txt 2d-i).',
            f'Marker stays up after this run; clear it only when decor is done, checks',
            f'pass and all open issues for the cell are closed: cell_marker.py --clear {tx},{tz}.',
        ]))
    elif gaps['trees_stale']:
        n += 1
        qid = f'Q-{n:03d}'
        first = first or qid
        blocks.append(_queue_block(qid, f'CELL {tx},{tz} (r={r}) TREES re-run (overhang rule, I-061). RULES: foliage.', [
            'Auto-queued: finished cell whose trees mask predates the overhang rule (no rule stamp).',
            'mask_undo trees; re-plan trees with trees_layer (tree belongs to the cell of its trunk, crowns overhang',
            'neighbours, tree-on-tree leaves merge: HANDOFF-LAYERED-PASSES §6); dry run, apply with SITE_OWNER;',
            f'update site/cells/{tx}_{tz}-STAGES.json. Ground and decor stay as they are; check decor interplay.',
        ]))
    if not blocks:
        return None
    QUEUE.write_text(QUEUE.read_text().rstrip('\n') + '\n' + ''.join(blocks))
    return next((i for i in _queue_items() if i['id'] == first), None)


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


def _cell_for_item(item):
    """Coverage cell from queue text ``CELL tx,tz`` or COVERAGE IN FLIGHT.

    @param item: queue item dict
    @returns: (tx, tz) or None
    """
    blob = ' '.join(item.get('lines') or [item.get('text', '')])
    m = re.search(r'CELL\s+(-?\d+)\s*,\s*(-?\d+)', blob, re.I)
    if m:
        return int(m.group(1)), int(m.group(2))
    return in_flight_cell()


def next_chat_prompt_line():
    """Return the one-line user message for the next chat (paste as first message).

    @returns: plain-text prompt for the user to send
    """
    return NEXT_CHAT_USER_MSG


def format_next_chat_copy_block():
    """Printable copy box for the next session (one line between COPY markers).

    @returns: multi-line string for terminal output after ``end``
    """
    line = next_chat_prompt_line()
    bar = '=' * 72
    return (
        f'\n{bar}\n'
        'NEXT CHAT — copy between >>> COPY and <<< COPY (fenced code in chat)\n'
        f'{bar}\n'
        '>>> COPY\n'
        f'{line}\n'
        '<<< COPY\n'
        f'{bar}\n'
    )


def brief_hint(item):
    """Guess useful context file paths from the queue text.

    @param item: queue item dict
    @returns: list of hint strings
    """
    hints = [
        'site/RULES-CONTEXT.txt (what to read when; anti-reread)',
        'site/QUEUE.txt (top open item)',
        'site/FOLIAGE.txt (foliage-last cadence + allowlist)',
        'site/HIGHFIELD-ZONES.txt (9 campus grounds zones)',
        'site/PROCESS.txt (slices only — see SESSION BRIEF RULES READING)',
        'site/COVERAGE.txt (focus + generated cells; coverage CLI in SESSION BRIEF)',
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
    cell = _cell_for_item(item)
    if cell is not None:
        rel = sources_path(*cell).relative_to(ROOT)
        hints.insert(1, f'{rel} (cell sources — read before imagery; regenerate with cell_sources.py --write)')
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


def _coverage_cheatsheet_lines():
    """CLI lines from scripts/coverage.py COVERAGE_CHEATSHEET (single source of truth).

    @returns: non-empty stripped lines for the session brief
    """
    path = ROOT / 'scripts' / 'coverage.py'
    src = path.read_text()
    m = re.search(r'^COVERAGE_CHEATSHEET = """(.*?)"""', src, re.DOTALL | re.MULTILINE)
    if not m:
        return ['(see site/PROCESS.txt §2c)']
    return [ln.rstrip() for ln in m.group(1).strip().splitlines()]


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
    cell = _cell_for_item(item)
    if cell is not None:
        rel = sources_path(*cell).relative_to(ROOT)
        parts += [
            '',
            f'CELL SOURCES ({cell[0]},{cell[1]}):',
            f'  Read {rel} before fetching or viewing reference imagery.',
            f'  Missing or stale: python3 scripts/cell_sources.py --cell {cell[0]},{cell[1]} --write',
            f'  Open source families: python3 scripts/cell_sources.py --cell {cell[0]},{cell[1]} --todo (TRIED ones: no retry without --retry-reason)',
            '  One-time sources pass per new cell (PROCESS §2e step 1b); build steps still obey',
            '  one primary aerial + one street Read per rules/reference-token-budget.md.',
            '  Foliage cadence: site/FOLIAGE.txt; zone index: site/HIGHFIELD-ZONES.txt.',
        ]
        try:
            from cross_zone import cross_zone_report, format_report

            cz = cross_zone_report('highfield', cell[0], cell[1], margin=8)
            parts += ['', 'CROSS-ZONE (read-only):']
            for ln in format_report(cz).splitlines():
                parts.append(f'  {ln}')
        except Exception:
            parts.append('  CROSS-ZONE: (unavailable — coverage built?)')
    cell_rel = None
    if cell is not None:
        cell_rel = str(sources_path(*cell).relative_to(ROOT))
    parts += ['', format_rules_brief(plan_for_item(item, cell_rel))]
    parts += ['', 'LAST REVIEWS (first lines; site/REVIEWS.txt):'] + [
        f'  {l[:150]}' for l in _last_reviews()
    ]
    parts += ['', 'SITE_KIT API (scripts/site_kit.py; read a function body only when needed):'] + _kit_api()
    parts += [
        '',
        'COVERAGE CLI (scripts/coverage.py — do not run --help; use this + PROCESS §2c):',
    ] + [f'  {ln}' if not ln.startswith(' ') else ln for ln in _coverage_cheatsheet_lines()]
    parts += [
        '', 'TOKEN RULES:',
        '- Obey RULES READING above; grep / sed -n; do not cat whole files or re-read listed paths.',
        '- Accuracy only: match photos / aerial / survey. No fictional districts or whimsy.',
        '- Review views via the CONTACT SHEET; open a single full-size view only for detail.',
        '- Batch anything needing the user into ONE ask; do not poll.',
        f'- {CHAIN_RULE}',
        f'- If context passes {CONTEXT_CEILING}, or a user check is needed, hand off with '
        'site_handoff.py end --summary/--view '
        '(run it outside any command sandbox so `say` is audible).',
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
    cell = _cell_for_item(item)
    cell_rel = str(sources_path(*cell).relative_to(ROOT)) if cell else None
    rules_line = format_starter_rules_line(plan_for_item(item, cell_rel))
    return f"""You are refining the Southampton Geocraft world in {ROOT}.

Accuracy to the real place only — no regions, themes or whimsy. Use the SESSION
BRIEF below (from `{NEXT_CHAT_CMD}`) instead of reading every site file.

{AUTO_START_RULE}

{rules_line}

Run: python3 scripts/site_lock.py status
If free: python3 scripts/site_lock.py claim {owner_placeholder} "{qid} …"
Then do {qid} from site/QUEUE.txt end to end (survey/plan → preview → apply with
SITE_OWNER=<you> → readback → walk → evidence check → records). Follow the
"Done bar" under RULES READING in the brief for this item's context.
Stop rule: geometry fix builds → revert + re-survey; no _b/_c patches (I-009).

Parcel coverage: commands are in the SESSION BRIEF below (not coverage.py --help).

Top open item:
  {qid}  {summary}

Context lives in files, not chat (grep / sed -n what you need):
{hints}

When the item is done: mark QUEUE [x], release the lock, then hand off with a
short session summary and a creative-mode view of the main change:
  python3 scripts/site_handoff.py end {qid} --summary "…" --view x,y,z[,lx,ly,lz]
Summary: open with one sentence naming the area and task, then what you did
(not an essay). That speaks "ready for handoff", prints area/task + summary,
and teleports the player.
Run it outside any command sandbox (a sandbox mutes `say`). Then stop — open a new chat for the next item.
{CHAIN_RULE}
Needs: Minecraft open with Southampton2023 + Fabric MCP (F3+P), sole MCP client.
""".strip() + '\n'


def set_pending(done_id, next_item, session_summary=None, view=None):
    """Arm the stop-hook nudge after a finished queue item.

    @param done_id: completed Q-nnn id (or None)
    @param next_item: next open item dict (or None)
    @param session_summary: short what-this-session-did string (or None)
    @param view: parsed view dict from ``parse_view`` (or None)
    """
    payload = {
        'done': done_id,
        'next': next_item['id'] if next_item else None,
        'next_summary': (next_item['text'][:160] if next_item else None),
        'session_summary': session_summary,
        'view': view,
        'armed_at': time.strftime('%Y-%m-%d %H:%M:%S'),
        'armed_ts': time.time(),
    }
    PENDING.write_text(json.dumps(payload, indent=1) + '\n')


def _flag_value(argv, name):
    """Return the value after ``name`` in argv, or None.

    @param argv: CLI args list
    @param name: flag including leading dashes (e.g. ``--summary``)
    @returns: string value or None
    """
    if name not in argv:
        return None
    i = argv.index(name)
    if i + 1 >= len(argv) or argv[i + 1].startswith('--'):
        raise SystemExit(f'{name} requires a value')
    return argv[i + 1]


def parse_view(spec):
    """Parse ``x,y,z`` or ``x,y,z,lx,ly,lz`` into eye / optional look-at.

    @param spec: comma-separated Minecraft coordinates
    @returns: dict with ``pos`` list and optional ``look`` list
    """
    parts = [p.strip() for p in spec.split(',')]
    if len(parts) not in (3, 6):
        raise SystemExit(
            '--view needs x,y,z or x,y,z,lookx,looky,lookz (Minecraft coords)'
        )
    try:
        nums = [float(p) for p in parts]
    except ValueError as e:
        raise SystemExit(f'--view: invalid number ({e})') from e
    out = {'pos': nums[:3]}
    if len(nums) == 6:
        out['look'] = nums[3:]
    return out


def in_cursor_seatbelt_sandbox():
    """Return True when a known agent command sandbox is active (mutes ``say``).

    @returns: True if ``CURSOR_SANDBOX`` is set
    """
    return bool(os.environ.get('CURSOR_SANDBOX'))


def announce_ready():
    """Speak the handoff cue aloud when the ``say`` command exists (macOS).

    MUTED: the spoken cue is commented out. Restore the block below to re-enable.

    @returns: True (nothing spoken while muted)
    """
    # if in_cursor_seatbelt_sandbox():
    #     print(f'ERROR: {SANDBOX_SAY_HINT}', file=sys.stderr)
    #     return False
    # try:
    #     result = subprocess.run(['say', SAY_PHRASE], check=False)
    # except FileNotFoundError:
    #     print(f'(no `say` command — skipped spoken "{SAY_PHRASE}")', file=sys.stderr)
    #     return False
    # if result.returncode != 0:
    #     print(
    #         f'WARNING: `say` exited {result.returncode} — spoken cue may have failed.',
    #         file=sys.stderr,
    #     )
    #     return False
    # print(f'Spoke: "{SAY_PHRASE}"')
    print(f'(spoken "{SAY_PHRASE}" muted)')
    return True


def move_player_creative_view(view):
    """Set creative mode and teleport the player to the handoff viewpoint.

    @param view: dict from ``parse_view`` (``pos``, optional ``look``)
    @returns: None
    @raises: Exception on MCP failure (caller may catch)
    """
    from mc_paced import D, UUID, Paced, xyz

    m = Paced()
    m.call('player_set_gamemode', {'uuid': UUID, 'gamemode': 'creative'})
    args = {
        'uuid': UUID,
        'dimension': D,
        'position': xyz(view['pos']),
    }
    if view.get('look') is not None:
        args['facing'] = xyz(view['look'])
    m.call('entity_teleport', args)
    pos = view['pos']
    print(f'Player -> creative at {pos[0]:g},{pos[1]:g},{pos[2]:g}', end='')
    if view.get('look') is not None:
        look = view['look']
        print(f' facing {look[0]:g},{look[1]:g},{look[2]:g}')
    else:
        print()


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


def tick_queue_item(qid):
    """Mark ``qid`` [x] in QUEUE.txt (atomic replace; no-op if absent or already ticked).

    @param qid: Q-nnn
    @returns: True when the file changed
    """
    text = QUEUE.read_text()
    new = re.sub(rf'^\[ \](\s+{re.escape(qid)}\b)', r'[x]\1', text, count=1, flags=re.M)
    if new == text:
        return False
    tmp = QUEUE.with_name(QUEUE.name + '.tmp')
    tmp.write_text(new)
    os.replace(tmp, QUEUE)
    return True


def release_lock():
    """Drop LOCK.json (session end: the builder is done). @returns: previous owner or None"""
    lk = lock_status()
    LOCK.unlink(missing_ok=True)
    return lk.get('owner') if lk else None


def finish_item(done):
    """The state change of ``end``, all together and first: tick the item, release the lock, clear the nudge.

    Done before anything cosmetic (say, teleport, archive, starter), so a later failure cannot leave
    the queue unticked, the lock held or a stale nudge naming the finished item (I-046).

    @param done: Q-nnn that was finished (or None)
    @returns: (ticked, released_owner)
    """
    ticked = tick_queue_item(done) if done else False
    owner = release_lock()
    clear_pending()
    return ticked, owner


def cmd_plan(_argv):
    """Read-only: what ``next`` would re-queue across all started cells (writes nothing)."""
    plan = requeue_plan()
    items = sum(len(g['features']) + (1 if g['layers'] or g['trees_stale'] else 0) + (1 if g.get('in_flight') else 0)
                for *_c, g in plan)
    print(f'{len(plan)} cell(s) not done, {items} queue item(s) would be written (nothing written):')
    for tx, tz, r, g in plan:
        bits = list(g.get('in_flight') or []) + [f'{f["kind"]} {f["label"]} bbox={list(f["bbox"])}' for f in g['features']]
        if g['layers']:
            bits.append('layered passes missing: ' + ','.join(g['layers']))
        elif g['trees_stale']:
            bits.append('TREES re-run (old overhang rule)')
        print(f'  {tx},{tz} r={r}: ' + ' | '.join(bits))
    return 0


def cmd_next(argv):
    """Print (and optionally copy/write) the boot prompt for the top open item.

    @param argv: remaining CLI args
    @returns: exit code
    """
    if '--plan' in argv or '--dry-run' in argv:
        return cmd_plan(argv)
    item = top_open()
    if not item or 'BACKLOG' in item['text'].upper():
        item = advance_to_next_cell() or item
    if not item:
        print('No open queue items in site/QUEUE.txt', file=sys.stderr)
        return 1
    text = starter_text(item)
    do_copy = '--copy' in argv
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
    """Mark session end: announce, summarise, move player, archive, arm hook.

    Archiving (``site_archive.run``) moves ``[x]`` queue items, closed issues
    and older reviews into ``site/archive/``; a failure there only warns.

    Requires ``--summary`` and ``--view`` so the user hears "ready for handoff",
    sees QUEUE area/task plus what this session did, and is left in creative
    at the main change. Summary should open with one sentence naming area + task.
    Invoke it outside any command sandbox so ``say`` is audible; a sandbox
    fails fast with exit 3.

    @param argv: remaining CLI args (Q-nnn, --summary, --view, optional --skip-say/--skip-view)
    @returns: exit code
    """
    done = None
    for a in argv:
        if re.fullmatch(r'Q-\d+', a):
            done = a
    summary = _flag_value(argv, '--summary')
    view_spec = _flag_value(argv, '--view')
    skip_say = '--skip-say' in argv
    skip_view = '--skip-view' in argv
    if not summary:
        print(
            'Usage: site_handoff.py end Q-nnn --summary "area + task; what you did" '
            '--view x,y,z[,lx,ly,lz]\n'
            '  Speaks "ready for handoff", prints QUEUE area/task + summary, '
            'moves the player in creative to the main change area.\n'
            '  Run outside any command sandbox (a sandbox mutes say).',
            file=sys.stderr,
        )
        return 2
    # if not skip_say and in_cursor_seatbelt_sandbox():
    #     print(f'ERROR: {SANDBOX_SAY_HINT}', file=sys.stderr)
    #     return 3
    view = None
    if not skip_view:
        if not view_spec:
            print(
                'end requires --view x,y,z[,lx,ly,lz] (main change viewpoint), '
                'or --skip-view if Minecraft/MCP is unavailable.',
                file=sys.stderr,
            )
            return 2
        view = parse_view(view_spec)

    items = _queue_items()
    if done is None:
        lk = lock_status()
        m = re.search(r'Q-\d+', (lk or {}).get('task', ''))
        done = m.group(0) if m else None
    if done is None:
        for it in reversed(items):
            if not it['open']:
                done = it['id']
                break
    done_item = next((it for it in items if it['id'] == done), None) if done else None
    area_line = None
    if done_item:
        area_line = done_item['text']
        if len(area_line) > 160:
            area_line = area_line[:157].rstrip() + '…'

    ticked, owner = finish_item(done)
    print(f'{done or "no item"}: {"ticked [x]" if ticked else "already ticked / not in queue"}; '
          f'lock {"released (was " + str(owner) + ")" if owner else "was not held"}; pending nudge cleared')

    print('')
    print('=' * 72)
    print(f'SESSION SUMMARY ({done or "unknown"})')
    if area_line:
        print(f'Area / task: {done} — {area_line}')
    print('=' * 72)
    print(summary.strip())
    print('=' * 72)
    print('')

    if not skip_say and not announce_ready():
        print(
            'ERROR: spoken handoff cue failed. Fix audio or pass --skip-say.',
            file=sys.stderr,
        )
        return 3
    if view is not None:
        try:
            move_player_creative_view(view)
        except Exception as e:
            print(f'WARNING: could not move player ({e}). MCP running?', file=sys.stderr)
            print('         Re-run with Minecraft + Fabric MCP, or pass --skip-view.',
                  file=sys.stderr)

    try:
        import site_archive
        site_archive.run()
    except Exception as e:
        print(f'WARNING: site_archive failed ({e}); live files left as they were.\n'
              '         Re-run: python3 scripts/site_archive.py run', file=sys.stderr)

    nxt = top_open()
    if nxt and nxt['id'] == done:
        nxt = None      # never name the finished item as the next one
    set_pending(done, nxt, session_summary=summary.strip(), view=view)
    print(f'Armed stop-hook nudge (done={done}, next={nxt["id"] if nxt else None})')
    sys.stdout.write(format_next_chat_copy_block())
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
    """Agent ``stop`` hook: remind the agent to tell the user to hand off.

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
        sess = pend.get('session_summary') or ''
        sess_bit = f' Session did: {sess}' if sess else ''
        out['followup_message'] = (
            f'Southampton Refine handoff: {done} is done.{sess_bit} '
            f'Confirm the user heard "ready for handoff" and is looking at the change in creative. '
            f'Then open a NEW chat. Show the NEXT CHAT copy box from `site_handoff.py end` '
            f'output (between >>> COPY and <<< COPY) as a markdown fenced code block — '
            f'not inline prose. Starter for {nxt}. Do not start {nxt} in this thread. Then stop.'
        )
        clear_pending()
    sys.stdout.write(json.dumps(out) + '\n')
    return 0


def cmd_hook_start(_argv):
    """Agent ``sessionStart`` hook: inject the top open queue item into context.

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
            f'Accuracy only (no fictional districts). Run `{NEXT_CHAT_CMD}` once; '
            f'follow RULES READING in the SESSION BRIEF (site/RULES-CONTEXT.txt). '
            f'Do not read the whole PROCESS.txt. '
            f'{AUTO_START_RULE} '
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
