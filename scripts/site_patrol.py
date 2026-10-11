#!/usr/bin/env python3
"""Glitch patrol over kit-built cells + optional random client views.

  python3 scripts/site_patrol.py sweep
  SITE_OWNER=<you> python3 scripts/site_patrol.py views [N] [seed]

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


def prop(st, key):
    """Read a block-state property value.

    @param st: block state string
    @param key: property name
    @returns: value or None
    """
    m = re.search(rf'{key}=(\w+)', st)
    return m.group(1) if m else None


def sweep():
    """Offline glitch sweep over every kit-built cell.

    @returns: (found_dict, links_dict)
    """
    w = World()
    cells = latest_cells()
    found = {'floating': [], 'door_to_wall': [], 'post_on_half_block': [], 'broken_bed_or_door': []}
    off = {'north': (0, -1), 'south': (0, 1), 'east': (1, 0), 'west': (-1, 0)}
    for (x, y, z), (owner, planned) in cells.items():
        st = w.block(x, y, z) or ''
        n = bid(st)[10:]
        below, above = w.block(x, y - 1, z) or '', w.block(x, y + 1, z) or ''

        def rec(kind, why):
            found[kind].append({'pos': [x, y, z], 'block': n, 'owner': owner, 'why': why})

        if n in ('lantern', 'soul_lantern'):
            if prop(st, 'hanging') == 'true' and not solid(above) and 'chain' not in above:
                rec('floating', 'hanging lantern with nothing above')
            if prop(st, 'hanging') == 'false' and not solid(below) and not below.split('[')[0].endswith(('_fence', '_wall')):
                rec('floating', 'standing lantern with nothing below')
        elif n.endswith('_wall_sign') or n.endswith('wall_torch'):
            f = prop(st, 'facing')
            if f in off:
                dx, dz = off[f]
                if not solid(w.block(x - dx, y, z - dz)):
                    rec('floating', 'wall sign/torch with no block behind')
        elif (n.endswith('_sign') and 'hanging' not in n) or n == 'torch':
            if not solid(below) and not bid(below).endswith(('_fence', '_wall')):
                rec('floating', 'standing sign/torch with nothing below')
        elif n.endswith('_door'):
            half = prop(st, 'half')
            if half == 'lower' and not bid(above).endswith('_door'):
                rec('broken_bed_or_door', 'door lower half without upper')
            if half == 'upper' and not bid(below).endswith('_door'):
                rec('broken_bed_or_door', 'door upper half without lower')
            if half == 'lower':
                f = prop(st, 'facing')
                if f in off:
                    dx, dz = off[f]
                    wall = lambda b: solid(b) and not bid(b or '').endswith('_trapdoor')
                    a = wall(w.block(x + dx, y, z + dz)) or wall(w.block(x + dx, y + 1, z + dz))
                    b = wall(w.block(x - dx, y, z - dz)) or wall(w.block(x - dx, y + 1, z - dz))
                    if a or b:
                        rec('door_to_wall', 'door opens onto a solid block')
        elif n.endswith('_bed'):
            f, part = prop(st, 'facing'), prop(st, 'part')
            if f in off:
                dx, dz = off[f]
                ox, oz = (x + dx, z + dz) if part == 'foot' else (x - dx, z - dz)
                if not bid(w.block(ox, y, oz) or '').endswith('_bed'):
                    rec('broken_bed_or_door', 'bed missing its other half')
        elif n in ('rail', 'powered_rail') or n.endswith('_carpet'):
            if not solid(below):
                rec('floating', f'{n} with nothing below')
        if (n.endswith(('_fence', '_wall')) or n == 'iron_bars') and 'gate' not in n:
            if ('_slab' in below and 'type=bottom' in below) or bid(below).endswith('_carpet'):
                rec('post_on_half_block', 'post floats over a half-height block')
    return found, {}


def views(n=8, seed=None):
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
            r = v.call('view_capture', {'downscale': 2, 'close_screen': True})
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
        n = int(sys.argv[2]) if len(sys.argv) > 2 else 8
        seed = int(sys.argv[3]) if len(sys.argv) > 3 else None
        out, shots = views(n, seed)
        print(out / 'contact.png', len(shots), 'views')
    else:
        print(__doc__, file=sys.stderr)
        raise SystemExit(2)
