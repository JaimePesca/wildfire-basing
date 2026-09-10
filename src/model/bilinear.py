"""The literal bilinear formulation (CLAUDE.md section 5.2, "What experiment
1 now compares"): delivered[f,s] as the direct product

    delivered[f,s] = sum_i sum_k sum_m liters[i,f,k,m] * dispatch[i,f,m,s] * refill_at[f,k,s]

with no serve auxiliary and no big-M linearization, dispatch (integer) times
refill_at (binary) multiplied directly. This is deliberately NOT the same
model as milp.py: milp.py is the exact linearized MILP (section 5.2
constraints 6a-6e); this module is the other half of experiment 1 (section
9), the pre-linearization bilinear/quadratic MIP, solved via a solver's
native quadratic support, not approximated.

Implemented directly against gurobipy (CONFIRMED WORKING 2026-08-30, see
CLAUDE.md section 10 and src/model/README.md): PuLP (used in milp.py) has
no native quadratic/bilinear support, and its bundled CBC does not solve
MIQPs either. liters[i,f,k,m] * dispatch[i,f,m,s] * refill_at[f,k,s] is a
constant coefficient (liters is precomputed, section 5.2) times a genuine
variable-times-variable bilinear term (integer dispatch times binary
refill_at); Gurobi handles this as a general, possibly nonconvex, quadratic
constraint, which requires NonConvex=2 (Gurobi refuses an indefinite QCQP
otherwise). Every other constraint (1-5, 7, 8, 9) is identical to milp.py,
only constraint 6 differs; each is labeled with its section 5.2 number
below so it can be checked directly against milp.py and against CLAUDE.md.

Mirrors milp.py's (build_model, solve, SolveResult, solve_model) shape
deliberately, so experiment 1's comparison code can call both on the same
(params, pre) and diff the two SolveResult-shaped outputs directly.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import gurobipy as gp
from gurobipy import GRB

from .precompute import Precomputed
from .schema import ModelParams


@dataclass
class BilinearVariables:
    base_open: dict[str, gp.Var] = field(default_factory=dict)
    water_open: dict[str, gp.Var] = field(default_factory=dict)
    n_aircraft: dict[tuple[str, str], gp.Var] = field(default_factory=dict)
    dispatch: dict[tuple[str, str, str, str], gp.Var] = field(default_factory=dict)
    refill_at: dict[tuple[str, str, str], gp.Var] = field(default_factory=dict)
    delivered: dict[tuple[str, str], gp.Var] = field(default_factory=dict)
    escape: dict[tuple[str, str], gp.Var] = field(default_factory=dict)
    loss: dict[str, gp.Var] = field(default_factory=dict)
    cvar_excess: dict[str, gp.Var] = field(default_factory=dict)
    var_level: gp.Var | None = None


def _declare_variables(model: gp.Model, params: ModelParams) -> BilinearVariables:
    v = BilinearVariables()

    for i in params.bases:
        v.base_open[i] = model.addVar(vtype=GRB.BINARY, name=f"base_open_{i}")
    for k in params.water_points:
        v.water_open[k] = model.addVar(vtype=GRB.BINARY, name=f"water_open_{k}")
    for i in params.bases:
        for m in params.aircraft_types:
            v.n_aircraft[(i, m)] = model.addVar(vtype=GRB.INTEGER, lb=0, name=f"n_aircraft_{i}_{m}")

    for scenario in params.scenarios:
        s = scenario.scenario_id
        v.loss[s] = model.addVar(vtype=GRB.CONTINUOUS, lb=0, name=f"loss_{s}")
        v.cvar_excess[s] = model.addVar(vtype=GRB.CONTINUOUS, lb=0, name=f"cvar_excess_{s}")
        for fire in scenario.fires:
            f_id = fire.fire_id
            v.delivered[(s, f_id)] = model.addVar(
                vtype=GRB.CONTINUOUS, lb=0, name=f"delivered_{s}_{f_id}"
            )
            v.escape[(s, f_id)] = model.addVar(vtype=GRB.BINARY, name=f"escape_{s}_{f_id}")
            for k in params.water_points:
                v.refill_at[(s, f_id, k)] = model.addVar(
                    vtype=GRB.BINARY, name=f"refill_at_{s}_{f_id}_{k}"
                )
            for i in params.bases:
                for m in params.aircraft_types:
                    v.dispatch[(s, i, f_id, m)] = model.addVar(
                        vtype=GRB.INTEGER, lb=0, name=f"dispatch_{s}_{i}_{f_id}_{m}"
                    )

    v.var_level = model.addVar(vtype=GRB.CONTINUOUS, lb=-GRB.INFINITY, name="var_level")
    return v


def build_bilinear_model(params: ModelParams, pre: Precomputed) -> tuple[gp.Model, BilinearVariables]:
    """Build the literal bilinear MIQCP. Returns (model, variables); pass
    both to solve()/solve_bilinear_model. Requires a licensed gurobipy
    (RuntimeError from a stale build of this module used to fire here when
    no license was available; that blocker is gone, CLAUDE.md section 10)."""
    model = gp.Model("wildfire_base_water_siting_bilinear")
    model.Params.NonConvex = 2  # dispatch * refill_at is a general, possibly indefinite, bilinear term
    model.Params.OutputFlag = 0
    v = _declare_variables(model, params)

    lam = params.mean_risk_weight
    alpha = params.cvar_alpha
    expectation_term = gp.quicksum(
        scenario.probability * v.loss[scenario.scenario_id] for scenario in params.scenarios
    )
    cvar_term = v.var_level + (1.0 / (1.0 - alpha)) * gp.quicksum(
        scenario.probability * v.cvar_excess[scenario.scenario_id] for scenario in params.scenarios
    )
    model.setObjective((1 - lam) * expectation_term + lam * cvar_term, GRB.MINIMIZE)

    # 1. Budget.
    model.addConstr(
        gp.quicksum(params.cost_base[i] * v.base_open[i] for i in params.bases)
        + gp.quicksum(
            params.cost_aircraft[m] * v.n_aircraft[(i, m)]
            for i in params.bases
            for m in params.aircraft_types
        )
        + gp.quicksum(params.cost_water[k] * v.water_open[k] for k in params.water_points)
        <= params.budget,
        name="budget",
    )

    # 2. Aircraft only at open bases, for all i, m.
    for i in params.bases:
        for m in params.aircraft_types:
            model.addConstr(
                v.n_aircraft[(i, m)] <= pre.Mbig[m] * v.base_open[i],
                name=f"aircraft_only_at_open_base_{i}_{m}",
            )

    for scenario in params.scenarios:
        s = scenario.scenario_id

        # 3. Refill only at enabled points, for all f, k (this s).
        for fire in scenario.fires:
            f_id = fire.fire_id
            for k in params.water_points:
                model.addConstr(
                    v.refill_at[(s, f_id, k)] <= v.water_open[k],
                    name=f"refill_only_enabled_{s}_{f_id}_{k}",
                )

        # 4. One refill point per served fire, for all f (this s).
        for fire in scenario.fires:
            f_id = fire.fire_id
            model.addConstr(
                gp.quicksum(v.refill_at[(s, f_id, k)] for k in params.water_points) <= 1,
                name=f"one_refill_point_{s}_{f_id}",
            )

        # 5. Dispatch limited by stationed fleet, for all i, m (this s).
        for i in params.bases:
            for m in params.aircraft_types:
                model.addConstr(
                    gp.quicksum(v.dispatch[(s, i, fire.fire_id, m)] for fire in scenario.fires)
                    <= v.n_aircraft[(i, m)],
                    name=f"fleet_limit_{s}_{i}_{m}",
                )

        # 6. Delivered liters, LITERAL BILINEAR PRODUCT (the difference from
        # milp.py: no serve auxiliary, no big-M, dispatch * refill_at
        # multiplied directly, liters[i,f,k,m] is the precomputed constant
        # coefficient, section 5.2).
        for fire in scenario.fires:
            f_id = fire.fire_id
            model.addConstr(
                v.delivered[(s, f_id)]
                == gp.quicksum(
                    pre.liters[(s, i, f_id, k, m)]
                    * v.dispatch[(s, i, f_id, m)]
                    * v.refill_at[(s, f_id, k)]
                    for i in params.bases
                    for k in params.water_points
                    for m in params.aircraft_types
                ),
                name=f"delivered_liters_bilinear_{s}_{f_id}",
            )

        # 7. Containment, for all f (this s).
        for fire in scenario.fires:
            f_id = fire.fire_id
            requirement_f = pre.requirement[(s, f_id)]
            model.addConstr(
                v.delivered[(s, f_id)] >= requirement_f * (1 - v.escape[(s, f_id)]),
                name=f"containment_{s}_{f_id}",
            )

        # 8a. Scenario loss.
        model.addConstr(
            v.loss[s]
            == gp.quicksum(fire.value_at_risk * v.escape[(s, fire.fire_id)] for fire in scenario.fires),
            name=f"scenario_loss_{s}",
        )
        # 8b. CVaR excess.
        model.addConstr(v.cvar_excess[s] >= v.loss[s] - v.var_level, name=f"cvar_excess_{s}")
        # 8c. cvar_excess[s] >= 0 is enforced by lb=0 at declaration.

    # 9. Variable types/bounds already enforced by vtype=/lb= at declaration.

    return model, v


def solve(model: gp.Model) -> str:
    """Solve the model in place. Returns a PuLP-style status string
    ("Optimal", "Infeasible", "Unbounded", ...) so callers comparing this
    against milp.solve()'s output can use the same string values.

    Same GUROBI() reuse hazard as milp.py does NOT apply here: this module
    builds a fresh gp.Model per call to build_bilinear_model, never reusing
    one across solves, so there is nothing to guard against on that front.
    Do still construct a fresh (params, pre) -> build_bilinear_model call
    per solve if used in a loop (a sweep or matheuristic iteration), rather
    than mutating and re-solving the same gp.Model."""
    model.optimize()
    status_map = {
        GRB.OPTIMAL: "Optimal",
        GRB.INFEASIBLE: "Infeasible",
        GRB.UNBOUNDED: "Unbounded",
        GRB.INF_OR_UNBD: "Undefined",
        GRB.TIME_LIMIT: "Not Solved",
    }
    return status_map.get(model.status, f"GurobiStatus_{model.status}")


@dataclass
class BilinearSolveResult:
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


def _as_bool(x: float) -> bool:
    return bool(round(x))


def _as_int(x: float) -> int:
    return int(round(x))


def solve_bilinear_model(params: ModelParams, pre: Precomputed) -> BilinearSolveResult:
    """Build, solve, and extract the literal bilinear MIQCP's solution in
    one call, mirroring milp.solve_model's shape exactly."""
    model, v = build_bilinear_model(params, pre)
    status = solve(model)
    is_optimal = status == "Optimal"

    return BilinearSolveResult(
        status=status,
        objective_value=model.ObjVal if is_optimal else None,
        base_open={i: _as_bool(var.X) for i, var in v.base_open.items()} if is_optimal else {},
        water_open={k: _as_bool(var.X) for k, var in v.water_open.items()} if is_optimal else {},
        n_aircraft={key: _as_int(var.X) for key, var in v.n_aircraft.items()} if is_optimal else {},
        dispatch={key: _as_int(var.X) for key, var in v.dispatch.items()} if is_optimal else {},
        refill_at={key: _as_bool(var.X) for key, var in v.refill_at.items()} if is_optimal else {},
        escape={key: _as_bool(var.X) for key, var in v.escape.items()} if is_optimal else {},
        delivered={key: var.X for key, var in v.delivered.items()} if is_optimal else {},
        loss={s: var.X for s, var in v.loss.items()} if is_optimal else {},
        var_level=v.var_level.X if is_optimal else None,
        cvar_excess={s: var.X for s, var in v.cvar_excess.items()} if is_optimal else {},
    )
