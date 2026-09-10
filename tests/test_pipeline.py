"""Tests for the src/pipeline package (section 5 of CLAUDE.md).

All fixtures here are synthetic, built inline, not real FIRMS data (none has
been downloaded yet, see CLAUDE.md section 8 and the pipeline README). The
January 2024 chaining validation mentioned in CLAUDE.md section 5 needs real
raw detections and is NOT covered here: it stays an open TODO, tracked in
src/pipeline/README.md, until real FIRMS data for that window is on disk.
"""

from __future__ import annotations

import math
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
import yaml

from src.pipeline.clean import clean_firms
from src.pipeline.events import build_events
from src.pipeline.io import load_firms_csv
from src.pipeline.project import project_to_crs
from src.pipeline.st_dbscan import STDBSCANConfig, cluster_detections

CONFIG_PATH = Path(__file__).resolve().parent.parent / "config" / "parameters.yaml"

EVENT_SCHEMA_FIELDS = [
    "event_id",
    "centroid_lat",
    "centroid_lon",
    "x_utm",
    "y_utm",
    "t_start",
    "t_end",
    "duration_h",
    "n_detections",
    "frp_total",
    "frp_peak",
    "extent",
    "confidence_mix",
    "municipality",
]


def load_config() -> dict:
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def offset_latlon(lat0: float, lon0: float, dx_m: float, dy_m: float) -> tuple[float, float]:
    """Approximate lat/lon offset for a given meter displacement.

    Equirectangular approximation, adequate at the small scales used in
    these fixtures (a few kilometers), not meant for production use.
    """
    dlat = dy_m / 111320.0
    dlon = dx_m / (111320.0 * math.cos(math.radians(lat0)))
    return lat0 + dlat, lon0 + dlon


def make_detections(rows: list[dict]) -> pd.DataFrame:
    """Build a DataFrame matching the post-load_firms_csv schema directly,
    so tests can construct fixtures without round-tripping through a CSV.
    """
    df = pd.DataFrame(rows)
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    return df


def run_pipeline_steps(df: pd.DataFrame, config: dict, st_config: STDBSCANConfig) -> pd.DataFrame:
    """Clean, project, cluster and build events; the load step is exercised
    separately in test_load_firms_csv_parses_expected_columns."""
    df = clean_firms(df, config["firms"]["min_confidence"])
    df = project_to_crs(df, epsg=config["crs"]["epsg"])
    labels = cluster_detections(df, st_config)
    return build_events(df, labels)


# ---------------------------------------------------------------------------
# io.py
# ---------------------------------------------------------------------------


def test_load_firms_csv_parses_expected_columns(tmp_path):
    csv_path = tmp_path / "firms_sample.csv"
    csv_path.write_text(
        "latitude,longitude,acq_date,acq_time,confidence,frp,satellite,instrument,daynight,version\n"
        "4.65,-74.15,2024-01-15,530,nominal,12.3,N,VIIRS,D,2.0\n"
        "4.66,-74.16,2024-01-15,5,high,20.1,N,VIIRS,D,2.0\n",
        encoding="utf-8",
    )
    df = load_firms_csv(str(csv_path))
    assert "timestamp" in df.columns
    assert df["timestamp"].dt.tz is not None
    # acq_time "530" -> 05:30, acq_time "5" -> 00:05 (zero padded to "0005").
    assert df.loc[0, "timestamp"].strftime("%H:%M") == "05:30"
    assert df.loc[1, "timestamp"].strftime("%H:%M") == "00:05"


def test_load_firms_csv_missing_required_column_raises(tmp_path):
    csv_path = tmp_path / "bad.csv"
    csv_path.write_text("latitude,longitude,acq_date\n4.65,-74.15,2024-01-15\n", encoding="utf-8")
    with pytest.raises(ValueError):
        load_firms_csv(str(csv_path))


# ---------------------------------------------------------------------------
# Two clusters, clearly separated in space and time -> 2 events.
# ---------------------------------------------------------------------------


def test_two_separated_clusters_recovered_as_two_events():
    config = load_config()
    st_config = STDBSCANConfig.from_dict(config["st_dbscan"])

    base_time = pd.Timestamp("2024-01-15T12:00:00Z")
    lat_a, lon_a = 4.65, -74.15  # Cundinamarca-ish
    lat_b, lon_b = 6.50, -75.50  # far away, different department

    rows = []
    # Cluster A: 3 detections within ~150 m and a few hours of each other.
    for i, (dx, dy, dh) in enumerate([(0, 0, 0), (100, 50, 1), (150, -80, 3)]):
        lat, lon = offset_latlon(lat_a, lon_a, dx, dy)
        rows.append(
            {
                "latitude": lat,
                "longitude": lon,
                "confidence": "nominal",
                "frp": 10.0 + i,
                "timestamp": base_time + pd.Timedelta(hours=dh),
            }
        )
    # Cluster B: 3 detections within ~150 m, 20 days later, far away.
    for i, (dx, dy, dh) in enumerate([(0, 0, 0), (120, -60, 2), (-100, 100, 4)]):
        lat, lon = offset_latlon(lat_b, lon_b, dx, dy)
        rows.append(
            {
                "latitude": lat,
                "longitude": lon,
                "confidence": "high",
                "frp": 30.0 + i,
                "timestamp": base_time + pd.Timedelta(days=20, hours=dh),
            }
        )

    df = make_detections(rows)
    events = run_pipeline_steps(df, config, st_config)

    assert len(events) == 2
    assert sorted(events["n_detections"].tolist()) == [3, 3]


# ---------------------------------------------------------------------------
# Close in space, far apart in time -> must NOT merge (isolates the temporal
# half of the two-eps AND neighbor definition, independent of spatial
# separation). Regression test for the datetime64 unit bug in st_dbscan.py:
# t_seconds used to be computed via astype("int64") / 1e9, which silently
# assumed datetime64[ns] input. On datetime64[us] input (what pandas actually
# produces here) that inflated eps_temporal_days by ~1000x, so points months
# apart in time were treated as temporal neighbors and wrongly merged.
# ---------------------------------------------------------------------------


def test_same_location_far_in_time_not_merged():
    config = load_config()
    st_config = STDBSCANConfig.from_dict(config["st_dbscan"])
    eps_temporal_days = config["st_dbscan"]["eps_temporal_days"]

    base_time = pd.Timestamp("2024-01-15T12:00:00Z")
    lat0, lon0 = 4.65, -74.15

    rows = []
    # Group A: 3 detections within ~150 m and a few hours, at base_time.
    for dx, dy, dh in [(0, 0, 0), (100, 50, 1), (150, -80, 3)]:
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
    # Group B: same location (within ~150 m), but many eps_temporal_days
    # later, well beyond the temporal radius. Spatially these two groups
    # would clearly merge if the temporal filter were broken.
    days_later = eps_temporal_days * 100
    for dx, dy, dh in [(0, 0, 0), (100, 50, 1), (150, -80, 3)]:
        lat, lon = offset_latlon(lat0, lon0, dx, dy)
        rows.append(
            {
                "latitude": lat,
                "longitude": lon,
                "confidence": "nominal",
                "frp": 10.0,
                "timestamp": base_time + pd.Timedelta(days=days_later, hours=dh),
            }
        )

    df = make_detections(rows)
    # Force datetime64[us] resolution explicitly rather than relying on
    # whatever the installed pandas version happens to default to. This is
    # the exact resolution the reviewers confirmed pandas actually produces,
    # and is what exposed the int64/1e9 (assumes nanoseconds) bug; asserting
    # on it here makes the regression test deterministic across pandas
    # versions instead of only failing when ambient dtype happens to be us.
    df["timestamp"] = df["timestamp"].astype("datetime64[us, UTC]")
    assert df["timestamp"].dtype == pd.DatetimeTZDtype(unit="us", tz="UTC")

    cleaned = clean_firms(df, config["firms"]["min_confidence"])
    projected = project_to_crs(cleaned, epsg=config["crs"]["epsg"])
    labels = cluster_detections(projected, st_config)

    non_noise = labels[labels != -1]
    n_clusters = len(set(non_noise.tolist()))
    assert n_clusters == 2, (
        "detections at (near) the same location but far apart in time must "
        "not be merged into one cluster; the two-eps neighbor rule is an "
        "AND of space and time, not space alone"
    )

    events = build_events(projected, labels)
    assert len(events) == 2
    assert sorted(events["n_detections"].tolist()) == [3, 3]


# ---------------------------------------------------------------------------
# Chain of detections spaced just under eps apart, end to end.
# ---------------------------------------------------------------------------


def _build_chain_df(config: dict) -> pd.DataFrame:
    """A chain where consecutive detections are within eps_spatial/eps_temporal
    of each other, but the first and last are not (space or time), so the
    chain is only connected through intermediate points (density-reachable,
    not directly reachable start-to-end). This is exactly the chaining risk
    flagged in CLAUDE.md section 5.
    """
    eps_spatial = config["st_dbscan"]["eps_spatial_m"]
    eps_temporal = config["st_dbscan"]["eps_temporal_days"]
    step_dx = 0.6 * eps_spatial  # comfortably under eps_spatial per step
    step_dt_days = 0.6 * eps_temporal  # comfortably under eps_temporal per step

    base_time = pd.Timestamp("2024-01-15T00:00:00Z")
    lat0, lon0 = 4.65, -74.15
    n_points = 6

    rows = []
    for i in range(n_points):
        lat, lon = offset_latlon(lat0, lon0, dx_m=i * step_dx, dy_m=0.0)
        rows.append(
            {
                "latitude": lat,
                "longitude": lon,
                "confidence": "nominal",
                "frp": 15.0,
                "timestamp": base_time + pd.Timedelta(days=i * step_dt_days),
            }
        )
    return make_detections(rows)


def test_chain_merges_with_split_off():
    config = load_config()
    df = _build_chain_df(config)

    st_config = STDBSCANConfig.from_dict(config["st_dbscan"])
    st_config.split_on_intra_event_gap = False

    cleaned = clean_firms(df, config["firms"]["min_confidence"])
    projected = project_to_crs(cleaned, epsg=config["crs"]["epsg"])
    labels = cluster_detections(projected, st_config)

    non_noise = labels[labels != -1]
    assert len(set(non_noise.tolist())) == 1, "chain should merge into a single cluster with the split off"


def test_chain_splits_with_gap_mitigation_on():
    config = load_config()
    df = _build_chain_df(config)

    st_config = STDBSCANConfig.from_dict(config["st_dbscan"])
    st_config.split_on_intra_event_gap = False
    cleaned = clean_firms(df, config["firms"]["min_confidence"])
    projected = project_to_crs(cleaned, epsg=config["crs"]["epsg"])

    # Confirm the step size used by the fixture (0.6 * eps_temporal) is what
    # we then deliberately undercut with a tight max_intra_event_gap_days.
    step_dt_days = 0.6 * config["st_dbscan"]["eps_temporal_days"]
    tight_gap = step_dt_days / 2.0

    st_config_split = STDBSCANConfig.from_dict(config["st_dbscan"])
    st_config_split.split_on_intra_event_gap = True
    st_config_split.max_intra_event_gap_days = tight_gap

    labels_merged = cluster_detections(projected, st_config)
    labels_split = cluster_detections(projected, st_config_split)

    n_clusters_merged = len(set(labels_merged[labels_merged != -1].tolist()))
    n_clusters_split = len(set(labels_split[labels_split != -1].tolist()))

    assert n_clusters_merged == 1
    assert n_clusters_split > 1, "tight max_intra_event_gap_days should demonstrably split the chained cluster"


# ---------------------------------------------------------------------------
# Output schema (CLAUDE.md section 6).
# ---------------------------------------------------------------------------


def test_event_records_match_section6_schema():
    config = load_config()
    st_config = STDBSCANConfig.from_dict(config["st_dbscan"])

    base_time = pd.Timestamp("2024-01-15T12:00:00Z")
    rows = []
    for i, (dx, dy, dh) in enumerate([(0, 0, 0), (100, 50, 1), (150, -80, 3)]):
        lat, lon = offset_latlon(4.65, -74.15, dx, dy)
        rows.append(
            {
                "latitude": lat,
                "longitude": lon,
                "confidence": "nominal",
                "frp": 10.0 + i,
                "timestamp": base_time + pd.Timedelta(hours=dh),
            }
        )
    df = make_detections(rows)
    events = run_pipeline_steps(df, config, st_config)

    assert len(events) == 1
    assert list(events.columns) == EVENT_SCHEMA_FIELDS

    row = events.iloc[0]
    assert isinstance(row["event_id"], str)
    assert isinstance(row["centroid_lat"], float)
    assert isinstance(row["centroid_lon"], float)
    assert isinstance(row["x_utm"], float)
    assert isinstance(row["y_utm"], float)
    assert isinstance(row["t_start"], pd.Timestamp)
    assert isinstance(row["t_end"], pd.Timestamp)
    assert isinstance(row["duration_h"], float)
    assert row["duration_h"] == pytest.approx(3.0)
    assert isinstance(row["n_detections"], (int, np.integer))
    assert row["n_detections"] == 3
    assert isinstance(row["frp_total"], float)
    assert row["frp_total"] == pytest.approx(10.0 + 11.0 + 12.0)
    assert isinstance(row["frp_peak"], float)
    assert row["frp_peak"] == pytest.approx(12.0)
    assert isinstance(row["extent"], float)
    assert row["extent"] >= 0.0
    assert isinstance(row["confidence_mix"], dict)
    assert row["municipality"] is None


# ---------------------------------------------------------------------------
# Open TODO, not silently skipped.
# ---------------------------------------------------------------------------


def test_january_2024_validation_is_not_yet_possible():
    """CLAUDE.md section 5 requires validating that the pipeline recovers the
    January 2024 Colombian fires as coherent, separate events. That needs
    real FIRMS/VIIRS raw data for that window, which is not in this repo yet
    (data/raw is gitignored and empty by design, see CLAUDE.md section 7 and
    8). This test documents the gap explicitly instead of skipping silently:
    it is a TODO, not a pass.
    """
    real_data_path = Path(__file__).resolve().parent.parent / "data" / "raw" / "firms_jan2024_colombia.csv"
    assert not real_data_path.exists(), (
        "Real January 2024 FIRMS data appeared in data/raw: wire up the actual "
        "validation test now (assert the known separate fires stay separate "
        "events) instead of this placeholder."
    )
