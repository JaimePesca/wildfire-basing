"""Tests for src/model/costs.py's uniform swept cost_base/cost_water
treatment (CLAUDE.md section 4/10 site-cost gap, decided 2026-08-30)."""

from __future__ import annotations

from src.model.costs import COST_BASE_RANGE_COP, COST_WATER_RANGE_COP, uniform_cost


def test_uniform_cost_applies_same_value_to_every_site():
    result = uniform_cost(["B1", "B2", "B3"], 1_000_000.0)
    assert result == {"B1": 1_000_000.0, "B2": 1_000_000.0, "B3": 1_000_000.0}


def test_uniform_cost_empty_sites_gives_empty_dict():
    assert uniform_cost([], 1_000_000.0) == {}


def test_ranges_are_positive_and_low_below_high():
    low, high = COST_BASE_RANGE_COP
    assert 0 < low < high
    low, high = COST_WATER_RANGE_COP
    assert 0 < low < high


def test_base_range_is_higher_than_water_range():
    # A base (aerodrome activation) should be documented as costlier to open
    # than a single water point (accessibility/staging only), per the
    # module docstring's benchmark scaling.
    assert COST_BASE_RANGE_COP[0] > COST_WATER_RANGE_COP[0]
    assert COST_BASE_RANGE_COP[1] > COST_WATER_RANGE_COP[1]
