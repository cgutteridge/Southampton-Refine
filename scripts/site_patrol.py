#!/usr/bin/env python3
"""Glitch patrol over kit-built cells + optional random client views.

  python3 scripts/site_patrol.py sweep
  SITE_OWNER=<you> python3 scripts/site_patrol.py views [N] [seed] [--hires | --midres]

Outputs: verification/site/patrol/<stamp>/
Look at contact.png and log oddities in site/ISSUES.txt.
"""
import base64
import json
import math
import random
import re
import sys
import time
from pathlib import Path

from floaters import cell_glitches
from site_kit import OUT, World, bid
from site_walk import solid

PATROL = OUT / 'patrol'


def latest_cells():
    """Merge archived cells; later builds win.

    @returns: {(x,y,z): (owner_name, state)}
    """
    latest = {}
    for f in sorted(OUT.glob('*-cells.json'), key=lambda f: f.stat().st_mtime):
        for k, st in json.loads(f.read_text()).items():
            latest[tuple(map(int, k.split(',')))] = (f.name[:-11], st)
    return latest


def sweep():
    """Offline glitch sweep over every kit-built cell.

    @returns: (found_dict, links_dict)
    """
    w = World()
    cells = latest_cells()
    found = {'floating': [], 'door_to_wall': [], 'post_on_half_block': [], 'broken_bed_or_door': []}
    for (x, y, z), (owner, planned) in cells.items():
        st = w.block(x, y, z) or ''
        for row in cell_glitches(w.block, x, y, z, st, owner=owner):
            kind = row['kind']
            found[kind].append({k: row[k] for k in ('pos', 'block', 'owner', 'why') if k in row})
    return found, {}


def views(n=8, seed=None, downscale=4):
    """Random client screenshots from walkable kit-built air cells.

    @param n: number of views
    @param seed: optional RNG seed
    @returns: (out_dir, shots_list)
    """
    from mc_paced import D, UUID, Paced, xyz
    import site_lock
    site_lock.check()
    R = random.Random(seed)
    w = World()
    cells = [q for q, (o, st) in latest_cells().items() if bid(st) == 'minecraft:air']
    R.shuffle(cells)
    spots = []
    for (x, y, z) in cells:
        if solid(w.block(x, y - 1, z)) and not solid(w.block(x, y, z)) and not solid(w.block(x, y + 1, z)):
            if all(abs(x - a) + abs(z - c) > 25 for a, _, c in spots):
                spots.append((x, y, z))
        if len(spots) >= n:
            break
    if not spots:
        raise SystemExit('No walkable kit-built air cells yet — apply a build first')
    stamp = time.strftime('%Y-%m-%d-%H%M')
    out = PATROL / stamp
    out.mkdir(parents=True, exist_ok=True)
    m, v = Paced(), Paced(8766)
    info = m.text('player_get_info', {'uuid': UUID})
    num = lambda k: float(re.search(rf'{k}: (-?[\d.]+)', info).group(1))
    mode = re.search(r'gameMode: (\w+)', info).group(1)
    shots = []
    m.call('player_set_gamemode', {'uuid': UUID, 'gamemode': 'spectator'})
    try:
        for i, (x, y, z) in enumerate(spots):
            a = R.uniform(0, 2 * math.pi)
            look = [x + 0.5 + 12 * math.cos(a), y + 1.2, z + 0.5 + 12 * math.sin(a)]
            m.call('entity_teleport', {
                'uuid': UUID, 'dimension': D,
                'position': xyz([x + 0.5, y, z + 0.5]), 'facing': xyz(look),
            })
            time.sleep(4)
            r = v.call('view_capture', {'downscale': downscale, 'close_screen': True})
            for b in r['content']:
                if b['type'] == 'image':
                    pth = out / f'view-{i:02d}_{x}_{y}_{z}.png'
                    pth.write_bytes(base64.b64decode(b['data']))
                    shots.append({'file': pth.name, 'pos': [x, y, z], 'look': [round(c, 1) for c in look]})
    finally:
        m.call('player_set_gamemode', {'uuid': UUID, 'gamemode': mode})
    try:
        from contact_sheet import make_sheet
        make_sheet([out / s['file'] for s in shots], out / 'contact.png')
    except Exception:
        pass
    (out / 'views.json').write_text(json.dumps(shots, indent=1))
    return out, shots


if __name__ == '__main__':
    cmd = sys.argv[1] if len(sys.argv) > 1 else 'sweep'
    if cmd == 'sweep':
        found, links = sweep()
        stamp = time.strftime('%Y-%m-%d-%H%M')
        out = PATROL / stamp
        out.mkdir(parents=True, exist_ok=True)
        (out / 'report.json').write_text(json.dumps({'found': found, 'links': links}, indent=1))
        print(json.dumps({k: len(v) for k, v in found.items()}, indent=1))
        for k, v in found.items():
            for f in v[:6]:
                print(' ', k, f)
        print('report:', out / 'report.json')
    elif cmd == 'views':
        from site_views import pop_downscale
        rest = sys.argv[2:]
        downscale = pop_downscale(rest)
        n = int(rest[0]) if len(rest) > 0 else 8
        seed = int(rest[1]) if len(rest) > 1 else None
        out, shots = views(n, seed, downscale)
        print(out / 'contact.png', len(shots), 'views')
    else:
        print(__doc__, file=sys.stderr)
        raise SystemExit(2)
