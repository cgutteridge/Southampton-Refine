#!/usr/bin/env python3
"""Cropped, gridded Google satellite windows for reading trees by eye, and the same window with a trees plan drawn on it.

Google is look-only (scripts/google_aerial.py): the page loads the tiles straight from Google in the browser pane, nothing is
saved. The crop is exact in block coordinates (an affine fit of the tile pixels to the MC grid), 5-block grid, labelled.

  python3 scripts/google_window.py crop --at 6240,-5664 --half 32x16 --ppb 13        # reading window
  python3 scripts/google_window.py crop --at 6240,-5664 --half 32x16 --outlines      # + OSM building outlines (check registration)
  python3 scripts/google_window.py plan --at 6240,-5664 --half 32x16 --plan p.json   # planned crowns (yellow) / skipped (red dashed)

A window must fit the browser pane (about 1100 x 600 css px): --half 32x16 --ppb 13 gives 64 x 32 blocks. Output:
instance/google-aerial/w_<x>_<z>.html (crop) or p_<x>_<z>.html (plan); open it as file://... in the browser pane
(close old tabs first: the pane has a tab cap). Method: site/FOLIAGE.txt "Redo from Google".
"""
from __future__ import annotations

import argparse
import json

import google_aerial as G
from script_env import ROOT  # noqa: E402

ZOOM = 20


def page(cx: int, cz: int, hx: int, hz: int, ppb: int, svg_fn) -> str:
    """HTML of the exact crop x cx-hx..cx+hx, z cz-hz..cz+hz; svg_fn(x0, z0, ppb) returns extra SVG drawn over it."""
    x0, z0, x1, z1 = cx - hx, cz - hz, cx + hx, cz + hz
    w, h = 2 * hx * ppb, 2 * hz * ppb
    tx0, ty0, tx1, ty1 = G.tile_range((x0, z0, x1, z1), ZOOM)
    s = 256
    p = [((fx - tx0) * s, (fy - ty0) * s) for fx, fy in G.mc_to_tile([(x0, z0), (x1, z0), (x0, z1)], ZOOM)]
    (ax, ay), (bx, by), (cx_, cy_) = p
    a, b, c, d = (bx - ax) / w, (by - ay) / w, (cx_ - ax) / h, (cy_ - ay) / h
    det = a * d - b * c
    ia, ib, ic, id_ = d / det, -b / det, -c / det, a / det
    tx, ty = -(ia * ax + ic * ay), -(ib * ax + id_ * ay)
    imgs = ''.join(f'<img src="{G.tile_url(x, y, ZOOM)}" style="position:absolute;left:{(x - tx0) * s}px;top:{(y - ty0) * s}px;width:{s}px;height:{s}px">'
                   for y in range(ty0, ty1 + 1) for x in range(tx0, tx1 + 1))
    svg = ''
    for v in range((x0 // 5 + 1) * 5, x1 + 1, 5):
        X = (v - x0) * ppb
        svg += f'<line x1="{X}" y1="0" x2="{X}" y2="{h}" stroke="#3f6" stroke-opacity=".6"/><text x="{X + 2}" y="11" fill="#3f6" font-size="11">{v}</text>'
    for v in range((z0 // 5 + 1) * 5, z1 + 1, 5):
        Y = (v - z0) * ppb
        svg += f'<line x1="0" y1="{Y}" x2="{w}" y2="{Y}" stroke="#3cf" stroke-opacity=".6"/><text x="2" y="{Y - 2}" fill="#3cf" font-size="11">{v}</text>'
    svg += svg_fn(x0, z0, ppb)
    return (f'<!doctype html><meta charset=utf-8><title>window {cx},{cz}</title><style>body{{margin:0;background:#111}}.box{{position:relative;width:{w}px;height:{h}px;overflow:hidden}}'
            f'.t{{position:absolute;left:0;top:0;width:{(tx1 - tx0 + 1) * s}px;height:{(ty1 - ty0 + 1) * s}px;transform-origin:0 0;transform:matrix({ia},{ib},{ic},{id_},{tx},{ty})}}'
            f'svg{{position:absolute;left:0;top:0}}</style><div class=box><div class=t>{imgs}</div><svg width="{w}" height="{h}">{svg}</svg></div>')


def outlines_svg(box: tuple[int, int, int, int]):
    def fn(x0, z0, ppb):
        out = ''
        for o in G.osm_outlines((box[0] - 20, box[1] - 20, box[2] + 20, box[3] + 20)):
            pts = ' '.join(f'{(x - x0) * ppb:.1f},{(z - z0) * ppb:.1f}' for x, z in o['ring'])
            out += f'<polygon points="{pts}" fill="none" stroke="#f0f" stroke-width="2"/>'
        return out
    return fn


def plan_svg(plan: dict):
    def fn(x0, z0, ppb):
        out = ''
        for x, z, r, *_k in plan['trees']:
            cx, cy = (x - x0 + .5) * ppb, (z - z0 + .5) * ppb
            out += f'<circle cx="{cx}" cy="{cy}" r="{r * ppb}" fill="none" stroke="#ff0" stroke-width="2.5"/><circle cx="{cx}" cy="{cy}" r="3" fill="#ff0"/>'
        for x, z, r, _why in plan['skipped']:
            out += f'<circle cx="{(x - x0 + .5) * ppb}" cy="{(z - z0 + .5) * ppb}" r="{r * ppb}" fill="none" stroke="#f33" stroke-width="2" stroke-dasharray="5 4"/>'
        return out
    return fn


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('mode', choices=('crop', 'plan'))
    ap.add_argument('--at', required=True, help='X,Z centre')
    ap.add_argument('--half', default='32x16', help='half width x half height in blocks')
    ap.add_argument('--ppb', type=int, default=13, help='css pixels per block')
    ap.add_argument('--outlines', action='store_true')
    ap.add_argument('--plan', help='JSON {"trees": [[x, z, r, kind]], "skipped": [[x, z, r, why]]} (trees_replan.py writes it)')
    a = ap.parse_args(argv)
    cx, cz = (int(v) for v in a.at.split(','))
    hx, hz = (int(v) for v in a.half.split('x'))
    if a.mode == 'plan':
        fn = plan_svg(json.loads(open(a.plan).read()))
    elif a.outlines:
        fn = outlines_svg((cx - hx, cz - hz, cx + hx, cz + hz))
    else:
        fn = lambda *_a: ''     # noqa: E731
    out = G.SHEETS / f'{"p" if a.mode == "plan" else "w"}_{cx}_{cz}.html'
    G.SHEETS.mkdir(parents=True, exist_ok=True)
    out.write_text(page(cx, cz, hx, hz, a.ppb, fn))
    print(f'{out}  x {cx - hx}..{cx + hx} z {cz - hz}..{cz + hz}  {a.ppb} px/block')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
