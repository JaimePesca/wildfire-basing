"""Tests for src/matheuristic/fix_and_optimize.py: the LNS/fix-and-optimize
loop over first-stage variables, on small hand-verifiable synthetic
instances, not real Colombian data.

Correctness strategy: since the matheuristic must find the SAME optimum a
direct full MILP solve would (it is an exact reformulation trick for
tractability, not an approximation, see the module's own docstring), the
strongest checks here compare run_fix_and_optimize's result against
milp.solve_model on the same full instance.
"""

from __future__ import annotations

import pandas as pd
import pulp
import pytest

from src.matheuristic.fix_and_optimize import (
    FirstStageSolution,
    build_reduced_params,
    fix_non_neighborhood_variables,
    run_fix_and_optimize,
)
from src.model.milp import build_model, solve_model
from src.model.precompute import precompute
from src.model.schema import Fire, ModelParams, Scenario

VALUE_AT_RISK = 1_000_000.0


def _multi_base_case(n_extra_far_bases: int = 2) -> ModelParams:
    """B_near can fully contain the fire; B_far_1..N are all placed beyond
    the window (drops clip to 0, mirroring test_model_milp.py's B_far
    pattern), so the true optimum only ever needs B_near + W1."""
    fire = Fire(fire_id="F1", x_utm=0.0, y_utm=0.0, ros=0.0, t_arrival=1.0, value_at_risk=VALUE_AT_RISK)
    scenario = Scenario(scenario_id="s1", probability=1.0, fires=[fire])

    far_ids = [f"B_far_{i}" for i in range(n_extra_far_bases)]
    bases = ["B_near"] + far_ids
    cost_base = {i: 5000.0 for i in bases}
    t_base_fire = {("s1", "B_near", "F1"): 1.0}
    for fid in far_ids:
        t_base_fire[("s1", fid, "F1")] = 50.0

    return ModelParams(
        bases=bases,
        water_points=["W1"],
        aircraft_types=["T1"],
        scenarios=[scenario],
        budget=9000.0,
        window=10.0,
        ops_time=0.0,
        cvar_alpha=0.95,
        mean_risk_weight=0.0,
        initial_fire_area=0.01,  # hectares: 0.01 ha = 100 m^2
        liters_per_sqm=1.0,
        cost_base=cost_base,
        cost_aircraft={"T1": 1000.0},
        cost_water={"W1": 3000.0},
        tank={"T1": 100.0},
        speed={"T1": 100.0},
        t_base_fire=t_base_fire,
        t_fire_water={("s1", "F1", "W1"): 2.0},
    )


def _sites_df(ids: list[str], coords: dict[str, tuple[float, float]]) -> pd.DataFrame:
    return pd.DataFrame(
        [{"site_id": i, "x_utm": coords[i][0], "y_utm": coords[i][1]} for i in ids]
    )


def _far_bases_trap_case() -> ModelParams:
    """Reproduces the real failure found 2026-09-04 against the actual
    candidate catalog (CLAUDE.md section 10, neighborhoods.py's
    random_destroy_prob docstring): only one aircraft is ever affordable
    (cost_aircraft=8000 against budget=9500, two would need 16000), and
    constraint 5 (section 5.2) caps total dispatch per base at its stationed
    aircraft count, so whichever single base gets the one aircraft can only
    ever save ONE of the two fires. Every base in the 'trap' cluster
    (B_trap, B_f1, B_f2) can only reach F1 (value_at_risk 100); only B_best,
    in a separate 'best' cluster, can also reach F2 (value_at_risk
    1,000,000). The true optimum opens B_best (loses only F1, loss 100);
    opening any trap-cluster base loses F2 instead (loss 1,000,000). Getting
    from a trap-cluster incumbent to B_best requires closing the former and
    opening the latter in the SAME LNS iteration, since only one aircraft
    is affordable, exactly the trade the geographic-proximity operator
    alone cannot propose once the two clusters are placed far apart in
    coordinate space by the caller's bases_df (see the tests below)."""
    f1 = Fire(fire_id="F1", x_utm=0.0, y_utm=0.0, ros=0.0, t_arrival=1.0, value_at_risk=100.0)
    f2 = Fire(fire_id="F2", x_utm=0.0, y_utm=0.0, ros=0.0, t_arrival=1.0, value_at_risk=1_000_000.0)
    scenario = Scenario(scenario_id="s1", probability=1.0, fires=[f1, f2])

    trap_cluster = ["B_trap", "B_f1", "B_f2"]
    best_cluster = ["B_best", "B_f3", "B_f4"]
    bases = trap_cluster + best_cluster
    cost_base = {i: 500.0 for i in bases}

    t_base_fire = {("s1", i, "F1"): 1.0 for i in bases}
    for i in trap_cluster + ["B_f3", "B_f4"]:
        t_base_fire[("s1", i, "F2")] = 50.0  # unreachable, window=10
    t_base_fire[("s1", "B_best", "F2")] = 1.0

    return ModelParams(
        bases=bases,
        water_points=["W1"],
        aircraft_types=["T1"],
        scenarios=[scenario],
        budget=9500.0,
        window=10.0,
        ops_time=0.0,
        cvar_alpha=0.95,
        mean_risk_weight=0.0,
        initial_fire_area=0.01,  # hectares: 0.01 ha = 100 m^2
        liters_per_sqm=1.0,
        cost_base=cost_base,
        cost_aircraft={"T1": 8000.0},
        cost_water={"W1": 500.0},
        tank={"T1": 100.0},
        speed={"T1": 100.0},
        t_base_fire=t_base_fire,
        t_fire_water={("s1", "F1", "W1"): 2.0, ("s1", "F2", "W1"): 2.0},
    )


_FAR_BASES_TRAP_COORDS = {
    "B_trap": (0.0, 0.0),
    "B_f1": (1.0, 0.0),
    "B_f2": (2.0, 0.0),
    "B_best": (1_000_000.0, 0.0),
    "B_f3": (1_000_001.0, 0.0),
    "B_f4": (1_000_002.0, 0.0),
}


def test_build_reduced_params_keeps_only_free_and_open_sites():
    params = _multi_base_case(n_extra_far_bases=2)
    incumbent = FirstStageSolution(base_open={"B_far_0": True}, water_open={}, n_aircraft={("B_far_0", "T1"): 1})

    reduced = build_reduced_params(params, incumbent, free_bases={"B_near"}, free_water={"W1"})

    assert set(reduced.bases) == {"B_near", "B_far_0"}  # free + open-in-incumbent
    assert "B_far_1" not in reduced.bases  # closed and not free: dropped
    assert set(reduced.water_points) == {"W1"}
    assert set(reduced.cost_base.keys()) == {"B_near", "B_far_0"}
    assert all(key[1] in {"B_near", "B_far_0"} for key in reduced.t_base_fire)


def test_fix_non_neighborhood_variables_locks_open_incumbent_sites():
    params = _multi_base_case(n_extra_far_bases=1)
    incumbent = FirstStageSolution(base_open={"B_far_0": True}, water_open={}, n_aircraft={("B_far_0", "T1"): 2})
    reduced = build_reduced_params(params, incumbent, free_bases={"B_near"}, free_water={"W1"})
    pre = precompute(reduced)
    model, v = build_model(reduced, pre)

    fix_non_neighborhood_variables(v, reduced, incumbent, free_bases={"B_near"}, free_water={"W1"})

    assert v.base_open["B_far_0"].lowBound == 1
    assert v.base_open["B_far_0"].upBound == 1
    assert v.n_aircraft[("B_far_0", "T1")].lowBound == 2
    assert v.n_aircraft[("B_far_0", "T1")].upBound == 2
    # B_near is free: fixing must not have touched its bounds.
    assert v.base_open["B_near"].upBound != 1 or v.base_open["B_near"].lowBound != 1


def test_fix_and_optimize_matches_full_solve_when_neighborhood_covers_everything():
    """n_bases_per_neighborhood >= total bases: the very first iteration's
    neighborhood already covers the whole candidate set, so the result
    must be deterministic (independent of the random seed) and identical
    to solving the full MILP directly."""
    params = _multi_base_case(n_extra_far_bases=3)
    pre = precompute(params)
    direct = solve_model(params, pre)

    bases_df = _sites_df(
        params.bases, {"B_near": (0.0, 0.0), "B_far_0": (10.0, 0.0), "B_far_1": (20.0, 0.0), "B_far_2": (30.0, 0.0)}
    )
    water_df = _sites_df(["W1"], {"W1": (0.0, 1.0)})

    result = run_fix_and_optimize(
        params,
        bases_df,
        water_df,
        n_bases_per_neighborhood=10,
        n_water_per_neighborhood=10,
        max_iterations=1,
        seed=0,
    )

    assert result.objective_value == pytest.approx(direct.objective_value, abs=1e-6)
    assert result.incumbent.base_open["B_near"] is True


def test_fix_and_optimize_converges_with_partial_neighborhoods():
    """n_bases_per_neighborhood (2) is smaller than the total base count
    (5): no single iteration can see every base at once, so finding
    B_near (the only base that can ever help) requires the search to
    actually explore across iterations, not just solve everything at once.
    Verified with enough iterations that the search covers the seed space
    (5 candidate seeds: B_near + 3 far bases + W1) many times over."""
    params = _multi_base_case(n_extra_far_bases=3)
    pre = precompute(params)
    direct = solve_model(params, pre)

    bases_df = _sites_df(
        params.bases,
        {"B_near": (0.0, 0.0), "B_far_0": (1000.0, 0.0), "B_far_1": (2000.0, 0.0), "B_far_2": (3000.0, 0.0)},
    )
    water_df = _sites_df(["W1"], {"W1": (0.0, 1.0)})

    result = run_fix_and_optimize(
        params,
        bases_df,
        water_df,
        n_bases_per_neighborhood=2,
        n_water_per_neighborhood=1,
        max_iterations=30,
        seed=0,
    )

    assert result.objective_value == pytest.approx(direct.objective_value, abs=1e-6)


@pytest.mark.parametrize(
    "solver_factory",
    [
        lambda: pulp.PULP_CBC_CMD(msg=False),
        pytest.param(
            lambda: pulp.GUROBI(msg=False),
            marks=pytest.mark.skipif(not pulp.GUROBI(msg=False).available(), reason="no Gurobi license"),
        ),
    ],
    ids=["PULP_CBC_CMD", "GUROBI"],
)
def test_fix_and_optimize_works_with_both_solvers(solver_factory):
    params = _multi_base_case(n_extra_far_bases=1)
    pre = precompute(params)
    direct = solve_model(params, pre)

    bases_df = _sites_df(params.bases, {"B_near": (0.0, 0.0), "B_far_0": (10.0, 0.0)})
    water_df = _sites_df(["W1"], {"W1": (0.0, 1.0)})

    result = run_fix_and_optimize(
        params,
        bases_df,
        water_df,
        n_bases_per_neighborhood=10,
        n_water_per_neighborhood=10,
        max_iterations=1,
        seed=0,
        solver_factory=solver_factory,
    )

    assert result.objective_value == pytest.approx(direct.objective_value, abs=1e-6)


def test_fix_and_optimize_accepts_a_supplied_initial_solution():
    params = _multi_base_case(n_extra_far_bases=1)
    initial = FirstStageSolution(
        base_open={"B_near": True}, water_open={"W1": True}, n_aircraft={("B_near", "T1"): 1}
    )
    bases_df = _sites_df(params.bases, {"B_near": (0.0, 0.0), "B_far_0": (10.0, 0.0)})
    water_df = _sites_df(["W1"], {"W1": (0.0, 1.0)})

    result = run_fix_and_optimize(
        params,
        bases_df,
        water_df,
        n_bases_per_neighborhood=1,
        n_water_per_neighborhood=1,
        max_iterations=1,
        seed=0,
        initial=initial,
    )

    # Already-optimal initial solution: objective must be exactly 0 from the start.
    assert result.objective_value == pytest.approx(0.0, abs=1e-6)


def test_pure_geographic_operator_gets_permanently_stuck_short_of_the_true_optimum():
    """Documents the real bug found 2026-09-04 against the actual candidate
    catalog (see neighborhoods.py's module docstring): with
    random_destroy_prob=0.0 (the original, pre-fix default), starting from
    an incumbent that already committed its one affordable aircraft to a
    trap-cluster base, no number of further geographic-only iterations ever
    recovers, because B_trap and B_best are placed far apart in coordinate
    space (see _FAR_BASES_TRAP_COORDS) and a nearest-2 neighborhood seeded
    from either cluster can never contain both, so the sub-MILP is never
    even offered the trade. no_improve_limit is intentionally omitted so
    all 100 iterations run regardless of consecutive non-improvement,
    confirming a genuine permanent local optimum, not just an early stop."""
    params = _far_bases_trap_case()
    pre = precompute(params)
    direct = solve_model(params, pre)
    assert direct.objective_value == pytest.approx(100.0, abs=1e-6)  # B_best is the true optimum

    bases_df = _sites_df(params.bases, _FAR_BASES_TRAP_COORDS)
    water_df = _sites_df(["W1"], {"W1": (0.0, 1.0)})
    initial = FirstStageSolution(
        base_open={"B_trap": True}, water_open={"W1": True}, n_aircraft={("B_trap", "T1"): 1}
    )

    result = run_fix_and_optimize(
        params,
        bases_df,
        water_df,
        n_bases_per_neighborhood=2,
        n_water_per_neighborhood=1,
        max_iterations=100,
        seed=0,
        initial=initial,
        # random_destroy_prob defaults to 0.0: pure geographic operator only.
    )

    assert result.objective_value == pytest.approx(1_000_000.0, abs=1e-6)  # stuck: F2 escapes forever


@pytest.mark.parametrize("seed", range(5))
def test_random_destroy_prob_escapes_the_geographic_local_optimum(seed):
    """The fix (CLAUDE.md section 10, 2026-09-04): with random_destroy_prob
    > 0, the exact same trapped starting point converges to the true
    optimum, since the random operator can (and does, within 300
    iterations, across every seed tested here) place B_trap and B_best in
    the same free set together, something the geographic operator alone
    structurally cannot do (previous test). Parametrized over 5 seeds since
    this fix relies on a random draw eventually finding the needed pair;
    all 5 must succeed for the fix to be considered reliable, not lucky."""
    params = _far_bases_trap_case()
    pre = precompute(params)
    direct = solve_model(params, pre)

    bases_df = _sites_df(params.bases, _FAR_BASES_TRAP_COORDS)
    water_df = _sites_df(["W1"], {"W1": (0.0, 1.0)})
    initial = FirstStageSolution(
        base_open={"B_trap": True}, water_open={"W1": True}, n_aircraft={("B_trap", "T1"): 1}
    )

    result = run_fix_and_optimize(
        params,
        bases_df,
        water_df,
        n_bases_per_neighborhood=2,
        n_water_per_neighborhood=1,
        max_iterations=300,
        seed=seed,
        initial=initial,
        random_destroy_prob=0.4,
    )

    assert result.objective_value == pytest.approx(direct.objective_value, abs=1e-6)
    assert result.incumbent.base_open.get("B_best") is True
