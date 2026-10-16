#!/usr/bin/env python3
"""Cluster survey for campus builds: pristine LIDAR roof map beside the annotated aerial.

  .venv/bin/python scripts/campus_survey.py x0,z0,x1,z1 out.png [mosaic.png]

Writes out.png (left: aerial_annot crop with OSM outlines + 10-block grid; right: roof top Y
from the PRISTINE Geocraft save, coloured by height, OSM outlines, way-id tails, a label of
the dominant top Y per 6x6 patch) and prints, per OSM building in the box: way, name,
loc_ref, ground (median edge terrain), top-Y histogram (bands >= 4% of cells).
One Read of out.png per cluster instead of per-building probing.
"""
import re
import subprocess
import sys
from collections import Counter
from pathlib import Path

from script_env import ROOT  # noqa: E402
from PIL import Image, ImageDraw  # noqa: E402
from site_kit import World  # noqa: E402
from osm_footprints import OSMIndex, PRISTINE  # noqa: E402

SKIP = ('air', 'leaves', '_log', 'vine', 'short_grass', 'tall_grass', 'fern', 'flower')
GROUND = ('grass_block', 'dirt', 'stone', 'gray_terracotta', 'gravel', 'coarse_dirt', 'podzol',
          'smooth_stone', 'andesite', 'polished_andesite', 'black_wool', 'dirt_path')


def tag(p, k):
    m = re.search(r'"%s"=>"([^"]*)"' % re.escape(k), p.get('other_tags') or '')
    return m.group(1) if m else None


def tops(w, x0, z0, x1, z1, ymax=120, ymin=30):
    t = {}
    for x in range(x0, x1 + 1):
        for z in range(z0, z1 + 1):
            y = ymax
            while y > ymin:
                b = w.block(x, y, z) or 'minecraft:air'
                if not any(s in b for s in SKIP):
                    break
                y -= 1
            t[(x, z)] = y
    return t


def colour(y, lo, hi):
    f = max(0.0, min(1.0, (y - lo) / max(1, hi - lo)))
    # dark blue (ground) -> green -> yellow -> red (tall)
    stops = [(0, (20, 30, 90)), (0.33, (40, 160, 70)), (0.66, (230, 210, 40)), (1, (220, 40, 40))]
    for (a, ca), (b, cb) in zip(stops, stops[1:]):
        if f <= b:
            k = (f - a) / (b - a)
            return tuple(int(ca[i] + (cb[i] - ca[i]) * k) for i in range(3))
    return stops[-1][1]


def main():
    x0, z0, x1, z1 = map(int, sys.argv[1].split(','))
    out = Path(sys.argv[2])
    mos = sys.argv[3] if len(sys.argv) > 3 else str(ROOT / 'reference/aerial/highfield-campus/mosaic-z18-8x8-centre-130055-87834.png')
    w = World(PRISTINE)
    idx = OSMIndex()
    t = tops(w, x0, z0, x1, z1)
    ys = sorted(t.values())
    lo, hi = ys[len(ys) // 20], ys[-1]
    S = 6
    W, H = (x1 - x0 + 1) * S, (z1 - z0 + 1) * S
    hm = Image.new('RGB', (W, H))
    d = ImageDraw.Draw(hm)
    for (x, z), y in t.items():
        d.rectangle(((x - x0) * S, (z - z0) * S, (x - x0 + 1) * S - 1, (z - z0 + 1) * S - 1), fill=colour(y, lo, hi))
    for gx in range(x0 - x0 % 10 + 10, x1 + 1, 10):
        d.line(((gx - x0) * S, 0, (gx - x0) * S, H), fill=(90, 90, 90))
        d.text(((gx - x0) * S + 2, 2), str(gx), fill=(255, 255, 255))
    for gz in range(z0 - z0 % 10 + 10, z1 + 1, 10):
        d.line((0, (gz - z0) * S, W, (gz - z0) * S), fill=(90, 90, 90))
        d.text((2, (gz - z0) * S + 2), str(gz), fill=(255, 255, 255))
    for px in range(x0, x1 + 1, 6):
        for pz in range(z0, z1 + 1, 6):
            c = Counter(t[(x, z)] for x in range(px, min(px + 6, x1 + 1)) for z in range(pz, min(pz + 6, z1 + 1)))
            y = c.most_common(1)[0][0]
            d.text(((px - x0) * S + 8, (pz - z0) * S + 10), str(y), fill=(0, 0, 0))
    cells = idx.cells()
    rows = []
    for i, (rings, p) in enumerate(idx.buildings):
        r = rings[0]
        if not any(x0 <= x <= x1 and z0 <= z <= z1 for x, z in r):
            continue
        pts = [((x - x0) * S, (z - z0) * S) for x, z in r]
        d.line(pts + [pts[0]], fill=(255, 255, 255), width=2)
        cx, cz = sum(x for x, _ in r[:-1]) / (len(r) - 1), sum(z for _, z in r[:-1]) / (len(r) - 1)
        d.text(((cx - x0) * S, (cz - z0) * S), (p.get('osm_way_id') or '')[-3:], fill=(255, 0, 255))
        mine = [q for q, j in cells.items() if j == i]
        inb = [q for q in mine if q in t]
        if not inb:
            continue
        h = Counter(t[q] for q in inb)
        edge = [t[(x + dx, z + dz)] for x, z in inb for dx, dz in ((3, 0), (-3, 0), (0, 3), (0, -3))
                if (x + dx, z + dz) in t and (x + dx, z + dz) not in cells]
        g = sorted(edge)[len(edge) // 2] if edge else None
        bands = ' '.join(f'{y}:{n}' for y, n in sorted(h.items()) if n >= 0.04 * len(inb))
        rows.append((p.get('osm_way_id'), p.get('name'), tag(p, 'loc_ref') or tag(p, 'ref'),
                     tag(p, 'building:levels'), len(mine), len(inb), g, bands))
    for r in rows:
        print('way %s | %s | ref %s | lv %s | cells %d (in box %d) | ground %s | tops %s' % r)
    if mos:
        tmp = out.with_suffix('.aerial.png')
        subprocess.run([str(ROOT / '.venv/bin/python'), str(ROOT / 'scripts/aerial_annot.py'),
                        f'{x0},{z0},{x1},{z1}', str(tmp), '4', mos], check=True, capture_output=True)
        a = Image.open(tmp)
        a = a.resize((int(a.width * H / a.height), H))
        sheet = Image.new('RGB', (a.width + W + 10, H), 'black')
        sheet.paste(a, (0, 0))
        sheet.paste(hm, (a.width + 10, 0))
        tmp.unlink()
    else:
        sheet = hm
    k = 1600 / max(sheet.size)
    if k < 1:
        sheet = sheet.resize((int(sheet.width * k), int(sheet.height * k)))
    sheet.save(out)
    print('wrote', out, sheet.size, 'colour range', lo, hi)


if __name__ == '__main__':
    main()
