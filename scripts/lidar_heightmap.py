#!/usr/bin/env python3
"""Lidar height map of the pristine Geocraft save, and the lump report built from it.

Geocraft is made from lidar: every column is a height. This reads the UNTOUCHED save (config/world.json
pristine_region_path), never the live world, so it is the same before and after any build or reset.

Per column (cell = 128 x 128, arrays indexed [x - x0, z - z0]):
  h      top of the lidar surface: carpet is ignored (it sits ON the lidar), leaves and logs count, because
         where there is no building Geocraft draws a tree as log + leaf. Grass tufts and flowers are ignored.
  base   top of the solid ground under any carpet / leaves / logs (ground or wall top, no vegetation)
  roof   y of the Geocraft roof carpet over the column, 0 if none
  kind   0 ground / paving, 1 roof (building lump), 2 tree, 3 tree overhanging a roof

The lump report groups roof columns into buildings and gives what a feature build needs and used to
guess: footprint, ground, eave and ridge height (so storeys), flat or pitched, ridge axis, trees over
the roof, and the OSM buildings under it (none = unmapped).

  python3 scripts/lidar_heightmap.py --cell 51,-41            # report
  python3 scripts/lidar_heightmap.py --cell 51,-41 --json     # machine-readable
  python3 scripts/lidar_heightmap.py --cell 51,-41 --write    # also keep verification/site/lidar/51_-41.npz

Lookups that may straddle a cell edge (B42 at z -5505):

  maps = Maps()                     # pristine by default; Maps(World()) for live
  maps.top_at(x, z)                 # roof carpet y if Geocraft had a roof, else surface h
  top_at(x, z)                      # same, with a module-level Maps cache
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import statistics
import sys

import numpy as np

import cellmath
from script_env import ROOT  # noqa: E402

TOP = 140
MIN_COLUMNS = 12                    # ignore slivers (bin stores, small sheds)
MIN_CORE = 6                        # columns left after eroding a lump 3 times (~7+ blocks wide) before its interior may judge flat vs pitched
STOREY = 3                          # blocks per storey
RIDGE_BASE = 3                      # ridge height above ground minus this, / STOREY = storeys. Calibrated 2026-10-16 against
                                    # OSM building:levels of 54 single-building lumps in the touched cells: 57% exact, 89%
                                    # within one level (eave height is useless: ~4 above ground whatever the levels)
GROUND, ROOF, TREE, TREE_OVER_ROOF = 0, 1, 2, 3
OUT = ROOT / 'verification/site/lidar'
_AIRS = ('minecraft:air', 'minecraft:cave_air', 'minecraft:void_air', 'minecraft:light')
_TREE = ('leaves', '_log', '_wood')
_PLANT = ('short_grass', 'tall_grass', 'fern', 'flower', 'tulip', 'poppy', 'dandelion', 'bush', 'vine', 'daisy',
          'bluet', 'orchid', 'allium', 'cornflower', 'lily', 'sugar_cane', 'mushroom', 'azure', 'peony', 'rose',
          'lilac', 'sunflower', 'dead_bush', 'petals', 'seagrass', 'kelp', '_sign')


def _id(b) -> str:
    return (b or 'minecraft:air').split('[')[0]


def column(world, x: int, z: int, top: int = TOP) -> tuple[int, int, int, int]:
    """Scan one column top-down.

    @param world: object with block(x, y, z) (and optionally uniform_air)
    @returns: (h, base, roof, kind); zeros when the column is empty
    """
    skip = getattr(world, 'uniform_air', None)
    h = base = roof = 0
    tree = False
    y = top
    while y > 0:
        if skip is not None and skip(x, y, z, _AIRS):
            y = ((y >> 4) << 4) - 1
            continue
        b = _id(world.block(x, y, z))
        if b in _AIRS or any(k in b for k in _PLANT):
            pass
        elif b.endswith('_carpet'):
            roof = roof or y
        elif any(k in b for k in _TREE):
            h = h or y
            tree = True
        else:
            h = h or y
            base = y
            break
        y -= 1
    kind = TREE_OVER_ROOF if (tree and roof) else ROOF if roof else TREE if tree else GROUND
    return h, base, roof, kind


def heightmap(world, cell: tuple[int, int]) -> dict:
    """Height map of one cell.

    @param world: World over the pristine save
    @param cell: (tx, tz)
    @returns: {'cell', 'x0', 'z0', 'h', 'base', 'roof', 'kind'} with 128x128 int16 / uint8 arrays
    """
    x0, z0, _x1, _z1 = cellmath.bounds(cell)
    n = cellmath.CELL
    arr = {k: np.zeros((n, n), dtype=np.int16) for k in ('h', 'base', 'roof')}
    arr['kind'] = np.zeros((n, n), dtype=np.uint8)
    for i in range(n):
        for j in range(n):
            arr['h'][i, j], arr['base'][i, j], arr['roof'][i, j], arr['kind'][i, j] = column(world, x0 + i, z0 + j)
    return {'cell': cell, 'x0': x0, 'z0': z0, **arr}


def save(hm: dict) -> 'Path':
    """Write the height map to verification/site/lidar/<tx>_<tz>.npz (regenerable, git-ignored)."""
    OUT.mkdir(parents=True, exist_ok=True)
    p = OUT / f'{hm["cell"][0]}_{hm["cell"][1]}.npz'
    np.savez_compressed(p, x0=hm['x0'], z0=hm['z0'], h=hm['h'], base=hm['base'], roof=hm['roof'], kind=hm['kind'])
    return p


def load(cell: tuple[int, int]) -> dict | None:
    """Height map from verification/site/lidar/<tx>_<tz>.npz, or None if missing."""
    p = OUT / f'{cell[0]}_{cell[1]}.npz'
    if not p.is_file():
        return None
    data = np.load(p)
    return {'cell': cell, 'x0': int(data['x0']), 'z0': int(data['z0']),
            'h': data['h'], 'base': data['base'], 'roof': data['roof'], 'kind': data['kind']}


def top_of(hm: dict, x: int, z: int) -> int:
    """Lidar top Y of one column inside ``hm``: roof carpet where present, else surface h.

    Same rule as lidar_audit.target: Geocraft paints a roof carpet on building tops.
    """
    i, j = x - hm['x0'], z - hm['z0']
    r = int(hm['roof'][i, j])
    return r if r else int(hm['h'][i, j])


class Maps:
    """Cached height maps keyed by cell, for lookups that may straddle cell edges.

    @param world: object with block(x,y,z); defaults to the pristine Geocraft save
    @param use_cache: load from verification/site/lidar/*.npz when present (pristine only)
    """

    def __init__(self, world=None, use_cache: bool = True):
        self.world = world
        self.use_cache = use_cache
        self._hm: dict[tuple[int, int], dict] = {}

    def of(self, cell: tuple[int, int]) -> dict:
        """Height map of one cell, loaded once per Maps instance."""
        if cell not in self._hm:
            if self.use_cache and self.world is None:
                got = load(cell)
                if got is not None:
                    self._hm[cell] = got
                    return got
            w = self.world if self.world is not None else pristine_world()
            self._hm[cell] = heightmap(w, cell)
        return self._hm[cell]

    def top_at(self, x: int, z: int) -> int:
        """Lidar top Y at (x, z): roof carpet if Geocraft had a roof, else surface h.

        Loads the cell containing the column (works across cell edges).
        """
        return top_of(self.of(cellmath.cell_of(x, z)), x, z)

    def get(self, x: int, z: int, field: str = 'h') -> int:
        """One array value at (x, z): field is 'h', 'base', 'roof' or 'kind'."""
        hm = self.of(cellmath.cell_of(x, z))
        return int(hm[field][x - hm['x0'], z - hm['z0']])


_DEFAULT_MAPS: Maps | None = None


def top_at(x: int, z: int, maps: Maps | None = None) -> int:
    """Lidar top Y at (x, z) across cell edges (module-level Maps cache of the pristine save).

    @param x: block X
    @param z: block Z
    @param maps: optional Maps instance (live world, tests); default is a shared pristine Maps
    """
    global _DEFAULT_MAPS
    if maps is not None:
        return maps.top_at(x, z)
    if _DEFAULT_MAPS is None:
        _DEFAULT_MAPS = Maps()
    return _DEFAULT_MAPS.top_at(x, z)


def _group(cols: set) -> list:
    left, out = set(cols), []
    while left:
        seed = min(left)
        comp, todo = {seed}, [seed]
        left.discard(seed)
        while todo:
            x, z = todo.pop()
            for dx, dz in cellmath.N8:
                q = (x + dx, z + dz)
                if q in left:
                    left.discard(q)
                    comp.add(q)
                    todo.append(q)
        out.append(comp)
    return sorted(out, key=lambda c: (-len(c), min(c)))


def _erode(cols: set) -> set:
    """Columns whose 8 neighbours are all in cols (one ring of the rim removed)."""
    return {(x, z) for x, z in cols if all((x + dx, z + dz) in cols for dx, dz in cellmath.N8)}


def _ground(hm: dict, comp: set, reach: int = 3) -> int | None:
    """Median ground top of the non-building columns ringing a lump (inside this cell)."""
    x0, z0 = hm['x0'], hm['z0']
    n = cellmath.CELL
    ring = {(x + dx, z + dz) for x, z in comp for dx in range(-reach, reach + 1)
            for dz in range(-reach, reach + 1)} - comp
    ys = [int(hm['base'][x - x0, z - z0]) for x, z in sorted(ring)
          if 0 <= x - x0 < n and 0 <= z - z0 < n and hm['kind'][x - x0, z - z0] == GROUND and hm['base'][x - x0, z - z0]]
    return int(statistics.median(ys)) if ys else None


def lumps(hm: dict, min_columns: int = MIN_COLUMNS) -> list:
    """Buildings in the height map (connected roof columns), largest first.

    Each item: bbox, centre, columns, ground_y, eave_y (10th percentile of roof y; of the interior columns for a wide lump, see MIN_CORE, because
    lidar blurs the rim low), ridge_y, height (ridge - ground), storeys (estimate: (ridge - ground - RIDGE_BASE)
    / STOREY, at least 1; osm_levels is added by report() when OSM has building:levels), roof ('flat' | 'pitched'), ridge_axis ('x' | 'z' | None), trees_over (columns) and
    cols (the column set, for OSM matching).
    """
    x0, z0 = hm['x0'], hm['z0']
    n = cellmath.CELL
    roofs = {(x0 + i, z0 + j) for i, j in zip(*np.nonzero(hm['roof'])) if hm['roof'][i, j] and i < n and j < n}
    out = []
    for comp in _group(roofs):
        if len(comp) < min_columns:
            continue
        ry = {c: int(hm['roof'][c[0] - x0, c[1] - z0]) for c in comp}
        vals = sorted(ry.values())
        lo, hi = vals[len(vals) // 10], vals[-1]      # eave = 10th percentile: ignores low annex / dormer slivers
        # Lidar blurs the building edge: the rim columns read 3-6 blocks low whatever the roof, so hi - lo over the whole
        # footprint says "pitched" for nearly every building (Oakdene Court, a flat 4-level block, included). A wide enough
        # building is judged on its interior (rim eroded away). A narrow one is not: its interior is just the ridge strip
        # and would read flat, so it keeps the whole-footprint test.
        inner = _erode(set(comp))
        if len(_erode(_erode(inner))) >= MIN_CORE:
            lo = sorted(ry[c] for c in inner)[len(inner) // 10]
            pitched = max(ry[c] for c in inner) - lo >= 2
        else:
            pitched = hi - lo >= 2
        g = _ground(hm, comp)
        xs = [x for x, _ in comp]
        zs = [z for _, z in comp]
        ridge = [c for c, y in ry.items() if y == hi]
        rx = max(x for x, _ in ridge) - min(x for x, _ in ridge)
        rz = max(z for _, z in ridge) - min(z for _, z in ridge)
        out.append({
            'bbox': [min(xs), min(zs), max(xs), max(zs)],
            'centre': [(min(xs) + max(xs)) // 2, (min(zs) + max(zs)) // 2],
            'columns': len(comp), 'ground_y': g, 'eave_y': lo, 'ridge_y': hi,
            'height': hi - g if g is not None else None,
            'storeys': max(1, round((hi - g - RIDGE_BASE) / STOREY)) if g is not None else None,
            'roof': 'pitched' if pitched else 'flat',
            'ridge_axis': ('x' if rx >= rz else 'z') if pitched and len(ridge) > 1 else None,
            'trees_over': sum(1 for c in comp if hm['kind'][c[0] - x0, c[1] - z0] == TREE_OVER_ROOF),
            'cols': comp})
    return out


def report(hm: dict, with_osm: bool = True) -> list:
    """lumps() plus the OSM buildings under each (``osm`` empty = not mapped)."""
    items = lumps(hm)
    if with_osm:
        import lump_scan
        from osm_footprints import OSMIndex
        idx = OSMIndex()
        levels = osm_levels(idx)
        for lp in items:
            lp['osm'] = lump_scan.osm_under(lp, idx)
            lv = {levels[r] for r in lp['osm'] if r in levels}
            lp['osm_levels'] = sorted(lv)
    return items


def pristine_path() -> Path:
    """Region folder of the untouched Geocraft save; stops with a clear message when it is missing or empty.

    config/world.json pristine_region_path is outside the repo; a read-only clone is kept in
    backups/pristine-geocraft/region (set pristine_region_path to it if the original moves).
    """
    p = Path(json.loads((ROOT / 'config/world.json').read_text())['pristine_region_path'])
    if not p.is_dir() or not any(p.glob('r.*.mca')):
        raise SystemExit(f'pristine Geocraft save not found at {p}\n'
                         f'  a clone lives in {ROOT / "backups/pristine-geocraft/region"}: point '
                         'config/world.json pristine_region_path there')
    return p


def pristine_world():
    """World over the untouched Geocraft save."""
    from site_kit import World
    return World(pristine_path())


def osm_levels(idx) -> dict:
    """{osm ref: building:levels as int} for OSM buildings that carry the tag."""
    import re
    from coverage import osm_ref
    out = {}
    for _rings, p in idx.buildings:
        m = re.search(r'"building:levels"=>"(\d+)', p.get('other_tags') or '')
        if m:
            out[osm_ref(p)] = int(m.group(1))
    return out


def format_report(cell, items: list) -> str:
    """Plain-text table of the lump report."""
    lines = [f'LIDAR LUMPS cell {cell[0]},{cell[1]}: {len(items)} building(s)',
             'bbox                       cols ground eave ridge st roof     axis trees lvl osm']
    for lp in items:
        osm = ','.join(lp.get('osm', [])[:3]) or ('UNMAPPED' if 'osm' in lp else '-')
        b = lp['bbox']
        lines.append(f'{b[0]},{b[1]}..{b[2]},{b[3]}'.ljust(27)
                     + f'{lp["columns"]:>4} {str(lp["ground_y"]):>6} {lp["eave_y"]:>4} {lp["ridge_y"]:>5} '
                     f'{str(lp["storeys"]):>2} {lp["roof"]:<8} {str(lp["ridge_axis"] or "-"):<4} {lp["trees_over"]:>5} '
                     f'{",".join(map(str, lp.get("osm_levels", []))) or "-":>3} {osm}')
    return '\n'.join(lines)


def touched_cells() -> list:
    """Cells that have a site/cells/<tx>_<tz>-STAGES.json file."""
    import re
    out = []
    for f in sorted((ROOT / 'site/cells').glob('*-STAGES.json')):
        m = re.match(r'(-?\d+)_(-?\d+)-STAGES', f.name)
        out.append((int(m[1]), int(m[2])))
    return out


def write_tables() -> int:
    """Write the lump table of every touched cell next to its STAGES file (regenerable; commit them)."""
    world = pristine_world()
    for cell in touched_cells():
        text = format_report(cell, report(heightmap(world, cell))) + '\n'
        (ROOT / f'site/cells/{cell[0]}_{cell[1]}-LIDAR.txt').write_text(text)
        print(f'{cell[0]},{cell[1]}: {text.splitlines()[0]}')
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--cell', help='tx,tz')
    ap.add_argument('--tables', action='store_true', help='write site/cells/<tx>_<tz>-LIDAR.txt for every cell with a STAGES file')
    ap.add_argument('--json', action='store_true', help='print JSON instead of a table')
    ap.add_argument('--write', action='store_true', help='keep the height map as .npz')
    ap.add_argument('--no-osm', action='store_true', help='skip the OSM match (faster)')
    a = ap.parse_args(argv)
    if a.tables:
        return write_tables()
    if not a.cell:
        ap.error('--cell or --tables is required')
    cell = cellmath.parse_cell(a.cell)
    hm = heightmap(pristine_world(), cell)
    if a.write:
        print(f'wrote {save(hm)}', file=sys.stderr)
    items = report(hm, with_osm=not a.no_osm)
    if a.json:
        print(json.dumps([{k: v for k, v in lp.items() if k != 'cols'} for lp in items], indent=1))
    else:
        print(format_report(cell, items))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
