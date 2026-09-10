"""Loading FIRMS CSV exports (section 5 pipeline, first step).

Implemented against the documented FIRMS CSV export schema (VIIRS or MODIS
active fire products): latitude, longitude, acq_date, acq_time, confidence,
frp, satellite, instrument, daynight, version. This module does not assume
any specific file exists on disk, call load_firms_csv(path) once real FIRMS
data has been downloaded into data/raw (see CLAUDE.md section 8).
"""

from __future__ import annotations

import pandas as pd

# Columns typically present in a standard FIRMS CSV export.
FIRMS_EXPECTED_COLUMNS = [
    "latitude",
    "longitude",
    "acq_date",
    "acq_time",
    "confidence",
    "frp",
    "satellite",
    "instrument",
    "daynight",
    "version",
]

# Columns that are useful downstream but not strictly required to build a
# timestamp; filled with NA when missing so later steps can rely on them.
_OPTIONAL_COLUMNS = ("confidence", "frp", "satellite", "instrument", "daynight", "version")

_REQUIRED_COLUMNS = ("latitude", "longitude", "acq_date", "acq_time")


def load_firms_csv(path: str) -> pd.DataFrame:
    """Load a standard FIRMS CSV export and return a standardized DataFrame.

    Adds a parsed UTC timestamp column ("timestamp") built from acq_date
    (YYYY-MM-DD) and acq_time (HHMM, zero padded; FIRMS reports this in UTC).
    Raises a clear error if required columns are missing rather than silently
    proceeding against the wrong schema.
    """
    df = pd.read_csv(path, dtype={"acq_time": str, "acq_date": str})

    missing = [c for c in _REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(
            f"FIRMS CSV at {path} is missing required columns: {missing}. "
            f"Expected a standard FIRMS export with columns like {FIRMS_EXPECTED_COLUMNS}."
        )

    # acq_time is HHMM, sometimes without leading zeros (e.g. "5" for 00:05).
    acq_time_padded = df["acq_time"].astype(str).str.zfill(4)
    timestamp_str = df["acq_date"].astype(str) + acq_time_padded
    df["timestamp"] = pd.to_datetime(timestamp_str, format="%Y-%m-%d%H%M", utc=True)

    for col in _OPTIONAL_COLUMNS:
        if col not in df.columns:
            df[col] = pd.NA

    return df
