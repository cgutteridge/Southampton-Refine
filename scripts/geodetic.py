#!/usr/bin/env python3
"""WGS84 ↔ OSGB36 via gdaltransform (shared by geo.py, ref_manifest, aerial tools)."""
from __future__ import annotations

import subprocess


def _gdal_transform(pairs: list[tuple[float, float]], src: str, dst: str) -> list[tuple[float, float]]:
    """Run gdaltransform on a list of (x, y) input coordinates.

    @param pairs: input points in source CRS (lon,lat for EPSG:4326; E,N for 27700)
    @param src: source SRS (e.g. EPSG:4326)
    @param dst: target SRS (e.g. EPSG:27700)
    @returns: transformed (x, y) pairs in destination CRS order
    """
    if not pairs:
        return []
    inp = ''.join(f'{a} {b}\n' for a, b in pairs)
    proc = subprocess.run(
        ['gdaltransform', '-s_srs', src, '-t_srs', dst],
        input=inp.encode(),
        capture_output=True,
        check=True,
    )
    out = []
    for line in proc.stdout.decode().splitlines():
        if not line.strip():
            continue
        parts = line.split()
        out.append((float(parts[0]), float(parts[1])))
    return out


def wgs84_to_osgb(lat: float, lon: float) -> tuple[float, float]:
    """Convert WGS84 to OSGB36 easting/northing via gdaltransform.

    @param lat: latitude (degrees)
    @param lon: longitude (degrees)
    @returns: (easting, northing)
    """
    e, n = _gdal_transform([(lon, lat)], 'EPSG:4326', 'EPSG:27700')[0]
    return e, n


def osgb_to_wgs84(easting: float, northing: float) -> tuple[float, float]:
    """Convert OSGB36 easting/northing to WGS84 lat/lon via gdaltransform.

    @param easting: OSGB easting (metres)
    @param northing: OSGB northing (metres)
    @returns: (lat, lon)
    """
    lon, lat = _gdal_transform([(easting, northing)], 'EPSG:27700', 'EPSG:4326')[0]
    return lat, lon


def wgs84_batch_to_osgb(lat_lon: list[tuple[float, float]]) -> list[tuple[float, float]]:
    """Convert many WGS84 points to OSGB (lon, lat inputs per gdal convention).

    @param lat_lon: list of (lat, lon)
    @returns: list of (easting, northing)
    """
    return _gdal_transform([(lon, lat) for lat, lon in lat_lon], 'EPSG:4326', 'EPSG:27700')


def osgb_batch_to_wgs84(en: list[tuple[float, float]]) -> list[tuple[float, float]]:
    """Convert many OSGB points to WGS84.

    @param en: list of (easting, northing)
    @returns: list of (lat, lon)
    """
    ll = _gdal_transform(en, 'EPSG:27700', 'EPSG:4326')
    return [(lat, lon) for lon, lat in ll]
