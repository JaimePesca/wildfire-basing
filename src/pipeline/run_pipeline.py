"""End-to-end CLI for the FIRMS to Event pipeline (section 5).

Wires together, in order: load_firms_csv (io.py), clean_firms (clean.py),
project_to_crs (project.py), cluster_detections (st_dbscan.py), build_events
(events.py). Reads parameters from config/parameters.yaml and writes one
Event record per detected fire event to the requested output path.

Usage:
    python -m src.pipeline.run_pipeline --input data/raw/firms_export.csv \
        --output data/processed/events.csv \
        --config config/parameters.yaml
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd
import yaml

from .clean import clean_firms
from .events import build_events
from .io import load_firms_csv
from .project import project_to_crs
from .st_dbscan import STDBSCANConfig, cluster_detections


def load_config(config_path: str) -> dict:
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def run_pipeline(input_path: str, output_path: str, config: dict) -> pd.DataFrame:
    """Run the full pipeline and return the Event record DataFrame.

    Also writes the result to output_path (CSV, inferred from suffix; use
    .parquet for a binary format if preferred).
    """
    df = load_firms_csv(input_path)
    df = clean_firms(df, config["firms"]["min_confidence"])
    df = project_to_crs(df, epsg=config["crs"]["epsg"])

    st_config = STDBSCANConfig.from_dict(config["st_dbscan"])
    labels = cluster_detections(df, st_config)

    events = build_events(df, labels)

    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    if out.suffix.lower() == ".parquet":
        events.to_parquet(out, index=False)
    else:
        events.to_csv(out, index=False)

    return events


def main() -> None:
    parser = argparse.ArgumentParser(
        description="FIRMS clean, project, ST-DBSCAN cluster, derive Event records."
    )
    parser.add_argument("--input", required=True, help="Path to a FIRMS CSV export.")
    parser.add_argument("--output", required=True, help="Path to write Event records to (CSV or Parquet).")
    parser.add_argument(
        "--config",
        default="config/parameters.yaml",
        help="Path to config/parameters.yaml (default: config/parameters.yaml).",
    )
    args = parser.parse_args()

    config = load_config(args.config)
    events = run_pipeline(args.input, args.output, config)
    print(f"Wrote {len(events)} event records to {args.output}")


if __name__ == "__main__":
    main()
