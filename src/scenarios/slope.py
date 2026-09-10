"""Compute terrain slope from SRTM 30m elevation tiles (CLAUDE.md section
5.3: ros[f]'s slope factor input, the Rothermel/Cheney exponential
relationship between rate of spread and slope angle).

Source switched 2026-08-21 from IGAC's own DTM (named in CLAUDE.md section
8) to SRTM GL1 (NASA, 30m, global), mirrored with no login required by
OpenTopography's public S3 bucket (opentopography.s3.sdsc.edu, endpoint
verified live 2026-08-21), the same "international source instead of
fighting Colombian government portals" pattern already used for OSM/CAR
water and ESA WorldCover land cover. IGAC's own DTM was not even attempted
here given the repo's track record with IGAC infrastructure (section 8);
this is a deliberate choice to try the international alternative first,
not a confirmed IGAC dead end the way CORINE, water and Aerocivil were.

16 tiles (N03-N06, W073-W076) cover the full Cundinamarca bounding box,
downloaded to data/raw/srtm_<TILE>.tif, 1 arc-second (30m) resolution,
EPSG:4326, nodata -32768.

Slope is computed with Horn's (1981) method, the standard algorithm used by
GDAL's and ArcGIS's own slope tools: a 3x3 elevation window around the
point, finite-difference gradient in x and y, slope = atan(magnitude of the
gradient). Citation: Horn, B.K.P. (1981), "Hill shading and the reflectance
map," Proceedings of the IEEE, 69(1), 14-47, a well-established source, not
independently verified against the primary IEEE text in this session, flag
if a reviewer wants that confirmed before the manuscript cites it.
"""

from __future__ import annotations

import math

import numpy as np
import rasterio
from rasterio.windows import Window

# Standard spherical-Earth approximation, meters per degree of latitude is
# roughly constant; meters per degree of longitude shrinks with cos(lat).
METERS_PER_DEGREE_LAT = 111320.0


def meters_per_degree(lat_deg: float) -> tuple[float, float]:
    """Return (meters per degree longitude, meters per degree latitude) at
    the given latitude."""
    m_per_deg_lon = METERS_PER_DEGREE_LAT * math.cos(math.radians(lat_deg))
    return m_per_deg_lon, METERS_PER_DEGREE_LAT


def sample_elevation_window(
    lon: float, lat: float, tile_paths: list[str]
) -> tuple[np.ndarray, float, float] | None:
    """Read the 3x3 pixel window centered on (lon, lat) from whichever tile
    covers it. Returns (elevation_3x3, pixel_size_x_deg, pixel_size_y_deg),
    or None if no tile covers the point, the window would run off a tile
    edge, or any of the 9 pixels is nodata (never interpolated/guessed)."""
    for path in tile_paths:
        with rasterio.open(path) as src:
            left, bottom, right, top = src.bounds
            if not (left <= lon <= right and bottom <= lat <= top):
                continue
            row, col = src.index(lon, lat)
            if row < 1 or col < 1 or row + 1 >= src.height or col + 1 >= src.width:
                continue
            data = src.read(1, window=Window(col - 1, row - 1, 3, 3)).astype(float)
            nodata = src.nodata if src.nodata is not None else -32768.0
            if np.any(data == nodata):
                return None
            return data, src.res[0], src.res[1]
    return None


def compute_slope_degrees(
    elevation_3x3: np.ndarray, pixel_size_x_m: float, pixel_size_y_m: float
) -> float:
    """Horn's (1981) method. elevation_3x3 rows run north (row 0) to south
    (row 2), columns west (col 0) to east (col 2), matching how rasterio
    reads a window off a north-up GeoTIFF; pixel_size_x_m/pixel_size_y_m
    must already be real distances (meters), not degrees, the caller
    converts degrees to meters (see meters_per_degree) before calling
    this. Returns slope magnitude in degrees (0 = flat, 90 = vertical),
    aspect/direction is not computed, this project only needs the
    magnitude for the Rothermel/Cheney slope factor.
    """
    a, b, c = elevation_3x3[0]
    d, _e, f = elevation_3x3[1]
    g, h, i = elevation_3x3[2]
    dzdx = ((c + 2 * f + i) - (a + 2 * d + g)) / (8 * pixel_size_x_m)
    dzdy = ((g + 2 * h + i) - (a + 2 * b + c)) / (8 * pixel_size_y_m)
    slope_rad = math.atan(math.hypot(dzdx, dzdy))
    return math.degrees(slope_rad)


def sample_slope_degrees(lon: float, lat: float, tile_paths: list[str]) -> float | None:
    """Slope in degrees at (lon, lat), or None if no tile covers the point
    or any of the 9 elevation pixels needed is nodata."""
    result = sample_elevation_window(lon, lat, tile_paths)
    if result is None:
        return None
    elevation_3x3, pixel_size_x_deg, pixel_size_y_deg = result
    m_per_deg_lon, m_per_deg_lat = meters_per_degree(lat)
    return compute_slope_degrees(
        elevation_3x3, pixel_size_x_deg * m_per_deg_lon, pixel_size_y_deg * m_per_deg_lat
    )
