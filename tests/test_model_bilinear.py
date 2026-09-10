"""Tests for src/model/bilinear.py: the literal bilinear MIQCP, built
directly against gurobipy (CONFIRMED WORKING 2026-08-30, CLAUDE.md section
10). Reuses test_model_milp.py's exact synthetic instances: since
bilinear.py and milp.py are two reformulations of the same section 5.2
model (one with the exact McCormick linearization, one with the literal
bilinear product), their optimal objective values must match exactly on
every instance both can solve, which is the actual point of experiment 1
(CLAUDE.md section 9) and the main thing these tests check.
"""

from __future__ import annotations

import pytest

from src.model.bilinear import solve_bilinear_model
from src.model.milp import solve_model
from src.model.precompute import precompute
from src.model.schema import Fire, ModelParams, Scenario
from tests.test_model_milp import VALUE_AT_RISK, _base_case


def test_fire_contained_when_budget_allows_near_base():
    params = _base_case(budget=9000.0, both_bases=True)
    pre = precompute(params)
    result = solve_bilinear_model(params, pre)

    assert result.status == "Optimal"
    assert result.base_open["B_near"] is True
    assert result.base_open["B_far"] is False
    assert result.water_open["W1"] is True
    assert result.escape[("s1", "F1")] is False
    assert result.delivered[("s1", "F1")] >= 100.0 - 1e-6
    assert result.objective_value == pytest.approx(0.0, abs=1e-6)


def test_fire_escapes_when_budget_too_small_to_open_anything():
    params = _base_case(budget=2000.0, both_bases=False)
    pre = precompute(params)
    result = solve_bilinear_model(params, pre)

    assert result.status == "Optimal"
    assert result.base_open["B_near"] is False
    assert result.escape[("s1", "F1")] is True
    assert result.delivered[("s1", "F1")] == pytest.approx(0.0)
    assert result.objective_value == pytest.approx(VALUE_AT_RISK, rel=1e-9)


@pytest.mark.parametrize("budget,both_bases", [(9000.0, True), (2000.0, False)])
def test_bilinear_objective_matches_linearized_milp_exactly(budget, both_bases):
    """The actual point of experiment 1: same section 5.2 model, two
    reformulations of constraint 6, must agree on the optimal objective
    value (not necessarily on every variable's value, alternate optima are
    possible and already documented in test_model_milp.py's CVaR test)."""
    params = _base_case(budget=budget, both_bases=both_bases)
    pre = precompute(params)

    linear_result = solve_model(params, pre)
    bilinear_result = solve_bilinear_model(params, pre)

    assert linear_result.status == "Optimal"
    assert bilinear_result.status == "Optimal"
    assert bilinear_result.objective_value == pytest.approx(linear_result.objective_value, abs=1e-6)


def test_scenario_with_no_fires_builds_and_solves():
    scenario = Scenario(scenario_id="s_empty", probability=1.0, fires=[])
    params = ModelParams(
        bases=["B1"],
        water_points=["W1"],
        aircraft_types=["T1"],
        scenarios=[scenario],
        budget=9000.0,
        window=10.0,
        ops_time=0.0,
        cvar_alpha=0.95,
        mean_risk_weight=0.0,
        initial_fire_area=100.0,
        liters_per_sqm=1.0,
        cost_base={"B1": 5000.0},
        cost_aircraft={"T1": 1000.0},
        cost_water={"W1": 3000.0},
        tank={"T1": 100.0},
        speed={"T1": 100.0},
        t_base_fire={},
        t_fire_water={},
    )
    pre = precompute(params)
    result = solve_bilinear_model(params, pre)

    assert result.status == "Optimal"
    assert result.objective_value == pytest.approx(0.0)
    assert result.loss["s_empty"] == pytest.approx(0.0)


def test_cvar_matches_hand_derivation_for_two_equally_likely_scenarios():
    """Same setup and same caveat as test_model_milp.py's version of this
    test: at alpha=0.5 with two equally-likely scenarios, this exact
    configuration is genuinely degenerate at the first-stage level (see
    that test's docstring), so only the forced-uncontainable fire's
    escape/loss and the objective value (the real hand-derived invariant)
    are asserted."""
    fire1 = Fire(fire_id="F1", x_utm=0.0, y_utm=0.0, ros=0.0, t_arrival=1.0, value_at_risk=VALUE_AT_RISK)
    fire2 = Fire(fire_id="F2", x_utm=0.0, y_utm=0.0, ros=0.0, t_arrival=1.0, value_at_risk=VALUE_AT_RISK)
    scenario1 = Scenario(scenario_id="s1", probability=0.5, fires=[fire1])
    scenario2 = Scenario(scenario_id="s2", probability=0.5, fires=[fire2])

    params = ModelParams(
        bases=["B_near"],
        water_points=["W1"],
        aircraft_types=["T1"],
        scenarios=[scenario1, scenario2],
        budget=9000.0,
        window=10.0,
        ops_time=0.0,
        cvar_alpha=0.5,
        mean_risk_weight=1.0,
        initial_fire_area=100.0,
        liters_per_sqm=1.0,
        cost_base={"B_near": 5000.0},
        cost_aircraft={"T1": 1000.0},
        cost_water={"W1": 3000.0},
        tank={"T1": 100.0},
        speed={"T1": 100.0},
        t_base_fire={
            ("s1", "B_near", "F1"): 1.0,
            ("s2", "B_near", "F2"): 50.0,
        },
        t_fire_water={
            ("s1", "F1", "W1"): 2.0,
            ("s2", "F2", "W1"): 2.0,
        },
    )
    pre = precompute(params)
    result = solve_bilinear_model(params, pre)

    assert result.status == "Optimal"
    assert result.escape[("s2", "F2")] is True
    assert result.loss["s2"] == pytest.approx(VALUE_AT_RISK, rel=1e-9)
    assert result.objective_value == pytest.approx(VALUE_AT_RISK, rel=1e-6)
