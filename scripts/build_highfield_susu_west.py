#!/usr/bin/env python3
"""Q-029 (campus C3): Students' Union B42 (OSM 33830305) + Compactor Store 42a (294963447),
West Building & Staff Social Centre B40 (34391673), Staff Club B38 (relation 2139045),
Blue Room (456577218).

Evidence
  OSM      reference/osm/highfield-campus
  aerial   reference/aerial/highfield-campus/mosaic-z18-8x8-centre-130055-87834.png
           B40: red-brown pitched tile roofs (campus.tiled) on the two long ranges, dark
           flat roofs on the north link; B38: white flat roofs round courtyards; B42: grey
           flat roofs with plant, stepping down the slope to the west.
  LIDAR    pristine Geocraft (survey views/q029-survey.png): B40 ground 54, ridges 63-67;
           B38 ground 55, tops 59-61; B42 ground 48 (W) .. 54, tops 53/57-58/60/62.
  photos   commons-114892434 / -123638152 / -113513149 / -7578485 (B40, the 1930s former
           Union: brown-red brick, red tile roofs, tall gabled ends with stone-framed tall
           windows, ivy); commons-24864637 (SUSU 2013 entrance: white panels + glass
           shopfront). B38 / B42 main ranges: no photo (brick as hint).
  Not built: 391790374 (small canopy, no evidence of walls).

  python3 scripts/build_highfield_susu_west.py            # preview + dry-run guards
  SITE_OWNER=... python3 scripts/build_highfield_susu_west.py --apply
"""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'scripts'))
from site_kit import apply, preview  # noqa: E402
from campus import Campus, RoofView, auto_parts, bbox, centre, lidar_parts, roof_greeblies, way_cells  # noqa: E402

NAME = 'highfield_susu_west'
BRICK = dict(wall='bricks', glass='glass', rows=(1, 2), pier=3, corner_glass=True)
WHITE = dict(wall='white_concrete', glass='glass', rows=(1, 2), pier=4, corner_glass=True)

b40, i40 = auto_parts('34391673', 'b40', loose=True, **BRICK)
b38, i38 = lidar_parts('2139045', 'b38', slab='white_concrete', **BRICK)
blue, _ = lidar_parts('456577218', 'blue', slab='white_concrete', **BRICK)
b42, i42 = lidar_parts('33830305', 'b42', **BRICK)
cmp_, _ = lidar_parts('294963447', 'b42a', min_cells=4, wall='gray_concrete', rows=())
PARTS = b40 + b38 + blue + b42 + cmp_
WAYS = ('34391673', '2139045', '456577218', '33830305', '294963447')
DOORS = [(None, 6200, -5600, None), (None, 6176, -5632, None), (None, 6205, -5660, None),
         (None, 6196, -5655, None), (None, 6203, -5569, None), (None, 6160, -5530, None),
         (None, 6205, -5516, None)]
STAIRS = [(p.name, centre(p)) for p in (b40[-1], b38[0], b42[0])]
BOX = bbox(PARTS, pad=2)
PALE = 'light_gray_concrete'
# Roof greeblies of B42 (OSM 33830305), measured off the Google z20 sheet 2026-10-16 (google_aerial.py --at 6186,-5543
# --radius 44 --zoom 20 --outlines): three pale raised roof blocks on the grey deck (NW, long centre, east), rows of round
# roof lights round them, (pale blocks are 2 above the deck: pristine lidar reads 62 on them, 60 elsewhere) X-marked hatches, two louvred vents on the centre block, a louvred vent, a dome and a fan on the NW link.
GREEBLIES = [
    ('plinth', [(6165, -5578), (6176, -5572), (6171, -5561), (6159, -5567)], 2, PALE),
    ('plinth', [(6182, -5570), (6206, -5559), (6202, -5548), (6176, -5560)], 2, PALE),
    ('plinth', [(6212, -5556), (6223, -5551), (6217, -5540), (6207, -5546)], 2, PALE),
    *[('vent', x, z) for x, z in [(6165, -5576), (6166, -5578), (6169, -5577), (6172, -5575), (6175, -5574), (6174, -5572),
                                  (6164, -5573), (6163, -5570), (6162, -5568), (6160, -5565), (6163, -5563), (6166, -5562),
                                  (6170, -5564), (6213, -5556), (6216, -5555), (6219, -5554), (6222, -5552), (6221, -5550),
                                  (6219, -5547), (6218, -5545), (6217, -5542), (6211, -5551), (6210, -5548), (6209, -5546)]],
    *[('hatch', x, z) for x, z in [(6168, -5570), (6185, -5561), (6191, -5559), (6198, -5555), (6215, -5548)]],
    ('louvre', [(6171, -5568), (6174, -5568), (6174, -5565), (6171, -5565)]),
    ('louvre', [(6197, -5560), (6202, -5558), (6202, -5555), (6196, -5557)]),
    ('louvre', [(6194, -5555), (6200, -5553), (6200, -5551), (6194, -5552)]),
    ('dome', 6175, -5567),
    # SW wing, extract-fan block and the dark membrane roof (Google z20, same sheet; lidar: wing 53, lanterns 60-61, membrane 58)
    *[('hatch', x, z) for x, z in [(6181, -5513), (6194, -5507), (6157, -5540), (6163, -5537), (6168, -5535), (6155, -5531),
                                   (6152, -5524), (6149, -5517), (6165, -5521), (6162, -5514), (6153, -5507), (6158, -5505)]],
    ('dome', 6154, -5534), ('dome', 6165, -5518),
    *[i for cx, cz in [(6183, -5546), (6181, -5540), (6178, -5535)] for i in (
        ('line', [(cx - 2, cz - 2), (cx + 2, cz - 2), (cx + 2, cz + 2), (cx - 2, cz + 2), (cx - 2, cz - 2)], 'light_gray_concrete', 1),
        ('patch', [(cx - 1, cz - 1), (cx + 2, cz - 1), (cx + 2, cz + 2), (cx - 1, cz + 2)], 'iron_trapdoor[facing=north,half=bottom,open=false]', 1))],
    ('fan', 6174, -5564),
]
# dark membrane roof: only on the cells that were lowered to it (its colour must not spill onto the higher block beside it)
MEMBRANE = [
    ('patch', [(6179, -5526), (6206, -5514), (6197, -5491), (6169, -5506)], 'gray_concrete', 0),
    *[('line', l, 'light_gray_concrete', 0) for l in ([(6173, -5515), (6202, -5502)], [(6187, -5521), (6176, -5506)],
                                                      [(6197, -5515), (6190, -5499)])],
]
EXTRA = lambda c: print('greeblies', roof_greeblies(c, GREEBLIES))  # noqa: E731


# Roofs the pristine lidar reads lower than the build (live-minus-lidar grid, 2026-10-16): the low block east of the
# lanterns (lidar 57) and the dark membrane roof (lidar 58); both were built 60. Lowered as part of this feature.
LOWER = [((6187, -5537, 6205, -5516), 57), ((6169, -5518, 6201, -5492), 58)]


def lower_map():
    """{(x, z): new deck} for the B42 cells inside the LOWER rectangles that stand at 60 (the original deck)."""
    v = RoofView(NAME, only=way_cells('33830305'))
    out = {}
    for (x0, z0, x1, z1), y in LOWER:
        for q in v.part:
            if x0 <= q[0] <= x1 and z0 <= q[1] <= z1 and v.deck(*q) >= 60:
                out[q] = y
    return out


def lower_plan():
    """Plan that cuts the listed roofs down to the lidar height: clear above the new deck, new slab, coping on the edge,
    and a wall on the higher neighbours' boundary cells."""
    from campus import Plan, N4
    low = lower_map()
    v = RoofView(NAME, only=way_cells('33830305'))
    p = Plan(NAME + '-lower')
    for (x, z), y in low.items():
        edge = any((x + a, z + b) not in v.part for a, b in N4)
        for yy in range(y + 1, 64):
            p.set(x, yy, z, 'air')
        p.set(x, y, z, 'light_gray_concrete')
        if edge:
            p.set(x, y + 1, z, 'smooth_stone_slab[type=bottom]')
        for a, b in N4:
            q = (x + a, z + b)
            if q in v.part and q not in low and v.deck(*q) >= 60:
                for yy in range(y + 1, 60):
                    p.set(q[0], yy, q[1], 'light_gray_concrete')
    return p


def greeblies_plan():
    """Follow-up step of this feature: roof greeblies on the standing B42 roof (no re-plan of the shells)."""
    low = lower_map()
    v = RoofView(NAME, only=way_cells('33830305'), lower=low)
    print('greeblies', roof_greeblies(v, GREEBLIES))
    m = RoofView(NAME, only=set(low), lower=low)
    print('membrane', roof_greeblies(m, MEMBRANE))
    v.p.cells.update(m.p.cells)
    return v.p


def make():
    return Campus(NAME, PARTS, WAYS, BOX, DOORS, STAIRS, avoid_built=True, step_down_stairs=True, max_fill=2)


def build():
    return make().build(EXTRA)


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--apply', action='store_true')
    ap.add_argument('--lower', action='store_true', help='cut the two roofs lidar reads lower down to its height (run before --greeblies)')
    ap.add_argument('--greeblies', action='store_true', help='only the roof greeblies, on the standing build (feature follow-up)')
    a = ap.parse_args()
    if a.lower:
        plan = lower_plan()
        preview(plan, ROOT / f'verification/site/{NAME}-lower-preview.png', scale=2)
        apply(plan, dry=not a.apply, modifies=(NAME, NAME + '-greeblies', 'highfield_q051_ur'))
        raise SystemExit(0)
    if a.greeblies:
        plan = greeblies_plan()
        preview(plan, ROOT / f'verification/site/{NAME}-greeblies-preview.png', scale=2)
        apply(plan, dry=not a.apply, modifies=(NAME, NAME + '-greeblies', NAME + '-lower', 'highfield_q051_ur'))
        raise SystemExit(0)
    c = make()
    plan = c.build(EXTRA)
    print('parts', {pt.name: sum(1 for q in c.part.values() if q is pt) for pt in PARTS})
    print('info', i40, i38, i42)
    print('stairs', c.stairs_at, 'doors', c.door_cells)
    preview(plan, ROOT / f'verification/site/{NAME}-preview.png', scale=2)
    print(json.dumps(plan.summary())[:300])
    apply(plan, dry=not a.apply)
