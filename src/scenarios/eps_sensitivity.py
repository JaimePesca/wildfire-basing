"""Sensitivity analysis of ST-DBSCAN event clustering to eps_spatial and
eps_temporal (section 5 pipeline; CLAUDE.md is explicit that this is
mandatory, not optional, since it is what makes the event definition
replicable rather than an arbitrary parameter choice).

This module implements only the sensitivity-on-eps part of the src/scenarios
folder scope in CLAUDE.md section 7 ("events to SAA scenarios, sensitivity on
eps"). The events-to-SAA-scenarios sampler is a separate, later task that
depends on still-open modeling decisions (CLAUDE.md section 10) and is
deliberately not built here.

Reuses src/pipeline building blocks (st_dbscan.cluster_detections,
st_dbscan.STDBSCANConfig) rather than reimplementing clustering; this module
only sweeps eps_spatial_m/eps_temporal_days over a grid and summarizes the
resulting cluster structure.
"""

from __future__ import annotations

import argparse
import itertools
from pathlib import Path

import pandas as pd
import yaml

from src.pipeline.clean import clean_firms
from src.pipeline.io import load_firms_csv
from src.pipeline.project import project_to_crs
from src.pipeline.st_dbscan import NOISE, STDBSCANConfig, cluster_detections

# Section 5: eps_spatial about 750 to 1000 m, eps_temporal about 1 to 2 days.
# Each default grid includes at least one point below and one point above its
# documented range, so the sensitivity is actually visible rather than only
# probing the interior of the recommended band.
DEFAULT_EPS_SPATIAL_GRID_M = [500.0, 750.0, 850.0, 1000.0, 1500.0]
DEFAULT_EPS_TEMPORAL_GRID_DAYS = [0.5, 1.0, 1.5, 2.0, 3.0]

SENSITIVITY_TABLE_COLUMNS = [
    "eps_spatial_m",
    "eps_temporal_days",
    "n_events",
    "n_noise",
    "median_event_size",
    "largest_event_size",
]


def _cluster_sizes(labels) -> pd.Series:
    """Event sizes (detections per non-noise cluster), as a pandas Series."""
    non_noise = labels[labels != NOISE]
    if non_noise.size == 0:
        return pd.Series(dtype=int)
    return pd.Series(non_noise).value_counts()


def run_eps_sensitivity(
    df: pd.DataFrame,
    eps_spatial_grid_m: list[float] = DEFAULT_EPS_SPATIAL_GRID_M,
    eps_temporal_grid_days: list[float] = DEFAULT_EPS_TEMPORAL_GRID_DAYS,
    min_pts: int = 1,
) -> pd.DataFrame:
    """Run ST-DBSCAN over every (eps_spatial, eps_temporal) combination in the
    grid and report one summary row per combination.

    Parameters
    ----------
    df : cleaned and projected detections (output of clean.clean_firms then
        project.project_to_crs), must have x_utm, y_utm and timestamp
        columns. This function does not clean or project; reuse the pipeline
        steps for that, do not duplicate them here.
    eps_spatial_grid_m, eps_temporal_grid_days : grids to sweep, defaults span
        the documented section 5 ranges plus a point outside each end.
    min_pts : passed through to STDBSCANConfig; section 5 says keep this low.

    Returns
    -------
    DataFrame with one row per grid combination: eps_spatial_m,
    eps_temporal_days, n_events (non-noise cluster count), n_noise (noise
    point count), median_event_size, largest_event_size.
    """
    rows = []
    for eps_spatial_m, eps_temporal_days in itertools.product(eps_spatial_grid_m, eps_temporal_grid_days):
        config = STDBSCANConfig(
            eps_spatial_m=eps_spatial_m,
            eps_temporal_days=eps_temporal_days,
            min_pts=min_pts,
        )
        labels = cluster_detections(df, config)
        sizes = _cluster_sizes(labels)
        n_noise = int((labels == NOISE).sum())

        rows.append(
            {
                "eps_spatial_m": eps_spatial_m,
                "eps_temporal_days": eps_temporal_days,
                "n_events": int(sizes.shape[0]),
                "n_noise": n_noise,
                "median_event_size": float(sizes.median()) if not sizes.empty else 0.0,
                "largest_event_size": int(sizes.max()) if not sizes.empty else 0,
            }
        )

    return pd.DataFrame(rows, columns=SENSITIVITY_TABLE_COLUMNS)


def load_config(config_path: str) -> dict:
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Sensitivity of ST-DBSCAN event clustering to eps_spatial_m and eps_temporal_days."
    )
    parser.add_argument("--input", required=True, help="Path to a FIRMS CSV export.")
    parser.add_argument("--output", required=True, help="Path to write the sensitivity table to (CSV).")
    parser.add_argument(
        "--config",
        default="config/parameters.yaml",
        help="Path to config/parameters.yaml, used for crs.epsg and firms.min_confidence (default: config/parameters.yaml).",
    )
    parser.add_argument(
        "--eps-spatial-grid-m",
        type=float,
        nargs="+",
        default=None,
        help="Override the eps_spatial_m grid (meters), space separated.",
    )
    parser.add_argument(
        "--eps-temporal-grid-days",
        type=float,
        nargs="+",
        default=None,
        help="Override the eps_temporal_days grid (days), space separated.",
    )
    args = parser.parse_args()

    config = load_config(args.config)
    df = load_firms_csv(args.input)
    df = clean_firms(df, config["firms"]["min_confidence"])
    df = project_to_crs(df, epsg=config["crs"]["epsg"])

    table = run_eps_sensitivity(
        df,
        eps_spatial_grid_m=args.eps_spatial_grid_m or DEFAULT_EPS_SPATIAL_GRID_M,
        eps_temporal_grid_days=args.eps_temporal_grid_days or DEFAULT_EPS_TEMPORAL_GRID_DAYS,
        min_pts=config["st_dbscan"]["min_pts"],
    )

    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    table.to_csv(out, index=False)
    print(f"Wrote sensitivity table with {len(table)} rows to {args.output}")


if __name__ == "__main__":
    main()
