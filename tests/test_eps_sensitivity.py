"""Tests for src/scenarios/eps_sensitivity.py.

Synthetic fixtures only, built the same way as tests/test_pipeline.py (no
real FIRMS data). See CLAUDE.md section 5: sensitivity analysis over
eps_spatial and eps_temporal is mandatory, not optional; this test asserts
the grid actually shows varying behavior rather than a tautological check.
"""

from __future__ import annotations

import math

import pandas as pd
import pytest

from src.pipeline.clean import clean_firms
from src.pipeline.project import project_to_crs
from src.scenarios.eps_sensitivity import SENSITIVITY_TABLE_COLUMNS, run_eps_sensitivity

CONFIG = {
    "crs": {"epsg": 9377},
    "firms": {"min_confidence": "nominal"},
}


def offset_latlon(lat0: float, lon0: float, dx_m: float, dy_m: float) -> tuple[float, float]:
    """Same equirectangular approximation used in tests/test_pipeline.py."""
    dlat = dy_m / 111320.0
    dlon = dx_m / (111320.0 * math.cos(math.radians(lat0)))
    return lat0 + dlat, lon0 + dlon


def _prepared_two_groups_df() -> pd.DataFrame:
    """Two groups of detections, each tight internally, separated by about
    600 m and by about 2.5 days: this is designed so that a small
    eps_spatial (below 600 m) or small eps_temporal (below 2.5 days) keeps
    them as two events, while a large eps_spatial/eps_temporal merges them
    into one, so the grid sweep is expected to show a real split.
    """
    base_time = pd.Timestamp("2024-01-15T00:00:00Z")
    lat0, lon0 = 4.65, -74.15

    rows = []
    # Group A: 3 tight detections around the origin, at base_time.
    for dx, dy, dh in [(0, 0, 0), (30, 20, 0), (-20, 10, 1)]:
        lat, lon = offset_latlon(lat0, lon0, dx, dy)
        rows.append(
            {
                "latitude": lat,
                "longitude": lon,
                "confidence": "nominal",
                "frp": 10.0,
                "timestamp": base_time + pd.Timedelta(hours=dh),
            }
        )
    # Group B: 3 tight detections about 600 m away, about 2.5 days later.
    for dx, dy, dh in [(600, 0, 0), (630, 20, 0), (580, -10, 1)]:
        lat, lon = offset_latlon(lat0, lon0, dx, dy)
        rows.append(
            {
                "latitude": lat,
                "longitude": lon,
                "confidence": "nominal",
                "frp": 10.0,
                "timestamp": base_time + pd.Timedelta(days=2.5, hours=dh),
            }
        )

    df = pd.DataFrame(rows)
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    df = clean_firms(df, CONFIG["firms"]["min_confidence"])
    df = project_to_crs(df, epsg=CONFIG["crs"]["epsg"])
    return df


def test_sensitivity_table_has_expected_columns():
    df = _prepared_two_groups_df()
    table = run_eps_sensitivity(
        df,
        eps_spatial_grid_m=[200.0],
        eps_temporal_grid_days=[1.0],
    )
    assert list(table.columns) == SENSITIVITY_TABLE_COLUMNS
    assert len(table) == 1


def test_sensitivity_grid_produces_varying_event_counts():
    df = _prepared_two_groups_df()

    # A grid where the small end keeps the two groups separate (n_events=2)
    # and the large end merges them (n_events=1): a real, non-tautological
    # difference driven by the eps sweep, not by construction of the assert.
    table = run_eps_sensitivity(
        df,
        eps_spatial_grid_m=[200.0, 1500.0],
        eps_temporal_grid_days=[1.0, 5.0],
    )

    assert len(table) == 4  # 2 x 2 grid
    n_events_values = set(table["n_events"].tolist())
    assert len(n_events_values) > 1, (
        "expected the eps grid to produce more than one distinct event count; "
        "got the same n_events at every grid point, which would suggest the "
        "sweep is not actually exercising the clustering"
    )

    tight = table[(table["eps_spatial_m"] == 200.0) & (table["eps_temporal_days"] == 1.0)].iloc[0]
    loose = table[(table["eps_spatial_m"] == 1500.0) & (table["eps_temporal_days"] == 5.0)].iloc[0]
    assert tight["n_events"] == 2
    assert loose["n_events"] == 1
    assert loose["largest_event_size"] == 6


def test_sensitivity_grid_reports_noise_when_min_pts_high():
    df = _prepared_two_groups_df()
    # min_pts=3 requires 3 neighbors including self, only the tight groups
    # (3 points each) qualify at a small eps; push eps_spatial down further
    # so isolated pairs would show up as noise instead of a tautological
    # all-zero table.
    table = run_eps_sensitivity(
        df,
        eps_spatial_grid_m=[10.0],
        eps_temporal_grid_days=[1.0],
        min_pts=3,
    )
    row = table.iloc[0]
    assert row["n_events"] == 0
    assert row["n_noise"] == 6
