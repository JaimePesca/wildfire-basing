"""Tests for src/model/sequential.py, the bases-first/water-second
baseline (experiment 3's comparator), on small hand-verifiable synthetic
instances, not real Colombian data.

The last two tests are the point of the whole experiment, reproduced in
miniature: (1) the sequential solution can never beat the integrated
optimum (it is feasible for the integrated model); (2) there exist
instances where it is STRICTLY worse at EVERY budget split phi, because
bases-first planning cannot see water costs: phase A chases the
marginally-more-valuable fire whose only water point is economically out
of reach, and no phi can undo that misdirected base commitment."""

from __future__ import annotations

import pulp
import pytest

from src.model.milp import solve_model
from src.model.precompute import precompute
from src.model.schema import Fire, ModelParams, Scenario
from src.model.sequential import (
    VIRTUAL_WATER_ID,
    make_water_blind_params,
    solve_phase_a,
    solve_sequential,
    solve_sequential_best_phi,
)


def _simple_case() -> ModelParams:
    """One fire, one base, two water points (one near, one far). Fully
    containable: B1 + 1 aircraft + W_near fits the budget."""
    fire = Fire(fire_id="F1", x_utm=0.0, y_utm=0.0, ros=0.0, t_arrival=1.0, value_at_risk=1000.0)
    scenario = Scenario(scenario_id="s1", probability=1.0, fires=[fire])
    return ModelParams(
        bases=["B1"],
        water_points=["W_near", "W_far"],
        aircraft_types=["T1"],
        scenarios=[scenario],
        budget=9000.0,
        window=10.0,
        ops_time=0.0,
        cvar_alpha=0.95,
        mean_risk_weight=0.5,
        initial_fire_area=0.01,  # hectares: 0.01 ha = 100 m^2
        liters_per_sqm=1.0,
        cost_base={"B1": 500.0},
        cost_aircraft={"T1": 4000.0},
        cost_water={"W_near": 300.0, "W_far": 300.0},
        tank={"T1": 100.0},
        speed={"T1": 100.0},
        t_base_fire={("s1", "B1", "F1"): 1.0},
        t_fire_water={("s1", "F1", "W_near"): 2.0, ("s1", "F1", "W_far"): 4.0},
    )


def test_make_water_blind_params_takes_true_best_cycle_and_zero_cost():
    params = _simple_case()
    blind = make_water_blind_params(params, base_budget=4500.0)
    assert blind.water_points == [VIRTUAL_WATER_ID]
    # The virtual point's travel time is the true best over the catalog.
    assert blind.t_fire_water[("s1", "F1", VIRTUAL_WATER_ID)] == 2.0
    assert blind.cost_water[VIRTUAL_WATER_ID] == 0.0
    assert blind.budget == 4500.0
    # Everything else passes through unchanged.
    assert blind.bases == params.bases
    assert blind.cost_base == params.cost_base


def test_make_water_blind_params_rejects_empty_water_catalog():
    import dataclasses

    params = dataclasses.replace(_simple_case(), water_points=[], t_fire_water={}, cost_water={})
    with pytest.raises(ValueError):
        make_water_blind_params(params, base_budget=1000.0)


def test_phase_a_opens_the_base_and_reports_spend():
    params = _simple_case()
    result = solve_phase_a(params, phi=0.6)  # 5400 covers base 500 + aircraft 4000
    assert result.status == "Optimal"
    assert result.base_open["B1"] is True
    assert result.n_aircraft[("B1", "T1")] == 1
    assert result.spend == pytest.approx(4500.0)


def test_phase_a_rejects_phi_outside_unit_interval():
    with pytest.raises(ValueError):
        solve_phase_a(_simple_case(), phi=1.5)


def test_sequential_matches_integrated_when_water_is_not_scarce():
    """No water scarcity: the best phi funds base+aircraft in phase A and
    leaves enough for the (cheap) water point in phase B, so the best
    sequential result equals the integrated optimum exactly."""
    params = _simple_case()
    pre = precompute(params)
    integrated = solve_model(params, pre)
    assert integrated.status == "Optimal"

    best, _all = solve_sequential_best_phi(params, phis=[0.3, 0.5, 0.7, 0.9])
    assert best.objective_value == pytest.approx(integrated.objective_value, abs=1e-6)


def _water_cost_trap_case() -> ModelParams:
    """The miniature of the paper's core claim. One scenario, two fires
    far apart: F1 (value 1000) reachable only from B1, F2 (value 1001)
    reachable only from B2. Each fire has exactly one usable water point;
    F1's costs 300, F2's costs 10000 (economically out of reach: budget
    1000). True integrated optimum: open B1 + 1 aircraft + W1, contain
    F1, lose F2, objective proportional to 1001. A water-blind phase A at
    ANY phi that can afford a base and an aircraft picks B2 instead (F2's
    value is marginally higher and water looks free), and phase B then
    cannot afford W2, so BOTH fires are lost, objective proportional to
    2001, strictly worse at every phi."""
    f1 = Fire(fire_id="F1", x_utm=0.0, y_utm=0.0, ros=0.0, t_arrival=1.0, value_at_risk=1000.0)
    f2 = Fire(fire_id="F2", x_utm=0.0, y_utm=0.0, ros=0.0, t_arrival=1.0, value_at_risk=1001.0)
    scenario = Scenario(scenario_id="s1", probability=1.0, fires=[f1, f2])
    unreachable = 50.0  # far beyond window=10, drops clip to 0
    return ModelParams(
        bases=["B1", "B2"],
        water_points=["W1", "W2"],
        aircraft_types=["T1"],
        scenarios=[scenario],
        budget=1000.0,
        window=10.0,
        ops_time=0.0,
        cvar_alpha=0.95,
        mean_risk_weight=0.5,
        initial_fire_area=0.01,  # hectares: 0.01 ha = 100 m^2
        liters_per_sqm=1.0,
        cost_base={"B1": 100.0, "B2": 100.0},
        cost_aircraft={"T1": 400.0},
        cost_water={"W1": 300.0, "W2": 10000.0},
        tank={"T1": 100.0},
        speed={"T1": 100.0},
        t_base_fire={
            ("s1", "B1", "F1"): 1.0,
            ("s1", "B1", "F2"): unreachable,
            ("s1", "B2", "F1"): unreachable,
            ("s1", "B2", "F2"): 1.0,
        },
        t_fire_water={
            ("s1", "F1", "W1"): 2.0,
            ("s1", "F1", "W2"): unreachable,
            ("s1", "F2", "W1"): unreachable,
            ("s1", "F2", "W2"): 2.0,
        },
    )


def test_sequential_never_beats_integrated():
    """Dominance: the sequential solution is feasible for the integrated
    model, so its objective can never be lower, on either instance."""
    for params in (_simple_case(), _water_cost_trap_case()):
        pre = precompute(params)
        integrated = solve_model(params, pre)
        assert integrated.status == "Optimal"
        for phi in (0.5, 0.7, 0.9):
            seq = solve_sequential(params, phi)
            if seq.phase_b.status == "Optimal":
                assert seq.objective_value >= integrated.objective_value - 1e-6


def test_sequential_strictly_worse_at_every_phi_on_the_water_cost_trap():
    params = _water_cost_trap_case()
    pre = precompute(params)
    integrated = solve_model(params, pre)
    assert integrated.status == "Optimal"
    assert integrated.base_open["B1"] is True  # contains F1, the affordable fire
    assert integrated.escape[("s1", "F2")] is True

    best, all_results = solve_sequential_best_phi(params, phis=[0.5, 0.6, 0.7, 0.8, 0.9, 1.0])
    # Phase A chases F2 (marginally higher value, water looks free)...
    assert best.phase_a.base_open["B2"] is True
    # ...and phase B cannot afford W2, so both fires are lost: strictly
    # worse than the integrated optimum at EVERY phi, not just the best.
    for r in all_results:
        if r.phase_b.status == "Optimal":
            assert r.objective_value > integrated.objective_value + 1e-6
    assert best.objective_value > integrated.objective_value + 1e-6
