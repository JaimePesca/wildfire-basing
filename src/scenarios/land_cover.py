"""Sample ESA WorldCover 10m land cover class at fire locations (CLAUDE.md
section 5.3: ros[f]'s base-rate-by-land-cover-class input).

Source switched 2026-08-21 from IDEAM CORINE (named in CLAUDE.md section 8)
to ESA WorldCover 10m v200 (2021) after four independent, confirmed dead
ends trying to reach a real Cundinamarca-covering CORINE product (see
section 5.3/8 for the full list: an Amazon-only SINCHI version, a
protected-areas-only Parques Nacionales service, IDER Cundinamarca's own
CORINE service on a now-dead subdomain, and a wrong-department Cauca
dataset). WorldCover is downloaded from the public AWS Open Data bucket
(s3://esa-worldcover/, no login/signing required), the same
"international source instead of unreachable Colombian portal" pattern
already used for OSM/CAR water bodies (src/pipeline/sites_water.py).

Class codes verified 2026-08-21 against multiple independent secondary
sources (ESA's own worldcover2021.esa.int site, Digital Earth Africa's
WorldCover data-spec docs, Sentinel Hub's WorldCover collection docs); the
primary ESA WorldCover Product User Manual PDF was not read directly, flag
this if a reviewer wants a primary-source citation before the manuscript
cites it.

Two tiles cover Cundinamarca (verified against the department's bounding
box, the same one already used for FIRMS/candidate sites):
data/raw/esa_worldcover_2021_N03W075.tif (bulk of the department),
data/raw/esa_worldcover_2021_N03W078.tif (a thin western sliver).
"""

from __future__ import annotations

import rasterio
from rasterio.windows import Window

# Confirmed 2026-08-21, see module docstring.
WORLDCOVER_CLASSES = {
    10: "Tree cover",
    20: "Shrubland",
    30: "Grassland",
    40: "Cropland",
    50: "Built-up",
    60: "Bare / sparse vegetation",
    70: "Snow and ice",
    80: "Permanent water bodies",
    90: "Herbaceous wetland",
    95: "Mangrove",
    100: "Moss and lichen",
}

NODATA_VALUE = 0


def sample_land_cover_class(lon: float, lat: float, tile_paths: list[str]) -> int | None:
    """Sample the WorldCover class code at one (lon, lat) WGS84-degree
    point, trying each tile in tile_paths until one covers the point.
    Returns None (not a guessed class) if no tile covers the point or the
    pixel is nodata."""
    for path in tile_paths:
        with rasterio.open(path) as src:
            left, bottom, right, top = src.bounds
            if not (left <= lon <= right and bottom <= lat <= top):
                continue
            row, col = src.index(lon, lat)
            if row < 0 or col < 0 or row >= src.height or col >= src.width:
                continue
            value = int(src.read(1, window=Window(col, row, 1, 1))[0, 0])
            return value if value != NODATA_VALUE else None
    return None


def sample_land_cover_for_fires(fires: list, tile_paths: list[str]) -> dict[str, int | None]:
    """Batch version: sample the class for every fire (objects with
    fire_id/lat/lon attributes, e.g. src.scenarios.day_scenarios.FireRecord),
    opening each tile once rather than once per fire. Fires whose point
    falls in no tile, or lands on nodata, map to None."""
    remaining = {fire.fire_id: (fire.lon, fire.lat) for fire in fires}
    result: dict[str, int | None] = {}

    for path in tile_paths:
        if not remaining:
            break
        with rasterio.open(path) as src:
            left, bottom, right, top = src.bounds
            still_remaining = {}
            for fire_id, (lon, lat) in remaining.items():
                if left <= lon <= right and bottom <= lat <= top:
                    row, col = src.index(lon, lat)
                    if 0 <= row < src.height and 0 <= col < src.width:
                        value = int(src.read(1, window=Window(col, row, 1, 1))[0, 0])
                        result[fire_id] = value if value != NODATA_VALUE else None
                        continue
                still_remaining[fire_id] = (lon, lat)
            remaining = still_remaining

    for fire_id in remaining:
        result[fire_id] = None
    return result
