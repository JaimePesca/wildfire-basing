"""The big-M linearized MILP (CLAUDE.md section 5.2, constraints 1-9 and the
objective), built with PuLP.

PuLP is used instead of gurobipy so this model is solvable today on PuLP's
bundled, free CBC solver, with no Gurobi license required. build_model()
returns a plain pulp.LpProblem; swapping to Gurobi later is a solver-backend
argument to solve() (pulp.GUROBI() / pulp.GUROBI_CMD()), not a rewrite of
build_model(). See src/model/README.md.

Every constraint below is labeled with its section 5.2 number so it can be
checked directly against CLAUDE.md. Variable and parameter names match
section 4's code identifiers exactly (CLAUDE.md preamble: "Code in this repo
and the manuscript must use the same symbols").
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pulp

from .precompute import Precomputed
from .schema import ModelParams


@dataclass
class Variables:
    base_open: dict[str, pulp.LpVariable] = field(default_factory=dict)
    water_open: dict[str, pulp.LpVariable] = field(default_factory=dict)
    n_aircraft: dict[tuple[str, str], pulp.LpVariable] = field(default_factory=dict)
    # all scenario-scoped dicts keyed with scenario_id first, matching precompute.py
    dispatch: dict[tuple[str, str, str, str], pulp.LpVariable] = field(default_factory=dict)
    refill_at: dict[tuple[str, str, str], pulp.LpVariable] = field(default_factory=dict)
    delivered: dict[tuple[str, str], pulp.LpVariable] = field(default_factory=dict)
    escape: dict[tuple[str, str], pulp.LpVariable] = field(default_factory=dict)
    loss: dict[str, pulp.LpVariable] = field(default_factory=dict)
    cvar_excess: dict[str, pulp.LpVariable] = field(default_factory=dict)
    serve: dict[tuple[str, str, str, str, str], pulp.LpVariable] = field(default_factory=dict)
    var_level: pulp.LpVariable | None = None


def _declare_variables(params: ModelParams) -> Variables:
    v = Variables()

    for i in params.bases:
        v.base_open[i] = pulp.LpVariable(f"base_open_{i}", cat=pulp.LpBinary)
    for k in params.water_points:
        v.water_open[k] = pulp.LpVariable(f"water_open_{k}", cat=pulp.LpBinary)
    for i in params.bases:
        for m in params.aircraft_types:
            v.n_aircraft[(i, m)] = pulp.LpVariable(
                f"n_aircraft_{i}_{m}", lowBound=0, cat=pulp.LpInteger
            )

    for scenario in params.scenarios:
        s = scenario.scenario_id
        v.loss[s] = pulp.LpVariable(f"loss_{s}", lowBound=0, cat=pulp.LpContinuous)
        v.cvar_excess[s] = pulp.LpVariable(f"cvar_excess_{s}", lowBound=0, cat=pulp.LpContinuous)
        for fire in scenario.fires:
            f_id = fire.fire_id
            v.delivered[(s, f_id)] = pulp.LpVariable(
                f"delivered_{s}_{f_id}", lowBound=0, cat=pulp.LpContinuous
            )
            v.escape[(s, f_id)] = pulp.LpVariable(f"escape_{s}_{f_id}", cat=pulp.LpBinary)
            for k in params.water_points:
                v.refill_at[(s, f_id, k)] = pulp.LpVariable(
                    f"refill_at_{s}_{f_id}_{k}", cat=pulp.LpBinary
                )
            for i in params.bases:
                for m in params.aircraft_types:
                    v.dispatch[(s, i, f_id, m)] = pulp.LpVariable(
                        f"dispatch_{s}_{i}_{f_id}_{m}", lowBound=0, cat=pulp.LpInteger
                    )
                    for k in params.water_points:
                        v.serve[(s, i, f_id, k, m)] = pulp.LpVariable(
                            f"serve_{s}_{i}_{f_id}_{k}_{m}", lowBound=0, cat=pulp.LpContinuous
                        )

    # var_level (eta): free, section 5.2 constraint 9, not forced nonnegative.
    v.var_level = pulp.LpVariable("var_level", lowBound=None, cat=pulp.LpContinuous)

    return v


def _validate_scenario_probabilities(params: ModelParams) -> None:
    """The CVaR objective (Rockafellar-Uryasev) is only convex/bounded under
    the standard precondition sum_s p_s = 1. CONFIRMED 2026-08-30 by direct
    reproduction: silently violating this (e.g. by slicing a subset of
    scenarios out of a larger bootstrap draw, such as
    read_scenarios_json(...)[:n], without renormalizing probabilities back
    to sum to 1 over that subset) does not raise a clear error, it makes
    the MILP genuinely UNBOUNDED (var_level can be driven to -infinity while
    cvar_excess grows to compensate, with no net objective penalty once
    sum_s p_s < 1). This matters beyond one-off scripts: any future
    scenario-subsetting workflow (an LNS neighborhood in the
    fix-and-optimize matheuristic, src/matheuristic/, or a reduced-scenario
    experiment) must renormalize probabilities, and this check exists so
    that forgetting to do so fails loudly here rather than as a mysterious
    solver-reported "Unbounded" status with no obvious cause."""
    if not params.scenarios:
        return
    total = sum(scenario.probability for scenario in params.scenarios)
    if abs(total - 1.0) > 1e-6:
        raise ValueError(
            f"scenario probabilities sum to {total}, not 1.0. The CVaR objective requires "
            "sum_s p_s = 1 (see build_model's _validate_scenario_probabilities docstring); "
            "if this ModelParams was built from a subset of a larger scenario draw, "
            "renormalize each scenario's probability to 1/len(scenarios) first."
        )


def build_model(params: ModelParams, pre: Precomputed) -> tuple[pulp.LpProblem, Variables]:
    """Build the section 5.2 MILP. Returns (model, variables); pass both to
    solve() and then read the variables' .varValue after solving."""
    _validate_scenario_probabilities(params)
    model = pulp.LpProblem("wildfire_base_water_siting", pulp.LpMinimize)
    v = _declare_variables(params)

    # Objective (section 4/5.2, unchanged):
    # min (1-lambda)*sum_s p_s*loss[s] + lambda*(var_level + (1/(1-alpha))*sum_s p_s*cvar_excess[s])
    lam = params.mean_risk_weight
    alpha = params.cvar_alpha
    expectation_term = pulp.lpSum(
        scenario.probability * v.loss[scenario.scenario_id] for scenario in params.scenarios
    )
    cvar_term = v.var_level + (1.0 / (1.0 - alpha)) * pulp.lpSum(
        scenario.probability * v.cvar_excess[scenario.scenario_id] for scenario in params.scenarios
    )
    model += (1 - lam) * expectation_term + lam * cvar_term, "objective"

    # 1. Budget.
    model += (
        pulp.lpSum(params.cost_base[i] * v.base_open[i] for i in params.bases)
        + pulp.lpSum(
            params.cost_aircraft[m] * v.n_aircraft[(i, m)]
            for i in params.bases
            for m in params.aircraft_types
        )
        + pulp.lpSum(params.cost_water[k] * v.water_open[k] for k in params.water_points)
        <= params.budget,
        "budget",
    )

    # 2. Aircraft only at open bases, for all i, m.
    for i in params.bases:
        for m in params.aircraft_types:
            model += (
                v.n_aircraft[(i, m)] <= pre.Mbig[m] * v.base_open[i],
                f"aircraft_only_at_open_base_{i}_{m}",
            )

    for scenario in params.scenarios:
        s = scenario.scenario_id

        # 3. Refill only at enabled points, for all f, k (this s).
        for fire in scenario.fires:
            f_id = fire.fire_id
            for k in params.water_points:
                model += (
                    v.refill_at[(s, f_id, k)] <= v.water_open[k],
                    f"refill_only_enabled_{s}_{f_id}_{k}",
                )

        # 4. One refill point per served fire, for all f (this s).
        for fire in scenario.fires:
            f_id = fire.fire_id
            model += (
                pulp.lpSum(v.refill_at[(s, f_id, k)] for k in params.water_points) <= 1,
                f"one_refill_point_{s}_{f_id}",
            )

        # 5. Dispatch limited by stationed fleet, for all i, m (this s).
        for i in params.bases:
            for m in params.aircraft_types:
                model += (
                    pulp.lpSum(
                        v.dispatch[(s, i, fire.fire_id, m)] for fire in scenario.fires
                    )
                    <= v.n_aircraft[(i, m)],
                    f"fleet_limit_{s}_{i}_{m}",
                )

        # 6. Delivered liters, McCormick linearization of dispatch * refill_at.
        for i in params.bases:
            for fire in scenario.fires:
                f_id = fire.fire_id
                for m in params.aircraft_types:
                    dispatch_var = v.dispatch[(s, i, f_id, m)]
                    mbig_m = pre.Mbig[m]
                    for k in params.water_points:
                        serve_var = v.serve[(s, i, f_id, k, m)]
                        refill_var = v.refill_at[(s, f_id, k)]
                        # 6a
                        model += (
                            serve_var <= dispatch_var,
                            f"serve_le_dispatch_{s}_{i}_{f_id}_{k}_{m}",
                        )
                        # 6b
                        model += (
                            serve_var <= mbig_m * refill_var,
                            f"serve_le_mbig_refill_{s}_{i}_{f_id}_{k}_{m}",
                        )
                        # 6c
                        model += (
                            serve_var >= dispatch_var - mbig_m * (1 - refill_var),
                            f"serve_ge_dispatch_minus_mbig_{s}_{i}_{f_id}_{k}_{m}",
                        )
                        # 6d (serve >= 0) is enforced by lowBound=0 at declaration.

        # 6e. delivered[f,s] = sum_i sum_k sum_m liters[i,f,k,m] * serve[i,f,k,m,s]
        for fire in scenario.fires:
            f_id = fire.fire_id
            model += (
                v.delivered[(s, f_id)]
                == pulp.lpSum(
                    pre.liters[(s, i, f_id, k, m)] * v.serve[(s, i, f_id, k, m)]
                    for i in params.bases
                    for k in params.water_points
                    for m in params.aircraft_types
                ),
                f"delivered_liters_{s}_{f_id}",
            )

        # 7. Containment, for all f (this s).
        for fire in scenario.fires:
            f_id = fire.fire_id
            requirement_f = pre.requirement[(s, f_id)]
            model += (
                v.delivered[(s, f_id)] >= requirement_f * (1 - v.escape[(s, f_id)]),
                f"containment_{s}_{f_id}",
            )

        # 8a. Scenario loss.
        model += (
            v.loss[s]
            == pulp.lpSum(fire.value_at_risk * v.escape[(s, fire.fire_id)] for fire in scenario.fires),
            f"scenario_loss_{s}",
        )
        # 8b. CVaR excess.
        model += (
            v.cvar_excess[s] >= v.loss[s] - v.var_level,
            f"cvar_excess_{s}",
        )
        # 8c. cvar_excess[s] >= 0 is enforced by lowBound=0 at declaration.

    # 9. base_open/water_open binary, n_aircraft/dispatch nonnegative integer,
    # refill_at/escape binary, delivered/loss/cvar_excess/serve nonnegative
    # continuous, var_level free: all already enforced by the cat=/lowBound=
    # arguments at variable declaration in _declare_variables above.

    return model, v


def solve(model: pulp.LpProblem, solver: pulp.LpSolver | None = None) -> str:
    """Solve the model in place. Defaults to PuLP's bundled CBC (msg=False);
    pass solver=pulp.GUROBI_CMD() or pulp.GUROBI() once a Gurobi license is
    available, no other code needs to change. Returns the PuLP status
    string (e.g. "Optimal", "Infeasible").

    GUROBI() REUSE HAZARD, CONFIRMED 2026-08-30 by direct reproduction: a
    single pulp.GUROBI() instance keeps its underlying gurobipy.Model on
    the solver object across calls and silently ACCUMULATES every
    LpProblem ever solved with that same instance into one Gurobi model,
    corrupting every solve after the first (the second solve's result can
    violate that second model's own constraints, e.g. a fire reported as
    contained with no base open at all). GUROBI_CMD() does not have this
    problem (it shells out a fresh process per solve). If passing
    solver=pulp.GUROBI(...), the caller MUST construct a brand new instance
    for every call to solve()/solve_model(), never reuse one across a loop
    (a sweep over experiment 6 parameters, or the matheuristic's
    fix-and-optimize/LNS iterations, src/matheuristic/, will each solve
    many sub-MILPs in sequence and must not share a GUROBI() instance
    between them). See tests/test_model_milp.py's module docstring for the
    reproduction."""
    if solver is None:
        solver = pulp.PULP_CBC_CMD(msg=False)
    model.solve(solver)
    return pulp.LpStatus[model.status]


@dataclass
class SolveResult:
    status: str
    objective_value: float | None
    base_open: dict[str, bool]
    water_open: dict[str, bool]
    n_aircraft: dict[tuple[str, str], int]
    dispatch: dict[tuple[str, str, str, str], int]
    refill_at: dict[tuple[str, str, str], bool]
    escape: dict[tuple[str, str], bool]
    delivered: dict[tuple[str, str], float]
    loss: dict[str, float]
    var_level: float | None
    cvar_excess: dict[str, float]


def _as_bool(x: float | None) -> bool:
    return bool(round(x)) if x is not None else False


def _as_int(x: float | None) -> int:
    return int(round(x)) if x is not None else 0


def solve_model(
    params: ModelParams, pre: Precomputed, solver: pulp.LpSolver | None = None
) -> SolveResult:
    """Build, solve, and extract the section 5.2 MILP's solution in one call."""
    model, v = build_model(params, pre)
    status = solve(model, solver=solver)
    obj = pulp.value(model.objective) if status == "Optimal" else None

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
