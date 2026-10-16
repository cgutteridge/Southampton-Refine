#!/usr/bin/env python3
"""Registered user aerials: image px <-> Minecraft x,z, and a crop by MC bbox with OSM outlines + 10-block grid.

A registration is <image>.registration.json next to the image: tie points (MC x,z <-> image px), a
similarity fit px = A . [x, z, 1], and the residual in blocks. Make or refit one with `fit`; crop with `crop`.

  .venv/bin/python scripts/aerial_registered.py fit  reference/aerial/highfield-user/<img>.registration.json
  .venv/bin/python scripts/aerial_registered.py crop reference/aerial/highfield-user/<img>.registration.json x0,z0,x1,z1 out.png [scale]
  .venv/bin/python scripts/aerial_registered.py at   <registration.json> x z      # prints image px

Image is not true ortho (3D-tile render, tall roofs lean ~1-2 blocks), so ties are on OSM corners that coincide
with ground-level or low-roof features; treat accuracy as about 1 block near the ties, 2-3 away from them.
"""
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'scripts'))


def fit_similarity(ties):
    """ties: [[x, z, u, v], ...] -> 2x3 matrix A with [u, v] = A . [x, z, 1] (rotation + uniform scale + shift)."""
    rows, rhs = [], []
    for x, z, u, v in ties:
        rows += [[x, -z, 1, 0], [z, x, 0, 1]]
        rhs += [u, v]
    a, b, tx, ty = np.linalg.lstsq(np.array(rows, float), np.array(rhs, float), rcond=None)[0]
    return np.array([[a, -b, tx], [b, a, ty]])


def load(reg_path):
    reg = json.loads(Path(reg_path).read_text())
    return reg, np.array(reg['A'], float)


def refit(reg_path):
    reg = json.loads(Path(reg_path).read_text())
    ties = [t['mc'] + t['px'] for t in reg['ties']]
    A = fit_similarity(ties)
    s = float(np.hypot(A[0, 0], A[1, 0]))
    res = [np.hypot(*(A @ [x, z, 1] - [u, v])) / s for x, z, u, v in ties]
    reg.update(A=A.tolist(), px_per_block=round(s, 3), rotation_deg=round(float(np.degrees(np.arctan2(A[1, 0], A[0, 0]))), 2),
               residual_blocks={'rms': round(float(np.sqrt(np.mean(np.square(res)))), 2), 'max': round(float(max(res)), 2),
                                'each': [round(float(r), 2) for r in res]})
    Path(reg_path).write_text(json.dumps(reg, indent=1) + '\n')
    return reg


def to_px(A, x, z):
    u, v = A @ [x, z, 1]
    return float(u), float(v)


def to_mc(A, u, v):
    M = np.linalg.inv(np.vstack([A, [0, 0, 1]]))
    x, z, _ = M @ [u, v, 1]
    return float(x), float(z)


def crop(reg_path, bbox, out, scale=2):
    from osm_footprints import OSMIndex
    reg, A = load(reg_path)
    im = Image.open(ROOT / 'reference' / reg['image']).convert('RGB')
    x0, z0, x1, z1 = bbox
    pts = [to_px(A, x, z) for x in (x0, x1) for z in (z0, z1)]
    bx0, by0 = int(min(p[0] for p in pts)), int(min(p[1] for p in pts))
    bx1, by1 = int(max(p[0] for p in pts)), int(max(p[1] for p in pts))
    c = im.crop((bx0, by0, bx1, by1))
    c = c.resize((c.width * scale, c.height * scale), Image.LANCZOS)
    d = ImageDraw.Draw(c)
    T = lambda x, z: ((to_px(A, x, z)[0] - bx0) * scale, (to_px(A, x, z)[1] - by0) * scale)
    for ring, p in OSMIndex().buildings:
        r = ring[0]
        if not any(x0 - 4 <= x <= x1 + 4 and z0 - 4 <= z <= z1 + 4 for x, z in r):
            continue
        q = [T(x, z) for x, z in r]
        d.line(q, fill=(255, 0, 0), width=2)
        d.text(q[0], (p.get('osm_way_id') or '')[-3:], fill=(255, 255, 0))
    for gx in range(x0 - x0 % 10 + 10, x1, 10):
        d.line([T(gx, z0), T(gx, z1)], fill=(0, 255, 255), width=1)
        d.text(T(gx, z0), str(gx), fill=(0, 255, 255))
    for gz in range(z0 - z0 % 10 + 10, z1, 10):
        d.line([T(x0, gz), T(x1, gz)], fill=(0, 255, 0), width=1)
        d.text(T(x0, gz), str(gz), fill=(0, 255, 0))
    c.save(out)
    return c.size


if __name__ == '__main__':
    cmd = sys.argv[1]
    if cmd == 'fit':
        r = refit(sys.argv[2])
        print(r['px_per_block'], 'px/block, rot', r['rotation_deg'], r['residual_blocks'])
    elif cmd == 'crop':
        print(crop(sys.argv[2], list(map(int, sys.argv[3].split(','))), sys.argv[4], int(sys.argv[5]) if len(sys.argv) > 5 else 2))
    elif cmd == 'at':
        _, A = load(sys.argv[2])
        print(to_px(A, float(sys.argv[3]), float(sys.argv[4])))
