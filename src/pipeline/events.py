"""Building Event records from clustered FIRMS detections (section 5 pipeline).

One Event record is built per non-noise cluster label (ST-DBSCAN labels of -1,
the DBSCAN noise convention, are dropped). The output fields match the Event
record schema in CLAUDE.md section 6 exactly:

event_id, centroid_lat, centroid_lon, x_utm, y_utm, t_start, t_end,
duration_h, n_detections, frp_total, frp_peak, extent, confidence_mix,
municipality.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

try:
    from scipy.spatial import ConvexHull
    from scipy.spatial import QhullError
except ImportError:  # pragma: no cover, scipy is a required dependency here
    ConvexHull = None
    QhullError = Exception


def _extent_m2(x: np.ndarray, y: np.ndarray) -> float:
    """Convex hull area in square meters for a cluster.

    Uses scipy.spatial.ConvexHull when the cluster has 3 or more points and
    they are not collinear (ConvexHull raises QhullError on degenerate input,
    e.g. collinear points or all points coincident). Falls back to the
    bounding-box area for clusters with fewer than 3 points, or when the hull
    cannot be built, since a hull is not defined for a line or a single point.
    """
    n = len(x)
    if n >= 3 and ConvexHull is not None:
        points = np.column_stack([x, y])
        try:
            hull = ConvexHull(points)
            return float(hull.volume)  # in 2D, ConvexHull.volume is the area
        except QhullError:
            pass
    # Bounding-box fallback (covers n < 3 and degenerate/collinear clusters).
    width = float(np.max(x) - np.min(x))
    height = float(np.max(y) - np.min(y))
    return width * height


def _confidence_mix(confidence: pd.Series) -> dict:
    """Count of detections per confidence level present in the cluster.

    Kept as raw counts (not proportions) so both the level breakdown and the
    total n_detections can be recovered from the record; values are the
    original confidence strings/numbers as seen in the cleaned data, not
    normalized into low/nominal/high, since MODIS confidence is numeric.
    """
    counts = confidence.astype(str).value_counts(dropna=False)
    return {str(k): int(v) for k, v in counts.items()}


def build_events(df: pd.DataFrame, labels: np.ndarray, id_prefix: str = "evt") -> pd.DataFrame:
    """Build one Event record per non-noise cluster.

    Parameters
    ----------
    df : cleaned, projected detections, expected to have at minimum the
        columns latitude, longitude, x_utm, y_utm, timestamp, confidence,
        frp. Must be aligned index-for-index with labels (same length,
        same order); reset_index before calling if in doubt.
    labels : cluster label per row, -1 for noise (DBSCAN convention, as
        returned by st_dbscan.cluster_detections).
    id_prefix : prefix for the generated event_id strings.

    Returns
    -------
    DataFrame with exactly the section 6 Event record schema columns:
    event_id, centroid_lat, centroid_lon, x_utm, y_utm, t_start, t_end,
    duration_h, n_detections, frp_total, frp_peak, extent, confidence_mix,
    municipality.
    """
    if len(df) != len(labels):
        raise ValueError(
            f"df and labels must be the same length (got {len(df)} and {len(labels)}); "
            "reset the index and realign before building events."
        )

    work = df.reset_index(drop=True).copy()
    work["_cluster"] = np.asarray(labels)

    records = []
    for cluster_id, group in work.groupby("_cluster", sort=True):
        if cluster_id == -1:
            continue  # noise, not an event

        x = group["x_utm"].to_numpy(dtype=float)
        y = group["y_utm"].to_numpy(dtype=float)
        t = pd.to_datetime(group["timestamp"])
        frp = pd.to_numeric(group["frp"], errors="coerce") if "frp" in group.columns else pd.Series(dtype=float)

        t_start = t.min()
        t_end = t.max()
        duration_h = float((t_end - t_start).total_seconds() / 3600.0)

        records.append(
            {
                "event_id": f"{id_prefix}_{int(cluster_id):06d}",
                "centroid_lat": float(group["latitude"].mean()),
                "centroid_lon": float(group["longitude"].mean()),
                "x_utm": float(x.mean()),
                "y_utm": float(y.mean()),
                "t_start": t_start,
                "t_end": t_end,
                "duration_h": duration_h,
                "n_detections": int(len(group)),
                "frp_total": float(frp.sum()) if len(frp) else 0.0,
                "frp_peak": float(frp.max()) if len(frp) and frp.notna().any() else 0.0,
                "extent": _extent_m2(x, y),
                "confidence_mix": _confidence_mix(group["confidence"]) if "confidence" in group.columns else {},
                # Municipality join needs a Colombian municipality boundary
                # layer (DIVIPOLA or IGAC, see CLAUDE.md section 8) which is
                # not yet present in data/raw. Left as None rather than
                # fabricated; wire in the spatial join once that layer lands.
                "municipality": None,
            }
        )

    columns = [
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
    return pd.DataFrame.from_records(records, columns=columns)
