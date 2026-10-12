#!/usr/bin/env python3
"""Geocraft coordinate hub: convert, probe, slope, views, survey bboxes, party pitch, tiles.

  python3 scripts/geo.py convert --mc 5652,-2492
  python3 scripts/geo.py convert --wgs84 50.903,-1.4044
  python3 scripts/geo.py convert --osgb 441900,112100 --json
  python3 scripts/geo.py slope --bearing 22
  python3 scripts/geo.py slope --points 7097,-5521,7110,-5550
  python3 scripts/geo.py slope --pitch 40
  python3 scripts/geo.py probe 7097,-5521
  python3 scripts/geo.py probe --bbox 7080,-5560,7120,-5500
  python3 scripts/geo.py view --at 7097,35,-5521 --heading 22
  python3 scripts/geo.py survey --at 7097,-5521 --preset terrace
  python3 scripts/geo.py party --bbox 7040,-5560,7140,-5500 --street "Broadlands Road"
  python3 scripts/geo.py place --name "Broadlands 20-22" --mc 7097,-5521
  python3 scripts/geo.py tiles --bbox 7040,-5560,7140,-5500 --zoom 18 --mosaic 3

Requires gdaltransform on PATH for WGS84 paths. MC ↔ OSGB uses config/map-maker-offsets.json.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'scripts'))

from geodetic import osgb_to_wgs84, wgs84_to_osgb  # noqa: E402
from osgb import in_bounds, load_offsets, to_mc, to_osgb  # noqa: E402
from ref_manifest import deg2num, mc_tiles_for_bbox, num2deg, wm_tile_bbox_mc  # noqa: E402
from terrace import snap_slope  # noqa: E402

SKIP_LIDAR_TOP = ('air', 'leaves', '_log', 'vine', 'short_grass', 'tall_grass', 'fern', 'flower')

SURVEY_PRESETS = {
    'house': {'pad_w': 28, 'pad_e': 28, 'pad_n': 35, 'pad_s': 55, 'radius_m': 120, 'region_margin': 1},
    'terrace': {'pad_w': 45, 'pad_e': 45, 'pad_n': 50, 'pad_s': 90, 'radius_m': 250, 'region_margin': 2},
    'campus': {'pad_w': 90, 'pad_e': 90, 'pad_n': 90, 'pad_s': 90, 'radius_m': 400, 'region_margin': 2},
}

def parse_xz(spec: str) -> tuple[int, int]:
    """Parse ``x,z`` Minecraft coordinates.

    @param spec: comma-separated integers
    @returns: (x, z)
    """
    parts = [p.strip() for p in spec.split(',')]
    if len(parts) != 2:
        raise SystemExit(f'expected x,z got {spec!r}')
    return int(parts[0]), int(parts[1])


def parse_bbox(spec: str) -> tuple[int, int, int, int]:
    """Parse inclusive MC bbox ``x0,z0,x1,z1``.

    @param spec: comma-separated four integers
    @returns: (x0, z0, x1, z1) normalized so min ≤ max
    """
    parts = [p.strip() for p in spec.split(',')]
    if len(parts) != 4:
        raise SystemExit(f'expected x0,z0,x1,z1 got {spec!r}')
    x0, z0, x1, z1 = map(int, parts)
    if x0 > x1:
        x0, x1 = x1, x0
    if z0 > z1:
        z0, z1 = z1, z0
    return x0, z0, x1, z1


def coord_triple_from_mc(x: int, z: int) -> dict:
    """Build OSGB + WGS84 + MC fields for one column.

    @param x: Minecraft X
    @param z: Minecraft Z
    @returns: dict with easting, northing, lat, lon, mc, in_bounds
    """
    e, n = to_osgb(x, z)
    lat, lon = osgb_to_wgs84(e, n)
    return {
        'mc': {'x': x, 'z': z},
        'osgb': {'easting': round(e, 2), 'northing': round(n, 2)},
        'wgs84': {'lat': round(lat, 6), 'lon': round(lon, 6)},
        'in_bounds': in_bounds(x, z),
    }


def coord_triple_from_osgb(e: float, n: float) -> dict:
    """Build full coord record from OSGB easting/northing.

    @param e: easting
    @param n: northing
    @returns: dict with mc, osgb, wgs84, in_bounds
    """
    x, z = to_mc(e, n)
    lat, lon = osgb_to_wgs84(e, n)
    return {
        'mc': {'x': x, 'z': z},
        'osgb': {'easting': round(e, 2), 'northing': round(n, 2)},
        'wgs84': {'lat': round(lat, 6), 'lon': round(lon, 6)},
        'in_bounds': in_bounds(x, z),
    }


def coord_triple_from_wgs84(lat: float, lon: float) -> dict:
    """Build full coord record from WGS84.

    @param lat: latitude
    @param lon: longitude
    @returns: dict with mc, osgb, wgs84, in_bounds
    """
    e, n = wgs84_to_osgb(lat, lon)
    x, z = to_mc(e, n)
    return {
        'mc': {'x': x, 'z': z},
        'osgb': {'easting': round(e, 2), 'northing': round(n, 2)},
        'wgs84': {'lat': round(lat, 6), 'lon': round(lon, 6)},
        'in_bounds': in_bounds(x, z),
    }


def slope_from_bearing(deg: float) -> dict:
    """Map a compass bearing (0=north, clockwise) to a block stair slope.

    @param deg: bearing in degrees
    @returns: slope tuple, approximate angle, and terrace plot_slope hint
    """
    rad = math.radians(deg)
    dx = math.sin(rad)
    dz = -math.cos(rad)
    sx, sz = snap_slope(dx, dz)
    ang = math.degrees(math.atan2(sx, sz))
    return {
        'bearing_deg': deg,
        'slope': {'dx': sx, 'dz': sz},
        'angle_deg': round(ang, 1),
        'terrace_hint': f'plot_slope=({sx}, {sz})',
    }


def slope_from_points(x0: int, z0: int, x1: int, z1: int) -> dict:
    """Block slope from rear toward front (first point → second).

    @param x0: start X
    @param z0: start Z
    @param x1: end X
    @param z1: end Z
    @returns: slope dict like slope_from_bearing
    """
    dx, dz = x1 - x0, z1 - z0
    sx, sz = snap_slope(float(dx), float(dz))
    ang = math.degrees(math.atan2(sx, sz))
    bearing = (math.degrees(math.atan2(dx, -dz)) + 360) % 360
    return {
        'from_mc': [x0, z0],
        'to_mc': [x1, z1],
        'raw_delta': {'dx': dx, 'dz': dz},
        'slope': {'dx': sx, 'dz': sz},
        'angle_deg': round(ang, 1),
        'bearing_deg': round(bearing, 1),
        'terrace_hint': f'plot_slope=({sx}, {sz})',
    }


def pitch_deg_to_slope(deg: float) -> dict:
    """Nearest Minecraft-friendly roof/plot slope for a real-world angle.

    @param deg: pitch angle in degrees (0 = flat along Z, 45 = 1:1 block stair)
    @returns: best (dx,dz), angle error, stair vs slab hint
    """
    rad = math.radians(deg)
    dx = math.sin(rad)
    dz = math.cos(rad)
    sx, sz = snap_slope(dx, dz)
    got = math.degrees(math.atan2(abs(sx), abs(sz) if sz else 1e9))
    hint = 'deepslate_tile_stairs (~45°)' if abs(got - 45) < 8 else 'slab courses (shallow)'
    return {
        'pitch_deg': deg,
        'slope': {'dx': sx, 'dz': sz},
        'mc_angle_deg': round(got, 1),
        'delta_deg': round(abs(got - deg), 1),
        'craft_hint': hint,
    }


def lidar_top(world, x: int, z: int, ymax: int = 120, ymin: int = 30) -> int:
    """Top solid block Y on pristine Geocraft, skipping vegetation/air.

    @param world: site_kit.World
    @param x: column X
    @param z: column Z
    @param ymax: start scan Y
    @param ymin: stop Y
    @returns: top Y of mass
    """
    y = ymax
    while y > ymin:
        b = world.block(x, y, z) or 'minecraft:air'
        if not any(s in b for s in SKIP_LIDAR_TOP):
            return y
        y -= 1
    return y


def probe_column(world, x: int, z: int, stack: int = 6) -> dict:
    """Ground and lidar top for one column.

    @param world: site_kit.World
    @param x: X
    @param z: Z
    @param stack: lines above ground to include
    @returns: probe record
    """
    yg = world.ground(x, z, top=200, bottom=0)
    yt = lidar_top(world, x, z)
    blocks = [world.block(x, yg + k, z) for k in range(stack + 1)]
    return {
        'mc': {'x': x, 'z': z},
        'ground_y': yg,
        'lidar_top_y': yt,
        'extrusion': yt - yg,
        'stack': blocks,
    }


def probe_bbox(world, x0: int, z0: int, x1: int, z1: int) -> dict:
    """Summarise ground and lidar tops over an inclusive bbox.

    @param world: site_kit.World
    @param x0: min X
    @param z0: min Z
    @param x1: max X
    @param z1: max Z
    @returns: min/median/max stats
    """
    grounds, tops, extr = [], [], []
    for x in range(x0, x1 + 1):
        for z in range(z0, z1 + 1):
            yg = world.ground(x, z, top=200, bottom=0)
            yt = lidar_top(world, x, z)
            grounds.append(yg)
            tops.append(yt)
            extr.append(yt - yg)
    def _med(v):
        s = sorted(v)
        return s[len(s) // 2]

    return {
        'bbox_mc': [x0, z0, x1, z1],
        'columns': len(grounds),
        'ground_y': {'min': min(grounds), 'median': _med(grounds), 'max': max(grounds)},
        'lidar_top_y': {'min': min(tops), 'median': _med(tops), 'max': max(tops)},
        'extrusion': {'min': min(extr), 'median': _med(extr), 'max': max(extr)},
    }


def view_from_heading(x: float, y: float, z: float, heading: float, distance: float = 25.0) -> dict:
    """Eye position and look-at from KartaView-style heading (0=north, clockwise).

    @param x: eye X
    @param y: eye Y
    @param z: eye Z
    @param heading: degrees
    @param distance: horizontal look distance in blocks
    @returns: pos/look lists for site_handoff --view
    """
    rad = math.radians(heading)
    lx = x + math.sin(rad) * distance
    lz = z - math.cos(rad) * distance
    return {
        'pos': [round(x, 2), round(y, 2), round(z, 2)],
        'look': [round(lx, 2), round(y, 2), round(lz, 2)],
        'handoff_view': f'{round(x)},{round(y)},{round(z)},{round(lx)},{round(y)},{round(lz)}',
        'heading_deg': heading,
    }


def door_facing_toward(dx: float, dz: float) -> str:
    """Minecraft door facing name for a horizontal direction toward the street.

    @param dx: delta X toward street
    @param dz: delta Z toward street
    @returns: south|north|east|west
    """
    if abs(dx) >= abs(dz):
        return 'east' if dx > 0 else 'west'
    return 'south' if dz > 0 else 'north'


def survey_bbox(x: int, z: int, preset: str) -> dict:
    """Suggested MC bbox and companion commands for a survey centre.

    @param x: centre X
    @param z: centre Z
    @param preset: house|terrace|campus key
    @returns: bbox, radii, shell command strings
    """
    p = SURVEY_PRESETS[preset]
    x0, x1 = x - p['pad_w'], x + p['pad_e']
    z0, z1 = z - p['pad_s'], z + p['pad_n']
    bbox = f'{x0},{z0},{x1},{z1}'
    return {
        'centre_mc': [x, z],
        'preset': preset,
        'bbox_mc': bbox,
        'commands': {
            'osm_extract': (
                f'python3 scripts/osm_extract.py --at {x},{z} --radius-m {p["radius_m"]} '
                f'--place SURVEY --dir osm/survey'
            ),
            'frontage': f'python3 scripts/osm_footprints.py frontage --bbox {bbox}',
            'plots': f'python3 scripts/osm_footprints.py plots --bbox {bbox}',
            'region_snap': (
                f'python3 scripts/region_backup.py snap --bbox {bbox} '
                f'--margin {p["region_margin"]} --name survey'
            ),
            'aerial_annot': f'python3 scripts/aerial_annot.py {bbox} reference/aerial/survey-annot.png',
        },
    }


def _street_tangent(idx, x: float, z: float) -> tuple[float, float] | None:
    """Unit tangent (dx, dz) of the nearest named street at (x, z).

    @param idx: OSMIndex
    @param x: MC x
    @param z: MC z
    @returns: normalized tangent or None
    """
    s = idx.nearest_street(x, z)
    if not s:
        return None
    foot = s[3]
    best_seg = None
    best_d = 1e9
    for name, _hw, pts in idx.streets:
        if name != s[1]:
            continue
        for a, b in zip(pts, pts[1:]):
            d = math.dist((x, z), foot)
            if d < best_d:
                best_d = d
                best_seg = (a, b)
    if not best_seg:
        return None
    ax, az = best_seg[0]
    bx, bz = best_seg[1]
    dx, dz = bx - ax, bz - az
    mag = math.hypot(dx, dz) or 1.0
    return dx / mag, dz / mag


def party_pitch_report(bbox: str, street: str | None) -> list[dict]:
    """Frontage width and suggested 4/5 block pitch per house in bbox.

    @param bbox: MC bbox spec
    @param street: optional addr:street filter
    @returns: list of house records sorted along street
    """
    from osm_footprints import OSMIndex, _addr  # noqa: WPS433

    idx = OSMIndex()
    x0, z0, x1, z1 = parse_bbox(bbox)
    rows = []
    for i, (rings, p) in enumerate(idx.buildings):
        ring = rings[0]
        cx = sum(v[0] for v in ring) / len(ring)
        cz = sum(v[1] for v in ring) / len(ring)
        if not (x0 <= cx <= x1 and z0 <= cz <= z1):
            continue
        num, st = _addr(p)
        if street and st != street:
            continue
        tan = _street_tangent(idx, cx, cz)
        if not tan:
            continue
        tx, tz = tan
        projs = [v[0] * tx + v[1] * tz for v in ring]
        width = max(projs) - min(projs)
        pitch = 4 if width < 4.75 else 5
        along = cx * tx + cz * tz
        s = idx.nearest_street(cx, cz)
        foot = s[3] if s else (cx, cz)
        face_dx, face_dz = foot[0] - cx, foot[1] - cz
        rows.append({
            'street': st or '?',
            'number': num or '-',
            'centroid_mc': [round(cx, 1), round(cz, 1)],
            'frontage_blocks': round(width, 1),
            'suggested_pitch': pitch,
            'along_street': round(along, 1),
            'door_facing': door_facing_toward(face_dx, face_dz),
        })
    rows.sort(key=lambda r: (r['street'], r['along_street']))
    if len(rows) >= 2:
        for a, b in zip(rows, rows[1:]):
            if a['street'] == b['street']:
                mid = (a['along_street'] + b['along_street']) / 2
                a['party_to_next'] = round(b['along_street'] - a['along_street'], 1)
                a['suggested_party_mc_xz_hint'] = (
                    f'midpoint along street ≈ {mid:.0f} (snap to integer column; check OSM centroids)'
                )
    return rows


def place_brief(name: str, record: dict) -> str:
    """Render a PLACE-TEMPLATE fragment for one centre.

    @param name: place label
    @param record: coord_triple dict
    @returns: plain-text brief
    """
    mc = record['mc']
    osg = record['osgb']
    wgs = record['wgs84']
    x, z = mc['x'], mc['z']
    pad = 40
    return '\n'.join([
        f'PLACE — {name}',
        'ID: P-XXX',
        'Created:',
        f"OSGB: E {osg['easting']} N {osg['northing']}",
        f'MC: X {x} Y … Z {z}   # run: python3 scripts/geo.py probe {x},{z}',
        f'Bounds (MC): X{x - pad}..{x + pad}  Z{z - pad}..{z + pad}',
        '',
        'EVIDENCE',
        '- Photos: reference/photos/…',
        '- Aerial: reference/aerial/…',
        '',
    ])


def tiles_for_bbox(bbox: str, zoom: int, mosaic: int) -> dict:
    """Web-mercator tiles and mosaic filename for an MC bbox.

    @param bbox: MC bbox
    @param zoom: WM zoom (default 18)
    @param mosaic: odd N×N mosaic size
    @returns: centre tile, wm ids, suggested mosaic path stem
    """
    x0, z0, x1, z1 = parse_bbox(bbox)
    cx, cz = (x0 + x1) // 2, (z0 + z1) // 2
    e, n = to_osgb(cx, cz)
    lat, lon = osgb_to_wgs84(e, n)
    tx, ty = deg2num(lat, lon, zoom)
    if mosaic % 2 == 0 or mosaic < 1:
        raise SystemExit('--mosaic must be odd and >= 1')
    half = mosaic // 2
    wm_tiles = [f'{zoom}/{tx + dx}/{ty + dy}' for dy in range(-half, half + 1)
                for dx in range(-half, half + 1)]
    stem = f'mosaic-z{zoom}-{mosaic}x{mosaic}-centre-{tx}-{ty}.png'
    return {
        'centre_mc': [cx, cz],
        'centre_wm': f'{zoom}/{tx}/{ty}',
        'wgs84': {'lat': round(lat, 6), 'lon': round(lon, 6)},
        'wm_tiles': wm_tiles,
        'mosaic_filename': stem,
        'mc_tiles': mc_tiles_for_bbox(x0, z0, x1, z1),
        'wm_tile_bbox_mc': list(wm_tile_bbox_mc(zoom, tx, ty)),
        'aerial_mosaic': (
            f'python3 scripts/aerial_mosaic.py --wm {zoom}/{tx}/{ty} --zoom {zoom} '
            f'--dir aerial/survey --size {mosaic}'
        ),
    }


def _print_json(obj) -> None:
    print(json.dumps(obj, indent=2))


def cmd_convert(args: argparse.Namespace) -> int:
    """Run convert subcommand."""
    if args.mc:
        x, z = parse_xz(args.mc)
        rec = coord_triple_from_mc(x, z)
    elif args.osgb:
        parts = [float(p.strip()) for p in args.osgb.split(',')]
        rec = coord_triple_from_osgb(parts[0], parts[1])
    elif args.wgs84:
        parts = [float(p.strip()) for p in args.wgs84.split(',')]
        rec = coord_triple_from_wgs84(parts[0], parts[1])
    else:
        raise SystemExit('convert: need --mc, --osgb, or --wgs84')
    o = load_offsets()
    rec['sea_level_y'] = o.get('SEA_LEVEL')
    if args.json:
        _print_json(rec)
    else:
        mc, osg, wgs = rec['mc'], rec['osgb'], rec['wgs84']
        print(f"MC X{mc['x']} Z{mc['z']}  ({'in' if rec['in_bounds'] else 'OUT OF'} bounds)")
        print(f"OSGB E{osg['easting']} N{osg['northing']}")
        print(f"WGS84 {wgs['lat']}, {wgs['lon']}")
    return 0


def cmd_slope(args: argparse.Namespace) -> int:
    """Run slope subcommand."""
    if args.bearing is not None:
        rec = slope_from_bearing(float(args.bearing))
    elif args.points:
        x0, z0, x1, z1 = map(int, args.points.split(','))
        rec = slope_from_points(x0, z0, x1, z1)
    elif args.pitch is not None:
        rec = pitch_deg_to_slope(float(args.pitch))
    else:
        raise SystemExit('slope: need --bearing, --points x0,z0,x1,z1, or --pitch')
    if args.json:
        _print_json(rec)
    else:
        if 'slope' in rec:
            s = rec['slope']
            print(f"slope ({s['dx']}, {s['dz']})  ≈ {rec.get('angle_deg', rec.get('mc_angle_deg'))}°")
        if rec.get('terrace_hint'):
            print(rec['terrace_hint'])
        if rec.get('craft_hint'):
            print(rec['craft_hint'])
        if rec.get('bearing_deg') is not None and 'from_mc' not in rec:
            print(f"bearing {rec['bearing_deg']}°")
    return 0


def cmd_probe(args: argparse.Namespace) -> int:
    """Run probe subcommand."""
    from site_kit import World  # noqa: WPS433

    world = World()
    if args.bbox:
        rec = probe_bbox(world, *parse_bbox(args.bbox))
    elif args.at:
        x, z = parse_xz(args.at)
        rec = probe_column(world, x, z)
    else:
        raise SystemExit('probe: give x,z or --bbox x0,z0,x1,z1')
    if args.json:
        _print_json(rec)
    elif 'columns' in rec:
        print(f"bbox {rec['bbox_mc']}  columns {rec['columns']}")
        print(f"ground_y  {rec['ground_y']}")
        print(f"lidar_top {rec['lidar_top_y']}")
        print(f"extrusion {rec['extrusion']}")
    else:
        print(f"MC ({rec['mc']['x']}, {rec['mc']['z']})  ground_y={rec['ground_y']}  "
              f"lidar_top={rec['lidar_top_y']}  extrusion={rec['extrusion']}")
        for i, b in enumerate(rec['stack']):
            print(f"  +{i}: {b}")
    return 0


def cmd_view(args: argparse.Namespace) -> int:
    """Run view subcommand."""
    parts = [float(p.strip()) for p in args.at.split(',')]
    if len(parts) != 3:
        raise SystemExit('--at needs x,y,z')
    rec = view_from_heading(parts[0], parts[1], parts[2], float(args.heading), args.distance)
    if args.json:
        _print_json(rec)
    else:
        print(f"--view {rec['handoff_view']}")
    return 0


def cmd_survey(args: argparse.Namespace) -> int:
    """Run survey subcommand."""
    x, z = parse_xz(args.at)
    rec = survey_bbox(x, z, args.preset)
    if args.json:
        _print_json(rec)
    else:
        print(f"preset {rec['preset']}  bbox {rec['bbox_mc']}")
        for name, cmd in rec['commands'].items():
            print(f'{name}: {cmd}')
    return 0


def cmd_party(args: argparse.Namespace) -> int:
    """Run party subcommand."""
    rows = party_pitch_report(args.bbox, args.street)
    if args.json:
        _print_json(rows)
    else:
        print('street | no | frontage blocks | pitch | centroid | door_facing')
        for r in rows:
            print(f"{r['street']} | {r['number']} | {r['frontage_blocks']} | {r['suggested_pitch']} | "
                  f"{r['centroid_mc']} | {r['door_facing']}")
    return 0


def cmd_place(args: argparse.Namespace) -> int:
    """Run place subcommand."""
    if args.mc:
        rec = coord_triple_from_mc(*parse_xz(args.mc))
    elif args.wgs84:
        parts = [float(p.strip()) for p in args.wgs84.split(',')]
        rec = coord_triple_from_wgs84(parts[0], parts[1])
    elif args.osgb:
        parts = [float(p.strip()) for p in args.osgb.split(',')]
        rec = coord_triple_from_osgb(parts[0], parts[1])
    else:
        raise SystemExit('place: need --mc, --osgb, or --wgs84')
    text = place_brief(args.name, rec)
    if args.json:
        _print_json({'brief': text, 'coords': rec})
    else:
        print(text)
    return 0


def cmd_tiles(args: argparse.Namespace) -> int:
    """Run tiles subcommand."""
    rec = tiles_for_bbox(args.bbox, args.zoom, args.mosaic)
    if args.json:
        _print_json(rec)
    else:
        print(f"centre_wm {rec['centre_wm']}  mosaic {rec['mosaic_filename']}")
        print(f"wm_tiles ({len(rec['wm_tiles'])}): {', '.join(rec['wm_tiles'][:5])}…")
        print(rec['aerial_mosaic'])
    return 0


def build_parser() -> argparse.ArgumentParser:
    """Build argparse tree for geo.py.

    @returns: configured ArgumentParser
    """
    p = argparse.ArgumentParser(description='Geocraft coordinate hub')
    p.add_argument('--json', action='store_true', help='machine-readable output')
    sub = p.add_subparsers(dest='cmd', required=True)

    c = sub.add_parser('convert', help='WGS84 ↔ OSGB ↔ MC')
    c.add_argument('--mc')
    c.add_argument('--osgb')
    c.add_argument('--wgs84', help='lat,lon')
    c.set_defaults(func=cmd_convert)

    s = sub.add_parser('slope', help='bearing or points → block slope; --pitch for roofs')
    s.add_argument('--bearing', type=float)
    s.add_argument('--points', help='x0,z0,x1,z1')
    s.add_argument('--pitch', type=float, help='real roof pitch degrees')
    s.set_defaults(func=cmd_slope)

    pr = sub.add_parser('probe', help='ground Y and LIDAR top (pristine world)')
    pr.add_argument('at', nargs='?', help='x,z column')
    pr.add_argument('--bbox', help='x0,z0,x1,z1 summary')
    pr.set_defaults(func=cmd_probe)

    v = sub.add_parser('view', help='heading → handoff --view')
    v.add_argument('--at', required=True, help='x,y,z eye')
    v.add_argument('--heading', type=float, required=True)
    v.add_argument('--distance', type=float, default=25.0)
    v.set_defaults(func=cmd_view)

    su = sub.add_parser('survey', help='survey bbox + companion commands')
    su.add_argument('--at', required=True, help='centre x,z')
    su.add_argument('--preset', choices=tuple(SURVEY_PRESETS), default='terrace')
    su.set_defaults(func=cmd_survey)

    pa = sub.add_parser('party', help='terrace frontage width → pitch 4/5')
    pa.add_argument('--bbox', required=True)
    pa.add_argument('--street')
    pa.set_defaults(func=cmd_party)

    pl = sub.add_parser('place', help='PLACE-TEMPLATE fragment')
    pl.add_argument('--name', required=True)
    pl.add_argument('--mc')
    pl.add_argument('--osgb')
    pl.add_argument('--wgs84')
    pl.set_defaults(func=cmd_place)

    t = sub.add_parser('tiles', help='MC bbox → z18 WM tiles + mosaic name')
    t.add_argument('--bbox', required=True)
    t.add_argument('--zoom', type=int, default=18)
    t.add_argument('--mosaic', type=int, default=3)
    t.set_defaults(func=cmd_tiles)

    return p


def main(argv: list[str] | None = None) -> int:
    """CLI entry.

    @param argv: optional argv (defaults to sys.argv)
    @returns: exit code
    """
    argv = list(sys.argv[1:] if argv is None else argv)
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == '__main__':
    raise SystemExit(main())
