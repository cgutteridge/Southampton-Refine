#!/usr/bin/env python3
"""I-056 (cell 47,-45): remove floating leaf blobs: leaf components with no log touching them and nothing solid
under them, in no trees mask (original Geocraft leaves whose trunk is gone). Leaves owned by any trees mask
(neighbour overhang) are kept. Only inside the cell and >=3 from the scan edge.

  python3 scripts/remove_orphan_leaves_47_m45.py            # dry run
  SITE_OWNER=... python3 scripts/remove_orphan_leaves_47_m45.py --apply
"""
import argparse, glob, sys
from collections import deque
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'scripts'))
from site_kit import Plan, World, apply, built_cells  # noqa: E402
import pass_mask as pm  # noqa: E402

NAME = 'highfield_47_m45_orphan_leaves'
CX0, CX1, CZ0, CZ1 = 6016, 6143, -5760, -5633
X0, X1, Z0, Z1 = CX0 - 8, CX1 + 8, CZ0 - 8, CZ1 + 8
D = ((1, 0, 0), (-1, 0, 0), (0, 1, 0), (0, -1, 0), (0, 0, 1), (0, 0, -1))


def nm(b):
    return (b or 'air').split('[')[0].replace('minecraft:', '')


def build():
    w = World()
    leaves, logs = set(), set()
    for x in range(X0, X1):
        for z in range(Z0, Z1):
            for y in range(45, 110):
                n = nm(w.block(x, y, z))
                if 'leaves' in n:
                    leaves.add((x, y, z))
                elif '_log' in n:
                    logs.add((x, y, z))
    owned = set()
    for f in glob.glob(str(ROOT / 'verification/site/masks/trees-*.mask.json')):
        owned |= set(pm.mask_placements(pm.read_mask(Path(f))))
    owned |= set(built_cells(exclude=(NAME,)))          # other builds' blocks (e.g. 48,-45 foliage) are not ours
    seen, p, n_comp = set(), Plan(NAME), 0
    for l in leaves:
        if l in seen:
            continue
        c, q = [l], deque([l])
        seen.add(l)
        while q:
            a = q.popleft()
            for d in D:
                n = (a[0] + d[0], a[1] + d[1], a[2] + d[2])
                if n in leaves and n not in seen:
                    seen.add(n); c.append(n); q.append(n)
        if any((a[0] + d[0], a[1] + d[1], a[2] + d[2]) in logs for a in c for d in D):
            continue
        if any(nm(w.block(a[0], a[1] - 1, a[2])) not in ('air', 'cave_air') and 'leaves' not in nm(w.block(a[0], a[1] - 1, a[2])) for a in c):
            continue
        if any(a[0] < X0 + 3 or a[0] > X1 - 4 or a[2] < Z0 + 3 or a[2] > Z1 - 4 for a in c):
            continue
        n_comp += 1
        for a in c:
            if a not in owned and CX0 <= a[0] <= CX1 and CZ0 <= a[2] <= CZ1:
                p.set(*a, 'air')
    print(n_comp, 'orphan components,', len(p.cells), 'leaf blocks to remove')
    return p


if __name__ == '__main__':
    ap = argparse.ArgumentParser(); ap.add_argument('--apply', action='store_true'); a = ap.parse_args()
    plan = build()
    apply(plan, dry=not a.apply, modifies=[], cell=(47, -45), strict=True)
