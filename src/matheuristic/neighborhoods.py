"""LNS destroy operator (Shaw 1998, CP98, LNCS 1520, pp. 417-431): picks
which candidate bases and water points get freed ("destroyed") for one
fix-and-optimize iteration (CLAUDE.md section 3, decided 2026-08-30 in
form: geographic proximity, Shaw's own "relatedness" principle, over pure
random selection or a fixed systematic partition).

A random seed site (a base or a water point, drawn from the combined real
candidate set) anchors each neighborhood; the n_bases nearest candidate
bases and n_water nearest candidate water points to that seed (real
Euclidean distance in the already-projected x_utm/y_utm coordinates, same
CRS as the rest of this repo, EPSG:9377) are freed together. This is a
deliberate fit to this paper's own central insight (CLAUDE.md section 2):
the base-water coupling is a cycle-time/distance relationship, so sites an
aircraft would actually cycle between are exactly the sites worth jointly
reconsidering in one sub-MILP solve, not an arbitrary random subset.

bases/water_points here are plain site-location DataFrames (site_id,
x_utm, y_utm), matching data/processed/candidate_bases.csv and
candidate_water.csv, not schema.ModelParams: ModelParams intentionally
carries no raw coordinates (see travel_times.py's own docstring), only
derived travel times, so neighborhood construction needs this separate,
smaller input.

Random destroy operator, ADDED 2026-09-04 (CLAUDE.md section 10): a real
run against the actual candidate catalog (src/experiments/
experiment2_matheuristic_vs_gurobi.py) found the pure-geographic operator
above can get permanently stuck strictly short of the true optimum. Cause,
confirmed by direct reproduction: the true optimal solution needed to close
an already-open, badly-placed base 174 km away from the actually-best base
(only one aircraft was ever affordable under the test budget, so this was a
"move the one aircraft's base" decision, not an "add a second base"
decision). Freeing only sites near ONE random seed can never place two
sites 174 km apart in the same free set, so the sub-MILP is never even
offered the chance to jointly reconsider both, no matter how many
iterations run (confirmed directly: 200 iterations, 101 run, zero
additional improvement past the first). pick_neighborhood's new
random_destroy_prob parameter fixes this the standard ALNS way (Ropke and
Pisinger 2006, "An Adaptive Large Neighborhood Search Heuristic for the
Pickup and Delivery Problem with Time Windows," Transportation Science
40(4):455-472, DOI 10.1287/trsc.1050.0135, verified 2026-09-04 against the
publisher page, existence/year/venue/page numbers all confirmed): with
that probability, skip geographic proximity entirely for one iteration and
free n_bases/n_water sites drawn uniformly at random from the WHOLE
candidate set instead, which CAN place two arbitrarily distant sites in the
same free set, restoring the model's ability to propose exactly this kind
of long-range trade. Default 0.0 keeps the original pure-geographic
behavior (CLAUDE.md section 10, 2026-08-30) unchanged for any caller that
does not opt in, including every existing test of pick_neighborhood itself.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def _nearest_site_ids(seed_x: float, seed_y: float, sites: pd.DataFrame, n: int) -> list[str]:
    """The n candidate site_ids in `sites` closest to (seed_x, seed_y) by
    Euclidean distance, nearest first. Returns all of them if n exceeds the
    number of available sites, never raises for that reason."""
    if sites.empty or n <= 0:
        return []
    distances = np.hypot(sites["x_utm"].to_numpy() - seed_x, sites["y_utm"].to_numpy() - seed_y)
    order = np.argsort(distances)[: min(n, len(sites))]
    return list(sites["site_id"].to_numpy()[order])


def _random_site_ids(rng: np.random.Generator, sites: pd.DataFrame, n: int) -> list[str]:
    """n candidate site_ids drawn uniformly at random from `sites`, no
    geographic weighting, unlike _nearest_site_ids. Returns all of them if n
    exceeds the number of available sites, never raises for that reason."""
    if sites.empty or n <= 0:
        return []
    n = min(n, len(sites))
    idx = rng.choice(len(sites), size=n, replace=False)
    return list(sites["site_id"].to_numpy()[idx])


def pick_neighborhood(
    bases: pd.DataFrame,
    water_points: pd.DataFrame,
    rng: np.random.Generator,
    n_bases: int,
    n_water: int,
    random_destroy_prob: float = 0.0,
) -> tuple[set[str], set[str]]:
    """Pick the set of site ids to free for one LNS iteration.

    With probability (1 - random_destroy_prob) (the default, and always
    when random_destroy_prob=0.0): pick one random seed site from bases and
    water_points combined, then return the n_bases nearest candidate bases
    and n_water nearest candidate water points to that seed (the original
    geographic-proximity operator, CLAUDE.md section 10, 2026-08-30).

    With probability random_destroy_prob: skip geography entirely and
    return n_bases/n_water sites drawn uniformly at random from the whole
    candidate set instead (ADDED 2026-09-04, see this module's docstring for
    why: a purely geographic operator can permanently miss a beneficial
    trade between two sites that are far apart under the geographic
    metric).

    Raises ValueError if both bases and water_points are empty (nothing to
    seed a neighborhood from)."""
    if bases.empty and water_points.empty:
        raise ValueError("pick_neighborhood needs at least one candidate base or water point")

    if rng.random() < random_destroy_prob:
        return set(_random_site_ids(rng, bases, n_bases)), set(_random_site_ids(rng, water_points, n_water))

    seed_pool = pd.concat(
        [bases[["site_id", "x_utm", "y_utm"]], water_points[["site_id", "x_utm", "y_utm"]]],
        ignore_index=True,
    )
    seed_idx = rng.integers(0, len(seed_pool))
    seed_x = float(seed_pool.iloc[seed_idx]["x_utm"])
    seed_y = float(seed_pool.iloc[seed_idx]["y_utm"])

    free_bases = set(_nearest_site_ids(seed_x, seed_y, bases, n_bases))
    free_water = set(_nearest_site_ids(seed_x, seed_y, water_points, n_water))
    return free_bases, free_water
