"""Tests for src/scenarios/slope.py: compute_slope_degrees against a
hand-derived 45-degree ramp, and sample_slope_degrees against a small
synthetic GeoTIFF, not the real 285 MB of downloaded SRTM tiles.
"""

from __future__ import annotations

import numpy as np
import pytest

rasterio = pytest.importorskip("rasterio")
from rasterio.transform import from_origin  # noqa: E402

from src.scenarios.slope import (  # noqa: E402
    compute_slope_degrees,
    sample_elevation_window,
    sample_slope_degrees,
)


def test_compute_slope_degrees_pure_east_west_ramp_is_45_degrees():
    # Elevation rises 30 m per 30 m pixel, purely east-west, no
    # north-south gradient: dz/dx = 30/30 = 1.0, dz/dy = 0, slope =
    # atan(1.0) = 45 degrees exactly, hand-verifiable.
    elevation = np.array(
        [
            [0.0, 30.0, 60.0],
            [0.0, 30.0, 60.0],
            [0.0, 30.0, 60.0],
        ]
    )
    slope = compute_slope_degrees(elevation, pixel_size_x_m=30.0, pixel_size_y_m=30.0)
    assert slope == pytest.approx(45.0)


def test_compute_slope_degrees_flat_is_zero():
    elevation = np.full((3, 3), 1000.0)
    slope = compute_slope_degrees(elevation, pixel_size_x_m=30.0, pixel_size_y_m=30.0)
    assert slope == pytest.approx(0.0)


def test_compute_slope_degrees_pure_north_south_ramp():
    # Rows run north (0) to south (2); a 60 m rise per 30 m pixel purely
    # north-south: dz/dy = 60/30 = 2.0, slope = atan(2.0).
    elevation = np.array(
        [
            [0.0, 0.0, 0.0],
            [60.0, 60.0, 60.0],
            [120.0, 120.0, 120.0],
        ]
    )
    slope = compute_slope_degrees(elevation, pixel_size_x_m=30.0, pixel_size_y_m=30.0)
    expected = np.degrees(np.arctan(2.0))
    assert slope == pytest.approx(expected)


def _write_synthetic_dem(path, west, north, pixel_size, values, nodata=-32768.0):
    height, width = values.shape
    transform = from_origin(west, north, pixel_size, pixel_size)
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        height=height,
        width=width,
        count=1,
        dtype="float32",
        crs="EPSG:4326",
        transform=transform,
        nodata=nodata,
    ) as dst:
        dst.write(values.astype("float32"), 1)


def test_sample_elevation_window_reads_correct_3x3(tmp_path):
    # A 5x5 tile, pixel_size 0.001 deg, values = row*10+col so the window
    # extracted around the center pixel (row=2,col=2) is hand-checkable.
    values = np.array([[r * 10 + c for c in range(5)] for r in range(5)], dtype=float)
    path = tmp_path / "dem.tif"
    _write_synthetic_dem(path, west=0.0, north=0.0, pixel_size=0.001, values=values)

    # Center of pixel (row=2, col=2): lon = west + 2.5*px, lat = north - 2.5*px
    lon = 0.0 + 2.5 * 0.001
    lat = 0.0 - 2.5 * 0.001
    result = sample_elevation_window(lon, lat, [str(path)])
    assert result is not None
    window, px_x, py_y = result
    expected = values[1:4, 1:4]
    assert np.array_equal(window, expected)
    assert px_x == pytest.approx(0.001)


def test_sample_elevation_window_nodata_in_window_returns_none(tmp_path):
    values = np.full((5, 5), 1000.0)
    values[2, 2] = -32768.0
    path = tmp_path / "dem_with_hole.tif"
    _write_synthetic_dem(path, west=0.0, north=0.0, pixel_size=0.001, values=values)
    lon = 0.0 + 2.5 * 0.001
    lat = 0.0 - 2.5 * 0.001
    assert sample_elevation_window(lon, lat, [str(path)]) is None


def test_sample_elevation_window_edge_pixel_returns_none(tmp_path):
    # Requesting the window centered on the tile's own edge pixel (no room
    # for a full 3x3) must not silently read past the tile.
    values = np.full((3, 3), 1000.0)
    path = tmp_path / "small.tif"
    _write_synthetic_dem(path, west=0.0, north=0.0, pixel_size=0.001, values=values)
    lon = 0.0 + 0.5 * 0.001  # column 0, no room for col-1
    lat = 0.0 - 0.5 * 0.001
    assert sample_elevation_window(lon, lat, [str(path)]) is None


def test_sample_slope_degrees_flat_synthetic_dem_is_zero(tmp_path):
    values = np.full((5, 5), 2600.0)
    path = tmp_path / "flat.tif"
    _write_synthetic_dem(path, west=-74.0, north=5.0, pixel_size=0.001, values=values)
    lon, lat = -74.0 + 2.5 * 0.001, 5.0 - 2.5 * 0.001
    slope = sample_slope_degrees(lon, lat, [str(path)])
    assert slope == pytest.approx(0.0, abs=1e-6)


def test_sample_slope_degrees_point_outside_all_tiles_returns_none(tmp_path):
    values = np.full((3, 3), 1000.0)
    path = tmp_path / "tile.tif"
    _write_synthetic_dem(path, west=0.0, north=0.0, pixel_size=0.001, values=values)
    assert sample_slope_degrees(100.0, 100.0, [str(path)]) is None
