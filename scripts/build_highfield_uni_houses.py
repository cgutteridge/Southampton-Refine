#!/usr/bin/env python3
"""Q-036 (campus C10): university-owned houses as whole properties — Chamberlain Road 8-58
(evens; OSM 159893739..787, uni refs 1401-1426), Hartley Avenue 17-31 (odds; 159865609..634,
refs 1501-1508), University Road 26 (H&S Office 1050, 159860991) + 28 (Counselling 1051,
159860988). One build per group: HOUSES=chamberlain_rd_8_58 | hartley_ave_17_31 |
university_rd_26_28 (one backup box per street; the whole set timed out the backup).

Whole property (rules/frontage-and-evidence.md): house on its OSM footprint (all sides, LIDAR
roof surface, floors + one stair, no rooms), door to its own street, front garden (lawn,
path from the door, closeboard fence at the back of the pavement with a gate gap), back
garden (lawn, fences on the plot lines from osm_footprints.py plots; clear Geocraft
           procedural trees, plant only dark-canopy positions from the campus aerial).

Evidence
  OSM      reference/osm/highfield-campus + portswood-x-broadlands (streets, footprints)
  plots    osm_footprints.py plots (verification/site/plots-*.json)
  aerial   mosaic-z18-8x8-centre-130055-87834.png — roof colour per house (campus.tiled):
           red clay tile → granite, else grey slate; back gardens lawn + trees.
  LIDAR    pristine Geocraft: ridge/eaves per cell (campus.pitched_part).
  photos   kartaview-1381543297 (Chamberlain Rd from ~6058,-5469 looking SE; uni houses on
           the left): 2-storey cream-rendered houses, white two-storey bays, mock-Tudor
           gables, grey slate roofs, arched brick porches, tall closeboard timber fences
           at the pavement. University Rd / 1050 / 1051 / 1630: no photo — brick as hint
           (red tile roofs on the aerial).

  Q-073 odd side (9-51): Street View pano IIlQp_3pAUwynN0r4jUFBw (May 2014, look-only, from the
           even side facing NW): 1930s two-storey semis, cream render over brick, two-storey
           bays with white windows, arched brick porches, red clay tile roofs, low brick front
           walls with piers + front lawns. Same RENDER style as the even side.

  HOUSES=hartley_ave_17_31 python3 scripts/build_highfield_uni_houses.py      # preview + dry-run
  SITE_OWNER=... HOUSES=... python3 scripts/build_highfield_uni_houses.py --apply
"""
import argparse
import json
import random
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'scripts'))
from site_kit import apply, preview  # noqa: E402
from campus import (N4, SLATE, TILE, Campus, aerial_rgb, bbox, centre, lidar_parts, lidar_top,  # noqa: E402
                    pitched_part, tiled, way_cells, _shared)

import os
CHAMBERLAIN = ['159893739', '159893740', '159893747', '159893748', '159893749', '159893750', '159893753',
               '159893755', '159893756', '159893757', '159893758', '159893760', '159893763', '159893765',
               '159893766', '159893767', '159893769', '159893772', '159893773', '159893774', '159893775',
               '159893780', '159893783', '159893784', '159893785', '159893787']
HARTLEY = ['159865609', '159865633', '159865623', '159865619', '159865622', '159865630', '159865612',
           '159865634']                                     # Hartley Avenue 17-31 (odds)
CHAMBERLAIN_ODD = ['173132097', '173132111', '173132124']   # Chamberlain Road 3, 5, 7 (SE end of the same run; Q-070)
CHAMBERLAIN_ODD_11_51 = ['173132126'] + [f'1731320{n}' if len(n) == 2 else f'173132{n}' for n in (
    '84', '86', '87', '88', '89', '91', '92', '93', '94', '95', '98', '99', '100', '102', '103', '104',
    '105', '107', '109', '110', '112')]                      # Chamberlain Road 9, 11-51 (odds; Q-073)
HAWTHORN = ['173021058', '173021059', '173021060', '173021071']      # Hawthorn Road 1-4 (Q-074)
HIGHCROWN = ['173021055', '173021056', '173021057']                  # Highcrown Street 27-31 (Q-075)
ROSELANDS = ['173021061', '173021062', '173021063']                  # Roselands Gardens 31-33 (Q-076)
UNIROAD = ['159860991', '159860988']                       # University Road 26, 28
# 159868612 (uni ref 1630) is 185 Broadlands Road: Broadlands builds are paused (user
# 2026-10-12) — noted in NOTES "Broadlands improvements", not built here.
GROUPS = {'chamberlain_rd_8_58': (CHAMBERLAIN, 'RENDER'), 'hartley_ave_17_31': (HARTLEY, 'BRICK'),
          'university_rd_26_28': (UNIROAD, 'BRICK'),
          'chamberlain_rd_3_7': (CHAMBERLAIN_ODD, 'RENDER'),
          'chamberlain_rd_9_51': (CHAMBERLAIN_ODD_11_51, 'RENDER'),
          'hawthorn_rd_1_4': (HAWTHORN, 'BRICKRENDER'), 'highcrown_st_27_31': (HIGHCROWN, 'BRICK'),
          'roselands_gdns_31_33': (ROSELANDS, 'GREY')}
# Houses only (no gardens): ground, trees and decor passes own everything outside the walls.
HOUSE_ONLY = {'chamberlain_rd_3_7', 'chamberlain_rd_9_51', 'hawthorn_rd_1_4', 'highcrown_st_27_31',
              'roselands_gdns_31_33'}
GROUP = os.environ.get('HOUSES', 'chamberlain_rd_8_58')     # one build per street group (backup size)
NAME = GROUP
RENDER = dict(wall='white_terracotta', glass='glass', rows=(1, 2), pier=2, corner_glass=True, floor='spruce_planks')
BRICK = dict(wall='bricks', glass='glass', rows=(1, 2), pier=2, corner_glass=True, floor='spruce_planks')
# Street View look-only, 2026-10-14: Hawthorn Rd 3 (pano A77vPWWAdxvjovue5leQwg, Aug 2025) red brick ground
# storey under white render, dark roof; Highcrown St 29 (Maps pano, 2026) red brick semis, red tile; Roselands
# Gardens 32 (Maps pano) grey pebbledash with red brick bands, red tile, chimney.
BRICKRENDER = dict(RENDER, ground=dict(wall='bricks', pier=2))
GREY = dict(RENDER, wall='light_gray_concrete')
STYLES = {'RENDER': RENDER, 'BRICK': BRICK, 'BRICKRENDER': BRICKRENDER, 'GREY': GREY}
FENCE = 'spruce_fence'


def plots_for(ways):
    """{way: set of plot cells} from osm_footprints.py plots over the houses' bbox."""
    cells = set().union(*(way_cells(w) for w in ways))
    x0, z0 = min(x for x, _ in cells) - 2, min(z for _, z in cells) - 2
    x1, z1 = max(x for x, _ in cells) + 2, max(z for _, z in cells) + 2
    bb = f'{x0},{z0},{x1},{z1}'
    subprocess.run([sys.executable, str(ROOT / 'scripts/osm_footprints.py'), 'plots', '--bbox', bb, '--reach', '20'],
                   check=True, capture_output=True)
    d = json.loads((ROOT / f'verification/site/plots-{bb.replace(",", "_")}.json').read_text())
    return {v['osm']: {tuple(c) for c in v['cells']} for v in d.values() if v['osm'] in ways}


HOUSES, PLOTS = [], {}
for group, style in ((GROUPS[GROUP][0], STYLES[GROUPS[GROUP][1]]),):
    plots = {} if GROUP in HOUSE_ONLY else plots_for(group)
    for w in group:
        cs = way_cells(w)
        if not cs:
            continue
        rgb = aerial_rgb(cs)
        red = sum(1 for q in cs if q in rgb and tiled(rgb[q], True)) > 0.4 * len(cs)
        g = lidar_parts(w, 'tmp')[1]['ground']
        eav = sorted(lidar_top(*q) for q in cs)[len(cs) * 15 // 100]
        # two storeys (photo): floors at ground and +3, eaves at least +6; roof = LIDAR above
        pt = pitched_part(f'h{w[-4:]}', cs, g, eaves=max(eav, g + 6), floors=(g, g + 3),
                          **(TILE if red else SLATE), **style)
        HOUSES.append((w, pt))
        PLOTS[w] = plots.get(w, set()) - cs
PARTS = [pt for _, pt in HOUSES]
WAYS = tuple(w for w, _ in HOUSES)


def street_anchor(pt):
    idx, _ = _shared()
    cx, cz = centre(pt)
    s = idx.nearest_street(cx + 0.5, cz + 0.5)
    return (round(s[3][0]), round(s[3][1])) if s else (cx, cz)


DOORS = [(pt.name, *street_anchor(pt), pt.base) for _, pt in HOUSES]
STAIRS = [(pt.name, centre(pt)) for _, pt in HOUSES if len(pt.floors) > 1]
BOX = bbox(PARTS, pad=2)
allplot = set().union(*PLOTS.values())
BOX = BOX if not allplot else (min(BOX[0], min(x for x, _ in allplot)), min(BOX[1], min(z for _, z in allplot)),
       max(BOX[2], max(x for x, _ in allplot)), max(BOX[3], max(z for _, z in allplot)))


def gardens(c):
    """Front + back gardens on each plot; fences on plot edges; path + gate from the door."""
    idx, _ = _shared()
    doors = {d[0]: d for d in getattr(c, 'door_cells', [])}
    mine = set().union(*PLOTS.values())
    c.garden_report = {}
    for w, pt in HOUSES:
        plot = PLOTS[w]
        if not plot:
            continue
        # door path: straight out from the door to the plot edge
        path = set()
        d = doors.get(pt.name)
        if d:
            _, x, y, z, face = d
            dx, dz = {'east': (1, 0), 'west': (-1, 0), 'south': (0, 1), 'north': (0, -1)}[face]
            k = 1
            while (x + dx * k, z + dz * k) in plot:
                path.add((x + dx * k, z + dz * k))
                k += 1
        front = {q for q in plot if idx.front_zone(*q)}
        fy = d[2] - 1 if d else None                     # door floor level
        for q in plot:
            if q in c.part or q in c.built or q in c.other:
                continue
            if fy is not None and any((q[0], y, q[1]) in c.p.cells for y in range(fy - 1, fy + 4)) \
                    and q in path:
                continue                                  # the door approach steps already sit here
            x, z = q
            g = c.terrain(x, z)
            c.set(x, g, z, 'polished_andesite' if q in path else 'grass_block')
            edge_out = [n for n in ((x + a, z + b) for a, b in N4) if n not in plot and n not in c.part]
            fence = bool(edge_out) and q not in path
            for y in range(g + 1, c.clear_to + 1):
                if (x, y, z) in c.p.cells:
                    continue
                if fence and y <= g + 2:
                    c.set(x, y, z, FENCE)
                else:
                    c.set(x, y, z, 'air')
        c.garden_report[w] = dict(front=len(front & plot), back=len(plot - front), path=len(path))
    plant_aerial_trees(c, idx)


def _aerial_canopy(rgb):
    """Dark green tree crown in the campus z18 mosaic (same heuristic as build_highfield_grounds)."""
    r, g, b = rgb
    return sum(rgb) < 200 and g >= r and g >= b and g > 55


def _tree_at(c, x, g, z):
    """Single backyard tree: short oak trunk + compact crown (aerial scale)."""
    for i in range(1, 6):
        c.set(x, g + i, z, 'oak_log')
    for dx in range(-2, 3):
        for dz in range(-2, 3):
            for dy in range(4, 8):
                if abs(dx) + abs(dz) + max(0, dy - 6) * 2 <= 3 and not (dx == dz == 0 and dy < 6):
                    xx, zz = x + dx, z + dz
                    if c.p.get(xx, g + dy, zz) in (None, 'minecraft:air'):
                        c.set(xx, g + dy, zz, 'oak_leaves[persistent=true]')


def plant_aerial_trees(c, idx):
    """Back gardens only: one tree per dark-canopy cluster on the aerial (no Geocraft carry-over)."""
    rgb = aerial_rgb(set().union(*PLOTS.values()))
    placed = []
    for w, pt in HOUSES:
        plot = PLOTS.get(w)
        if not plot:
            continue
        back = {q for q in plot if not idx.front_zone(*q) and q not in c.part}
        cand = [q for q in back if q in rgb and _aerial_canopy(rgb[q])]
        rnd = random.Random(int(w[-6:]))
        rnd.shuffle(cand)
        n = 0
        for x, z in cand:
            if n >= 3:
                break
            if any(abs(x - px) < 7 and abs(z - pz) < 7 for px, pz in placed):
                continue
            g = c.terrain(x, z)
            if any(c.p.get(x, y, z) not in (None, 'minecraft:air') for y in range(g + 1, g + 9)):
                continue
            placed.append((x, z))
            _tree_at(c, x, g, z)
            n += 1
    c.garden_trees = len(placed)


EXTRA = None


class HouseCampus(Campus):
    def build(self, extra=None):
        self.soft_stairs = True                 # a house too small for the kit stair is logged
        self.shells()
        for pt in self.parts:                   # one invisible light per storey (no fittings)
            cx, cz = centre(pt)
            x, z = min((q for q, p in self.part.items() if p is pt and not self.exposed(q[0], q[1], pt.base + 1)),
                       key=lambda q: abs(q[0] - cx) + abs(q[1] - cz), default=(cx, cz))
            for f in pt.floors:
                if self.p.get(x, f + 2, z) in (None, 'minecraft:air'):
                    self.set(x, f + 2, z, 'light[level=15]')
        self.stair()
        self.doors()
        if GROUP in HOUSE_ONLY:
            self.garden_report = {}
        else:
            gardens(self)                       # after doors (path) and before the envelope
        self.envelope(ring=1)
        return self.p


def make():
    return HouseCampus(NAME, PARTS, WAYS, BOX, DOORS, STAIRS, avoid_built=True, step_down_stairs=True, max_fill=2)


def build():
    return make().build()


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--apply', action='store_true')
    a = ap.parse_args()
    c = make()
    plan = c.build()
    print('houses', len(HOUSES), 'roofs', sum(1 for _, p in HOUSES if p.roof_fill == 'granite'), 'tile')
    print('eaves', sorted({p.deck - p.base for _, p in HOUSES}), 'stairs', len(c.stairs_at),
          'no stair', getattr(c, 'no_stair', []))
    print('gardens', sum(v['front'] for v in c.garden_report.values()), 'front cells',
          sum(v['back'] for v in c.garden_report.values()), 'back cells',
          'aerial trees', getattr(c, 'garden_trees', 0))
    preview(plan, ROOT / f'verification/site/{NAME}-preview.png', scale=2)
    print(json.dumps(plan.summary())[:300])
    apply(plan, dry=not a.apply)
