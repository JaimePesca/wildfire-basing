"""Reprojection from geographic lat/lon to the configured metric CRS.

Clustering must never happen in degrees: a degree of longitude is not a
constant physical distance, and ST-DBSCAN's eps_spatial is defined in meters
(CLAUDE.md section 5). Always project first, on the configured CRS
(EPSG:9377, MAGNA-SIRGAS 2018 / Origen-Nacional CTM12), then cluster on the
resulting x_utm/y_utm columns.
"""

from __future__ import annotations

import pandas as pd
from pyproj import Transformer


def project_to_crs(
    df: pd.DataFrame,
    epsg: int,
    lon_col: str = "longitude",
    lat_col: str = "latitude",
) -> pd.DataFrame:
    """Add x_utm/y_utm columns (meters) by reprojecting lon/lat to the given EPSG code."""
    transformer = Transformer.from_crs("EPSG:4326", f"EPSG:{epsg}", always_xy=True)
    x, y = transformer.transform(df[lon_col].to_numpy(), df[lat_col].to_numpy())
    out = df.copy()
    out["x_utm"] = x
    out["y_utm"] = y
    return out


def project_from_crs(
    df: pd.DataFrame,
    epsg: int,
    x_col: str = "x_utm",
    y_col: str = "y_utm",
) -> pd.DataFrame:
    """Add lon/lat columns (WGS84 decimal degrees) by inverse-reprojecting
    x/y metric coordinates from the given EPSG code.

    This is the exact inverse of project_to_crs, and is the single shared
    code path any loader must use to go from a metric CRS back to lon/lat
    (sites_schema.py: "Never reprojected ad hoc with a different EPSG in a
    loader"). Do not hand-roll a second pyproj Transformer elsewhere for this
    direction; call this function instead.
    """
    transformer = Transformer.from_crs(f"EPSG:{epsg}", "EPSG:4326", always_xy=True)
    lon, lat = transformer.transform(df[x_col].to_numpy(), df[y_col].to_numpy())
    out = df.copy()
    out["lon"] = lon
    out["lat"] = lat
    return out
