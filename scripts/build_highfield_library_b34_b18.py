#!/usr/bin/env python3
"""Q-028 (campus C2): Hartley Library B36 (OSM 33830050), Education B34 (66696202), SU Retail
Centre B57 (33830236), Jubilee Sports Complex B18 (93729745) + its post-LIDAR extension.

Evidence
  OSM      reference/osm/highfield-campus
  aerial   reference/aerial/highfield-campus/mosaic-z18-8x8-centre-130055-87834.png
           Library: red-brown pitched tile roof on the west hall strip (sampled per cell:
           campus.tiled), flat grey roofs + plant on the 1960s/2005 ranges, curved east end;
           Sports: one big white flat roof; B34/B57 grey flat roofs.
  LIDAR    pristine Geocraft (views/q028-survey.png): Library ground 54, hall eaves ~60
           ridge 69-70, ranges 64-68; B34 53 → 57-64; B57 54 → 61; Sports hall 64, and
           ~2000 footprint cells still at ground (the extension post-dates the LIDAR).
  photos   commons-123638141 / -7578617 (library W front: tall plain brick 1930s hall,
           tall narrow windows, glazed entrance box), -7578641 (rear: curved cream render
           + glass ribbon extension), -171520825 / -123638127 (Edwardian red brick with
           stone dressings and a big arched window at the library's south end; which OSM
           way it is stays unresolved — modelled as plain brick bands), -134990207 (B34:
           dark red-brown brick, 2 storeys + steel windows), -113513069 (sports: long low
           brick box), -171520857 (2025: Jubilee extension, orange brick, 2 tall storeys,
           deep glazed bays). Licences in reference/manifest.jsonl.
  Not built: 171869344 (no LIDAR height, no photo).

  python3 scripts/build_highfield_library_b34_b18.py            # preview + dry-run guards
  SITE_OWNER=... python3 scripts/build_highfield_library_b34_b18.py --apply
"""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'scripts'))
from site_kit import apply, preview  # noqa: E402
from campus import (Campus, N4, Part, RoofView, XZ, aerial_rgb, bbox, centre, lidar_parts,  # noqa: E402
                    pitched_part, roof_greeblies, tiled, way_cells)

NAME = 'highfield_library_b34_b18'
BRICK = dict(wall='bricks', glass='glass', rows=(1, 2), pier=3, corner_glass=True)
RENDER = dict(wall='smooth_quartz', glass='light_gray_stained_glass', rows=(1, 2), pier=0, corner_glass=True)
TILE = dict(roof_fill='granite', roof_stair='granite_stairs', roof_ridge='granite_slab[type=bottom]')


def majority(cells, inside, rounds=2):
    """3x3 majority smoothing of a cell mask, limited to `inside`."""
    m = set(cells)
    for _ in range(rounds):
        m = {(x, z) for x, z in inside
             if sum((x + a, z + b) in m for a in (-1, 0, 1) for b in (-1, 0, 1)) >= 5}
    return m


# Library: tiled hall strip (aerial colour) as one pitched part; the rest by LIDAR bands
lib = way_cells('33830050')
rgb = aerial_rgb(lib)
hall = majority({q for q in lib if q in rgb and tiled(rgb[q])}, lib)
hall = {(x + a, z + b) for x, z in hall for a, b in N4 + ((0, 0),)} & lib     # full strip width
lib_rest = lib - hall
ext = {q for q in lib_rest if q[0] >= 6362}                                  # curved cream east end
b36_hall = pitched_part('b36_hall', hall, 54, storey=3, **TILE, **BRICK)
b36, i36 = lidar_parts('33830050', 'b36', only=lib_rest - ext, **BRICK)
b36x, _ = lidar_parts('33830050', 'b36x', only=ext, slab='gray_concrete', **RENDER)
b34, _ = lidar_parts('66696202', 'b34', **BRICK)
b57, _ = lidar_parts('33830236', 'b57', **BRICK)
b18, i18 = lidar_parts('93729745', 'b18', slab='white_concrete', **BRICK)
# extension: footprint cells LIDAR still shows as ground (built after the survey) — photo
# 171520857: two tall storeys of orange-red brick with deep glazed bays
sports = way_cells('93729745')
new = sports - set().union(*(p.cells for p in b18))
g18 = i18['ground']
b18x = Part('b18x', g18, g18 + 9, g18 + 10, (g18, g18 + 4), frame=XZ, cells=new, wall='bricks',
            glass='glass', rows=(1, 2, 3), pier=4, slab='light_gray_concrete')

PARTS = [b36_hall] + b36 + b36x + b34 + b57 + b18 + [b18x]
WAYS = ('33830050', '66696202', '33830236', '93729745')
DOORS = [(None, 6296, -5642, None), (None, 6390, -5640, None), (None, 6352, -5562, None),
         (None, 6240, -5560, None), (None, 6282, -5498, None), (None, 6232, -5470, None)]
STAIRS = [(b36[0].name, centre(b36[0])), (b34[0].name, centre(b34[0])),
          (b57[0].name, centre(b57[0])), ('b18x', centre(b18x))]
BOX = bbox(PARTS, pad=2)
# Roof greeblies of the Jubilee Sports Complex (OSM 93729745), measured off the Google z20 sheet 2026-10-16
# (google_aerial.py --at 6243,-5495 --radius 44 --zoom 20 --outlines). Sports hall: white standing-seam roof with two
# seams, a plant yard of AC units at the NW corner (flat: lidar reads the hall deck, 64, there), round roof lights and hatches. Extension (2025, south): beige flat
# roof, a blue-grey metal strip along its north edge, rows of tilted solar panels (navy), white duct runs.
EXT_GREEBLIES = [
    ('patch', [(6250, -5483), (6277, -5495), (6303, -5490), (6303, -5425), (6230, -5425), (6229, -5473), (6238, -5476)],
     'mushroom_stem', 0),
    ('patch', [(6250, -5483), (6277, -5495), (6279, -5489), (6253, -5476)], 'light_blue_terracotta', 0),
]
HALL_GREEBLIES = [
    ('line', [(6247, -5531), (6263, -5495)], 'light_gray_concrete', 0),
    ('line', [(6230, -5508), (6252, -5521)], 'light_gray_concrete', 0),
    *[('fan', x, z) for x, z in [(6217, -5516), (6220, -5515), (6221, -5512), (6218, -5510)]],
    *[('vent', x, z, 'light_gray_concrete') for x, z in [(6224, -5525), (6226, -5522), (6228, -5517), (6229, -5514)]],
    *[('hatch', x, z) for x, z in [(6243, -5510), (6234, -5505), (6247, -5499), (6238, -5494), (6228, -5489), (6225, -5502)]],
]
EXT_GREEBLIES += [
    ('line', [(6264, -5478), (6269, -5469)], 'white_concrete', 1),
    ('line', [(6273, -5468), (6279, -5452)], 'white_concrete', 1),
    *[('patch', q, 'blue_terracotta', 1) for q in [
        [(6253, -5480), (6257, -5481), (6258, -5478), (6254, -5477)], [(6268, -5487), (6274, -5488), (6274, -5485), (6269, -5484)],
        [(6257, -5466), (6265, -5468), (6267, -5465), (6258, -5462)], [(6261, -5457), (6269, -5460), (6270, -5457), (6262, -5454)],
        [(6265, -5450), (6273, -5452), (6274, -5447), (6265, -5445)], [(6275, -5473), (6283, -5476), (6284, -5472), (6276, -5470)],
        [(6279, -5465), (6287, -5468), (6288, -5464), (6279, -5462)], [(6282, -5457), (6291, -5460), (6291, -5456), (6283, -5452)]]],
]
EXTRA = None


def greeblies_plan():
    """Follow-up step of this feature: roof greeblies on the standing Jubilee roof (no re-plan of the shells)."""
    sports = way_cells('93729745')
    ext = RoofView(NAME, only=sports & new)          # colours of the 2025 extension stay on its own cells (user: no spill)
    hall = RoofView(NAME, only=sports - new)
    print('greeblies ext', roof_greeblies(ext, EXT_GREEBLIES), 'hall', roof_greeblies(hall, HALL_GREEBLIES))
    ext.p.cells.update(hall.p.cells)
    return ext.p


def make():
    return Campus(NAME, PARTS, WAYS, BOX, DOORS, STAIRS, avoid_built=True, step_down_stairs=True)


def build():
    return make().build()


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--apply', action='store_true')
    ap.add_argument('--greeblies', action='store_true', help='only the roof greeblies, on the standing build (feature follow-up)')
    a = ap.parse_args()
    if a.greeblies:
        plan = greeblies_plan()
        preview(plan, ROOT / f'verification/site/{NAME}-greeblies-preview.png', scale=2)
        apply(plan, dry=not a.apply, modifies=(NAME,))
        raise SystemExit(0)
    c = make()
    plan = c.build()
    print('parts', {pt.name: sum(1 for q in c.part.values() if q is pt) for pt in PARTS})
    print('b36', i36, 'b18', i18, 'hall eaves', b36_hall.deck, 'new', len(new))
    print('stairs', c.stairs_at, 'doors', c.door_cells)
    preview(plan, ROOT / f'verification/site/{NAME}-preview.png', scale=2)
    print(json.dumps(plan.summary())[:400])
    apply(plan, dry=not a.apply)
