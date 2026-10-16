#!/usr/bin/env python3
"""Static HTML pages for people: one index of cells and one page per cell, built only from files that already exist.

Writes site/pages/index.html and site/pages/cell-<tx>_<tz>.html. It never renders, screenshots or copies media:
images are linked in place from verification/site when a build or a person already made them. A cell page shows
the layer table, every stage record, the matching images, related issues and run-log blocks.

  .venv/bin/python scripts/site_pages.py            # all cells with a STAGES file (+ not-started ring cells on the index)
  .venv/bin/python scripts/site_pages.py --no-gaps  # skip the slow authoritative cell_gaps check (about 20 s)

Extra images that have no cell id in their name: add them to site/pages/media-map.json as
{"file name in verification/site": ["tx,tz", ...]}.
"""
from __future__ import annotations

import argparse
import html
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path

from script_env import ROOT  # noqa: E402
import site_status as ss  # noqa: E402
from cellmath import CELL  # noqa: E402

PAGES = ROOT / 'site/pages'
MEDIA = ROOT / 'verification/site'
ISSUES = ROOT / 'site/ISSUES.txt'
MEDIA_MAP = PAGES / 'media-map.json'
IMG = ('.png', '.jpg', '.jpeg', '.webp')
RING_LIMIT = 3                         # cells beyond this ring are not listed as "not started"
CAPTIONS = [
    ('-ground-kinds', 'Ground classes the layer chose (grass, paving, brick, tarmac) before it was applied.'),
    ('-trees-crowns', 'Tree sites: magenta tree, cyan bush, red skipped.'),
    ('-preview', 'Plan preview of what the stage placed.'),
    ('cmp-', 'Comparison panels (aerial vs plan). The title inside the image says which panel is which.'),
    ('-aerial-crop', 'Aerial crop with OSM outlines and a 10-block grid.'),
]
STATUS_ORDER = ['In progress', 'Completed', 'Built, items remaining', 'Layers incomplete', 'Not started']

CSS = """
:root{--bg:#fafaf7;--fg:#1d1f21;--muted:#5c6166;--card:#fff;--line:#dcdcd4;--accent:#1f6f43;--accent-bg:#e6f2ea;
--warn:#8a4b00;--warn-bg:#fdf1dc;--bad:#9b2222;--bad-bg:#fbe7e7;--code-bg:#f0efe8}
@media(prefers-color-scheme:dark){:root:not([data-theme=light]){--bg:#17181a;--fg:#e8e8e3;--muted:#a2a7ad;--card:#1f2124;
--line:#34373b;--accent:#6fcf97;--accent-bg:#1c2a22;--warn:#f0b45c;--warn-bg:#2d2415;--bad:#ff8a8a;--bad-bg:#331c1c;--code-bg:#26282b}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);font:16px/1.55 system-ui,-apple-system,"Segoe UI",sans-serif}
main{max-width:70rem;margin:0 auto;padding:1.6rem 1rem 4rem}h1{font-size:1.7rem;margin:.2rem 0}h2{font-size:1.2rem;margin:2rem 0 .6rem;
padding-top:.7rem;border-top:1px solid var(--line)}a{color:var(--accent)}code{font-family:ui-monospace,Menlo,monospace;font-size:.88em;
background:var(--code-bg);padding:.08em .35em;border-radius:4px}.muted{color:var(--muted)}.crumbs{font-size:.9rem}
table{border-collapse:collapse;width:100%;font-size:.93rem;margin:.4rem 0 1rem}th,td{text-align:left;vertical-align:top;
padding:.4rem .55rem;border-bottom:1px solid var(--line)}th{color:var(--muted);font-size:.82rem}
.badge{display:inline-block;padding:.05rem .55rem;border-radius:999px;font-size:.8rem;border:1px solid var(--line);background:var(--card)}
.b-done{background:var(--accent-bg);color:var(--accent);border-color:var(--accent)}.b-prog{background:var(--warn-bg);color:var(--warn);border-color:var(--warn)}
.b-bad{background:var(--bad-bg);color:var(--bad);border-color:var(--bad)}
.cards{display:grid;gap:.8rem;grid-template-columns:repeat(auto-fill,minmax(13.5rem,1fr))}
.card{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:.7rem .8rem}.card h3{margin:.1rem 0 .3rem;font-size:1rem}
.card img{width:100%;height:7rem;object-fit:cover;border-radius:6px;background:var(--code-bg);margin-bottom:.4rem}
.gallery{display:grid;gap:1rem;grid-template-columns:repeat(auto-fill,minmax(20rem,1fr))}
figure{margin:0;background:var(--card);border:1px solid var(--line);border-radius:10px;padding:.6rem}
figure img{width:100%;height:auto;border-radius:6px;background:var(--code-bg)}figcaption{font-size:.85rem;color:var(--muted);margin-top:.4rem}
details{margin:.3rem 0}summary{cursor:pointer}pre{white-space:pre-wrap;background:var(--code-bg);padding:.6rem .8rem;border-radius:8px;font-size:.85rem}
"""


def e(s) -> str:
    return html.escape(str(s))


def rel(path: Path, start: Path) -> str:
    return os.path.relpath(path, start).replace(os.sep, '/')


def cell_tokens(cell) -> list[str]:
    tx, tz = cell
    return [f'{tx}_m{abs(tz)}' if tz < 0 else f'{tx}_{tz}']


def plan_names(sts: dict) -> list[str]:
    seen = []
    for v in sts.values():
        m = re.match(r'[\w]+', str(v.get('plan') or ''))
        if m and m[0] not in seen:
            seen.append(m[0])
    return seen


def find_media(cell, sts: dict, media_dir: Path | None = None, extra: dict | None = None) -> list[tuple[str, Path]]:
    """[(group, path)] for existing images that belong to this cell. Nothing is created."""
    media_dir = media_dir or MEDIA
    if not media_dir.exists():
        return []
    plans, toks = plan_names(sts), cell_tokens(cell)
    key = f'{cell[0]},{cell[1]}'
    out = []
    for f in sorted(media_dir.iterdir(), key=lambda p: (p.stat().st_mtime, p.name)):
        if f.suffix.lower() not in IMG or f.name.startswith('cell_marker'):
            continue
        group = next((p for p in plans if f.name.startswith(p + '-')), None)
        if group is None and (any(t in f.name for t in toks) or key in (extra or {}).get(f.name, [])):
            group = 'Comparisons and extras'
        if group:
            out.append((group, f))
    return out


def caption(f: Path) -> str:
    for needle, text in CAPTIONS:
        if needle in f.name:
            return text
    return ''


def load_media_map() -> dict:
    return ss.read_json(MEDIA_MAP) or {}


def issues_for(cell) -> list[tuple[str, str]]:
    """[(issue id + title line, first 500 chars)] for ISSUES.txt entries that mention this cell."""
    if not ISSUES.exists():
        return []
    pat = re.compile(r'(?<![\d-])' + re.escape(f'{cell[0]},{cell[1]}') + r'(?!\d)')
    out = []
    for block in re.split(r'(?m)^(?=I-\d+\s)', ISSUES.read_text()):
        m = re.match(r'(I-\d+)\s+(.*)', block)
        if m and pat.search(block):
            out.append((f'{m[1]}  {m[2][:110]}', block.strip()[:500]))
    return out


def classify(cell, sts, gaps: dict | None, here, lock_task: str) -> str:
    in_flight = (gaps or {}).get('in_flight') or any(v.get('status') == 'applying' for v in sts.values())
    if cell == here or in_flight or f'{cell[0]},{cell[1]}' in (lock_task or ''):
        return 'In progress'
    if gaps is not None:
        if not any(v for k, v in gaps.items() if v):
            return 'Completed'
        return 'Built, items remaining' if ss.layers_applied(sts) else 'Layers incomplete'
    return 'Built, items remaining' if ss.layers_applied(sts) else 'Layers incomplete'


def gap_text(g: dict | None) -> str:
    if g is None:
        return 'not checked'
    parts = [k.replace('_', ' ') if v is True else f'{k} {len(v) if hasattr(v, "__len__") else v}' for k, v in g.items() if v]
    return ', '.join(parts) or 'none'


def bbox(cell) -> str:
    x0, z0 = cell[0] * CELL, cell[1] * CELL
    return f'x {x0}..{x0 + 127}, z {z0}..{z0 + 127}'


def badge(status: str, here: bool = False) -> str:
    cls = {'Completed': 'b-done', 'In progress': 'b-prog', 'Layers incomplete': 'b-bad'}.get(status, '')
    return f'<span class="badge {cls}">{e(status)}</span>' + (' <span class="badge b-prog">marker is here</span>' if here else '')


def page(title: str, body: str, depth_note: str = '') -> str:
    return (f'<!doctype html><html lang="en-GB"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
            f'<title>{e(title)}</title><style>{CSS}</style></head><body><main>{depth_note}{body}'
            f'<p class="muted">Generated {datetime.now():%Y-%m-%d %H:%M} by scripts/site_pages.py from STAGES files, ISSUES.txt and existing images. '
            f'Nothing on this page was rendered for it.</p></main></body></html>')


def cell_page(cell, sts, gaps, status, media, here, runlog) -> str:
    out = PAGES
    rows = []
    for layer, keys in ss.LAYER_KEYS.items():
        v = max((sts[k] for k in keys if k in sts), key=lambda x: ss.stage_time(x) or datetime.min, default=None)
        s = ss.layer_status(sts, layer)
        rb = (v or {}).get('readback') or {}
        rows.append(f'<tr><td>{layer}</td><td>{"✓ " if s in ss.GOOD else ""}{e(s or "not recorded")}</td>'
                    f'<td>{e((ss.stage_time(v) or "") if v else "")}</td><td>{e((v or {}).get("blocks", ""))}</td><td>{e(rb.get("mismatches", ""))}</td></tr>')
    stage_rows = []
    for ev in ss.events({cell: sts}):
        stage_rows.append(f'<tr><td>{ev["when"]:%d %b %H:%M}</td><td><code>{e(ev["stage"])}</code></td><td>{e(ev["status"])}</td>'
                          f'<td>{e(ev["blocks"] if ev["blocks"] is not None else "")}</td><td>{e(ev["mismatches"] or "")}</td></tr>')
    notes = ''.join(f'<details><summary><code>{e(k)}</code> note</summary><pre>{e(v.get("note"))}</pre></details>'
                    for k, v in sts.items() if v.get('note'))
    groups: dict = {}
    for g, f in media:
        groups.setdefault(g, []).append(f)
    gallery = ''
    for g, files in groups.items():
        figs = ''.join(f'<figure><a href="{rel(f, out)}"><img loading="lazy" src="{rel(f, out)}" alt="{e(f.name)}"></a>'
                       f'<figcaption><code>{e(f.name)}</code> · {datetime.fromtimestamp(f.stat().st_mtime):%d %b %H:%M}<br>{e(caption(f))}</figcaption></figure>'
                       for f in files)
        gallery += f'<h3>{e(g)}</h3><div class="gallery">{figs}</div>'
    iss = ''.join(f'<details><summary>{e(t)}</summary><pre>{e(b)}</pre></details>' for t, b in issues_for(cell)) \
        or '<p class="muted">No issue mentions this cell.</p>'
    log = ''.join(f'<pre>{e(b)}</pre>' for b in runlog) or '<p class="muted">No run-log entry yet.</p>'
    links = ' · '.join(f'<a href="{rel(p, out)}">{n}</a>' for n, p in [
        ('STAGES json', ROOT / f'site/cells/{cell[0]}_{cell[1]}-STAGES.json'),
        ('SOURCES', ROOT / f'site/cells/{cell[0]}_{cell[1]}-SOURCES.txt')] if p.exists())
    body = (f'<p class="crumbs"><a href="index.html">All cells</a> · <a href="{rel(ROOT / "HUMANS.html", out)}">HUMANS</a></p>'
            f'<h1>Cell {cell[0]},{cell[1]} {badge(status, cell == here)}</h1>'
            f'<p class="muted">Ring {ss.ring(cell)} · {bbox(cell)} · remaining per cell_gaps: {e(gap_text(gaps))}</p>'
            f'<p>{links}</p>'
            f'<h2>Layers</h2><table><tr><th>Layer</th><th>Status</th><th>When</th><th>Blocks</th><th>Mismatches</th></tr>{"".join(rows)}</table>'
            f'<h2>Run log</h2>{log}'
            f'<h2>Images already made for this cell</h2>{gallery or "<p class=muted>No existing images match this cell.</p>"}'
            f'<h2>Related issues</h2>{iss}'
            f'<h2>Every stage record</h2><table><tr><th>When</th><th>Stage</th><th>Status</th><th>Blocks</th><th>Mismatches</th></tr>'
            f'{"".join(stage_rows)}</table>{notes}')
    return page(f'Cell {cell[0]},{cell[1]}', body)


def ring_cells(limit: int = RING_LIMIT):
    cx, cz = ss.CENTRE
    return [(cx + dx, cz + dz) for dx in range(-limit, limit + 1) for dz in range(-limit, limit + 1)]


def index_page(infos: dict, not_started: list, here, lock: str) -> str:
    out = PAGES
    secs = ''
    for status in STATUS_ORDER:
        cells = sorted((c for c, i in infos.items() if i['status'] == status), key=lambda c: (ss.ring(c), c))
        if status == 'Not started':
            if not not_started:
                continue
            chips = ''.join(f'<span class="badge">{c[0]},{c[1]}</span> ' for c in sorted(not_started, key=lambda c: (ss.ring(c), c)))
            secs += f'<h2>Not started ({len(not_started)}, rings 0 to {RING_LIMIT})</h2><p>{chips}</p>'
            continue
        if not cells:
            continue
        cards = ''
        for c in cells:
            i = infos[c]
            thumb = f'<img loading="lazy" src="{rel(i["thumb"], out)}" alt="">' if i['thumb'] else ''
            cards += (f'<div class="card"><a href="cell-{c[0]}_{c[1]}.html">{thumb}</a><h3><a href="cell-{c[0]}_{c[1]}.html">{c[0]},{c[1]}</a> '
                      f'<span class="muted">r{ss.ring(c)}</span></h3><div class="muted">{e(ss.layer_marks(i["sts"]))}</div>'
                      f'<div class="muted">{e(gap_text(i["gaps"]) if i["status"] != "Completed" else "")}</div>'
                      f'{"<span class=badge>marker</span>" if c == here else ""}</div>')
        secs += f'<h2>{e(status)} ({len(cells)})</h2><div class="cards">{cards}</div>'
    counts = ' · '.join(f'{s}: {sum(1 for i in infos.values() if i["status"] == s)}' for s in STATUS_ORDER[:4])
    body = (f'<p class="crumbs"><a href="{rel(ROOT / "HUMANS.html", out)}">HUMANS</a></p><h1>Cells: completed and in progress</h1>'
            f'<p class="muted">{counts}{f" · not started: {len(not_started)}" if not_started else ""}<br>Marker (where work is): '
            f'{f"{here[0]},{here[1]}" if here else "none"} · Lock: {e(lock)}</p>'
            f'<p class="muted"><strong>Completed</strong> means <code>site_handoff.cell_gaps</code> is empty. <strong>In progress</strong> means the marker is on it, '
            f'a stage is in flight, or the lock names it. <strong>Built, items remaining</strong> means ground, trees and decor are applied but cell_gaps still lists work '
            f'(houses, lumps, stale trees). Thumbnails are the cell\'s existing ground preview.</p>{secs}')
    return page('Cells overview', body)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--no-gaps', action='store_true')
    a = ap.parse_args(argv)
    stages = ss.load_stages()
    here, extra = ss.marker_cell(), load_media_map()
    lock = ss.lock_line()
    lock_task = (ss.read_json(ss.LOCK) or {}).get('task', '')
    PAGES.mkdir(parents=True, exist_ok=True)
    infos = {}
    for cell, sts in sorted(stages.items()):
        gaps = None
        if not a.no_gaps:
            import site_handoff
            gaps = site_handoff.cell_gaps(cell)
        media = find_media(cell, sts, extra=extra)
        status = classify(cell, sts, gaps, here, lock_task)
        previews = [f for g, f in media if f.name.endswith('_ground-preview.png')] or [f for _g, f in media if f.name.endswith('-preview.png')]
        infos[cell] = {'sts': sts, 'gaps': gaps, 'status': status, 'thumb': previews[-1] if previews else None, 'media': media}
        runlog = [b for b in ss.run_log_blocks() if re.search(rf'— cell {cell[0]},{cell[1]}\b', b.splitlines()[0])]
        (PAGES / f'cell-{cell[0]}_{cell[1]}.html').write_text(cell_page(cell, sts, gaps, status, media, here, runlog))
    not_started = [c for c in ring_cells() if c not in stages and ss.ring(c) <= RING_LIMIT]
    (PAGES / 'index.html').write_text(index_page(infos, not_started, here, lock))
    counts = {s: sum(1 for i in infos.values() if i['status'] == s) for s in STATUS_ORDER[:4]}
    n_img = sum(len(i['media']) for i in infos.values())
    print(f'wrote {PAGES / "index.html"} and {len(infos)} cell pages; {n_img} existing images linked, none created; {counts}; not started {len(not_started)}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
