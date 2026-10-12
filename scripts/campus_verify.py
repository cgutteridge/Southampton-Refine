#!/usr/bin/env python3
"""Verify an applied campus build: readback, OSM footprint check, door + stair walks.

  python3 scripts/campus_verify.py build_highfield_b25_b28

Imports the build module, rebuilds its plan (make() + build extras via build()), then:
  readback   planned vs saved region files (save the world first)
  footprint  osm_footprints.py check --build <name>
  walks      per door: 4 out on the approach -> 2 inside; and door -> top of each stair
Writes verification/site/<name>-result.json (merging into an existing one) and prints a summary.
"""
import importlib
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'scripts'))
from site_kit import World, readback  # noqa: E402
from site_walk import solid, walk  # noqa: E402

def standable(w, q):
    x, y, z = q
    return not solid(w.block(x, y, z)) and not solid(w.block(x, y + 1, z)) and solid(w.block(x, y - 1, z))


def walk_jump(w, start, goal, box):
    """Like site_walk.walk but a 1-block step up needs only headroom (a player's jump)."""
    from collections import deque
    x0, z0, x1, z1 = box
    ok = lambda x, y, z: x0 <= x <= x1 and z0 <= z <= z1 and standable(w, (x, y, z))
    seen, q = {start}, deque([start])
    while q:
        c = q.popleft()
        if c == goal:
            return True
        x, y, z = c
        for dx, dz in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            for dy in (0, 1, -1, -2):
                n = (x + dx, y + dy, z + dz)
                if n in seen or not ok(*n):
                    continue
                if dy == 1 and solid(w.block(x, y + 2, z)):
                    continue
                seen.add(n)
                q.append(n)
                break
    return False


VEC = {'east': (1, 0), 'west': (-1, 0), 'south': (0, 1), 'north': (0, -1)}


def main():
    mod = importlib.import_module(sys.argv[1])
    c = mod.make()
    extra = getattr(mod, 'EXTRA', None)
    plan = c.build(extra) if extra else c.build()
    rb = readback(plan)
    print('readback', rb['planned'], 'mismatches', rb['mismatches'])
    for k, v in list(rb['mismatch_sample'].items())[:6]:
        print('  ', k, v)
    fp = subprocess.run([sys.executable, str(ROOT / 'scripts/osm_footprints.py'), 'check', '--build', plan.name],
                        capture_output=True, text=True)
    print('footprint:', (fp.stdout.strip().splitlines() or ['?'])[-1])
    w = World()
    walks = []
    for _p, x, y, z, face in c.door_cells:
        dx, dz = VEC[face]
        box = (x - 60, z - 60, x + 60, z + 60)
        cands = [(abs(yy - y), k, (x + dx * k, yy, z + dz * k)) for k in (3, 4, 5, 6, 2)
                 for yy in range(y - 3, y + 4) if standable(w, (x + dx * k, yy, z + dz * k))]
        out = min(cands)[2] if cands else None            # approach cell nearest the door's level
        ins = (x - dx, y, z - dz)
        p = walk(w, out, ins, box) if out else None
        if not p and out and walk_jump(w, out, ins, box):
            p = 'jump'
        walks.append((f'door {x},{y},{z} {face}', 'jump' if p == 'jump' else bool(p)))
        for sx, sz in getattr(c, 'stairs_at', []):
            if abs(sx - x) > 60 or abs(sz - z) > 60:
                continue
            pt = c.part.get((sx, sz))
            if not pt or len(pt.floors) < 2:
                continue
            goal = None
            for gx in range(sx - 3, sx + 12):
                for gz in range(sz - 3, sz + 5):
                    q = (gx, pt.floors[-1] + 1, gz)
                    if standable(w, q) and c.part.get((gx, gz)) is pt:
                        goal = q
                        break
                if goal:
                    break
            if goal and walk(w, ins, goal, box):
                walks.append((f'  -> top floor {pt.name} at {goal}', True))
                break
        else:
            pass
    for name, ok in walks:
        print('walk', name, 'REACHABLE-WITH-1-BLOCK-JUMPS' if ok == 'jump' else 'REACHABLE' if ok else 'NOT REACHABLE')
    res = ROOT / f'verification/site/{plan.name}-result.json'
    d = json.loads(res.read_text()) if res.exists() else {}
    d['verify'] = {'readback': {k: rb[k] for k in ('planned', 'mismatches', 'checked')},
                   'footprint': fp.stdout.strip().splitlines()[-1:] if fp.stdout else [],
                   'walks': walks}
    res.write_text(json.dumps(d, indent=1))


if __name__ == '__main__':
    main()
