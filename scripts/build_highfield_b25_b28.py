#!/usr/bin/env python3
"""Q-027 (campus C1): Highfield campus east of B30 — Chemistry B27 (OSM 66696206) with its roof
flues, B28 (66696198), B26 (225234901), eScience B25 (66696205). (Low shed 242322573 is
already the bike shelter of highfield_b35_grounds — left alone.)

Evidence
  OSM      reference/osm/highfield-campus (footprints; B27 a C-shape on the 2:1 campus grid)
  aerial   reference/aerial/highfield-campus/mosaic-z18-5x5-centre-130056-87835.png
           B27: pale ribbed roof over the east block (x6448-6480 z-5586..-5548) with plant
           on its SE edge; dark grey roofs elsewhere. B28/B26/B25 grey flat roofs.
  LIDAR    pristine Geocraft via campus.lidar_parts (survey: views/q027-survey-*.png)
           B27 ground 49, west range top 61, rest 57; B28 ground 52 top 60 (56 strip);
           B26 51 → 59; B25 50 → 61 / 58; shed 48 → 52.
  photos   commons-51225046 (Mountain-Eric, CC BY-SA 3.0; ~6486,-5543 looking W): B27 red
           brick, blue-grey window panels, pale curved metal roof, FIVE tall steel flues in
           a row on the ridge (user 2026-10-12: "add a note about the chimneys on the main
           chemistry building" — NOTES "Highfield campus notes"); commons-134990184 /
           -134990153 (DS Pugh, CC BY-SA 2.0, 2016, University Rd): brick perimeter + low
           brick east ranges under grey roofs. B25/B26/B28: no photos — brick as hint
           from B27 / B29 neighbours.

  python3 scripts/build_highfield_b25_b28.py            # preview + dry-run guards
  SITE_OWNER=... python3 scripts/build_highfield_b25_b28.py --apply
"""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'scripts'))
from site_kit import apply, preview  # noqa: E402
from campus import Campus, N4, bbox, centre, lidar_parts, way_cells  # noqa: E402

NAME = 'highfield_b25_b28'
BRICK = dict(wall='bricks', glass='light_blue_stained_glass', rows=(1, 2), pier=3, corner_glass=True)
PLAIN = dict(wall='bricks', glass='glass', rows=(1, 2), pier=3, corner_glass=True)
EAST = lambda q: 6448 <= q[0] <= 6481 and -5587 <= q[1] <= -5547     # B27 pale-roofed block

c27 = way_cells('66696206')
b27e, _ = lidar_parts('66696206', 'b27_east', only={q for q in c27 if EAST(q)}, slab='light_gray_concrete',
                      **BRICK)
b27, i27 = lidar_parts('66696206', 'b27', only={q for q in c27 if not EAST(q)}, **BRICK)
b28, _ = lidar_parts('66696198', 'b28', **PLAIN)
b26, _ = lidar_parts('225234901', 'b26', **PLAIN)
b25, _ = lidar_parts('66696205', 'b25', slab='gray_concrete', **PLAIN)
PARTS = b27 + b27e + b28 + b26 + b25
WAYS = ('66696206', '66696198', '225234901', '66696205')
DOORS = [(None, 6428, -5545, None), (None, 6478, -5552, None), (None, 6410, -5586, None),
         (None, 6426, -5588, None), (None, 6452, -5590, None), (None, 6476, -5612, None)]
STAIRS = [(b27[0].name, centre(b27[0])), (b28[0].name, centre(b28[0])), (b26[0].name, centre(b26[0])),
          (b25[0].name, centre(b25[0]))]
BOX = bbox(PARTS, pad=2)


def depth(cells):
    """Steps from the edge of a cell set (1 = edge cell)."""
    d, frontier = {}, [q for q in cells if any((q[0] + a, q[1] + b) not in cells for a, b in N4)]
    for q in frontier:
        d[q] = 1
    while frontier:
        nxt = []
        for x, z in frontier:
            for a, b in N4:
                n = (x + a, z + b)
                if n in cells and n not in d:
                    d[n] = d[(x, z)] + 1
                    nxt.append(n)
        frontier = nxt
    return d


def roof_and_flues(c):
    """B27 east block: low barrel (pale metal) rising 2 over the deck, five steel flues on the ridge."""
    for pt in [p for p in c.parts if p.name.startswith('b27_east')]:
        cells = {q for q, p in c.part.items() if p is pt}
        # barrel: rises across the block's width (campus u axis), constant along the ridge (v)
        cx = sum(x for x, _ in cells) / len(cells)
        cz = sum(z for _, z in cells) / len(cells)
        ux, uz = 2 / 5 ** 0.5, 1 / 5 ** 0.5
        vx, vz = -1 / 5 ** 0.5, 2 / 5 ** 0.5
        off = {q: (q[0] + 0.5 - cx) * ux + (q[1] + 0.5 - cz) * uz for q in cells}
        half = max(abs(o) for o in off.values())
        for (x, z), o in off.items():
            r = abs(o) / half
            for y in range(1, (2 if r < 0.35 else 1 if r < 0.7 else 0) + 1):
                c.set(x, pt.deck + y, z, 'light_gray_concrete')
        base = pt.deck + 2
        c.flues = []
        for k in (-8, -4, 0, 4, 8):
            fx, fz = round(cx + vx * k), round(cz + vz * k)
            c.flues.append((fx, fz))
            for a in (0, 1):
                for b in (0, 1):
                    for y in range(pt.deck + 1, base + 7):
                        c.set(fx + a, y, fz + b, 'iron_block')
                    c.set(fx + a, base + 7, fz + b, 'polished_andesite')
        lo, hi, L = c.flues[0], c.flues[-1], 16
        c.flue_span = (lo, hi, round(L))


EXTRA = roof_and_flues


def make():
    return Campus(NAME, PARTS, WAYS, BOX, DOORS, STAIRS, avoid_built=True, step_down_stairs=True)


def build():
    c = make()
    return c.build(roof_and_flues)


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--apply', action='store_true')
    a = ap.parse_args()
    c = make()
    plan = c.build(roof_and_flues)
    print('parts', {pt.name: sum(1 for q in c.part.values() if q is pt) for pt in PARTS})
    print('b27 info', i27, 'flues', c.flues, c.flue_span)
    print('stairs', c.stairs_at, 'doors', c.door_cells)
    preview(plan, ROOT / f'verification/site/{NAME}-preview.png', scale=2)
    print(json.dumps(plan.summary())[:500])
    apply(plan, dry=not a.apply)
