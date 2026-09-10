"""Shared helper for the experiment scripts: a time-limited Gurobi
solve of the full section 5.2 MILP that still reports the best
incumbent found when the limit cuts the search short.

Why this exists (found the hard way, 2026-09-10, CLAUDE.md section 10):
experiment 3's two-aircraft-regime probe (budget 160,000M, 20 bases, 50
water points, 10 scenarios, 81 fires) ran a direct, un-limited
solve_model for almost 16 wall-clock hours (about 48 CPU-hours) without
proving optimality before being killed. Multi-aircraft regimes blow up
the direct MILP even at modest catalog sizes, which is precisely
experiment 2's thesis and the matheuristic's reason to exist; any
experiment whose sweep can enter such a regime (experiment 3's budget
probes, experiment 6's budget axis) must therefore bound its solves and
report (incumbent, MIP gap, timed_out) honestly instead of hanging.

milp.solve_model cannot be reused for this: it discards the objective
on any non-Optimal status, and PuLP maps Gurobi's TIME_LIMIT to
"Not Solved" even when a perfectly good incumbent exists. Gurobi keeps
incumbent variable values whenever SolCount >= 1 (PuLP's gurobi_api
findSolutionValues populates them), so this helper extracts the full
solution regardless of proof status, alongside the remaining MIP gap.
Same pattern experiment 2's _solve_pure_gurobi already used inline;
lifted here so experiments 3, 4 and 6 share one implementation.
"""

from __future__ import annotations

import time
from dataclasses import dataclass

import pulp

from src.model.milp import SolveResult, _as_bool, _as_int, build_model, solve
from src.model.precompute import Precomputed
from src.model.schema import ModelParams


@dataclass
class TimedSolve:
    solution: SolveResult
    mip_gap: float | None
    timed_out: bool
    elapsed_s: float


def solve_with_time_limit(
    params: ModelParams,
    pre: Precomputed,
    time_limit_s: float | None,
    gap_rel: float = 0.0,
) -> TimedSolve:
    """Build and solve the full MILP with Gurobi under a wall-clock
    limit (None = no limit, use sparingly, see module docstring).
    solution.objective_value carries the best incumbent even when the
    limit was hit (status "Not Solved" per PuLP's mapping); it is None
    only when no incumbent exists at all. mip_gap is Gurobi's remaining
    relative gap for the incumbent, timed_out says whether the limit
    cut the search short of proof."""
    model, v = build_model(params, pre)
    solver = pulp.GUROBI(msg=False, timeLimit=time_limit_s, gapRel=gap_rel)
    start = time.perf_counter()
    status = solve(model, solver=solver)
    elapsed = time.perf_counter() - start

    mip_gap = None
    timed_out = False
    has_incumbent = False
    solver_model = getattr(model, "solverModel", None)
    if solver_model is not None:
        import gurobipy as gp

        timed_out = solver_model.Status == gp.GRB.TIME_LIMIT
        has_incumbent = solver_model.SolCount >= 1
        if has_incumbent:
            try:
                mip_gap = solver_model.MIPGap
            except AttributeError:
                mip_gap = None

    objective = pulp.value(model.objective) if (status == "Optimal" or has_incumbent) else None
    solution = SolveResult(
        status=status,
        objective_value=objective,
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
    return TimedSolve(solution=solution, mip_gap=mip_gap, timed_out=timed_out, elapsed_s=elapsed)
