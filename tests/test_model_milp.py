"""Tests for src/model/milp.py: build and solve small, hand-verifiable
synthetic instances, not data presented as if it were real Colombian fires
or infrastructure.

Parametrized across every available PuLP solver backend (SOLVER_FACTORIES
below): PuLP's bundled CBC always, plus Gurobi automatically once an
academic license is available (CLAUDE.md section 3 names Gurobi as the
benchmark solver "on small instances"). Running the same hand-verified
assertions against both is not redundant: CONFIRMED 2026-08-30,
cross-checking against Gurobi surfaced (1) a genuine degeneracy in the
CVaR test (see its docstring), and (2) a serious PuLP/Gurobi footgun this
suite now guards against structurally: pulp.GUROBI() (the in-process API
binding, unlike GUROBI_CMD()) keeps its underlying gurobipy.Model on the
solver object across calls and silently ACCUMULATES every LpProblem ever
solved with the same instance into that one Gurobi model, corrupting every
solve after the first (confirmed by direct reproduction: reusing one
pulp.GUROBI() instance across two different small models produced a
result violating that second model's own constraints, e.g. escape=False
with no base open and zero possible delivery). A brand new pulp.GUROBI()
instance must be constructed for every solve; SOLVER_FACTORIES below holds
factory callables, not solver instances, specifically to force this. This
matters far beyond these tests: any future sweep (experiment 6) or
matheuristic loop (fix-and-optimize/LNS, src/matheuristic/) that solves
many sub-MILPs in sequence must construct a fresh pulp.GUROBI() per solve,
never reuse one across iterations for "efficiency".

Common setup (see _base_case): a fire reachable from a "near" base can be
fully contained by one aircraft with liters to spare; a "far" base is placed
beyond the critical window so it can never help, exercising the drops
max(0, ...) clip end to end.
"""

from __future__ import annotations

import pulp
import pytest

from src.model.milp import solve_model
from src.model.precompute import precompute
from src.model.schema import Fire, ModelParams, Scenario

VALUE_AT_RISK = 1_000_000.0


def _available_solver_factories() -> list[tuple[str, object]]:
    """Factory callables, not solver instances: each test must build its own
    fresh solver object (see module docstring on why pulp.GUROBI() must
    never be reused across solves)."""
    factories = [("PULP_CBC_CMD", lambda: pulp.PULP_CBC_CMD(msg=False))]
    if pulp.GUROBI(msg=False).available():
        factories.append(("GUROBI", lambda: pulp.GUROBI(msg=False)))
    return factories


_SOLVER_FACTORIES = _available_solver_factories()
SOLVER_IDS = [name for name, _ in _SOLVER_FACTORIES]
SOLVER_FACTORIES = [factory for _, factory in _SOLVER_FACTORIES]


def _base_case(budget: float, both_bases: bool = True) -> ModelParams:
    """1 (or 2) bases, 1 water point, 1 aircraft type, 1 scenario, 1 fire.
    speed=100, distances chosen so B_near's cycle allows 2 drops of 100 L
    each (200 L) against a 100 L requirement (comfortably contained), while
    B_far is far enough that window - t_base_fire is negative (drops clip)."""
    fire = Fire(fire_id="F1", x_utm=0.0, y_utm=0.0, ros=0.0, t_arrival=1.0, value_at_risk=VALUE_AT_RISK)
    scenario = Scenario(scenario_id="s1", probability=1.0, fires=[fire])

    bases = ["B_near", "B_far"] if both_bases else ["B_near"]
    cost_base = {"B_near": 5000.0, "B_far": 5000.0}
    t_base_fire = {
        ("s1", "B_near", "F1"): 1.0,  # window(10) - 1.0 = 9.0, / cycle(4.0) = 2.25 -> 2 drops
        ("s1", "B_far", "F1"): 50.0,  # window(10) - 50.0 negative -> clipped to 0 drops
    }
    if not both_bases:
        del t_base_fire[("s1", "B_far", "F1")]

    return ModelParams(
        bases=bases,
        water_points=["W1"],
        aircraft_types=["T1"],
        scenarios=[scenario],
        budget=budget,
        window=10.0,
        ops_time=0.0,
        cvar_alpha=0.95,
        mean_risk_weight=0.0,  # risk neutral: objective = sum_s p_s * loss[s]
        initial_fire_area=100.0,
        liters_per_sqm=1.0,  # requirement = 1.0 * 100.0 * exp(0*1.0) = 100.0
        cost_base={i: cost_base[i] for i in bases},
        cost_aircraft={"T1": 1000.0},
        cost_water={"W1": 3000.0},
        tank={"T1": 100.0},
        speed={"T1": 100.0},
        t_base_fire=t_base_fire,
        t_fire_water={("s1", "F1", "W1"): 2.0},  # cycle_time = 2*2.0+0 = 4.0
    )


@pytest.mark.parametrize("solver_factory", SOLVER_FACTORIES, ids=SOLVER_IDS)
def test_fire_contained_when_budget_allows_near_base(solver_factory):
    solver = solver_factory()
    # 5000 (B_near) + 3000 (W1) + 1000 (1 aircraft) = 9000 exactly; not
    # enough left over to also open B_far (would need +5000 = 14000).
    params = _base_case(budget=9000.0, both_bases=True)
    pre = precompute(params)
    result = solve_model(params, pre, solver=solver)

    assert result.status == "Optimal"
    assert result.base_open["B_near"] is True
    assert result.base_open["B_far"] is False, "too far to ever help, and budget cannot afford it anyway"
    assert result.water_open["W1"] is True
    assert result.escape[("s1", "F1")] is False
    assert result.delivered[("s1", "F1")] >= 100.0 - 1e-6
    assert result.refill_at[("s1", "F1", "W1")] is True
    assert result.objective_value == pytest.approx(0.0, abs=1e-6)


@pytest.mark.parametrize("solver_factory", SOLVER_FACTORIES, ids=SOLVER_IDS)
def test_fire_escapes_when_budget_too_small_to_open_anything(solver_factory):
    solver = solver_factory()
    # Cheapest single base alone costs 5000; budget 2000 cannot open any
    # base, so nothing can be dispatched anywhere.
    params = _base_case(budget=2000.0, both_bases=False)
    pre = precompute(params)
    result = solve_model(params, pre, solver=solver)

    assert result.status == "Optimal"
    assert result.base_open["B_near"] is False
    assert result.escape[("s1", "F1")] is True
    assert result.delivered[("s1", "F1")] == pytest.approx(0.0)
    assert result.objective_value == pytest.approx(VALUE_AT_RISK, rel=1e-9)


@pytest.mark.parametrize("solver_factory", SOLVER_FACTORIES, ids=SOLVER_IDS)
def test_fire_escapes_when_no_base_is_within_the_window(solver_factory):
    solver = solver_factory()
    # Both candidate bases too far (drops clipped to 0 for both), budget is
    # ample, but spending it cannot help: containment is physically
    # impossible regardless of first-stage choices.
    fire = Fire(fire_id="F1", x_utm=0.0, y_utm=0.0, ros=0.0, t_arrival=1.0, value_at_risk=VALUE_AT_RISK)
    scenario = Scenario(scenario_id="s1", probability=1.0, fires=[fire])
    params = ModelParams(
        bases=["B_far"],
        water_points=["W1"],
        aircraft_types=["T1"],
        scenarios=[scenario],
        budget=20_000.0,
        window=10.0,
        ops_time=0.0,
        cvar_alpha=0.95,
        mean_risk_weight=0.0,
        initial_fire_area=100.0,
        liters_per_sqm=1.0,
        cost_base={"B_far": 5000.0},
        cost_aircraft={"T1": 1000.0},
        cost_water={"W1": 3000.0},
        tank={"T1": 100.0},
        speed={"T1": 100.0},
        t_base_fire={("s1", "B_far", "F1"): 50.0},
        t_fire_water={("s1", "F1", "W1"): 2.0},
    )
    pre = precompute(params)
    result = solve_model(params, pre, solver=solver)

    assert result.status == "Optimal"
    assert result.escape[("s1", "F1")] is True
    assert result.delivered[("s1", "F1")] == pytest.approx(0.0)
    assert result.objective_value == pytest.approx(VALUE_AT_RISK, rel=1e-9)


@pytest.mark.parametrize("solver_factory", SOLVER_FACTORIES, ids=SOLVER_IDS)
def test_scenario_with_no_fires_builds_and_solves(solver_factory):
    solver = solver_factory()
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
    result = solve_model(params, pre, solver=solver)

    assert result.status == "Optimal"
    assert result.objective_value == pytest.approx(0.0)
    assert result.loss["s_empty"] == pytest.approx(0.0)


@pytest.mark.parametrize("solver_factory", SOLVER_FACTORIES, ids=SOLVER_IDS)
def test_cvar_matches_hand_derivation_for_two_equally_likely_scenarios(solver_factory):
    solver = solver_factory()
    """s1's fire is containable with the shared 9000 budget (loss=0 if
    contained); s2's fire is unreachable by the same infrastructure
    regardless (t_base_fire=50 always clips drops to 0, so escape[s2,F2]
    and loss[s2]=V are forced in every feasible solution, not just the
    optimal one). With p=0.5/0.5, mean_risk_weight=1 (pure CVaR) and
    alpha=0.5, the Rockafellar-Uryasev objective for a two-point {0, V}
    equally-likely distribution is exactly V (worked by hand in the commit
    that added this test, see CLAUDE.md section 5.2 objective).

    CONFIRMED 2026-08-30, cross-checked against Gurobi once an academic
    license became available (previously only ever run against PuLP's
    bundled CBC): the objective value V is robust across solvers as
    expected, but this exact configuration is genuinely degenerate at the
    first-stage level, not just in var_level's split point as originally
    documented here. At alpha=0.5 with two equally-likely scenarios,
    CVaR_0.5 only depends on the single worse outcome (s2's forced V), so
    "contain s1" (loss={0,V}) and "open nothing at all" (loss={V,V}) both
    score exactly V: CBC happens to find the former, Gurobi the latter,
    both genuinely optimal. Only escape[s2,F2]/loss[s2] (forced regardless
    of any first-stage choice) and the objective value (the actual
    hand-derived invariant) are asserted below; escape[s1,F1]/loss[s1] are
    solver-dependent under this exact setup and must not be asserted.
    """
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
        mean_risk_weight=1.0,  # pure CVaR
        initial_fire_area=100.0,
        liters_per_sqm=1.0,
        cost_base={"B_near": 5000.0},
        cost_aircraft={"T1": 1000.0},
        cost_water={"W1": 3000.0},
        tank={"T1": 100.0},
        speed={"T1": 100.0},
        t_base_fire={
            ("s1", "B_near", "F1"): 1.0,  # reachable, containable
            ("s2", "B_near", "F2"): 50.0,  # unreachable regardless (drops clipped to 0)
        },
        t_fire_water={
            ("s1", "F1", "W1"): 2.0,
            ("s2", "F2", "W1"): 2.0,
        },
    )
    pre = precompute(params)
    result = solve_model(params, pre, solver=solver)

    assert result.status == "Optimal"
    assert result.escape[("s2", "F2")] is True
    assert result.loss["s2"] == pytest.approx(VALUE_AT_RISK, rel=1e-9)
    assert result.objective_value == pytest.approx(VALUE_AT_RISK, rel=1e-6)


def test_build_model_rejects_scenario_probabilities_not_summing_to_one():
    """CONFIRMED 2026-08-30 by direct reproduction against real data
    (src/model/run_instance.py): silently slicing a subset of scenarios out
    of a larger bootstrap draw without renormalizing probabilities makes
    the CVaR objective genuinely UNBOUNDED (var_level can run to -infinity
    while cvar_excess compensates at no net objective cost once sum_s p_s
    < 1), not just numerically off. build_model must reject this before it
    ever reaches the solver."""
    fire = Fire(fire_id="F1", x_utm=0.0, y_utm=0.0, ros=0.0, t_arrival=1.0, value_at_risk=VALUE_AT_RISK)
    # Two scenarios sliced from a larger 200-scenario draw, each still
    # carrying its original probability (1/200), summing to 0.01, not 1.0.
    scenario1 = Scenario(scenario_id="s1", probability=0.005, fires=[fire])
    scenario2 = Scenario(scenario_id="s2", probability=0.005, fires=[fire])
    params = ModelParams(
        bases=["B_near"],
        water_points=["W1"],
        aircraft_types=["T1"],
        scenarios=[scenario1, scenario2],
        budget=9000.0,
        window=10.0,
        ops_time=0.0,
        cvar_alpha=0.95,
        mean_risk_weight=0.5,
        initial_fire_area=100.0,
        liters_per_sqm=1.0,
        cost_base={"B_near": 5000.0},
        cost_aircraft={"T1": 1000.0},
        cost_water={"W1": 3000.0},
        tank={"T1": 100.0},
        speed={"T1": 100.0},
        t_base_fire={("s1", "B_near", "F1"): 1.0, ("s2", "B_near", "F1"): 1.0},
        t_fire_water={("s1", "F1", "W1"): 2.0, ("s2", "F1", "W1"): 2.0},
    )
    pre = precompute(params)

    with pytest.raises(ValueError, match="sum to"):
        solve_model(params, pre)
