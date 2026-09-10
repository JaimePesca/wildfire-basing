"""Tests for src/scenarios/population.py against a small synthetic
population raster (rasterio), not the real 614 MB WorldPop file.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pytest

rasterio = pytest.importorskip("rasterio")
from rasterio.transform import from_origin  # noqa: E402

from src.scenarios.population import (  # noqa: E402
    sum_population_for_fires,
    sum_population_in_buffer,
)


@dataclass
class _Fire:
    fire_id: str
    lon: float
    lat: float


def _write_synthetic_pop_raster(path, west, north, pixel_size, values, nodata=-99999.0):
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


def test_sum_population_in_buffer_includes_orthogonal_neighbors_only(tmp_path):
    # 5x5 grid, pixel_size 0.001 deg (~111.32 m at the equator), each cell
    # population 1.0, query centered on lat=0 so cos(lat)=1 keeps the
    # meters-per-degree math exact and hand-verifiable. Orthogonal
    # neighbors sit at ~111.32 m, diagonal neighbors at ~157.4 m.
    values = np.ones((5, 5))
    path = tmp_path / "pop.tif"
    # west=-0.0025 so the grid is centered on lon=0 (5 cells * 0.001 wide, centered)
    _write_synthetic_pop_raster(path, west=-0.0025, north=0.0025, pixel_size=0.001, values=values)

    # Buffer 150 m: center cell + 4 orthogonal neighbors = 5 cells.
    result_150 = sum_population_in_buffer(0.0, 0.0, str(path), buffer_radius_m=150.0)
    assert result_150 == pytest.approx(5.0, abs=1e-6)

    # Buffer 200 m: also picks up the 4 diagonal neighbors = 9 cells.
    result_200 = sum_population_in_buffer(0.0, 0.0, str(path), buffer_radius_m=200.0)
    assert result_200 == pytest.approx(9.0, abs=1e-6)


def test_sum_population_in_buffer_treats_negative_as_nodata(tmp_path):
    values = np.array([[-99999.0, 5.0], [5.0, 5.0]])
    path = tmp_path / "pop_with_nodata.tif"
    _write_synthetic_pop_raster(path, west=0.0, north=0.0, pixel_size=0.01, values=values)
    result = sum_population_in_buffer(0.005, -0.005, str(path), buffer_radius_m=5000.0)
    assert result == pytest.approx(15.0)  # 3 real cells of 5.0, the nodata cell contributes 0


def test_sum_population_in_buffer_point_outside_raster_returns_none(tmp_path):
    values = np.ones((3, 3))
    path = tmp_path / "small.tif"
    _write_synthetic_pop_raster(path, west=0.0, north=0.0, pixel_size=0.001, values=values)
    assert sum_population_in_buffer(100.0, 100.0, str(path)) is None


def test_sum_population_for_fires_batches(tmp_path):
    values = np.full((5, 5), 2.0)
    path = tmp_path / "pop.tif"
    _write_synthetic_pop_raster(path, west=-0.0025, north=0.0025, pixel_size=0.001, values=values)
    fires = [_Fire(fire_id="f1", lon=0.0, lat=0.0), _Fire(fire_id="f2", lon=999.0, lat=999.0)]
    result = sum_population_for_fires(fires, str(path), buffer_radius_m=150.0)
    assert result["f1"] == pytest.approx(2.0 * 5)  # 5 cells * population 2.0
    assert result["f2"] is None
