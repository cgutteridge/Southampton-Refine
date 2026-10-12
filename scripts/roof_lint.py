#!/usr/bin/env python3
"""Roof lint: find ridges that jog sideways between neighbouring rows.

A real pitched roof (gable or hip) on a squared Minecraft footprint keeps each ridge
on one straight block line. A ridge whose position shifts by one or more columns from
one row to the next means the slope under it has been displaced sideways, so every stair
on that seam changes height and the roof reads as zig-zagged / misaligned blocks
(I-034: broadlands_rd_56_62 squared a 22 deg pair as three stepped segments, each with
its own ridge column).

  python3 scripts/roof_lint.py <build> [<build> ...]   # recorded *-cells.json
  python3 scripts/roof_lint.py --all

site_kit.apply() runs ridge_jogs() on every plan and refuses jogs unless the plan
sets `roof_jog_ok = "<reason + evidence id>"`.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / 'verification/site'

# facing -> (axis the slope rises along, +1/-1 uphill direction on that axis)
_UP = {'east': ('x', 1), 'west': ('x', -1), 'south': ('z', 1), 'north': ('z', -1)}
_SKIP = ('minecraft:air', 'minecraft:light', 'minecraft:cave_air')
_THIN = ('pane', 'pot', 'potted', 'torch', 'lantern', 'sign', 'button', 'fence', 'wall', 'bars',
         'door', 'carpet', 'leaves', 'flower', 'sapling', 'grass[', 'short_grass', 'fern')


def _props(state: str) -> dict:
    if '[' not in state:
        return {}
    return dict(kv.split('=', 1) for kv in state[state.index('[') + 1:-1].split(','))


def _tops(cells: dict) -> dict:
    """Highest structural planned block per column.

    @param cells: {(x, y, z): block state}
    @returns: {(x, z): (y, state)} ignoring air, panes, pots and other thin attachables
    """
    top = {}
    for (x, y, z), s in cells.items():
        if s in _SKIP or any(t in s.split(':', 1)[-1] for t in _THIN):
            continue
        if (x, z) not in top or y > top[(x, z)][0]:
            top[(x, z)] = (y, s)
    return top


def _slope(top: dict, x: int, z: int):
    """Facing of the roof stair on top of column (x, z), or None if it is not one."""
    t = top.get((x, z))
    if not t or '_stairs' not in t[1]:
        return None
    p = _props(t[1])
    return p.get('facing') if p.get('half', 'bottom') == 'bottom' else None


def _party_cap(top: dict, at, row: int, p: int, q: int) -> bool:
    """True if the ridge cap between slope ends p and q is a party-wall parapet.

    A parapet is >= 2 blocks wide and not of the roof's own material (e.g. bricks across a
    deepslate_tile ridge). A 1-wide stack is a chimney, not a party wall.
    """
    if q - p - 1 < 2:
        return False
    mat = top[at(row, p)][1].split(':', 1)[-1].split('[')[0].replace('_stairs', '')
    return any(not top[at(row, i)][1].split(':', 1)[-1].startswith(mat) for i in range(p + 1, q))


def _ridges(top: dict, axis: str) -> dict:
    """Ridge positions per row for slopes rising along `axis`.

    A ridge is where a run of >= 2 stairs rising in + direction meets (directly or across a
    1-4 block cap of non-stair blocks) a run of >= 2 stairs rising in - direction.

    @returns: {row: [(pos2, y, party), ...]} with pos2 = twice the ridge midpoint (integer)
        and party = True when the cap is a party-wall parapet (see _party_cap)
    """
    rise, fall = ('east', 'west') if axis == 'x' else ('south', 'north')
    key = (lambda c: (c[1], c[0])) if axis == 'x' else (lambda c: (c[0], c[1]))
    rows = {}
    for c in top:
        row, pos = key(c)
        rows.setdefault(row, set()).add(pos)
    at = (lambda row, pos: (pos, row)) if axis == 'x' else (lambda row, pos: (row, pos))
    out = {}
    for row, poss in rows.items():
        lo, hi = min(poss), max(poss)
        face = {p: _slope(top, *at(row, p)) for p in range(lo, hi + 1)}
        for p in range(lo + 1, hi + 1):
            if face[p] != rise or face[p - 1] != rise or face.get(p + 1) == rise:
                continue
            for cap in range(5):
                q = p + cap + 1
                if face.get(q) == fall and face.get(q + 1) == fall and \
                        all(face.get(p + i) not in (rise, fall) and (p + i) in poss
                            for i in range(1, cap + 1)):
                    y = max(top[at(row, i)][0] for i in range(p, q + 1))
                    out.setdefault(row, []).append((p + q, y, _party_cap(top, at, row, p, q)))
                    break
    return out


def ridge_jogs(cells: dict) -> list[dict]:
    """Find ridge lines that shift sideways between adjacent rows.

    Steps beside a party-wall parapet are allowed: terrace houses may stagger where they
    meet. A shift anywhere else is one roof displaced against itself.

    @param cells: {(x, y, z): block state} (a Plan's cells or a recorded *-cells.json)
    @returns: list of {'axis', 'row', 'pos', 'next_pos', 'y', 'shift'} — one per seam; the
        positions are MC block coordinates of the ridge midpoint on the slope axis
    """
    top = _tops(cells)
    jogs = []
    for axis in ('x', 'z'):
        ridges = _ridges(top, axis)
        for row, rs in ridges.items():
            nxt = ridges.get(row - 1, ())
            for pos2, y, party in rs:
                if party or any(q == pos2 for q, _, _ in nxt):
                    continue
                for npos2, ny, nparty in nxt:
                    shift = (npos2 - pos2) / 2
                    # half-block shifts are a ridge cap widening by one, not a displaced slope
                    if not nparty and 1 <= abs(shift) <= 4 and abs(ny - y) <= abs(shift) + 1:
                        jogs.append({'axis': axis, 'row': row, 'pos': pos2 / 2,
                                     'next_pos': npos2 / 2, 'y': y, 'shift': shift})
    return jogs


def _load(name: str) -> dict:
    f = OUT / f'{name}-cells.json'
    raw = json.loads(f.read_text())
    return {tuple(int(v) for v in k.split(',')): s for k, s in raw.items()}


def main() -> int:
    """CLI: report ridge jogs for recorded builds.

    @returns: process exit code (1 if any jog was found)
    """
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('builds', nargs='*')
    ap.add_argument('--all', action='store_true', help='every verification/site/*-cells.json')
    a = ap.parse_args()
    names = a.builds or ([f.name[:-len('-cells.json')] for f in sorted(OUT.glob('*-cells.json'))]
                         if a.all else [])
    if not names:
        ap.error('name a build or pass --all')
    bad = 0
    for n in names:
        jogs = ridge_jogs(_load(n))
        if jogs:
            bad += 1
            print(f'{n}: {len(jogs)} ridge jog(s)')
            for j in jogs[:8]:
                print(f"   ridge along {'z' if j['axis'] == 'x' else 'x'} row {j['row']}: "
                      f"{j['axis']}={j['pos']:g} -> {j['next_pos']:g} (y{j['y']}, shift {j['shift']:+g})")
    if not bad:
        print(f'{len(names)} build(s): no ridge jogs')
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main())
