"""Tests for src/scenarios/land_cover.py against a small synthetic GeoTIFF
built in the test itself (rasterio), not the real 96 MB ESA WorldCover tile.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pytest

rasterio = pytest.importorskip("rasterio")
from rasterio.transform import from_origin  # noqa: E402

from src.scenarios.land_cover import (  # noqa: E402
    sample_land_cover_class,
    sample_land_cover_for_fires,
)


@dataclass
class _Fire:
    fire_id: str
    lon: float
    lat: float


def _write_synthetic_tile(path, west, north, pixel_size, values):
    """values: 2D numpy array, row 0 is the northernmost row (standard
    raster convention, matches from_origin's top-left anchor)."""
    height, width = values.shape
    transform = from_origin(west, north, pixel_size, pixel_size)
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        height=height,
        width=width,
        count=1,
        dtype="uint8",
        crs="EPSG:4326",
        transform=transform,
        nodata=0,
    ) as dst:
        dst.write(values, 1)


def test_sample_land_cover_class_reads_correct_pixel(tmp_path):
    # A 4x4 tile spanning lon [0, 4), lat (-4, 0], pixel_size=1 deg.
    # Row 0 (northernmost, lat in (-1,0]) = class 10, row 3 (lat in (-4,-3])
    # = class 40, to make it easy to hand-verify which row is sampled.
    values = np.array(
        [
            [10, 10, 10, 10],
            [20, 20, 20, 20],
            [30, 30, 30, 30],
            [40, 40, 40, 40],
        ],
        dtype="uint8",
    )
    path = tmp_path / "synthetic.tif"
    _write_synthetic_tile(path, west=0.0, north=0.0, pixel_size=1.0, values=values)

    # lon=1.5 lat=-0.5 -> row 0 (top strip) -> class 10
    assert sample_land_cover_class(1.5, -0.5, [str(path)]) == 10
    # lon=1.5 lat=-3.5 -> row 3 (bottom strip) -> class 40
    assert sample_land_cover_class(1.5, -3.5, [str(path)]) == 40


def test_sample_land_cover_class_nodata_returns_none(tmp_path):
    values = np.zeros((2, 2), dtype="uint8")  # all nodata (0)
    path = tmp_path / "empty.tif"
    _write_synthetic_tile(path, west=0.0, north=0.0, pixel_size=1.0, values=values)
    assert sample_land_cover_class(0.5, -0.5, [str(path)]) is None


def test_sample_land_cover_class_point_outside_all_tiles_returns_none(tmp_path):
    values = np.full((2, 2), 50, dtype="uint8")
    path = tmp_path / "tile.tif"
    _write_synthetic_tile(path, west=0.0, north=0.0, pixel_size=1.0, values=values)
    # Point nowhere near the tile.
    assert sample_land_cover_class(100.0, 100.0, [str(path)]) is None


def test_sample_land_cover_class_tries_multiple_tiles_in_order(tmp_path):
    tile_a = tmp_path / "a.tif"
    tile_b = tmp_path / "b.tif"
    _write_synthetic_tile(tile_a, west=0.0, north=0.0, pixel_size=1.0, values=np.full((2, 2), 20, dtype="uint8"))
    _write_synthetic_tile(tile_b, west=5.0, north=0.0, pixel_size=1.0, values=np.full((2, 2), 80, dtype="uint8"))

    # Falls only inside tile_b's extent.
    result = sample_land_cover_class(5.5, -0.5, [str(tile_a), str(tile_b)])
    assert result == 80


def test_sample_land_cover_for_fires_batches_across_fires_and_tiles(tmp_path):
    tile_a = tmp_path / "a.tif"
    tile_b = tmp_path / "b.tif"
    _write_synthetic_tile(tile_a, west=0.0, north=0.0, pixel_size=1.0, values=np.full((2, 2), 20, dtype="uint8"))
    _write_synthetic_tile(tile_b, west=5.0, north=0.0, pixel_size=1.0, values=np.full((2, 2), 80, dtype="uint8"))

    fires = [
        _Fire(fire_id="f_in_a", lon=0.5, lat=-0.5),
        _Fire(fire_id="f_in_b", lon=5.5, lat=-0.5),
        _Fire(fire_id="f_nowhere", lon=99.0, lat=99.0),
    ]
    result = sample_land_cover_for_fires(fires, [str(tile_a), str(tile_b)])

    assert result == {"f_in_a": 20, "f_in_b": 80, "f_nowhere": None}
