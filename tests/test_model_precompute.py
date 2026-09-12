"""Tests for src/model/precompute.py against hand-calculated values, not
data presented as if it were real Colombian fires.
"""

from __future__ import annotations

import math

from src.model.precompute import (
    SQM_PER_HECTARE,
    compute_cycle_time,
    compute_drops,
    compute_liters,
    compute_mbig,
    compute_requirement,
    precompute,
)
from src.model.schema import Fire, ModelParams, Scenario


def _tiny_params(t_base_fire_value: float = 1.0) -> ModelParams:
    """One base, one water point, one aircraft type, one scenario, one
    fire. window=4.0, ops_time=0.2, t_fire_water=0.5 -> cycle_time=1.2.
    t_base_fire is a parameter so a clip test can push it past window."""
    fire = Fire(
        fire_id="F1", x_utm=0.0, y_utm=0.0, ros=0.1, t_arrival=5.0, value_at_risk=1000.0
    )
    scenario = Scenario(scenario_id="s1", probability=1.0, fires=[fire])
    return ModelParams(
        bases=["B1"],
        water_points=["W1"],
        aircraft_types=["T1"],
        scenarios=[scenario],
        budget=100_000.0,
        window=4.0,
        ops_time=0.2,
        cvar_alpha=0.95,
        mean_risk_weight=0.0,
        initial_fire_area=10.0,
        liters_per_sqm=2.0,
        cost_base={"B1": 5000.0},
        cost_aircraft={"T1": 10_000.0},
        cost_water={"W1": 3000.0},
        tank={"T1": 1000.0},
        speed={"T1": 100.0},
        t_base_fire={("s1", "B1", "F1"): t_base_fire_value},
        t_fire_water={("s1", "F1", "W1"): 0.5},
    )


def test_cycle_time_matches_formula():
    params = _tiny_params()
    cycle_time = compute_cycle_time(params)
    # 2 * t_fire_water + ops_time = 2*0.5 + 0.2 = 1.2
    assert cycle_time[("s1", "F1", "W1", "T1")] == 1.2


def test_drops_matches_formula_when_reachable():
    params = _tiny_params(t_base_fire_value=1.0)
    cycle_time = compute_cycle_time(params)
    drops = compute_drops(params, cycle_time)
    # floor((4.0 - 1.0) / 1.2) = floor(2.5) = 2
    assert drops[("s1", "B1", "F1", "W1", "T1")] == 2


def test_drops_clipped_at_zero_when_base_too_far():
    # t_base_fire = 5.0 > window = 4.0, so (window - t_base_fire)/cycle_time
    # is negative; the section 5.2 max(0, ...) clip must apply, not a
    # negative drop count.
    params = _tiny_params(t_base_fire_value=5.0)
    cycle_time = compute_cycle_time(params)
    drops = compute_drops(params, cycle_time)
    raw = math.floor((params.window - 5.0) / 1.2)
    assert raw < 0, "test setup should produce a negative raw value to exercise the clip"
    assert drops[("s1", "B1", "F1", "W1", "T1")] == 0


def test_liters_is_drops_times_tank():
    params = _tiny_params(t_base_fire_value=1.0)
    cycle_time = compute_cycle_time(params)
    drops = compute_drops(params, cycle_time)
    liters = compute_liters(params, drops)
    # drops=2, tank=1000 -> 2000
    assert liters[("s1", "B1", "F1", "W1", "T1")] == 2000.0


def test_requirement_matches_exponential_formula():
    # initial_fire_area is in hectares, liters_per_sqm per square meter:
    # the hectare-to-m^2 conversion must appear exactly once (CLAUDE.md
    # section 10, 2026-09-12: it was missing before that date).
    params = _tiny_params()
    requirement = compute_requirement(params)
    expected = 2.0 * 10.0 * SQM_PER_HECTARE * math.exp(0.1 * 5.0)
    assert requirement[("s1", "F1")] == expected


def test_mbig_is_floor_budget_over_cost_aircraft():
    params = _tiny_params()
    mbig = compute_mbig(params)
    # floor(100000 / 10000) = 10
    assert mbig["T1"] == 10


def test_precompute_bundles_all_four_tables():
    params = _tiny_params()
    pre = precompute(params)
    assert pre.cycle_time[("s1", "F1", "W1", "T1")] == 1.2
    assert pre.drops[("s1", "B1", "F1", "W1", "T1")] == 2
    assert pre.liters[("s1", "B1", "F1", "W1", "T1")] == 2000.0
    assert pre.requirement[("s1", "F1")] == 2.0 * 10.0 * SQM_PER_HECTARE * math.exp(0.5)
    assert pre.Mbig["T1"] == 10
