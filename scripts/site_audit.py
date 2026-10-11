#!/usr/bin/env python3
"""Offline audit of every kit build against the saved world (no MCP calls).

Drift: cells whose current block differs from what the latest build placed.
Dark: walkable cells inside builds with block light 0.

  python3 scripts/site_audit.py [prefix]
Writes verification/site/audits/<date>-<prefix>.json. Save the world first.
"""
import json
import sys
import time

from site_kit import OUT, World, bid, same
from site_walk import solid


def norm(st):
    """Ignore living-world noise: doors opening, power, copper ageing.

    @param st: block state or None
    @returns: normalised state string or None
    """
    if st is None:
        return None
    for age in ('exposed_', 'weathered_', 'oxidized_', 'waxed_'):
        st = st.replace('minecraft:' + age, 'minecraft:')
    if '[' in st:
        name, props = st[:-1].split('[')
        keep = [kv for kv in props.split(',')
                if kv.split('=')[0] not in ('open', 'powered', 'waterlogged', 'age', 'moisture', 'up')]
        st = name + ('[' + ','.join(keep) + ']' if keep else '')
    return st


prefix = sys.argv[1] if len(sys.argv) > 1 else ''
latest = {}
for f in sorted(OUT.glob('*-cells.json'), key=lambda f: f.stat().st_mtime):
    name = f.name[:-len('-cells.json')]
    if not name.startswith(prefix):
        continue
    for k, st in json.loads(f.read_text()).items():
        latest[tuple(map(int, k.split(',')))] = (name, st)
w = World()
drift, dark, walk = {}, [], 0
for q, (name, st) in latest.items():
    a = w.block(*q)
    if not same(norm(st), norm(a)):
        drift.setdefault(name, []).append([q, st, a])
    x, y, z = q
    if bid(st) == 'minecraft:air' and not solid(a) and not solid(w.block(x, y + 1, z)) and solid(w.block(x, y - 1, z)):
        walk += 1
        if not w.light(x, y, z):
            dark.append(q)
rep = {
    'time': time.strftime('%Y-%m-%d %H:%M'), 'prefix': prefix, 'cells': len(latest),
    'drift': {k: {'count': len(v), 'sample': v[:20]} for k, v in drift.items()},
    'walkable': walk, 'dark': len(dark), 'dark_sample': dark[:40],
}
d = OUT / 'audits'
d.mkdir(exist_ok=True)
(d / f"{time.strftime('%Y-%m-%d-%H%M')}-{prefix or 'all'}.json").write_text(json.dumps(rep, indent=1))
print(json.dumps({
    k: (v if k != 'drift' else {n: x['count'] for n, x in v.items()})
    for k, v in rep.items() if k != 'dark_sample'
}, indent=1))
