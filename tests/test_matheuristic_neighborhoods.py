"""Tests for src/matheuristic/neighborhoods.py's geographic LNS destroy
operator, using small synthetic coordinate fixtures, not real candidate
site data."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from src.matheuristic.neighborhoods import _nearest_site_ids, _random_site_ids, pick_neighborhood


def _sites(rows: list[tuple[str, float, float]]) -> pd.DataFrame:
    return pd.DataFrame(rows, columns=["site_id", "x_utm", "y_utm"])


def test_nearest_site_ids_orders_by_distance():
    sites = _sites([("A", 0.0, 0.0), ("B", 10.0, 0.0), ("C", 1.0, 0.0), ("D", 100.0, 0.0)])
    result = _nearest_site_ids(0.0, 0.0, sites, n=2)
    assert result == ["A", "C"]


def test_nearest_site_ids_caps_at_available_count():
    sites = _sites([("A", 0.0, 0.0), ("B", 1.0, 0.0)])
    result = _nearest_site_ids(0.0, 0.0, sites, n=10)
    assert set(result) == {"A", "B"}


def test_nearest_site_ids_empty_sites_returns_empty():
    sites = _sites([])
    assert _nearest_site_ids(0.0, 0.0, sites, n=3) == []


def test_pick_neighborhood_seeded_from_a_base_includes_that_base():
    # Bases far apart, water points clustered near B1; whichever site gets
    # drawn as seed, the nearest n_bases/n_water to it must include itself
    # (distance 0), and the closer of its own cluster.
    bases = _sites([("B1", 0.0, 0.0), ("B2", 0.0, 0.0), ("B3", 1000.0, 0.0)])
    water = _sites([("W1", 0.0, 0.0), ("W2", 5000.0, 0.0)])

    for seed_val in range(20):
        rng = np.random.default_rng(seed_val)
        free_bases, free_water = pick_neighborhood(bases, water, rng, n_bases=1, n_water=1)
        assert len(free_bases) == 1
        assert len(free_water) == 1


def test_pick_neighborhood_caps_at_available_sites():
    bases = _sites([("B1", 0.0, 0.0)])
    water = _sites([("W1", 1.0, 1.0)])
    rng = np.random.default_rng(0)
    free_bases, free_water = pick_neighborhood(bases, water, rng, n_bases=5, n_water=5)
    assert free_bases == {"B1"}
    assert free_water == {"W1"}


def test_pick_neighborhood_raises_when_nothing_to_seed_from():
    empty = _sites([])
    with pytest.raises(ValueError):
        pick_neighborhood(empty, empty, np.random.default_rng(0), n_bases=1, n_water=1)


def test_random_site_ids_returns_requested_count_from_whole_set():
    sites = _sites([("A", 0.0, 0.0), ("B", 100.0, 0.0), ("C", 200.0, 0.0), ("D", 300.0, 0.0)])
    rng = np.random.default_rng(0)
    result = _random_site_ids(rng, sites, n=2)
    assert len(result) == 2
    assert set(result) <= {"A", "B", "C", "D"}


def test_random_site_ids_caps_at_available_count():
    sites = _sites([("A", 0.0, 0.0), ("B", 1.0, 0.0)])
    result = _random_site_ids(np.random.default_rng(0), sites, n=10)
    assert set(result) == {"A", "B"}


def test_random_site_ids_empty_sites_returns_empty():
    assert _random_site_ids(np.random.default_rng(0), _sites([]), n=3) == []


def test_random_site_ids_can_pick_geographically_distant_sites_together():
    """The whole point of the random operator (CLAUDE.md section 10,
    2026-09-04): unlike _nearest_site_ids, it is not restricted to one
    seed's local cluster, so two far-apart sites CAN land in the same draw.
    Over enough seeds, at least one draw must include both A and D (0 and
    1,000,000 apart), which _nearest_site_ids with n=2 could never do if
    B/C sit strictly between them."""
    sites = _sites([("A", 0.0, 0.0), ("B", 10.0, 0.0), ("C", 20.0, 0.0), ("D", 1_000_000.0, 0.0)])
    found_both = False
    for seed_val in range(200):
        result = set(_random_site_ids(np.random.default_rng(seed_val), sites, n=2))
        if result == {"A", "D"}:
            found_both = True
            break
    assert found_both


def test_pick_neighborhood_random_destroy_prob_one_ignores_geography():
    """random_destroy_prob=1.0 must always take the random branch: the seed
    site itself (distance 0, always the geographic operator's top pick)
    should NOT always appear when random selection is forced."""
    bases = _sites([("B1", 0.0, 0.0), ("B2", 10.0, 0.0), ("B3", 1_000_000.0, 0.0)])
    water = _sites([("W1", 0.0, 0.0)])
    ever_excluded_seed_cluster = False
    for seed_val in range(50):
        rng = np.random.default_rng(seed_val)
        free_bases, _ = pick_neighborhood(bases, water, rng, n_bases=1, n_water=1, random_destroy_prob=1.0)
        if free_bases == {"B3"}:
            ever_excluded_seed_cluster = True
            break
    assert ever_excluded_seed_cluster


def test_pick_neighborhood_random_destroy_prob_zero_matches_original_geographic_behavior():
    bases = _sites([("B1", 0.0, 0.0), ("B2", 1000.0, 0.0)])
    water = _sites([("W1", 0.0, 0.0)])
    for seed_val in range(10):
        geographic = pick_neighborhood(bases, water, np.random.default_rng(seed_val), n_bases=1, n_water=1)
        explicit_zero = pick_neighborhood(
            bases, water, np.random.default_rng(seed_val), n_bases=1, n_water=1, random_destroy_prob=0.0
        )
        assert geographic == explicit_zero
