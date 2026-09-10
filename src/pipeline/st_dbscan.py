"""ST-DBSCAN clustering of fire detections into events (section 5 pipeline).

Citation: Birant, D., & Kut, A. (2007). ST-DBSCAN: An algorithm for
clustering spatial-temporal data. Data & Knowledge Engineering, 60(1),
208-221. https://doi.org/10.1016/j.datak.2006.01.013

Disclosure (do not overclaim the citation): the original paper formalizes
clustering on space plus one NON-SPATIAL ATTRIBUTE (e.g. temperature), with
time handled separately as a discrete "temporal neighbor" pre-filter
(consecutive days, or same day across consecutive years), not as a second
continuous Eps threshold. What this module implements instead is the common
practical adaptation used across the ST-DBSCAN software ecosystem: a genuine
continuous temporal Eps2 (|t_i - t_j| <= eps_temporal), combined with the
spatial Eps1 via the same AND/intersection rule the paper defines for its
Eps-neighborhood. This is the standard "eps_spatial/eps_temporal" scheme
CLAUDE.md section 5 asks for, but it is a substitution for the paper's literal
non-spatial-attribute Eps2, worth one disclosure sentence in the manuscript's
methods section.

Also not implemented: the paper's Delta-eps border-sharing rule (a point
already in one cluster can be pulled into an adjacent cluster if it passes an
attribute-similarity check against that cluster's running average) and the
density_factor diagnostic (defined in the paper but never operationalized in
its own published pseudocode). Border points here are assigned to whichever
cluster reaches them first, the standard (non-Birant-Kut) DBSCAN convention.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from scipy.spatial import cKDTree

NOISE = -1
_UNVISITED = -2


def st_dbscan(
    x: np.ndarray,
    y: np.ndarray,
    timestamps: pd.Series,
    eps_spatial_m: float,
    eps_temporal_days: float,
    min_pts: int = 1,
) -> np.ndarray:
    """Cluster points on space (meters) and time (days) jointly.

    A neighbor of point i is any point j with Euclidean distance <=
    eps_spatial_m AND absolute time difference <= eps_temporal_days
    (Birant and Kut's Eps-neighborhood, Retrieve_Neighbors(Eps1) INTERSECT
    Retrieve_Neighbors(Eps2), adapted with a continuous temporal Eps2, see
    module docstring). Uses a cKDTree spatial prefilter so no full O(n^2)
    distance matrix is built; the temporal test is then applied only to the
    spatially-close candidates returned by the tree.

    Parameters
    ----------
    x, y : arrays of projected coordinates, in meters (never degrees).
    timestamps : pandas Series of datetime64 (or convertible), one per point.
    eps_spatial_m : spatial radius, meters.
    eps_temporal_days : temporal radius, days.
    min_pts : minimum neighborhood size (including the point itself) for a
        point to be a core object. Section 5: keep this low, rely on the
        confidence filter (clean.py) to control false positives instead.

    Returns
    -------
    numpy array of int cluster labels, one per input point, -1 for noise
    (the DBSCAN convention).
    """
    n = len(x)
    if n == 0:
        return np.array([], dtype=int)

    coords = np.column_stack([np.asarray(x, dtype=float), np.asarray(y, dtype=float)])
    t = pd.to_datetime(pd.Series(timestamps).reset_index(drop=True))
    # Do not use t.astype("int64") here: that cast silently returns the raw
    # integer count in whatever the Series' underlying datetime64 resolution
    # happens to be (ns, us, or ms depending on pandas version and how the
    # timestamps were constructed), not necessarily nanoseconds. Dividing
    # that by 1e9 assumes nanoseconds and is wrong (off by up to 1000x) on
    # datetime64[us] or datetime64[ms] data, which silently inflates
    # eps_temporal_days by the same factor. Subtracting an explicit epoch and
    # calling total_seconds() is resolution independent.
    epoch = pd.Timestamp("1970-01-01", tz=t.dt.tz) if t.dt.tz is not None else pd.Timestamp("1970-01-01")
    t_seconds = (t - epoch).dt.total_seconds().to_numpy()
    eps_temporal_s = eps_temporal_days * 86400.0

    tree = cKDTree(coords)
    # Precompute spatial-only neighbor candidates once; the temporal filter
    # is cheap and applied on top of this smaller candidate set.
    spatial_neighbors = tree.query_ball_point(coords, r=eps_spatial_m)

    def region_query(i: int) -> np.ndarray:
        candidates = np.asarray(spatial_neighbors[i], dtype=int)
        if candidates.size == 0:
            return candidates
        within_time = np.abs(t_seconds[candidates] - t_seconds[i]) <= eps_temporal_s
        return candidates[within_time]

    labels = np.full(n, _UNVISITED, dtype=int)
    visited = np.zeros(n, dtype=bool)
    cluster_id = 0

    for i in range(n):
        if visited[i]:
            continue
        visited[i] = True
        neighbors = region_query(i)
        if neighbors.size < min_pts:
            labels[i] = NOISE
            continue

        cluster_id += 1
        labels[i] = cluster_id
        seeds = list(neighbors)
        pos = 0
        while pos < len(seeds):
            current = seeds[pos]
            pos += 1
            if not visited[current]:
                visited[current] = True
                current_neighbors = region_query(current)
                if current_neighbors.size >= min_pts:
                    seeds.extend(int(j) for j in current_neighbors)
            if labels[current] in (_UNVISITED, NOISE):
                labels[current] = cluster_id

    return labels


def split_clusters_on_gap(
    labels: np.ndarray,
    timestamps: pd.Series,
    max_intra_event_gap_days: float,
) -> np.ndarray:
    """Optionally split a cluster where consecutive detections (sorted by
    time) are separated by more than max_intra_event_gap_days.

    Why this exists: density clustering is transitive, a chain of close and
    continuous ignitions can merge what should be distinct fire events into
    one blob (section 5 "chaining" risk). This is a mitigation, not a
    default: it is a blunt post-hoc cut and can itself over-split a single
    slow-moving fire with an intermittent detection record. Off by default
    (st_dbscan.split_on_intra_event_gap in config/parameters.yaml).
    """
    labels = np.asarray(labels).copy()
    t = pd.to_datetime(pd.Series(timestamps).reset_index(drop=True))
    next_id = int(labels.max()) + 1 if labels.size and labels.max() >= 0 else 1

    for cluster_id in sorted(set(labels[labels != NOISE].tolist())):
        idx = np.where(labels == cluster_id)[0]
        if idx.size <= 1:
            continue
        order = idx[np.argsort(t.iloc[idx].to_numpy())]
        gaps_days = np.diff(t.iloc[order].to_numpy()).astype("timedelta64[s]").astype(float) / 86400.0
        split_points = np.where(gaps_days > max_intra_event_gap_days)[0]
        if split_points.size == 0:
            continue
        # Reassign everything after each split point to a fresh cluster id.
        segment_start = 0
        for cut in split_points:
            segment_start = cut + 1
            labels[order[segment_start:]] = next_id
            next_id += 1

    return labels


@dataclass
class STDBSCANConfig:
    eps_spatial_m: float
    eps_temporal_days: float
    min_pts: int
    split_on_intra_event_gap: bool = False
    max_intra_event_gap_days: float = 2.0

    @classmethod
    def from_dict(cls, d: dict) -> "STDBSCANConfig":
        return cls(
            eps_spatial_m=d["eps_spatial_m"],
            eps_temporal_days=d["eps_temporal_days"],
            min_pts=d["min_pts"],
            split_on_intra_event_gap=d.get("split_on_intra_event_gap", False),
            max_intra_event_gap_days=d.get("max_intra_event_gap_days", 2.0),
        )


def cluster_detections(df: pd.DataFrame, config: STDBSCANConfig) -> np.ndarray:
    """Convenience wrapper: run st_dbscan then the optional gap split, from a
    DataFrame with x_utm, y_utm and timestamp columns."""
    labels = st_dbscan(
        df["x_utm"].to_numpy(),
        df["y_utm"].to_numpy(),
        df["timestamp"],
        eps_spatial_m=config.eps_spatial_m,
        eps_temporal_days=config.eps_temporal_days,
        min_pts=config.min_pts,
    )
    if config.split_on_intra_event_gap:
        labels = split_clusters_on_gap(labels, df["timestamp"], config.max_intra_event_gap_days)
    return labels
