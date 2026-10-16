#!/usr/bin/env python3
"""Students' Union Retail Centre B57 (OSM way 33830236), Highfield. Rebuilt from the evidence alone (user, 2026-10-16: delete it and
start again from the processes and references; the earlier builds are not a reference).

EVIDENCE TABLE (each fact, its source)
  footprint  OSM way 33830236 (441 cells). It is a rectangle 36.6 x 12.0 whose long axis runs 23.7 deg south of east. It is the ROOF
             outline: the canopy is inside it (see canopy).
  heights    pristine lidar, cell by cell (lidar_heightmap.py 48,-44): ground 54 under and round it; roof surface 60 on every interior
             column (282 cells; the 57/58 columns are the rim, lidar reads edges low); Geocraft roof carpet 61. Flat roof, deck 61.
  storeys    2: university photo (reference/photos/buildings/57.jpg) and the user's photo (reference/aerial/highfield-user/
             union-shop-front.webp), the same face. Floors at 54 and 57, walls 54..60.
  front      the SHORT WEST END (photo: it is ~12 wide, a long brick side wall recedes at the right; the Edwardian B40/library roof
             stands at the left of the picture, i.e. north, which is what you see looking east from the plaza). Portal 57-A "Union
             Shop" (reference/portals, 6224.9,-5566.3) sits 1.3 blocks behind the west roof edge + 4, on the south half of that end:
             the door line is the glazing line under the canopy.
  canopy     the flat roof cantilevers ~4 over the front on two grey steel posts at the corners (photo: dark grey fascia, cream soffit).
             Google z20 shows a pale roof upstand line parallel to the west end at along -14.5, i.e. 3.8 in from the west edge: the
             canopy/wall join. So walls stand at along >= -14.3, the first 4 blocks are open canopy.
  front face from the photo, left (north) to right (south), 12 blocks, t = 0..12:
             t 0-1 brick pier both storeys; t 1-3 glazed door bay (glass below, tall window above, white render between);
             t 3-4 dark steel mullion full height; t 4-5 ATM bay (brick below, white render, small window above);
             t 5-12 shopfront: glazing between steel mullions below, bright blue "union shop" sign band at floor level (y 57),
             white render above with one window at the right end, brick return at the south corner.
  other faces  not seen: inferred, brick on both storeys (the visible south side wall is brick), upper-storey window glass block
             every 6 along on flat treads (stepped diagonal rule, site/CRAFTSMANSHIP.txt §2), never on corners.
  roof       Google z20 (look-only): pale membrane; thin grey upstand line at along -13.8 from across -5.5 to +3; a long grey seam at
             across -2.4 from along -13.5 to +14, turning south at the east end to across +4; a solar/rooflight array along the north
             side (along -6.5..10.5, across -5.5..-3.4); a hatch near the west end (-11.4,-4.8); a 2x2 plant box at the east end
             (14.7,-5.1), 1 high (lidar 61 there). Positions were measured off the sheet in the building's own frame.
  blocks     block_reference.py nearest: sign light_blue_concrete (35,137,198); steel gray_concrete (54,57,61); render white_concrete;
             seam light_gray_concrete; array light_blue_terracotta; brick = bricks.
  doors      one portal, 57-A, an automatic shop entrance: an open 2-wide passage in the glazing line with steel jambs and the sign
             band as lintel. No steps or paving (ground pass).

  python3 scripts/build_highfield_su_retail.py            # preview + dry run
  SITE_OWNER=... python3 scripts/build_highfield_su_retail.py --apply
"""
import argparse
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'scripts'))
from site_kit import OUT, Plan, World, _parse_cells_file, apply, built_cells, preview  # noqa: E402
from campus import BuildingFrame, Campus, Part, bbox, roof_greeblies, way_cells  # noqa: E402

NAME = 'highfield_su_retail'
WAY = '33830236'
BASE, DECK = 54, 61
FLOORS = (54, 57)
A_WALL = -14.3                                # walls start here; west of it is the open canopy
PORTAL = (6224.9, -5566.3)                    # 57-A Union Shop

FOOT = set(way_cells(WAY))
F = BuildingFrame(FOOT)                       # centroid (6238.16, -5564.10), long axis 23.7 deg; across positive to the south-south-west
OLD_RECORDS = {'highfield_library_b34_b18', 'highfield_library_b34_b18-greeblies', 'highfield_library_b34_b18-retail-fill',
               'highfield_q052_b57', NAME}
KEEP = {'highfield_48_m44_trees'}
N4 = ((1, 0), (-1, 0), (0, 1), (0, -1))


frame = F.frame


WALLED = {q for q in FOOT if frame(*q)[0] >= A_WALL}
CANOPY = FOOT - WALLED
BOX = bbox([Part('b57', BASE, DECK, cells=FOOT)], pad=4)
GLASS, BRICK, RENDER, STEEL, SIGN = 'glass', 'bricks', 'white_concrete', 'gray_concrete', 'light_blue_concrete'


FEATURES = [
    ('patch', F.rect(-6.5, 10.5, -5.5, -3.4), 'light_blue_terracotta', 0),         # solar / rooflight array
    ('line', F.line((-13.5, -2.4), (14, -2.4), (14, 4)), 'light_gray_concrete', 0),       # long seam turning at the east end
    ('line', F.line((-13.8, -5.5), (-13.8, 3)), 'light_gray_concrete', 0),        # upstand where the canopy joins
    ('hatch', *[round(v) for v in F.world_xz(-11.4, -4.8)]),
    ('plinth', F.rect(13.7, 15.7, -6.1, -4.1), 1, 'white_concrete'),               # plant box
]


SIDE = {'a0': 'front', 's0': 'north', 's1': 'south', 'a1': 'east'}
WALLS = dict(a0=A_WALL, a1=18.3, s0=-6, s1=6)       # the wall rectangle in (along, across): the front is set back from the outline


def face_of(x, z):
    return SIDE[F.face_of(x, z, **WALLS)]


class Retail(Campus):
    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self.passage = F.entrance_cells(WALLED, PORTAL, 'a0', **WALLS)
        self.jambs = F.jambs(self.passage)
        self.posts = set()
        edge = [q for q in CANOPY if any((q[0] + dx, q[1] + dz) not in FOOT for dx, dz in N4)]
        for s in (-5.3, 5.3):
            px, pz = F.world_xz(-17.8, s)
            self.posts.add(min(edge, key=lambda q: (q[0] + .5 - px) ** 2 + (q[1] + .5 - pz) ** 2))

    # --- the shell, written for this building: walls only on WALLED, open canopy on the rest ------------------------
    def shells(self):
        for (x, z) in self.part:
            for y in range(BASE - 3, BASE):
                self.set(x, y, z, 'stone')
            if (x, z) in CANOPY:
                outline = any((x + dx, z + dz) not in FOOT for dx, dz in N4)
                for y in range(BASE + 1, self.clear_to + 1):
                    if y == DECK:
                        self.set(x, y, z, STEEL if outline else 'calcite')        # dark fascia, cream soffit
                    elif y < DECK:
                        self.set(x, y, z, STEEL if (x, z) in self.posts else 'air')
                    else:
                        self.set(x, y, z, 'air')
                continue
            ex = [(dx, dz) for dx, dz in N4 if (x + dx, z + dz) not in WALLED]
            for y in range(BASE, self.clear_to + 1):
                if y > DECK:
                    self.set(x, y, z, 'air')
                elif y == DECK:
                    self.set(x, y, z, 'calcite')
                elif ex:
                    self.set(x, y, z, self.facade(x, y, z, ex))
                elif y in FLOORS:
                    self.set(x, y, z, 'smooth_stone')
                else:
                    self.set(x, y, z, 'air')
        self.entrance()

    def facade(self, x, y, z, ex):
        face = face_of(x, z)
        a, s = frame(x, z)
        rel = y - BASE
        single = len(ex) == 1
        if face != 'front':
            if rel == 0:
                return BRICK
            if single and rel == 5 and math.floor(a) % 6 == 2:
                return GLASS
            return BRICK
        t = s + 6
        if rel == 0:
            return STEEL                                                  # dark plinth
        if t < 1 or t >= 11.4:
            return BRICK                                                  # end piers
        corner = not single
        if t < 3:                                                         # glazed door bay
            if rel in (1, 2):
                return STEEL if corner else GLASS
            return GLASS if rel in (4, 5) and not corner else RENDER
        if t < 4:
            return STEEL                                                  # steel mullion
        if t < 5:                                                         # ATM bay
            if rel in (1, 2):
                return BRICK
            return GLASS if rel == 5 and not corner else RENDER
        if rel in (1, 2):                                                 # shopfront
            return STEEL if corner else GLASS
        if rel == 3:
            return SIGN
        return GLASS if (rel == 5 and t >= 10 and not corner) else RENDER

    def entrance(self):
        x = self.passage[0][0]
        for (px, pz) in self.passage:
            for y in (BASE + 1, BASE + 2):
                self.set(px, y, pz, 'air')
            self.set(px, BASE, pz, 'smooth_stone')
            self.set(px, BASE + 3, pz, SIGN)                              # the sign band is the lintel
        for (jx, jz) in self.jambs:
            for y in (BASE + 1, BASE + 2):
                self.set(jx, y, jz, STEEL)
            self.set(jx, BASE + 3, jz, SIGN)
            self.set(jx, BASE, jz, STEEL)

    def doors(self):
        pass


class PlanOverWorld:
    def __init__(self, plan, world, ignore=()):
        self.plan, self.world, self.ignore = plan, world, set(ignore)

    def block(self, x, y, z):
        if (x, y, z) in self.plan.cells:
            return self.plan.cells[(x, y, z)]
        if (x, y, z) in self.ignore:
            return 'minecraft:air'
        return self.world.block(x, y, z)


def build():
    c = Retail(NAME, [Part('b57', BASE, DECK, floors=FLOORS, cells=FOOT)], (WAY,), BOX, [], [], avoid_built=False)
    plan = c.build(lambda cc: print('roof features', roof_greeblies(cc, FEATURES)))
    print('passage', c.passage, 'jambs', c.jambs, 'posts', sorted(c.posts), 'canopy cells', len(CANOPY))
    # delete what earlier retail records left: restore their own recorded cells, then plan on top (re-runnable)
    try:
        oldown, _air = _parse_cells_file(OUT / f'{NAME}-cells.json')
    except (OSError, ValueError, KeyError):
        oldown = {}
    clear = Plan(NAME)
    try:
        prev = built_cells(exclude=(NAME,), within=list(oldown))
    except (OSError, ValueError, KeyError):
        prev = {}
    for q in oldown:
        if q not in plan.cells:
            clear.set(*q, prev[q][1] if q in prev else 'minecraft:air')
    col = [(x + a, y, z + b) for x, z in FOOT for a in (-1, 0, 1) for b in (-1, 0, 1) for y in range(BASE + 1, DECK + 6)]
    for q, (b, _s) in built_cells(within=col).items():
        if b in OLD_RECORDS and q not in plan.cells:
            clear.set(*q, 'minecraft:air')
    clear.cells.update(plan.cells)
    held = {q for q, (b, _s) in built_cells(within=clear.cells).items() if b in KEEP and clear.cells[q].endswith('air')}
    for q in held:
        del clear.cells[q]                                   # never cut a tree
    clear.signs, clear.entities = plan.signs, plan.entities
    clear.outside_footprint_ok = 'the canopy and its posts are inside the OSM roof outline'
    return clear, c


def owners(plan):
    return sorted({b for b, _s in built_cells(within=plan.cells).values()})


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--apply', action='store_true')
    a = ap.parse_args()
    plan, c = build()
    print('cells', len(plan.cells))
    mod = tuple(sorted((set(owners(plan)) | OLD_RECORDS | {'highfield_grounds_sc', 'highfield_q050_opens', 'highfield_48_m44_foliage'}) - {NAME} - KEEP))
    print('replaces blocks of', mod)
    preview(plan, ROOT / f'verification/site/{NAME}-preview.png', scale=2)
    apply(plan, dry=not a.apply, modifies=mod)
