#!/usr/bin/env python3
"""Oakdene Court (OSM w173805553, Welbeck Avenue / Church Lane, cell 49,-42): flats rebuilt to match the evidence (I-069).

The first build (build_cell_49_m42_lumps.py) gave it the right plan, four storeys and a flat roof, but the house defaults: dark
slate-tile roof and a brick face with a few 1-wide glass slits. This reuses that builder's floors, doors and stoops unchanged and
replaces only the roof and the openings. It clears only the blocks the first build placed (never trees).

Evidence (rules/evidence-order.md):
  storeys  Street View look-only frame, Church Lane yaw 90 (50.931839,-1.395051): 4 window rows            -> 4 storeys of 3
  roof     Google z20 sheet at 6379,-5277 + uni aerial: flat, pale grey membrane, white fascia, a dark glazed
           lantern, one block high, on the roof near x6376; lidar interior columns flat (57/58)                              -> smooth_stone slabs
  openings Street View: the 8-cell straight front reads WW_BB_WW per storey (user, 2026-10-16): 2x1 window pairs, a 2-wide open
           balcony (white front, no glass) over the entrance, brick piers; same rhythm inferred for every straight face
  not done (good enough): white balconies on the SE face, the taller stair core (lidar 58 centre vs 57 wings), cars.
The lantern position is a hint (aerial lean puts roof detail a few blocks off its ground position).

  .venv/bin/python scripts/oakdene_court.py            # dry run + preview + door reachability
  SITE_OWNER=... .venv/bin/python scripts/oakdene_court.py --apply
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'scripts'))
import build_cell_49_m42_lumps as m  # noqa: E402
from site_kit import OUT, preview, apply  # noqa: E402

WAY = '173805553'
OLD = m.NAME                                          # the build whose Oakdene blocks this replaces
ROOF, FASCIA, LANTERN = 'smooth_stone', 'smooth_quartz', ((6376, -5277), (6377, -5277), (6378, -5277), (6376, -5276), (6377, -5276), (6378, -5276))

m.SPEC = {WAY: ('W', 4, True)}
m.WAYS = {WAY: WAY}
m.GROUPS = [dict(nos=[WAY], mode='each', front='W')]
m.ROOFS = {WAY: ROOF}
m.NAME = 'oakdene_court'
m.MODIFIES = tuple(m.MODIFIES) + (OLD,)
DIRS, N8, pane = m.DIRS, m.N8, m.pane


def runs(cells, d):
    """Straight wall runs facing ``d``: lists of cells on one wall line, consecutive along the wall."""
    lat = 1 if d in 'EW' else 0
    line = {}
    for c in cells:
        line.setdefault(c[1 - lat], []).append(c)
    out = []
    for cs in line.values():
        cs.sort(key=lambda c: c[lat])
        run = [cs[0]]
        for c in cs[1:]:
            if c[lat] == run[-1][lat] + 1:
                run.append(c)
            else:
                out.append(run)
                run = [c]
        out.append(run)
    return out


def pair_slots(n):
    """Window pairs along a straight run of n wall cells: [(i, i+1), ...], one-block brick piers between them, the group centred.
    The run's two end cells are already walls beside a corner cell, so a pair may start at the very end of the run.
    A real front is e.g. 8 cells = WW_BB_WW (windows, balcony, windows); every face gets the same rhythm so unseen backs are inferred."""
    pairs = (n + 1) // 3
    if not pairs:
        return []
    off = (n - (3 * pairs - 1)) // 2
    return [(off + 3 * i, off + 3 * i + 1) for i in range(pairs)]


class Oakdene(m.Build):
    def clear(self):
        """Remove only what the first build placed above the floor (walls, roof, openings); leave trees and ground alone."""
        h = self.houses[0]
        ring1 = {(x + dx, z + dz) for x, z in self.owner for dx in (-1, 0, 1) for dz in (-1, 0, 1)}
        ring2 = {(x + dx, z + dz) for x, z in self.owner for dx in range(-2, 3) for dz in range(-2, 3)}
        self.earlier -= ring1                        # the old overhang is ours, not a neighbour's roof
        self.cols = ring2
        gone = 0
        for name in (OLD, m.NAME):                   # the first build, and this one when it is re-applied
            f = OUT / f'{name}-cells.json'
            for key, st in (json.loads(f.read_text()) if f.exists() else {}).items():
                x, y, z = map(int, key.split(','))
                if (x, z) in ring2 and y > h.b and not st.endswith('air'):
                    self.set(x, y, z, 'air')
                    gone += 1
        print('earlier Oakdene blocks cleared:', gone)

    def windows(self, k, h):
        """2-wide window pairs on straight faces only (never on corners or the stepped diagonals: a lone pane there looks wrong).
        The middle pair of the entrance face is the balcony instead (WW_BB_WW)."""
        b = h.b
        front = getattr(h, 'door', None)
        doors = {q for q in (front, getattr(h, 'rear', None)) if q}
        exp = {c: [d for d in 'NSEW' if self.exposed(c, d)] for c in h.walls}
        n = 0
        for d in 'NSEW':
            axis = 'z' if d in 'EW' else 'x'
            for run in runs([c for c, e in exp.items() if e == [d]], d):
                slots = pair_slots(len(run))
                balcony = None
                if front in run and len(slots) % 2 == 1:            # only the front entrance has balconies over it, not the rear door
                    mid = slots[len(slots) // 2]
                    if front in (run[mid[0]], run[mid[1]]):
                        balcony = mid
                for i, j in slots:
                    pair = (run[i], run[j])
                    if (i, j) == balcony:
                        self.balcony(h, pair, d)
                        continue
                    for s_ in range(h.levels):
                        if s_ == 0 and doors & set(pair):
                            continue                  # the rear door sits in this pair on the ground floor
                        for c in pair:
                            self.set(c[0], b + 2 + 3 * s_, c[1], pane(axis))
                    n += 2
        print('window panes per storey', n, 'x', h.levels, 'storeys')

    def balcony(self, h, pair, d):
        """Open recessed balcony, 2 wide, on every upper storey over the entrance: white parapet at the face, open above it,
        plain white back wall one cell in. No glass. Sealed (brick piers either side, floor course below, next floor above)."""
        b = h.b
        fx, fz = DIRS[d]
        for c in pair:
            behind = (c[0] - fx, c[1] - fz)
            if behind not in h.inner:
                print('balcony skipped: no interior behind', c)
                return
        for c in pair:
            behind = (c[0] - fx, c[1] - fz)
            for s_ in range(1, h.levels):
                y = b + 3 * s_
                self.set(c[0], y + 1, c[1], FASCIA)
                self.set(c[0], y + 2, c[1], 'air')
                self.set(behind[0], y + 1, behind[1], FASCIA)
                self.set(behind[0], y + 2, behind[1], FASCIA)
        print('balcony pockets', pair, 'storeys 2-%d' % h.levels)

    def roof(self):
        h = self.houses[0]
        own = h.cells
        y = h.b + h.H
        for (x, z) in own:
            self.set(x, y, z, f'{ROOF}_slab[type=bottom]')
        for (x, z) in {(x + dx, z + dz) for x, z in own for dx, dz in N8} - set(own):
            if (x, z) not in self.owner and (x, z) not in self.foreign and (x, z) not in self.earlier:
                self.set(x, y, z, f'{FASCIA}_slab[type=bottom]')              # white fascia round a one-block overhang
        if all(c in own for c in LANTERN):
            for x, z in LANTERN:
                self.set(x, y + 1, z, 'tinted_glass')                       # one dark glazed layer: reads from above, stays at roof height
        else:
            print('lantern skipped: not wholly on the roof')


def build():
    return Oakdene().build()


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--apply', action='store_true')
    a = ap.parse_args()
    plan = build()
    r = m.door_report(plan.cells)
    bad = sorted(k for k, v in r.items() if not v)
    print('door reachability (dry-run overlay): doors', len(r), 'unreachable', len(bad), bad)
    preview(plan, ROOT / f'verification/site/{m.NAME}-preview.png', scale=4)
    print(json.dumps(plan.summary())[:600])
    apply(plan, dry=not a.apply, modifies=m.MODIFIES)
