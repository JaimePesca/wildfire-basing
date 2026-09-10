"""Fix-and-optimize matheuristic (Helber and Sahling 2010, International
Journal of Production Economics 123(2):247-256) with LNS (Shaw 1998, CP98,
LNCS 1520, pp. 417-431) over first-stage variables (CLAUDE.md section 3,
FROZEN method choice; section 10, 2026-08-30: neighborhoods are geographic,
see neighborhoods.py).

Why this exists, concretely: CLAUDE.md section 10/src/model/README.md's
"First real-data solve" note found the real candidate water point set
(5,449 sites) intractable for an exact, all-at-once MILP solve (the exact
McCormick linearization adds |I|*|K| serve[i,f,k,m,s] auxiliary variables
per fire per scenario). This module is the actual answer to that problem,
not a separate concern: each LNS iteration solves a REDUCED sub-MILP
containing only (a) the current neighborhood's candidate sites (free to
reconsider) and (b) whatever sites are already open in the incumbent
(fixed open, kept only so their real contribution to budget/containment
stays correctly represented). A site that is closed in the incumbent and
outside the current neighborhood is dropped from the sub-problem entirely,
which is exact, not an approximation: a dropped site is mathematically
identical to one with base_open/water_open forced to 0 (see
build_reduced_params's docstring for the full argument). This keeps every
sub-MILP's serve-variable count bounded by the neighborhood size plus
however many sites the incumbent has opened so far, not the full 5,449,
regardless of how large the real candidate catalog is.

Deliberately unchanged from CLAUDE.md section 5.2/milp.py: every
constraint, the objective, and the full scenario/fire set. LNS here only
ever restricts which first-stage SITES (bases, water points) a sub-MILP is
allowed to reconsider; it does not subset scenarios (CLAUDE.md section 3
says "LNS ... over first-stage variables", not over the recourse problem).
Every sub-MILP therefore still solves the complete scenario set, which is
a separate, not-yet-addressed potential performance concern if the real
scenario/fire counts turn out to be large, distinct from the water-point
tractability problem this module solves.

GUROBI() reuse hazard (CLAUDE.md section 10, src/model/milp.py's solve()
docstring): this module calls build_model fresh every iteration and
requires a solver FACTORY (a zero-argument callable returning a brand new
solver instance), never a shared solver object, specifically to avoid
that exact corruption across the many sub-MILP solves an LNS run performs.

random_destroy_prob (ADDED 2026-09-04, see neighborhoods.py's module
docstring for the full story): a real run against the actual candidate
catalog found the pure-geographic destroy operator can get permanently
stuck strictly short of the true optimum, when the beneficial move needs to
jointly reconsider two sites that are far apart geographically (confirmed:
200 iterations, zero improvement past the first, for a case needing exactly
this kind of trade). Passed straight through to neighborhoods.pick_neighborhood;
default 0.0 keeps run_fix_and_optimize's original pure-geographic behavior
unchanged for any caller that does not opt in, including every existing
test in this package.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd
import pulp

from src.model.milp import Variables, build_model, solve
from src.model.precompute import precompute
from src.model.schema import ModelParams

from .neighborhoods import pick_neighborhood


@dataclass
class FirstStageSolution:
    """The only state carried between LNS iterations: which sites are open
    and how many aircraft are stationed where. Second-stage values
    (dispatch, refill_at, delivered, escape, ...) are never carried across
    iterations, each sub-MILP solve derives them fresh and self-consistently
    from whatever first-stage values that iteration's sub-problem fixes."""

    base_open: dict[str, bool] = field(default_factory=dict)
    water_open: dict[str, bool] = field(default_factory=dict)
    n_aircraft: dict[tuple[str, str], int] = field(default_factory=dict)


def initial_solution() -> FirstStageSolution:
    """Every candidate site closed, no aircraft anywhere. Always feasible
    (budget constraint holds trivially at zero spend) regardless of budget,
    so no separate constructive heuristic is needed to seed the search;
    every fire escapes under this solution, giving a well-defined, easily
    hand-checked starting objective (CLAUDE.md section 5.2 constraint 7
    forces escape=1 when delivered=0)."""
    return FirstStageSolution()


def build_reduced_params(
    params: ModelParams,
    incumbent: FirstStageSolution,
    free_bases: set[str],
    free_water: set[str],
) -> ModelParams:
    """Construct the sub-MILP's ModelParams: keep only sites that are
    either in the current neighborhood (free_bases/free_water) or already
    open in the incumbent (kept fixed open, see module docstring for why
    dropping a closed, non-neighborhood site is exact, not approximate).
    t_base_fire/t_fire_water/cost_base/cost_water are filtered to match.
    """
    keep_bases = free_bases | {i for i in params.bases if incumbent.base_open.get(i, False)}
    keep_water = free_water | {k for k in params.water_points if incumbent.water_open.get(k, False)}

    t_base_fire = {key: v for key, v in params.t_base_fire.items() if key[1] in keep_bases}
    t_fire_water = {key: v for key, v in params.t_fire_water.items() if key[2] in keep_water}
    cost_base = {i: params.cost_base[i] for i in keep_bases}
    cost_water = {k: params.cost_water[k] for k in keep_water}

    return ModelParams(
        bases=sorted(keep_bases),
        water_points=sorted(keep_water),
        aircraft_types=params.aircraft_types,
        scenarios=params.scenarios,
        budget=params.budget,
        window=params.window,
        ops_time=params.ops_time,
        cvar_alpha=params.cvar_alpha,
        mean_risk_weight=params.mean_risk_weight,
        initial_fire_area=params.initial_fire_area,
        liters_per_sqm=params.liters_per_sqm,
        cost_base=cost_base,
        cost_aircraft=params.cost_aircraft,
        cost_water=cost_water,
        tank=params.tank,
        speed=params.speed,
        t_base_fire=t_base_fire,
        t_fire_water=t_fire_water,
    )


def fix_non_neighborhood_variables(
    v: Variables,
    reduced_params: ModelParams,
    incumbent: FirstStageSolution,
    free_bases: set[str],
    free_water: set[str],
) -> None:
    """After build_model(reduced_params, ...), lock base_open/n_aircraft for
    every base in reduced_params.bases that is NOT in the current
    neighborhood to its incumbent value, by setting the PuLP variable's
    lowBound=upBound (standard PuLP variable-fixing, no constraint-set
    change). By construction of build_reduced_params, every such base is
    open in the incumbent (a closed, non-neighborhood base was already
    dropped from reduced_params entirely), so this always fixes to open
    (1) with the incumbent's aircraft count, never to closed. Same for
    water points."""
    for i in reduced_params.bases:
        if i in free_bases:
            continue
        v.base_open[i].lowBound = v.base_open[i].upBound = 1
        for m in reduced_params.aircraft_types:
            n_val = incumbent.n_aircraft.get((i, m), 0)
            v.n_aircraft[(i, m)].lowBound = v.n_aircraft[(i, m)].upBound = n_val
    for k in reduced_params.water_points:
        if k in free_water:
            continue
        v.water_open[k].lowBound = v.water_open[k].upBound = 1


def _extract_first_stage(v: Variables) -> FirstStageSolution:
    return FirstStageSolution(
        base_open={i: bool(round(pulp.value(var))) for i, var in v.base_open.items()},
        water_open={k: bool(round(pulp.value(var))) for k, var in v.water_open.items()},
        n_aircraft={key: int(round(pulp.value(var))) for key, var in v.n_aircraft.items()},
    )


def _merge_into_incumbent(
    incumbent: FirstStageSolution, reduced_solution: FirstStageSolution
) -> FirstStageSolution:
    """Sites present in the reduced sub-problem take their freshly solved
    value (whether newly decided by a free variable, or re-confirmed by a
    fixed one); every other site (dropped from the sub-problem, i.e.
    closed and outside the neighborhood) stays closed, unchanged from the
    prior incumbent."""
    base_open = dict(incumbent.base_open)
    base_open.update(reduced_solution.base_open)
    water_open = dict(incumbent.water_open)
    water_open.update(reduced_solution.water_open)
    n_aircraft = dict(incumbent.n_aircraft)
    n_aircraft.update(reduced_solution.n_aircraft)
    return FirstStageSolution(base_open=base_open, water_open=water_open, n_aircraft=n_aircraft)


@dataclass
class IterationRecord:
    iteration: int
    free_bases: set[str]
    free_water: set[str]
    status: str
    objective_value: float | None
    accepted: bool


@dataclass
class FixAndOptimizeResult:
    incumbent: FirstStageSolution
    objective_value: float
    history: list[IterationRecord]


def run_fix_and_optimize(
    params: ModelParams,
    bases: pd.DataFrame,
    water_points: pd.DataFrame,
    *,
    n_bases_per_neighborhood: int,
    n_water_per_neighborhood: int,
    max_iterations: int,
    no_improve_limit: int | None = None,
    seed: int = 0,
    solver_factory=lambda: pulp.PULP_CBC_CMD(msg=False),
    initial: FirstStageSolution | None = None,
    random_destroy_prob: float = 0.0,
) -> FixAndOptimizeResult:
    """Run the LNS loop: each iteration picks a neighborhood
    (neighborhoods.pick_neighborhood), solves the corresponding reduced,
    exact sub-MILP, and accepts the result only if it strictly improves the
    incumbent objective (the simplest, standard fix-and-optimize/LNS
    acceptance rule; Helber and Sahling 2010 also just keep the better of
    the two at each step, no simulated-annealing-style acceptance of worse
    solutions). Stops at max_iterations, or earlier if no_improve_limit is
    given and that many consecutive iterations fail to improve.

    solver_factory must be a zero-argument callable returning a FRESH
    solver instance (default pulp.PULP_CBC_CMD(msg=False)); pass e.g.
    `lambda: pulp.GUROBI(msg=False)` for Gurobi, never a shared solver
    object (see module docstring's GUROBI() reuse hazard note).

    random_destroy_prob: passed straight through to
    neighborhoods.pick_neighborhood (see that module's docstring and this
    module's docstring, both updated 2026-09-04): with this probability,
    each iteration frees sites uniformly at random from the whole candidate
    set instead of the default geographic-proximity operator, needed to
    escape a real, confirmed local optimum the pure-geographic operator
    cannot reach on its own. Default 0.0 preserves the original behavior.

    bases/water_points are the real candidate-site DataFrames
    (site_id/x_utm/y_utm), separate from params (see neighborhoods.py's
    docstring for why).
    """
    rng = np.random.default_rng(seed)
    incumbent = initial if initial is not None else initial_solution()
    incumbent_objective = _resolve_objective(params, incumbent, solver_factory)

    history: list[IterationRecord] = []
    no_improve_streak = 0

    for iteration in range(max_iterations):
        free_bases, free_water = pick_neighborhood(
            bases, water_points, rng, n_bases_per_neighborhood, n_water_per_neighborhood,
            random_destroy_prob=random_destroy_prob,
        )
        reduced_params = build_reduced_params(params, incumbent, free_bases, free_water)
        pre = precompute(reduced_params)
        model, v = build_model(reduced_params, pre)
        fix_non_neighborhood_variables(v, reduced_params, incumbent, free_bases, free_water)
        status = solve(model, solver=solver_factory())
        objective_value = pulp.value(model.objective) if status == "Optimal" else None

        accepted = status == "Optimal" and objective_value < incumbent_objective - 1e-9
        if accepted:
            reduced_solution = _extract_first_stage(v)
            incumbent = _merge_into_incumbent(incumbent, reduced_solution)
            incumbent_objective = objective_value
            no_improve_streak = 0
        else:
            no_improve_streak += 1

        history.append(
            IterationRecord(
                iteration=iteration,
                free_bases=free_bases,
                free_water=free_water,
                status=status,
                objective_value=objective_value,
                accepted=accepted,
            )
        )

        if no_improve_limit is not None and no_improve_streak >= no_improve_limit:
            break

    return FixAndOptimizeResult(incumbent=incumbent, objective_value=incumbent_objective, history=history)


def _resolve_objective(params: ModelParams, incumbent: FirstStageSolution, solver_factory) -> float:
    """Solve the full model once with EVERY site fixed to the given
    incumbent's exact values (an empty neighborhood: nothing is left free),
    to score a starting solution before any LNS iteration runs. Passing an
    empty free_bases/free_water to build_reduced_params/
    fix_non_neighborhood_variables is deliberate here, not a placeholder:
    it means every open site is kept and fixed open, every closed site is
    dropped, and nothing is left for the solver to reconsider, which is
    exactly "evaluate this incumbent" rather than "search from it"."""
    reduced_params = build_reduced_params(params, incumbent, free_bases=set(), free_water=set())
    pre = precompute(reduced_params)
    model, v = build_model(reduced_params, pre)
    fix_non_neighborhood_variables(v, reduced_params, incumbent, free_bases=set(), free_water=set())
    status = solve(model, solver=solver_factory())
    if status != "Optimal":
        raise ValueError(f"could not evaluate the supplied initial solution, solver status: {status}")
    return pulp.value(model.objective)
