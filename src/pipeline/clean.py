"""Cleaning FIRMS detections: confidence filtering, deduplication, lat/lon validation.

Section 5: the real lever against false positives is the confidence filter,
not min_pts (min_pts is kept low so single-detection fires are not dropped).
"""

from __future__ import annotations

import pandas as pd

# VIIRS confidence is categorical, ordered low < nominal < high. The actual
# CSV encodes this as single lowercase letters l/n/h, confirmed two ways: (1)
# empirically, real VIIRS_SNPP_SP rows downloaded for Cundinamarca, January
# 2024 contain exactly the values "l", "n", "h" in the confidence column, (2)
# the NASA Earthdata FIRMS forum ("FIRMS: What is the detection confidence?",
# https://forum.earthdata.nasa.gov/viewtopic.php?t=5182) states VIIRS
# confidence is "high (h), nominal (n), or low (l)". The full words are also
# accepted here (config readability, and in case a different export variant
# spells them out) but the single letters are the primary real-world case,
# an earlier version of this filter only recognized the full words and
# silently dropped every VIIRS row as a result.
VIIRS_CONFIDENCE_ORDER = {
    "low": 0, "l": 0,
    "nominal": 1, "n": 1,
    "high": 2, "h": 2,
}


def _keep_row(confidence, min_confidence) -> bool:
    if pd.isna(confidence):
        return False
    conf_str = str(confidence).strip().lower()

    if conf_str in VIIRS_CONFIDENCE_ORDER:
        # VIIRS: categorical low/nominal/high (or l/n/h).
        threshold = str(min_confidence).strip().lower() if isinstance(min_confidence, str) else "nominal"
        if threshold not in VIIRS_CONFIDENCE_ORDER:
            threshold = "nominal"
        return VIIRS_CONFIDENCE_ORDER[conf_str] >= VIIRS_CONFIDENCE_ORDER[threshold]

    # MODIS: numeric 0 to 100.
    try:
        conf_num = float(confidence)
    except (TypeError, ValueError):
        return False
    if isinstance(min_confidence, str):
        # A categorical threshold configured against a numeric row: this is a
        # configuration mismatch, fall back to a conservative default instead
        # of guessing a categorical-to-numeric mapping.
        threshold_num = 50.0
    else:
        threshold_num = float(min_confidence)
    return conf_num >= threshold_num


def filter_by_confidence(df: pd.DataFrame, min_confidence) -> pd.DataFrame:
    """Filter detections by confidence, handling both FIRMS confidence encodings.

    VIIRS confidence is categorical (low, nominal, high). MODIS confidence is
    numeric (0 to 100). min_confidence may be given as either a VIIRS level
    string or a MODIS numeric threshold; it is interpreted per row based on
    whether that row's own confidence value is categorical or numeric.
    """
    if df.empty:
        return df.copy()
    mask = df["confidence"].apply(lambda c: _keep_row(c, min_confidence))
    return df.loc[mask].reset_index(drop=True)


def drop_exact_duplicates(df: pd.DataFrame) -> pd.DataFrame:
    """Drop exact duplicate detection rows."""
    return df.drop_duplicates().reset_index(drop=True)


def validate_latlon(df: pd.DataFrame) -> pd.DataFrame:
    """Drop rows with missing or out-of-range latitude/longitude."""
    mask = (
        df["latitude"].notna()
        & df["longitude"].notna()
        & df["latitude"].between(-90.0, 90.0)
        & df["longitude"].between(-180.0, 180.0)
    )
    return df.loc[mask].reset_index(drop=True)


def clean_firms(df: pd.DataFrame, min_confidence) -> pd.DataFrame:
    """Run the full cleaning sequence: lat/lon validation, dedupe, confidence filter."""
    df = validate_latlon(df)
    df = drop_exact_duplicates(df)
    df = filter_by_confidence(df, min_confidence)
    return df
