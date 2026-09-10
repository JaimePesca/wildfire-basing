"""Sequential baseline (CLAUDE.md section 3, FROZEN benchmark choice:
"a sequential baseline (bases first, water second) as the star
comparison"; design details DECIDED 2026-09-09, section 10): the
two-phase planner experiment 3 compares the integrated model against.

Phase A, bases first, water-blind: choose base_open/n_aircraft while
assuming water is never the constraint. Implemented WITHOUT a second
model formulation, to make formula drift impossible: milp.build_model is
reused unchanged on a modified ModelParams whose water catalog is a
single VIRTUAL, zero-cost water point per instance, whose
t_fire_water[s,f,W_VIRTUAL] is the true minimum over the FULL real water
catalog for that fire. That is exactly the classical planner's implicit
assumption ("water will be available wherever I need it, at no charge"):
every drops/liters/cycle_time number phase A sees is the best physically
achievable one, and water costs nothing against its budget. Phase A gets
only a fraction phi of the total budget (the exogenous budget split a
sequential planner must pick a priori and the integrated model decides
endogenously, CLAUDE.md section 2); experiment 3 sweeps phi and reports
the BEST sequential result, so the integrated model is compared against
a best-case sequential planner, not a straw man.

Phase B, water second: the FULL section 5.2 model on the real water
catalog and the real total budget, with every base_open[i] and
n_aircraft[i,m] FIXED (variable bounds, the same mechanism
src/matheuristic/fix_and_optimize.py uses) to phase A's values, open or
closed. The solver only decides water_open and the recourse. Because
phase A's spend enters constraint 1 through the fixed variables, phase B
can only afford water out of what phase A left over, which is the whole
point: a bad phi starves the water network, and no phi can replicate the
integrated model's joint tradeoff when the coupling matters.

The phase B objective value is directly comparable to the integrated
model's (same objective, same constraints, same scenario set), and can
never beat the integrated optimum on the same instance (the sequential
solution is feasible for the integrated model), which the tests assert.
"""

from __future__ import annotations

from dataclasses import dataclass

import pulp

from .milp import SolveResult, build_model, solve, solve_model
from .precompute import precompute
from .schema import ModelParams

VIRTUAL_WATER_ID = "W_VIRTUAL"


def make_water_blind_params(params: ModelParams, base_budget: float) -> ModelParams:
    """Phase A's ModelParams: the real water catalog replaced by one
    virtual, zero-cost point whose t_fire_water is each fire's true best
    over the full catalog, and the budget replaced by base_budget
    (phi * total). Raises ValueError if params has no water points at all
    (a best-over-the-catalog is undefined then, and the sequential
    baseline is meaningless)."""
    if not params.water_points:
        raise ValueError("make_water_blind_params needs a non-empty real water catalog")

    t_fire_water: dict[tuple[str, str, str], float] = {}
    for scenario in params.scenarios:
        s = scenario.scenario_id
        for fire in scenario.fires:
            f_id = fire.fire_id
            best = min(params.t_fire_water[(s, f_id, k)] for k in params.water_points)
            t_fire_water[(s, f_id, VIRTUAL_WATER_ID)] = best

    return ModelParams(
        bases=params.bases,
        water_points=[VIRTUAL_WATER_ID],
        aircraft_types=params.aircraft_types,
        scenarios=params.scenarios,
        budget=base_budget,
        window=params.window,
        ops_time=params.ops_time,
        cvar_alpha=params.cvar_alpha,
        mean_risk_weight=params.mean_risk_weight,
        initial_fire_area=params.initial_fire_area,
        liters_per_sqm=params.liters_per_sqm,
        cost_base=params.cost_base,
        cost_aircraft=params.cost_aircraft,
        cost_water={VIRTUAL_WATER_ID: 0.0},
        tank=params.tank,
        speed=params.speed,
        t_base_fire=params.t_base_fire,
        t_fire_water=t_fire_water,
    )


@dataclass
class PhaseAResult:
    status: str
    base_open: dict[str, bool]
    n_aircraft: dict[tuple[str, str], int]
    spend: float


def solve_phase_a(
    params: ModelParams, phi: float, solver_factory=lambda: pulp.PULP_CBC_CMD(msg=False)
) -> PhaseAResult:
    """Solve the water-blind phase A model with budget phi * params.budget.
    Returns the first-stage base/aircraft decisions and their spend (the
    virtual water point costs 0, so spend is bases plus aircraft only)."""
    if not 0.0 <= phi <= 1.0:
        raise ValueError(f"phi must be in [0, 1], got {phi}")
    blind = make_water_blind_params(params, base_budget=phi * params.budget)
    pre = precompute(blind)
    result = solve_model(blind, pre, solver=solver_factory())
    spend = sum(params.cost_base[i] for i, open_ in result.base_open.items() if open_) + sum(
        params.cost_aircraft[m] * n for (i, m), n in result.n_aircraft.items()
    )
    return PhaseAResult(
        status=result.status,
        base_open=result.base_open,
        n_aircraft=result.n_aircraft,
        spend=spend,
    )


def solve_phase_b(
    params: ModelParams,
    phase_a: PhaseAResult,
    solver_factory=lambda: pulp.PULP_CBC_CMD(msg=False),
) -> SolveResult:
    """Solve the FULL section 5.2 model (real water catalog, real total
    budget) with base_open/n_aircraft fixed to phase A's values via
    variable bounds, open or closed; only water_open and the recourse are
    decided. Fixing closed bases to 0 is deliberate: a sequential planner
    does not reopen the basing question during water siting."""
    pre = precompute(params)
    model, v = build_model(params, pre)
    for i in params.bases:
        val = 1 if phase_a.base_open.get(i, False) else 0
        v.base_open[i].lowBound = v.base_open[i].upBound = val
        for m in params.aircraft_types:
            n_val = phase_a.n_aircraft.get((i, m), 0)
            v.n_aircraft[(i, m)].lowBound = v.n_aircraft[(i, m)].upBound = n_val
    status = solve(model, solver=solver_factory())
    obj = pulp.value(model.objective) if status == "Optimal" else None

    from .milp import _as_bool, _as_int

    return SolveResult(
        status=status,
        objective_value=obj,
        base_open={i: _as_bool(pulp.value(var)) for i, var in v.base_open.items()},
        water_open={k: _as_bool(pulp.value(var)) for k, var in v.water_open.items()},
        n_aircraft={key: _as_int(pulp.value(var)) for key, var in v.n_aircraft.items()},
        dispatch={key: _as_int(pulp.value(var)) for key, var in v.dispatch.items()},
        refill_at={key: _as_bool(pulp.value(var)) for key, var in v.refill_at.items()},
        escape={key: _as_bool(pulp.value(var)) for key, var in v.escape.items()},
        delivered={key: pulp.value(var) or 0.0 for key, var in v.delivered.items()},
        loss={s: pulp.value(var) or 0.0 for s, var in v.loss.items()},
        var_level=pulp.value(v.var_level),
        cvar_excess={s: pulp.value(var) or 0.0 for s, var in v.cvar_excess.items()},
    )


@dataclass
class SequentialResult:
    phi: float
    phase_a: PhaseAResult
    phase_b: SolveResult

    @property
    def objective_value(self) -> float | None:
        return self.phase_b.objective_value


def solve_sequential(
    params: ModelParams, phi: float, solver_factory=lambda: pulp.PULP_CBC_CMD(msg=False)
) -> SequentialResult:
    """Run the full sequential baseline at one budget split phi."""
    phase_a = solve_phase_a(params, phi, solver_factory)
    if phase_a.status != "Optimal":
        raise ValueError(f"phase A did not solve to optimality: {phase_a.status}")
    phase_b = solve_phase_b(params, phase_a, solver_factory)
    return SequentialResult(phi=phi, phase_a=phase_a, phase_b=phase_b)


def solve_sequential_best_phi(
    params: ModelParams,
    phis: list[float],
    solver_factory=lambda: pulp.PULP_CBC_CMD(msg=False),
) -> tuple[SequentialResult, list[SequentialResult]]:
    """Sweep the budget split and return (best sequential result, all of
    them). "Best" is the lowest phase B objective among splits whose
    phase B solved to optimality; raises ValueError if none did. This is
    the best-case sequential planner experiment 3 compares against."""
    results = [solve_sequential(params, phi, solver_factory) for phi in phis]
    solved = [r for r in results if r.phase_b.status == "Optimal"]
    if not solved:
        raise ValueError("no phi produced an optimal phase B solve")
    best = min(solved, key=lambda r: r.objective_value)
    return best, results
