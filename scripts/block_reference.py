#!/usr/bin/env python3
"""Block reference sheets: how a block looks from the side, from above, and from natural angles above and below.

Textures and models come from a Minecraft client jar (default: 1.21.11; the 26.2 world has no jar installed, and the
blocks used here look the same). Nothing from the jar is committed: the sheets go to instance/block-reference/ and only
reference/blocks/blocks.json (average colours, partial flag, connects flag) is kept in git.

  .venv/bin/python scripts/block_reference.py extract                  # unpack textures/models from the jar (once)
  .venv/bin/python scripts/block_reference.py index                    # reference/blocks/blocks.json for EVERY block (text, cheap)
  .venv/bin/python scripts/block_reference.py describe mushroom_stem   # one line: colours, flat/patterned, opaque, full/partial
  .venv/bin/python scripts/block_reference.py nearest 213,177,161 [--flat] [--opaque] [--group grey-mid] [--partial]
  .venv/bin/python scripts/block_reference.py one oak_fence glass_pane # one image per block, with neighbour variants
  .venv/bin/python scripts/block_reference.py sheets                   # colour contact sheets (images; on demand only)

For AI use: start with `nearest` and `describe` (text, a few tokens); open an image (`one`, a sheet) only to choose between
close candidates by texture.

Views per block: TOP (straight down), SIDE (south face), ABOVE (45 deg yaw, 30 deg down), BELOW (45 deg yaw, 30 deg up).
REMINDER: panes, iron bars, walls and fences change shape with their neighbours; `one` draws alone, straight run, corner,
T and beside a full block. Stairs depend on facing/shape, slabs on type. Grass, leaves and ferns are tinted green here.
"""
from __future__ import annotations

import argparse
import colorsys
import json
import math
import re
import sys
import zipfile
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from script_env import ROOT  # noqa: E402

JAR = Path.home() / 'Library/Application Support/minecraft/versions/1.21.11/1.21.11.jar'
ASSETS = ROOT / 'instance' / 'block-reference' / 'assets' / 'minecraft'
OUT = ROOT / 'instance' / 'block-reference'
INDEX = ROOT / 'reference' / 'blocks' / 'blocks.json'
TINT = (121, 192, 90)
MUSHROOM_BLOCKS = ('mushroom_stem', 'brown_mushroom_block', 'red_mushroom_block')
SHADE = {'up': 1.0, 'north': 0.8, 'south': 0.8, 'east': 0.6, 'west': 0.6, 'down': 0.5}
NORMAL = {'up': (0, 1, 0), 'down': (0, -1, 0), 'north': (0, 0, -1), 'south': (0, 0, 1), 'east': (1, 0, 0), 'west': (-1, 0, 0)}
PARTIAL = ('_slab', '_carpet', '_stairs', '_trapdoor', '_button', '_pressure_plate', 'snow', 'candle', '_wall', '_fence')
CONNECTS = ('_pane', 'iron_bars', '_wall', '_fence', 'chain')
TINTED = ('grass_block', 'leaves', 'fern', 'short_grass', 'tall_grass', 'vine', 'lily_pad')
TILE = 112


def extract(jar: Path = JAR) -> int:
    """Unpack block textures, models and blockstates from the jar into instance/block-reference/.

    @param jar: client jar
    @returns: number of files written
    """
    n = 0
    with zipfile.ZipFile(jar) as z:
        for name in z.namelist():
            if re.match(r'assets/minecraft/(textures/block|models/block|blockstates)/.*\.(png|json)$', name):
                dest = OUT / name
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_bytes(z.read(name))
                n += 1
    return n


# --- models ----------------------------------------------------------------------------------------------------------
_cache: dict = {}


def _json(path: Path):
    return json.loads(path.read_text())


def model(name: str) -> dict:
    """A model with its parents merged: {'textures': {...}, 'elements': [...]}."""
    name = name.replace('minecraft:', '').replace('block/', '')
    if name in _cache:
        return _cache[name]
    d = _json(ASSETS / 'models' / 'block' / f'{name}.json')
    base = {'textures': {}, 'elements': []}
    if 'parent' in d:
        p = d['parent'].replace('minecraft:', '')
        if p.startswith('builtin/'):
            base = {'textures': {}, 'elements': []}
        else:
            base = json.loads(json.dumps(model(p)))
    base['textures'].update(d.get('textures', {}))
    if 'elements' in d:
        base['elements'] = d['elements']
    _cache[name] = base
    return base


def resolve(tex: str, textures: dict) -> str | None:
    """Follow #references to a texture name."""
    seen = 0
    while tex and tex.startswith('#') and seen < 10:
        tex = textures.get(tex[1:])
        seen += 1
    return tex.replace('minecraft:', '').replace('block/', '') if tex else None


def _load_tex(name: str) -> np.ndarray | None:
    p = ASSETS / 'textures' / 'block' / f'{name}.png'
    if not p.exists():
        return None
    im = Image.open(p).convert('RGBA')
    if im.height > im.width:                         # animated strip: first frame
        im = im.crop((0, 0, im.width, im.width))
    return np.asarray(im)


def parts_for(block: str, props: dict | None = None) -> list[tuple[dict, int, int]]:
    """Models (merged), y rotation, x rotation used by a block's blockstate for the given properties.

    @param block: block name without namespace
    @param props: e.g. {'facing': 'north', 'type': 'bottom'}; multipart blocks take {'north': 'true', ...} style keys
    @returns: [(model dict, y rot, x rot)]
    """
    bs = _json(ASSETS / 'blockstates' / f'{block}.json')
    props = {**{'half': 'bottom', 'shape': 'straight', 'type': 'bottom', 'facing': 'north', 'axis': 'y', 'open': 'false'}, **(props or {})}
    if block in MUSHROOM_BLOCKS:                    # placed with no state, a mushroom block shows its outside on every face
        props = {**{k: 'true' for k in ('north', 'south', 'east', 'west', 'up', 'down')}, **props}
    out = []

    def pick(v):
        if isinstance(v, list):
            v = v[0]
        return model(v['model']), v.get('y', 0), v.get('x', 0)

    if 'variants' in bs:
        want = None
        for key in bs['variants']:
            kv = dict(p.split('=') for p in key.split(',')) if key else {}
            if all(kv.get(k) == str(val) for k, val in props.items() if k in kv):
                want = key
                break
        if want is None:
            want = next(iter(bs['variants']))
        out.append(pick(bs['variants'][want]))
    else:
        for part in bs['multipart']:
            cond = part.get('when')
            if cond is None or _matches(cond, props):
                out.append(pick(part['apply']))
    return out


def _matches(cond: dict, props: dict) -> bool:
    if 'OR' in cond:
        return any(_matches(c, props) for c in cond['OR'])
    if 'AND' in cond:
        return all(_matches(c, props) for c in cond['AND'])
    return all(str(props.get(k, 'false')) in str(v).split('|') for k, v in cond.items())


# --- rendering ---------------------------------------------------------------------------------------------------------
def _rot_y(p, deg):
    a = math.radians(deg)
    x, y, z = p
    return (x * math.cos(a) + z * math.sin(a), y, -x * math.sin(a) + z * math.cos(a))


def _rot_x(p, deg):
    a = math.radians(deg)
    x, y, z = p
    return (x, y * math.cos(a) - z * math.sin(a), y * math.sin(a) + z * math.cos(a))


def faces_of(block: str, props: dict | None = None, offset=(0, 0, 0)) -> list[dict]:
    """Textured quads in block space (0..16 each axis, centre 8) for a block state, with shade and tint flags."""
    out = []
    for m, ry, rx in parts_for(block, props):
        for el in m['elements']:
            (x0, y0, z0), (x1, y1, z1) = el['from'], el['to']
            for fname, f in el['faces'].items():
                tex = resolve(f['texture'], m['textures'])
                if not tex:
                    continue
                c = {'up': [(x0, y1, z0), (x1, y1, z0), (x1, y1, z1), (x0, y1, z1)],
                     'down': [(x0, y0, z1), (x1, y0, z1), (x1, y0, z0), (x0, y0, z0)],
                     'north': [(x1, y1, z0), (x0, y1, z0), (x0, y0, z0), (x1, y0, z0)],
                     'south': [(x0, y1, z1), (x1, y1, z1), (x1, y0, z1), (x0, y0, z1)],
                     'west': [(x0, y1, z0), (x0, y1, z1), (x0, y0, z1), (x0, y0, z0)],
                     'east': [(x1, y1, z1), (x1, y1, z0), (x1, y0, z0), (x1, y0, z1)]}[fname]
                uv = f.get('uv') or _default_uv(fname, el['from'], el['to'])
                pts = []
                for p in c:
                    q = (p[0] - 8, p[1] - 8, p[2] - 8)
                    if rx:
                        q = _rot_x(q, -rx)
                    if ry:
                        q = _rot_y(q, -ry)
                    pts.append((q[0] + 8 + offset[0], q[1] + 8 + offset[1], q[2] + 8 + offset[2]))
                n = NORMAL[fname]
                if rx:
                    n = _rot_x(n, -rx)
                if ry:
                    n = _rot_y(n, -ry)
                out.append({'pts': pts, 'uv': uv, 'tex': tex, 'normal': n, 'tint': 'tintindex' in f,
                            'shade': SHADE[fname if not (rx or ry) else _face_of(n)]})
    return out


def _face_of(n):
    ax = max(range(3), key=lambda i: abs(n[i]))
    return [('east', 'west'), ('up', 'down'), ('south', 'north')][ax][0 if n[ax] > 0 else 1]


def _default_uv(face, a, b):
    (x0, y0, z0), (x1, y1, z1) = a, b
    return {'up': [x0, z0, x1, z1], 'down': [x0, 16 - z1, x1, 16 - z0], 'north': [16 - x1, 16 - y1, 16 - x0, 16 - y0],
            'south': [x0, 16 - y1, x1, 16 - y0], 'west': [z0, 16 - y1, z1, 16 - y0],
            'east': [16 - z1, 16 - y1, 16 - z0, 16 - y0]}[face]


def render(faces: list[dict], yaw: float, pitch: float, size: int = TILE, tint=TINT, span: float = 26.0) -> Image.Image:
    """Orthographic render of quads. yaw rotates about the vertical axis; pitch > 0 looks down from above, < 0 up from below."""
    yaw_r, pit_r = math.radians(yaw), math.radians(pitch)
    cam = (math.sin(yaw_r) * math.cos(pit_r), math.sin(pit_r), math.cos(yaw_r) * math.cos(pit_r))   # towards the viewer
    right = (math.cos(yaw_r), 0, -math.sin(yaw_r))
    up = (-math.sin(yaw_r) * math.sin(pit_r), math.cos(pit_r), -math.cos(yaw_r) * math.sin(pit_r))
    scale = size / span
    img = np.zeros((size, size, 4), np.float32)
    depth = np.full((size, size), -1e9, np.float32)

    def proj(p):
        q = (p[0] - 8, p[1] - 8, p[2] - 8)
        return (size / 2 + scale * sum(q[i] * right[i] for i in range(3)),
                size / 2 - scale * sum(q[i] * up[i] for i in range(3)),
                sum(q[i] * cam[i] for i in range(3)))

    for f in faces:
        if sum(f['normal'][i] * cam[i] for i in range(3)) <= 1e-6:
            continue
        tex = _load_tex(f['tex'])
        if tex is None:
            continue
        P = [proj(p) for p in f['pts']]
        u0, v0, u1, v1 = f['uv']
        uvs = [(u0, v0), (u1, v0), (u1, v1), (u0, v1)]
        xs, ys = [p[0] for p in P], [p[1] for p in P]
        bx0, bx1 = max(0, int(min(xs))), min(size - 1, int(max(xs)) + 1)
        by0, by1 = max(0, int(min(ys))), min(size - 1, int(max(ys)) + 1)
        if bx1 < bx0 or by1 < by0:
            continue
        # affine: screen = P0 + s*(P1-P0) + t*(P3-P0), s,t in [0,1]; texture uv bilinear in (s,t)
        ax, ay = P[1][0] - P[0][0], P[1][1] - P[0][1]
        bx, by = P[3][0] - P[0][0], P[3][1] - P[0][1]
        det = ax * by - ay * bx
        if abs(det) < 1e-6:
            continue
        gy, gx = np.mgrid[by0:by1 + 1, bx0:bx1 + 1]
        dx, dy = gx + 0.5 - P[0][0], gy + 0.5 - P[0][1]
        s = (dx * by - dy * bx) / det
        t = (ax * dy - ay * dx) / det
        m = (s >= 0) & (s <= 1) & (t >= 0) & (t <= 1)
        u = (uvs[0][0] + s * (uvs[1][0] - uvs[0][0]) + t * (uvs[3][0] - uvs[0][0])) / 16 * tex.shape[1]
        v = (uvs[0][1] + s * (uvs[1][1] - uvs[0][1]) + t * (uvs[3][1] - uvs[0][1])) / 16 * tex.shape[0]
        ui = np.clip(u.astype(int), 0, tex.shape[1] - 1)
        vi = np.clip(v.astype(int), 0, tex.shape[0] - 1)
        col = tex[vi, ui].astype(np.float32)
        d = (P[0][2] + s * (P[1][2] - P[0][2]) + t * (P[3][2] - P[0][2]))
        ok = m & (col[..., 3] > 127) & (d > depth[gy, gx])
        rgb = col[..., :3] * f['shade']
        if f['tint']:
            rgb = rgb * np.array(tint, np.float32) / 255.0
        img[gy[ok], gx[ok], :3] = rgb[ok]
        img[gy[ok], gx[ok], 3] = 255
        depth[gy[ok], gx[ok]] = d[ok]
    return Image.fromarray(np.clip(img, 0, 255).astype(np.uint8), 'RGBA')


VIEWS = (('top', 0, 90), ('side', 0, 0), ('above', 35, 30), ('below', 35, -30))


def block_views(block: str, props: dict | None = None) -> list[Image.Image]:
    """The four views (top, side, above, below) of one block state, on a mid-grey backdrop."""
    faces = faces_of(block, props)
    tint = TINT if any(k in block for k in TINTED) else (255, 255, 255)
    out = []
    for _n, yaw, pit in VIEWS:
        im = render(faces, yaw, pit, tint=tint)
        bg = Image.new('RGBA', im.size, (92, 96, 104, 255))
        bg.alpha_composite(im)
        out.append(bg)
    return out


def average_colour(block: str) -> tuple[int, int, int] | None:
    """Mean RGB of the opaque pixels over the top and side faces of the default model (tint applied)."""
    try:
        faces = faces_of(block)
    except (OSError, KeyError, ValueError, StopIteration):
        return None
    px = []
    for f in faces:
        if f['normal'][1] > 0 or abs(f['normal'][2]) > 0.9:
            t = _load_tex(f['tex'])
            if t is None:
                continue
            a = t[t[..., 3] > 127][:, :3].astype(float)
            if len(a):
                m = a.mean(axis=0)
                if f['tint'] and any(k in block for k in TINTED):
                    m = m * np.array(TINT) / 255.0
                px.append(m)
    return tuple(int(v) for v in np.mean(px, axis=0)) if px else None


# --- sets, sheets ----------------------------------------------------------------------------------------------------------
SLICE = [r'.*_concrete$', r'.*_terracotta$', r'.*_wool$', r'^(stone|cobblestone|andesite|diorite|granite|smooth_stone|'
         r'polished_(andesite|diorite|granite|blackstone|deepslate)|stone_bricks|mossy_stone_bricks|cracked_stone_bricks|'
         r'bricks|deepslate|deepslate_bricks|deepslate_tiles|cobbled_deepslate|blackstone|gilded_blackstone|mud_bricks|'
         r'sandstone|smooth_sandstone|cut_sandstone|red_sandstone|smooth_red_sandstone|quartz_block|smooth_quartz|'
         r'quartz_bricks|chiseled_quartz_block|calcite|tuff|dripstone_block|prismarine|prismarine_bricks|dark_prismarine|'
         r'bone_block|mushroom_stem|brown_mushroom_block|red_mushroom_block|iron_block|gold_block|copper_block|'
         r'cut_copper|exposed_copper|weathered_copper|oxidized_copper|netherrack|nether_bricks|red_nether_bricks|'
         r'end_stone|end_stone_bricks|purpur_block|basalt|smooth_basalt|packed_ice|snow_block|clay|gravel|dirt|coarse_dirt|'
         r'grass_block|podzol|mud|sand|red_sand|terracotta|glass|tinted_glass|white_stained_glass|'
         r'(oak|spruce|birch|jungle|acacia|dark_oak|mangrove|cherry|bamboo|crimson|warped)_planks|'
         r'(oak|spruce|birch|jungle|acacia|dark_oak|mangrove|cherry)_leaves|iron_bars|glass_pane|smooth_stone_slab|'
         r'stone_slab|stone_brick_stairs|stone_brick_wall|oak_fence|brick_wall|cobblestone_wall|light_gray_concrete_powder|'
         r'.*_slab|.*_stairs)$']


def names_in(patterns: list[str]) -> list[str]:
    allbs = sorted(p.stem for p in (ASSETS / 'blockstates').glob('*.json'))
    rx = [re.compile(p) for p in patterns]
    return [n for n in allbs if any(r.match(n) for r in rx)]


def hue_group(rgb) -> str:
    r, g, b = (c / 255 for c in rgb)
    h, l, s = colorsys.rgb_to_hls(r, g, b)
    if s < 0.12:
        return 'grey-black' if l < 0.25 else 'grey-dark' if l < 0.45 else 'grey-mid' if l < 0.7 else 'grey-white'
    if l < 0.15:
        return 'grey-black'
    names = [(15, 'red'), (40, 'orange-brown'), (70, 'yellow-beige'), (170, 'green'), (200, 'cyan'), (260, 'blue'),
             (330, 'purple-pink'), (361, 'red')]
    deg = h * 360
    return next(n for lim, n in names if deg < lim)


LIGHT = ('glowstone', 'sea_lantern', 'shroomlight', 'lantern', 'froglight', 'torch', 'beacon', 'jack_o_lantern',
         'redstone_lamp', 'magma_block', 'crying_obsidian', 'candle', 'campfire', 'respawn_anchor', 'conduit', 'end_rod',
         'copper_bulb')


def _texture_stats(block: str):
    """(top rgb, side rgb, noise, transparent, full cube) from the default model, None when it has no faces."""
    faces = faces_of(block)
    if not faces:
        return None
    cols = {'top': [], 'side': []}
    noise, transparent = [], False
    for f in faces:
        t = _load_tex(f['tex'])
        if t is None:
            continue
        opaque = t[..., 3] > 127
        if not opaque.all():
            transparent = True
        if not opaque.any():
            continue
        px = t[opaque][:, :3].astype(float)
        m = px.mean(axis=0)
        if f['tint'] and any(k in block for k in TINTED):
            m = m * np.array(TINT) / 255.0
        if f['normal'][1] > 0.9:
            cols['top'].append(m)
        elif abs(f['normal'][1]) < 0.1:
            cols['side'].append(m)
        noise.append(float((px @ np.array([0.299, 0.587, 0.114])).std()))
    allc = cols['top'] + cols['side']
    if not allc:
        return None
    top = np.mean(cols['top'] or allc, axis=0)
    side = np.mean(cols['side'] or allc, axis=0)
    m = parts_for(block)[0][0]['elements']
    full = len(m) == 1 and m[0]['from'] == [0, 0, 0] and m[0]['to'] == [16, 16, 16]
    return ([int(v) for v in top], [int(v) for v in side], round(float(np.mean(noise)), 1), transparent, full)


def lightness_word(rgb) -> str:
    l = colorsys.rgb_to_hls(*(c / 255 for c in rgb))[1]
    return 'very dark' if l < 0.2 else 'dark' if l < 0.38 else 'mid' if l < 0.6 else 'light' if l < 0.8 else 'very light'


def build_info(block: str) -> dict | None:
    """Text-first record for one block (colours, texture character, opacity, shape class)."""
    st = _texture_stats(block)
    if st is None:
        return None
    top, side, noise, transparent, full = st
    rgb = [int((a + b) / 2) for a, b in zip(top, side)]
    texture = 'flat' if noise < 6 else 'subtle' if noise < 14 else 'patterned' if noise < 28 else 'busy'
    shape = 'partial' if any(k in block for k in PARTIAL) else 'full' if (full or block in MUSHROOM_BLOCKS) else 'other'
    d = {'rgb': rgb, 'top_rgb': top, 'side_rgb': side, 'noise': noise, 'texture': texture, 'opaque': not transparent,
         'shape': shape, 'partial': shape == 'partial', 'connects': any(k in block for k in CONNECTS),
         'emits_light': any(k in block for k in LIGHT), 'group': hue_group(rgb)}
    d['text'] = (f'{lightness_word(rgb)} {d["group"]}, {texture} texture, {"opaque" if not transparent else "see-through parts"}, '
                 f'{shape} block; top {tuple(top)} side {tuple(side)}'
                 + ('; shape depends on neighbours' if d['connects'] else '') + ('; emits light' if d['emits_light'] else ''))
    return d


def build_index() -> int:
    """Write reference/blocks/blocks.json for every blockstate that renders (text only)."""
    info = {}
    for n in sorted(p.stem for p in (ASSETS / 'blockstates').glob('*.json')):
        try:
            d = build_info(n)
        except Exception:                    # noqa: BLE001 - odd blockstates are skipped
            d = None
        if d:
            info[n] = d
    INDEX.parent.mkdir(parents=True, exist_ok=True)
    INDEX.write_text(json.dumps({'source': JAR.name, 'note': 'rgb = mean of top+side faces (tinted blocks shown green); '
                                 'noise = luminance std of the texture; partial = slab/stairs/carpet/...; connects = shape '
                                 'depends on neighbours', 'blocks': info}, indent=0, sort_keys=True))
    return len(info)


def describe(name: str) -> str:
    """One line from the index (builds it first if missing)."""
    if not INDEX.exists():
        build_index()
    b = json.loads(INDEX.read_text())['blocks'].get(name)
    return f'{name}: {b["text"]}' if b else f'{name}: not in the index'


def sheets(patterns: list[str]) -> int:
    """Contact sheets grouped by colour (sorted by lightness) and the reference/blocks/blocks.json index."""
    names = names_in(patterns)
    info, groups = {}, {}
    for n in names:
        try:
            rgb = average_colour(n)
        except Exception:                       # noqa: BLE001 - odd blockstates are skipped, not fatal
            rgb = None
        if not rgb:
            continue
        info[n] = {'rgb': list(rgb), 'group': hue_group(rgb), 'partial': any(k in n for k in PARTIAL),
                   'connects': any(k in n for k in CONNECTS)}
        groups.setdefault(info[n]['group'], []).append(n)
    font = ImageFont.load_default()
    n_img = 0
    for g, items in groups.items():
        items.sort(key=lambda n: sum(info[n]['rgb']))
        per = 5
        for page in range(0, len(items), per * 4):
            chunk = items[page:page + per * 4]
            rows = math.ceil(len(chunk) / per)
            W, H = per * (TILE * 4 // 2 + 6), rows * (TILE // 2 + 22)
            sheet = Image.new('RGB', (W, H), (40, 42, 48))
            d = ImageDraw.Draw(sheet)
            for i, n in enumerate(chunk):
                x, y = (i % per) * (TILE * 2 + 6), (i // per) * (TILE // 2 + 22)
                try:
                    views = block_views(n)
                except Exception:                # noqa: BLE001
                    continue
                for k, v in enumerate(views):
                    sheet.paste(v.resize((TILE // 2 * 1, TILE // 2 * 1)).convert('RGB'), (x + k * (TILE // 2), y + 14))
                d.text((x + 1, y), n[:30] + ('*' if info[n]['connects'] else ''), fill=(235, 235, 235), font=font)
            OUT.mkdir(parents=True, exist_ok=True)
            sheet.save(OUT / f'sheet-{g}-{page // (per * 4) + 1}.png')
            n_img += 1
    return n_img


def one(names: list[str]) -> list[Path]:
    """One image per block; connecting blocks also drawn as straight run, corner, T and beside a full block."""
    outs = []
    OUT.mkdir(parents=True, exist_ok=True)
    for n in names:
        rows = [('alone', [(0, 0, {})])]
        if any(k in n for k in CONNECTS):
            lo = 'true' if '_wall' not in n else 'low'
            ew = {'east': lo, 'west': lo}
            ns = {'north': lo, 'south': lo}
            rows = [('alone', [(0, 0, {})]), ('straight', [(0, 0, ew), (16, 0, ew), (-16, 0, ew)]),
                    ('corner', [(0, 0, {'north': lo, 'east': lo}), (16, 0, ew), (0, -16, ns)]),
                    ('T', [(0, 0, {'north': lo, 'east': lo, 'west': lo}), (-16, 0, ew), (16, 0, ew), (0, -16, ns)])]
        W = len(VIEWS) * TILE
        sheet = Image.new('RGB', (W, len(rows) * TILE + 16), (40, 42, 48))
        d = ImageDraw.Draw(sheet)
        d.text((2, 2), f'{n}   (shape depends on neighbours)' if len(rows) > 1 else n, fill=(235, 235, 235))
        for r, (label, cells) in enumerate(rows):
            faces = []
            for ox, oz, props in cells:
                faces += faces_of(n, props, (ox, 0, oz))
            for k, (_vn, yaw, pit) in enumerate(VIEWS):
                im = render(faces, yaw, pit, tint=TINT if any(t in n for t in TINTED) else (255, 255, 255),
                            span=26.0 if len(cells) == 1 else 50.0)
                bg = Image.new('RGBA', im.size, (92, 96, 104, 255))
                bg.alpha_composite(im)
                sheet.paste(bg.convert('RGB'), (k * TILE, 16 + r * TILE))
            d.text((2, 16 + r * TILE + 2), label, fill=(255, 255, 160))
        p = OUT / f'one-{n}.png'
        sheet.save(p)
        outs.append(p)
    return outs


def nearest(rgb: tuple[int, int, int], k: int = 12, partial: bool = False, flat: bool = False, opaque: bool = False,
            group: str | None = None) -> list[tuple[str, tuple]]:
    """Blocks in reference/blocks/blocks.json whose average colour is closest to rgb (weighted RGB distance).

    @param rgb: target colour, e.g. read off the Google sheet
    @param k: how many
    @param partial: also list slabs, stairs, walls, fences (same colour as their full block, so off by default)
    @param flat: only flat or subtle textures (not patterned/busy)
    @param opaque: only fully opaque blocks
    @param group: only this colour group (grey-mid, orange-brown, ...)
    """
    if not INDEX.exists():
        build_index()
    data = {n: v for n, v in json.loads(INDEX.read_text())['blocks'].items()
            if (partial or not v['partial']) and (not flat or v['texture'] in ('flat', 'subtle'))
            and (not opaque or v['opaque']) and (group is None or v['group'] == group)}
    def dist(c):
        rm = (c[0] + rgb[0]) / 2
        return math.sqrt((2 + rm / 256) * (c[0] - rgb[0]) ** 2 + 4 * (c[1] - rgb[1]) ** 2 + (2 + (255 - rm) / 256) * (c[2] - rgb[2]) ** 2)
    return sorted(((n, tuple(v['rgb'])) for n, v in data.items()), key=lambda t: dist(t[1]))[:k]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('cmd', choices=('extract', 'index', 'describe', 'sheets', 'one', 'nearest'))
    ap.add_argument('args', nargs=argparse.REMAINDER)
    a = ap.parse_args()
    if a.cmd == 'extract':
        print(extract(), 'files')
    elif a.cmd == 'index':
        print(build_index(), 'blocks in', INDEX)
    elif a.cmd == 'describe':
        for n in a.args:
            print(describe(n))
    elif a.cmd == 'sheets':
        print(sheets(SLICE), 'sheets in', OUT)
    elif a.cmd == 'one':
        for p in one(a.args):
            print(p)
    else:
        rgb = tuple(int(v) for v in a.args[0].split(','))
        grp = a.args[a.args.index('--group') + 1] if '--group' in a.args else None
        for n, c in nearest(rgb, partial='--partial' in a.args, flat='--flat' in a.args, opaque='--opaque' in a.args, group=grp):
            print(f'{n:34} {c}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
