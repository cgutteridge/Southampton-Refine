"""Southampton Refine build kit: plan cells offline, preview, back up, batch-fill, read back.

A Plan maps (x, y, z) -> block state string ('minecraft:' optional). Every planned
cell is written, including air (so excavation is explicit). apply():
  1. refuses if the backup record is missing and cannot be created,
  2. saves one structure template of the plan's bounding box (+1 margin)
     as southampton_refine:before_<name> (only the first time),
  3. writes merged boxes with block_fill_batch (<= 8000 entries/call),
     solid blocks first and attachable blocks (doors, signs, torches...) after,
  4. writes sign text, summons entities,
  5. saves the world and reads every planned cell back from the region files.
Reports land in verification/site/<name>-*.json.
"""
import json, math, struct, sys, time, zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'scripts'))
import nbt_min as N  # noqa: E402

_CFG = json.loads((ROOT / 'config/world.json').read_text())
REGION = Path(_CFG['region_path'])
STRUCTURE_NS = _CFG.get('structure_namespace', 'southampton_refine')
OUT = ROOT / 'verification/site'
D = 'minecraft:overworld'
ATTACH = ('door', 'sign', 'torch', 'lantern', 'pane', 'bars', 'bed', 'button', 'lever',
          'trapdoor', 'end_rod', 'chain', 'carpet', 'rail', 'ladder', 'vine', 'banner',
          'flower_pot', 'potted', 'candle', 'rod', 'campfire', 'scaffolding', 'sapling')


def full(s):
    return s if ':' in s.split('[')[0] else 'minecraft:' + s


def bid(s):
    return full(s).split('[')[0]


class Plan:
    def __init__(self, name):
        self.name = name
        self.cells = {}
        self.signs = []      # (pos, [4 lines], colour, glowing)
        self.entities = []   # (entity_type, (x,y,z), snbt or None)

    # --- primitives -------------------------------------------------------
    def set(self, x, y, z, s):
        """Record one block in the plan.

        @param x: block X
        @param y: block Y
        @param z: block Z
        @param s: block id or short name
        @raises SystemExit: if ``s`` is a sapling (project rule: never build saplings)
        """
        st = full(s)
        if 'sapling' in st and not getattr(self, 'allow_saplings', False):
            raise SystemExit(
                f'{self.name}: sapling blocks are forbidden ({st} at {x},{y},{z}); '
                'they grow on random tick (not idempotent) — use static log+leaves or clear only',
            )
        self.cells[(x, y, z)] = st

    def fill(self, a, b, s):
        """Fill an axis-aligned box with one block state.

        @param a: corner [x,y,z]
        @param b: opposite corner
        @param s: block id or short name
        @raises SystemExit: if ``s`` is a sapling
        """
        (x0, x1), (y0, y1), (z0, z1) = (sorted((a[i], b[i])) for i in range(3))
        st = full(s)
        if 'sapling' in st and not getattr(self, 'allow_saplings', False):
            raise SystemExit(f'{self.name}: sapling blocks are forbidden in fill ({st})')
        for x in range(x0, x1 + 1):
            for y in range(y0, y1 + 1):
                for z in range(z0, z1 + 1):
                    self.cells[(x, y, z)] = st

    def get(self, x, y, z):
        return self.cells.get((x, y, z))

    def sign(self, pos, lines, colour='black', glow=False):
        self.signs.append((tuple(pos), (list(lines) + ['', '', '', ''])[:4], colour, glow))

    def entity(self, kind, pos, snbt=None):
        self.entities.append((kind, tuple(pos), snbt))

    def bounds(self):
        xs, ys, zs = zip(*self.cells)
        return (min(xs), min(ys), min(zs)), (max(xs), max(ys), max(zs))

    # --- compression into boxes ------------------------------------------
    def boxes(self):
        """Greedy merge: x-runs, then along z, then along y. Returns [(lo, hi, state)]."""
        rows = {}
        for (x, y, z), s in self.cells.items():
            rows.setdefault((y, z), []).append((x, s))
        runs = []
        for (y, z), xs in rows.items():
            xs.sort()
            start, prev, cur = xs[0][0], xs[0][0], xs[0][1]
            for x, s in xs[1:]:
                if x == prev + 1 and s == cur:
                    prev = x
                    continue
                runs.append((start, prev, y, z, cur))
                start, prev, cur = x, x, s
            runs.append((start, prev, y, z, cur))
        # merge along z
        byk = {}
        for x0, x1, y, z, s in runs:
            byk.setdefault((x0, x1, y, s), []).append(z)
        slabs = []
        for (x0, x1, y, s), zs in byk.items():
            zs.sort()
            a = p = zs[0]
            for z in zs[1:]:
                if z == p + 1:
                    p = z
                    continue
                slabs.append((x0, x1, a, p, y, s)); a = p = z
            slabs.append((x0, x1, a, p, y, s))
        # merge along y
        byk = {}
        for x0, x1, z0, z1, y, s in slabs:
            byk.setdefault((x0, x1, z0, z1, s), []).append(y)
        out = []
        for (x0, x1, z0, z1, s), ys in byk.items():
            ys.sort()
            a = p = ys[0]
            for y in ys[1:]:
                if y == p + 1:
                    p = y
                    continue
                out.append(((x0, a, z0), (x1, p, z1), s)); a = p = y
            out.append(((x0, a, z0), (x1, p, z1), s))
        attach = lambda s: any(k in bid(s) for k in ATTACH)
        # clear (air) first, then solids bottom-up, then attachables: surfaces such as
        # dirt_path or crops are never placed under terrain that is still to be cleared
        out.sort(key=lambda b: (attach(b[2]), bid(b[2]) != 'minecraft:air', b[0][1], b[0][0], b[0][2]))
        return out

    def summary(self):
        from collections import Counter
        c = Counter(bid(s) for s in self.cells.values())
        lo, hi = self.bounds()
        return {'name': self.name, 'cells': len(self.cells), 'boxes': len(self.boxes()),
                'bounds': [lo, hi], 'materials': dict(c.most_common()),
                'signs': len(self.signs), 'entities': len(self.entities)}


# --- offline preview ------------------------------------------------------
def colour(s):
    b = bid(s)[10:]
    if b in ('air', 'cave_air', 'light', 'void_air'):
        return None
    table = [ ('black_concrete', (25, 25, 30)), ('gray_concrete', (60, 64, 68)),
        ('light_gray_concrete', (125, 125, 115)), ('white_concrete', (210, 214, 215)),
        ('deepslate', (70, 70, 75)), ('blackstone', (45, 40, 48)), ('tinted', (45, 35, 55)),
        ('magenta', (200, 60, 190)), ('pink', (235, 140, 170)), ('cyan', (30, 150, 160)),
        ('light_blue', (90, 170, 220)), ('lime', (120, 200, 30)), ('purple', (120, 40, 170)),
        ('yellow', (240, 200, 40)), ('orange', (230, 110, 20)), ('red', (160, 40, 35)),
        ('sea_lantern', (200, 230, 225)), ('froglight', (240, 220, 200)), ('glowstone', (250, 210, 120)),
        ('iron_chain', (60, 60, 70)), ('end_rod', (240, 240, 240)), ('iron', (200, 200, 200)),
        ('copper', (90, 160, 140)), ('stone_brick', (120, 120, 120)), ('glass', (170, 200, 210)),
        ('andesite', (135, 135, 135)), ('smooth_stone', (160, 160, 160)), ('stone', (125, 125, 125)),
        ('spruce', (100, 75, 45)), ('oak', (160, 130, 80)), ('dark_oak', (65, 45, 25)),
        ('bed', (180, 40, 40)), ('barrel', (120, 90, 50)), ('lantern', (250, 200, 100)),
    ]
    for k, c in table:
        if k in b:
            return c
    return (150, 120, 150)


def preview(plan, path, scale=4):
    """Top view plus the four elevations, written as one PNG (needs matplotlib)."""
    import numpy as np
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    (x0, y0, z0), (x1, y1, z1) = plan.bounds()
    W, H, L = x1 - x0 + 1, y1 - y0 + 1, z1 - z0 + 1
    vox = {}
    for (x, y, z), s in plan.cells.items():
        c = colour(s)
        if c:
            vox[(x - x0, y - y0, z - z0)] = c

    def project(axes, depth_axis, rev, shape):
        img = np.ones(shape + (3,)) * 0.08
        dep = np.full(shape, -1e9)
        for p, c in vox.items():
            u, v = p[axes[0]], p[axes[1]]
            d = p[depth_axis] * (-1 if rev else 1)
            if d > dep[v, u]:
                dep[v, u] = d
                img[v, u] = np.array(c) / 255
        return img

    views = {
        'top (north up)': project((0, 2), 1, False, (L, W)),
        'east face (looking west)': project((2, 1), 0, False, (H, L))[::-1, ::-1],
        'south face (looking north)': project((0, 1), 2, False, (H, W))[::-1],
        'west face (looking east)': project((2, 1), 0, True, (H, L))[::-1],
        'north face (looking south)': project((0, 1), 2, True, (H, W))[::-1, ::-1],
    }
    fig, axs = plt.subplots(1, 5, figsize=(5 * 4, 6), dpi=110)
    for ax, (t, im) in zip(axs, views.items()):
        ax.imshow(im, interpolation='nearest')
        ax.set_title(t, fontsize=9)
        ax.set_xticks([]); ax.set_yticks([])
    fig.suptitle(f'{plan.name}: X{x0}..{x1} Y{y0}..{y1} Z{z0}..{z1}')
    plt.tight_layout()
    plt.savefig(path)
    plt.close(fig)


# --- region-file readback --------------------------------------------------
class World:
    """Read-only block access from the saved region files."""

    def __init__(self, region=REGION):
        self.region = Path(region)
        self.chunks = {}
        self.files = {}

    def _chunk(self, cx, cz):
        k = (cx, cz)
        if k in self.chunks:
            return self.chunks[k]
        rx, rz = cx >> 5, cz >> 5
        f = self.region / f'r.{rx}.{rz}.mca'
        if f not in self.files:
            self.files[f] = f.read_bytes() if f.exists() else b''
        data = self.files[f]
        secs = None
        if data:
            idx = (cx & 31) + (cz & 31) * 32
            off = struct.unpack_from('>I', data, idx * 4)[0]
            if off:
                sec = (off >> 8) * 4096
                ln = struct.unpack_from('>I', data, sec)[0]
                if data[sec + 4] == 2:
                    buf = zlib.decompress(data[sec + 5:sec + 4 + ln])
                    n = struct.unpack_from('>H', buf, 1)[0]
                    c = N._read(buf, 3 + n, buf[0])[0].value
                    secs = {}
                    for s in c['sections'].value[1]:
                        s = s.value
                        bs = s.get('block_states')
                        if not bs:
                            continue
                        pal = []
                        for p in bs.value['palette'].value[1]:
                            p = p.value
                            props = p.get('Properties')
                            st = p['Name'].value
                            if props:
                                st += '[' + ','.join(f'{k}={v.value}' for k, v in sorted(props.value.items())) + ']'
                            pal.append(st)
                        bits = max(4, math.ceil(math.log2(len(pal))))      # once per section, not once per block read
                        secs[s['Y'].value] = (pal, bs.value['data'].value if 'data' in bs.value else None,
                                              bits, 64 // bits)
        self.chunks[k] = secs
        return secs

    def block(self, x, y, z):
        secs = self._chunk(x >> 4, z >> 4)
        if secs is None:
            return None
        s = secs.get(y >> 4)
        if s is None:
            return 'minecraft:air'
        pal, longs, bits, per = s
        if longs is None:
            return pal[0]
        i = ((y & 15) * 256) + ((z & 15) * 16) + (x & 15)
        L = longs[i // per] & ((1 << 64) - 1)
        return pal[(L >> ((i % per) * bits)) & ((1 << bits) - 1)]

    def uniform_air(self, x, y, z, airs) -> bool:
        """True when the 16-block section holding (x, y, z) is absent or one block whose id (no properties) is in ``airs``.

        Lets a top-down column scan jump a whole empty section; block() would return the same answer 16 times.
        """
        secs = self._chunk(x >> 4, z >> 4)
        if secs is None:
            return True                                   # block() gives None here, which callers read as air
        s = secs.get(y >> 4)
        return s is None or (s[1] is None and s[0][0].split('[')[0] in airs)

    def light(self, x, y, z, kind='BlockLight'):
        """Stored light level (BlockLight or SkyLight) from the region file; None if absent."""
        key = ('L', kind, x >> 4, z >> 4)
        if key not in self.chunks:
            self._chunk(x >> 4, z >> 4)
            rx, rz = x >> 9, z >> 9
            data = self.files[self.region / f'r.{rx}.{rz}.mca']
            idx = ((x >> 4) & 31) + ((z >> 4) & 31) * 32
            off = struct.unpack_from('>I', data, idx * 4)[0]
            sec = (off >> 8) * 4096
            ln = struct.unpack_from('>I', data, sec)[0]
            buf = zlib.decompress(data[sec + 5:sec + 4 + ln])
            n = struct.unpack_from('>H', buf, 1)[0]
            c = N._read(buf, 3 + n, buf[0])[0].value
            self.chunks[key] = {s.value['Y'].value: s.value[kind].value
                                for s in c['sections'].value[1] if kind in s.value}
        arr = self.chunks[key].get(y >> 4)
        if arr is None:
            return None
        i = (y & 15) * 256 + (z & 15) * 16 + (x & 15)
        b = arr[i >> 1]
        return (b >> 4) & 15 if i & 1 else b & 15

    def ground(self, x, z, top=140, bottom=40):
        skip = ('air', 'water', 'leaves', '_log', 'short_grass', 'tall_grass', 'fern', 'flower', 'tulip', 'poppy',
                'dandelion', 'kelp', 'seagrass', 'bush', 'litter', 'vine', 'daisy', 'bluet', 'orchid',
                'allium', 'cornflower', 'lily', 'sugar_cane', 'mushroom')
        for y in range(top, bottom, -1):
            b = self.block(x, y, z)
            if b and not any(k in b for k in skip):
                return y
        return bottom


def same(planned, actual):
    """Compare id and the planned properties (unplanned properties may differ)."""
    if actual is None:
        return False
    p = full(planned)
    if bid(p) != actual.split('[')[0]:
        return False
    if '[' in p:
        want = dict(kv.split('=') for kv in p[p.index('[') + 1:-1].split(','))
        got = dict(kv.split('=') for kv in actual[actual.index('[') + 1:-1].split(',')) if '[' in actual else {}
        return all(got.get(k) == v for k, v in want.items() if k not in ('waterlogged',))
    return True


# --- live application ------------------------------------------------------
CELLS_CACHE = ROOT / 'backups/cells-cache'      # git-ignored; one pickle per *-cells.json, rebuilt when its mtime/size change


def _parse_cells_file(f: Path):
    """(adds {(x,y,z): (build, state)}, air [(x,y,z)]) for one cells file, via the on-disk cache when it is current."""
    import pickle
    st = f.stat()
    key = (st.st_mtime_ns, st.st_size)
    cache = CELLS_CACHE / (f.name + '.pkl')
    try:
        with cache.open('rb') as fh:
            got = pickle.load(fh)
        if got[0] == key:
            return got[1], got[2]
    except Exception:
        pass                                                   # missing, truncated or old: reparse
    name = f.name[:-len('-cells.json')]
    adds, air = {}, []
    for k, s in json.loads(f.read_text()).items():
        q = tuple(int(v) for v in k.split(','))
        if bid(s) in ('minecraft:air', 'minecraft:light'):
            air.append(q)
        else:
            adds[q] = (name, s)
    try:
        CELLS_CACHE.mkdir(parents=True, exist_ok=True)
        tmp = cache.with_name(f'{cache.name}.{id(adds)}.tmp')
        with tmp.open('wb') as fh:
            pickle.dump((key, adds, air), fh, protocol=pickle.HIGHEST_PROTOCOL)
        tmp.replace(cache)                                     # atomic: a concurrent reader never sees half a file
    except OSError:
        pass
    return adds, air


def built_cells(exclude=()):
    """Non-air cells placed by earlier builds (verification/town/*-cells.json)."""
    owned = {}
    for f in sorted(OUT.glob('*-cells.json'), key=lambda f: f.stat().st_mtime):  # later builds win
        name = f.name[:-len('-cells.json')]
        if name in exclude:
            continue
        adds, air = _parse_cells_file(f)
        owned.update(adds)                                     # keys are unique within a file, so update-then-pop
        for q in air:                                          # is the same as the old entry-by-entry loop
            owned.pop(q, None)
    return owned


def apply(plan, protect=None, dry=False, modifies=(), stage=None, cell=None, meta=None, strict=False):
    """protect: optional callable(pos, existing_state) -> bool; True = refuse to overwrite.
    Cells owned by earlier builds are always protected unless that build is in `modifies`.

    Stage state machine (site_stages): before the first live block write the cell's STAGES file
    gets ``stage`` (default 'feature-<plan>') as 'applying' with the plan, owner, structure backup,
    region snapshot and planned-cells file; after the readback it becomes 'applied' (or
    'applied-with-mismatches'). An abort leaves 'applying' for site_recover.py. ``cell`` defaults
    to the cell holding most of the plan; ``meta`` is merged into the entry (e.g. kind 'undo').
    ``strict``: a readback with mismatches raises and leaves the stage 'applying'."""
    from mc_paced import Paced, box, xyz
    OUT.mkdir(parents=True, exist_ok=True)
    lo, hi = plan.bounds()
    w = World()
    # lint: posts (fences, walls, bars) over half-height blocks float by half a block
    floats = []
    for (x, y, z), st in plan.cells.items():
        n = bid(st)[10:]
        if (n.endswith(('_fence', '_wall')) or n == 'iron_bars') and 'gate' not in n:
            below = plan.cells.get((x, y - 1, z)) or w.block(x, y - 1, z) or ''
            if ('_slab' in below and 'type=bottom' in below) or bid(below).endswith('_carpet'):
                floats.append((x, y, z))
    if floats and not getattr(plan, 'allow_float', False):
        raise SystemExit(f'{len(floats)} posts would float over half-height blocks, e.g. {floats[:5]}; '
                         'extend them down or put a full block under them (or set plan.allow_float)')
    # guard (I-009): building-like blocks standing >2 above Geocraft ground outside every OSM
    # footprint are almost always a façade built on the pavement / front garden
    import osm_footprints
    fp = osm_footprints.guard(plan.cells)
    if fp['outside'] or fp['blind']:
        (OUT / f'{plan.name}-footprint-hits.json').write_text(json.dumps(
            {'outside': {str(q): v for q, v in fp['outside'].items()},
             'blind': [list(q) for q in fp['blind']]}, indent=1))
        why = getattr(plan, 'outside_footprint_ok', None)
        if not why:
            raise SystemExit(
                f'{len(fp["outside"])} building-like cells stand outside OSM footprints and '
                f'{len(fp["blind"])} have no OSM clip; see {plan.name}-footprint-hits.json. House fronts '
                'go on the OSM footprint line (scripts/osm_footprints.py frontage), not at the kerb. '
                'Missing clip: osm_extract.py --layers buildings,highways. Genuinely unmapped structure '
                '(evidence in hand): set plan.outside_footprint_ok = "<reason + evidence id>".')
        print(f'footprint guard overridden ({len(fp["outside"]) + len(fp["blind"])} cells): {why}')
    # guard (I-034): a ridge that shifts sideways between rows zig-zags every stair on the seam
    import roof_lint
    jogs = roof_lint.ridge_jogs(plan.cells)
    if jogs:
        (OUT / f'{plan.name}-roof-jogs.json').write_text(json.dumps(jogs, indent=1))
        why = getattr(plan, 'roof_jog_ok', None)
        if not why:
            raise SystemExit(
                f'{len(jogs)} roof ridge(s) jog sideways between rows; see {plan.name}-roof-jogs.json. '
                'Keep each roof on one straight ridge line (square the footprint, do not step it '
                'with the OSM rotation). Real offset roofs (evidence in hand): set '
                'plan.roof_jog_ok = "<reason + evidence id>".')
        print(f'roof jog guard overridden ({len(jogs)} seams): {why}')
    owned = built_cells(exclude=set(modifies) | {plan.name})
    clash = {str(q): [owned[q][0], owned[q][1], st] for q, st in plan.cells.items()
             if q in owned and owned[q][1] != st}
    if clash:
        (OUT / f'{plan.name}-clashes.json').write_text(json.dumps(clash, indent=1))
        raise SystemExit(f'{len(clash)} cells belong to earlier builds; see {plan.name}-clashes.json')
    if protect:
        hits = {str(p): w.block(*p) for p in plan.cells if protect(p, w.block(*p))}
        if hits:
            (OUT / f'{plan.name}-protect-hits.json').write_text(json.dumps(hits, indent=1))
            raise SystemExit(f'{len(hits)} protected cells would change; see {plan.name}-protect-hits.json')
    boxes = plan.boxes()
    print(f'{plan.name}: {len(plan.cells)} cells in {len(boxes)} boxes; bounds {lo}..{hi}; no clashes')
    if dry:
        return
    import site_lock
    site_lock.check()                       # single-builder rule: refuse without the world lock
    m = Paced()
    rec = OUT / f'{plan.name}-backup.json'
    if not rec.exists():
        name = f'{STRUCTURE_NS}:before_{plan.name}'
        a = [lo[0] - 1, lo[1], lo[2] - 1]
        b = [hi[0] + 1, hi[1], hi[2] + 1]
        res = m.text('structure_save_from_world', {'name': name, 'dimension': D, 'box': box(a, b)})
        if 'saved' not in res:
            raise SystemExit('Backup failed: ' + res)
        rec.write_text(json.dumps({'structure': name, 'from': a, 'to': b, 'result': res,
                                   'time': time.strftime('%Y-%m-%d %H:%M:%S')}, indent=2))
        print('backup:', res)
        structure = {'name': name, 'from': a, 'to': b}
    else:
        # the first-time backup above is the original Geocraft; recovery needs the state before THIS apply
        name = f'{STRUCTURE_NS}:before_{plan.name}_{time.strftime("%Y%m%d%H%M%S")}'
        a = [lo[0] - 1, lo[1], lo[2] - 1]
        b = [hi[0] + 1, hi[1], hi[2] + 1]
        res = m.text('structure_save_from_world', {'name': name, 'dimension': D, 'box': box(a, b)})
        if 'saved' not in res:
            raise SystemExit('Backup failed: ' + res)
        structure = {'name': name, 'from': a, 'to': b}
    import site_stages
    key = stage or f'feature-{plan.name}'
    cell = tuple(cell) if cell else site_stages.primary_cell(plan.cells)
    planned = OUT / f'{plan.name}-planned.json'
    planned.write_text(json.dumps({f'{x},{y},{z}': st for (x, y, z), st in plan.cells.items()}))
    site_stages.begin(cell, key, plan.name, blocks=len(plan.cells), structure=structure,
                      snapshot=site_stages.latest_snapshot(plan.name), planned=str(planned.relative_to(ROOT) if planned.is_relative_to(ROOT) else planned),
                      **(meta or {}))
    # fills into unloaded chunks silently do nothing: if the player is far from the build,
    # hop them (spectator) over it while filling, then put them back exactly
    restore = _bring_player(m, lo, hi)
    results = []
    for i in range(0, len(boxes), 8000):
        chunk = boxes[i:i + 8000]
        res = m.text('block_fill_batch', {'dimension': D, 'fills': [
            {'from': list(a), 'to': list(b), 'block': s} for a, b, s in chunk]})
        results.append(res)
        print('fill:', res.replace('\n', '; ')[:300])
    for pos, lines, col, glow in plan.signs:
        nbt = ('{is_waxed:1b,front_text:{messages:[' + ','.join(json.dumps(t) for t in lines) +
               f'],color:"{col}",has_glowing_text:{1 if glow else 0}b}},back_text:{{messages:[' +
               ','.join(json.dumps(t) for t in lines) + f'],color:"{col}",has_glowing_text:{1 if glow else 0}b}}}}')
        m.call('block_entity_set_nbt', {'dimension': D, 'position': xyz(pos), 'nbt': nbt})
    ents = []
    for kind, pos, snbt in plan.entities:
        args = {'dimension': D, 'entity_type': kind, 'position': xyz(pos)}
        if snbt:
            args['nbt'] = snbt
        ents.append(m.text('entity_summon', args))
    (OUT / f'{plan.name}-cells.json').write_text(json.dumps(
        {f'{x},{y},{z}': st for (x, y, z), st in plan.cells.items()}))
    if restore:
        restore()
    m.call('server_save_all_worlds', {})
    time.sleep(3)
    rep = readback(plan)
    rep.update({'fill_results': results, 'entities': ents})
    (OUT / f'{plan.name}-result.json').write_text(json.dumps(rep, indent=1))
    print(json.dumps({k: v for k, v in rep.items() if k != 'mismatch_sample'}, indent=1)[:1500])
    if rep['mismatches'] and strict:
        raise SystemExit(f'{plan.name}: readback has {rep["mismatches"]} mismatches; stage {key} left '
                         "'applying' (python scripts/site_recover.py status)")
    site_stages.finish(cell, key, 'applied' if not rep['mismatches'] else 'applied-with-mismatches',
                       readback={k: v for k, v in rep.items() if k in ('planned', 'mismatches', 'checked')})
    return rep


def _bring_player(m, lo, hi, reach=80):
    """If the player is more than `reach` blocks (XZ) from the build's centre, teleport them in
    spectator mode above it and wait for chunks; return a function that restores them."""
    import math, re
    from mc_paced import UUID, xyz
    info = m.text('player_get_info', {'uuid': UUID})
    num = lambda k: float(re.search(rf'{k}: (-?[\d.]+)', info).group(1))
    px, py, pz = num('x'), num('y'), num('z')
    yaw, pitch = num('yaw'), num('pitch')
    mode = re.search(r'gameMode: (\w+)', info).group(1)
    cx, cz = (lo[0] + hi[0]) / 2, (lo[2] + hi[2]) / 2
    if math.hypot(px - cx, pz - cz) <= reach:
        return None
    m.call('player_set_gamemode', {'uuid': UUID, 'gamemode': 'spectator'})
    m.call('entity_teleport', {'uuid': UUID, 'dimension': D, 'position': xyz([cx, hi[1] + 20, cz])})
    time.sleep(6)
    print(f'  (moved player to {cx:.0f},{cz:.0f} to load chunks)')

    def restore():
        # user (10 Oct 2026): no need to put them back where they were - leave them at the
        # build, just give back their game mode
        m.call('player_set_gamemode', {'uuid': UUID, 'gamemode': mode})
    return restore


def readback(plan, world=None):
    w = world or World()
    bad = {}
    for p, s in plan.cells.items():
        a = w.block(*p)
        if not same(s, a):
            bad[str(p)] = [s, a]
    return {'planned': len(plan.cells), 'mismatches': len(bad),
            'mismatch_sample': dict(list(bad.items())[:60]),
            'checked': time.strftime('%Y-%m-%d %H:%M:%S')}
