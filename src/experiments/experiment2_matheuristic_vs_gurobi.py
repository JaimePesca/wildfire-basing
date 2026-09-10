"""Experiment 2 (CLAUDE.md section 9): matheuristic vs pure Gurobi.

For a series of candidate-catalog sizes (n_bases, n_water_points), drawn
from the SAME real bases/water/scenario data as src/model/run_instance.py
and src/matheuristic/run_real_instance.py, this script solves the identical
instance two ways and compares them:

1. Pure Gurobi, direct: build_model() (the full, exact, section 5.2 MILP,
   src/model/milp.py) solved as one Gurobi call, with a wall-clock time
   limit (CLAUDE.md section 3: "pure Gurobi on small instances" is the
   named benchmark). If Gurobi does not prove optimality within the time
   limit, the best incumbent found so far and its remaining MIP gap are
   still reported (Gurobi keeps an incumbent's variable values even under
   TIME_LIMIT whenever SolCount >= 1, see pulp's gurobi_api.py
   findSolutionValues; solve_model()/milp.py's own wrapper discards the
   objective on any non-Optimal status, which is why this script calls
   build_model()/solve() directly instead of reusing solve_model()).
2. The fix-and-optimize/LNS matheuristic (src/matheuristic/fix_and_optimize.py),
   run on the exact same instance's full base/water set (no truncation
   beyond what this script's own instance-size sweep already applies), each
   LNS iteration itself calling Gurobi on a small reduced sub-MILP.

The comparison that matters for the paper: at small sizes pure Gurobi
should win outright (it can prove optimality fast, and the matheuristic
adds LNS overhead for no benefit); the experiment's real point is showing
where that crosses over, i.e. where pure Gurobi's per-instance solve time
starts blowing up (or timing out short of proven optimality) while the
matheuristic's per-iteration cost stays roughly flat, since each of its
sub-MILPs only ever sees a bounded neighborhood, not the whole catalog
(the same tractability argument as src/matheuristic/README.md's "why this
exists" section).

Two things this script does NOT resolve, both already flagged elsewhere and
repeated here for anyone reading this file in isolation:

1. budget/cvar_alpha/mean_risk_weight/window are the user's own call
   (CLAUDE.md section 4/10). --illustrative-smoke-test must be passed
   explicitly, exactly like run_instance.py/run_real_instance.py.
2. t_arrival[f] (CLAUDE.md section 5.3) is recomputed per instance size
   against THAT size's truncated base set, not the full real 120-base
   catalog, the same truncation-consistency compromise
   run_instance.py/run_real_instance.py already make (t_arrival is defined
   as the minimum over "the fixed candidate set I", but is recomputed here
   per truncation size for consistency with those two scripts' existing
   precedent, not re-litigated). This shifts t_arrival slightly between
   differently-sized instances; disclosed, not hidden.

Neighborhood size, max_iterations and the Gurobi time limit/MIP gap here
are this script's own runtime knobs, not sourced or independently tuned;
see src/matheuristic/README.md's own "not yet tuned" disclosure for the
same caveat.
"""

from __future__ import annotations

import argparse
import csv
import time
from dataclasses import dataclass, fields

import pandas as pd
import pulp

from src.matheuristic.fix_and_optimize import run_fix_and_optimize
from src.model.aircraft import COST_AIRCRAFT, FIREHAWK_OPS_TIME_H, SPEED, TANK
from src.model.costs import uniform_cost
from src.model.milp import build_model, solve
from src.model.precompute import precompute
from src.model.travel_times import assemble_model_params
from src.scenarios.assemble import enrich_scenarios_with_ros_and_value_at_risk, to_model_scenarios
from src.scenarios.day_scenarios import enrich_t_arrival, read_scenarios_json

DEFAULT_WORLDCOVER_TILES = [
    "data/raw/esa_worldcover_2021_N03W075.tif",
    "data/raw/esa_worldcover_2021_N03W078.tif",
]
DEFAULT_SRTM_TILES = [
    f"data/raw/srtm_N0{lat}W07{lon}.tif" for lat in (3, 4, 5, 6) for lon in (3, 4, 5, 6)
]
DEFAULT_WORLDPOP_RASTER = "data/raw/worldpop_col_2020_constrained.tif"
DEFAULT_INSTANCE_SIZES = [(5, 10), (10, 25), (20, 50)]


@dataclass
class InstanceResult:
    n_bases: int
    n_water: int
    n_scenarios: int
    n_fires: int
    gurobi_status: str
    gurobi_objective: float | None
    gurobi_mip_gap: float | None
    gurobi_timed_out: bool
    gurobi_time_s: float
    matheuristic_objective: float
    matheuristic_time_s: float
    matheuristic_iterations: int
    matheuristic_accepted: int
    quality_gap_abs: float | None
    quality_gap_pct: float | None


def _solve_pure_gurobi(params, pre, time_limit_s: float, gap_rel: float):
    """Solve the full, untruncated MILP for this instance with one Gurobi
    call. Returns (status, objective, mip_gap, timed_out, elapsed_s).
    objective is read directly from the model regardless of status: Gurobi
    populates variable values whenever it has found at least one incumbent
    (SolCount >= 1), even if the time limit cut off the search before
    optimality was proven, so a TIME_LIMIT run still reports its best
    incumbent rather than None."""
    model, v = build_model(params, pre)
    solver = pulp.GUROBI(msg=False, timeLimit=time_limit_s, gapRel=gap_rel)
    start = time.perf_counter()
    status = solve(model, solver=solver)
    elapsed = time.perf_counter() - start

    objective = pulp.value(model.objective)
    mip_gap = None
    timed_out = False
    solver_model = getattr(model, "solverModel", None)
    if solver_model is not None:
        import gurobipy as gp

        timed_out = solver_model.Status == gp.GRB.TIME_LIMIT
        if solver_model.SolCount >= 1:
            try:
                mip_gap = solver_model.MIPGap
            except AttributeError:
                mip_gap = None

    return status, objective, mip_gap, timed_out, elapsed


def _solve_matheuristic(
    params,
    bases_df: pd.DataFrame,
    water_df: pd.DataFrame,
    *,
    n_bases_per_neighborhood: int,
    n_water_per_neighborhood: int,
    max_iterations: int,
    no_improve_limit: int,
    seed: int,
    random_destroy_prob: float = 0.0,
):
    start = time.perf_counter()
    result = run_fix_and_optimize(
        params,
        bases_df,
        water_df,
        n_bases_per_neighborhood=n_bases_per_neighborhood,
        n_water_per_neighborhood=n_water_per_neighborhood,
        max_iterations=max_iterations,
        no_improve_limit=no_improve_limit,
        seed=seed,
        solver_factory=lambda: pulp.GUROBI(msg=False),
        random_destroy_prob=random_destroy_prob,
    )
    elapsed = time.perf_counter() - start
    n_accepted = sum(1 for record in result.history if record.accepted)
    return result.objective_value, elapsed, len(result.history), n_accepted


def _parse_instance_sizes(raw: list[str]) -> list[tuple[int, int]]:
    sizes = []
    for item in raw:
        n_bases_str, n_water_str = item.split(":")
        sizes.append((int(n_bases_str), int(n_water_str)))
    return sizes


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Experiment 2 (CLAUDE.md section 9): matheuristic vs pure Gurobi, across a sweep "
        "of candidate-catalog sizes (see module docstring for what is and is not resolved here)."
    )
    parser.add_argument("--bases", default="data/processed/candidate_bases.csv")
    parser.add_argument("--water", default="data/processed/candidate_water.csv")
    parser.add_argument("--scenarios", default="data/processed/scenarios_2024full.json")
    parser.add_argument("--max-scenarios", type=int, default=2, help="Fixed scenario count at every instance size.")
    parser.add_argument(
        "--instance-sizes",
        nargs="+",
        default=[f"{b}:{w}" for b, w in DEFAULT_INSTANCE_SIZES],
        help="List of n_bases:n_water_points pairs, e.g. 5:10 10:25 20:50.",
    )
    parser.add_argument("--worldcover-tiles", nargs="+", default=DEFAULT_WORLDCOVER_TILES)
    parser.add_argument("--srtm-tiles", nargs="+", default=DEFAULT_SRTM_TILES)
    parser.add_argument("--worldpop-raster", default=DEFAULT_WORLDPOP_RASTER)
    parser.add_argument("--ros-scale", type=float, required=True, help="CLAUDE.md section 3/9, swept in experiment 6.")
    parser.add_argument("--initial-fire-area", type=float, required=True, help="A0, hectares, CLAUDE.md section 3/9.")
    parser.add_argument("--liters-per-sqm", type=float, required=True, help="c, L/m^2, CLAUDE.md section 3/9.")
    parser.add_argument(
        "--cost-base", type=float, required=True, help="Uniform cost_base[i] sweep point, COP, src/model/costs.py."
    )
    parser.add_argument(
        "--cost-water", type=float, required=True, help="Uniform cost_water[k] sweep point, COP, src/model/costs.py."
    )
    parser.add_argument("--budget", type=float, required=True, help="B, COP. The user's own call.")
    parser.add_argument("--cvar-alpha", type=float, required=True, help="alpha. The user's own call.")
    parser.add_argument("--mean-risk-weight", type=float, required=True, help="lambda. The user's own call.")
    parser.add_argument("--window", type=float, required=True, help="W, hours. The user's own call.")
    parser.add_argument(
        "--illustrative-smoke-test",
        action="store_true",
        help="Required flag: acknowledges budget/cvar-alpha/mean-risk-weight/window are not sourced/decided "
        "values for this run, only a smoke test/demonstration of the comparison methodology.",
    )
    parser.add_argument("--gurobi-time-limit", type=float, default=120.0, help="Seconds, pure-Gurobi baseline.")
    parser.add_argument("--gurobi-gap-rel", type=float, default=0.0, help="Relative MIP gap target, pure-Gurobi baseline.")
    parser.add_argument("--n-bases-per-neighborhood", type=int, default=5)
    parser.add_argument("--n-water-per-neighborhood", type=int, default=10)
    parser.add_argument("--max-iterations", type=int, default=30)
    parser.add_argument("--no-improve-limit", type=int, default=15)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument(
        "--random-destroy-prob",
        type=float,
        default=0.3,
        help="Probability of a uniformly-random (not geographic) destroy move each iteration "
        "(src/matheuristic/neighborhoods.py, ADDED 2026-09-04 after a real run at this small size found "
        "the pure-geographic operator alone can get permanently stuck short of the true optimum, see "
        "src/matheuristic/README.md). A low --no-improve-limit relative to instance size can still cut "
        "the search off before the random operator gets enough draws to find a specific beneficial pair; "
        "this script does not auto-tune that tradeoff.",
    )
    parser.add_argument("--output-csv", default="results/experiment2_matheuristic_vs_gurobi.csv")
    args = parser.parse_args()

    if not args.illustrative_smoke_test:
        parser.error(
            "budget/cvar-alpha/mean-risk-weight/window are the user's own call (CLAUDE.md section 4/10), "
            "not to be treated as defaults. Pass --illustrative-smoke-test to acknowledge this run is a "
            "methodology demonstration, not a real experiment."
        )
    if not pulp.GUROBI(msg=False).available():
        parser.error("This experiment requires a working Gurobi license (CLAUDE.md section 3's 'pure Gurobi' benchmark).")

    instance_sizes = _parse_instance_sizes(args.instance_sizes)

    full_bases = pd.read_csv(args.bases)
    full_water = pd.read_csv(args.water)
    max_n_bases = max(n for n, _ in instance_sizes)
    max_n_water = max(n for _, n in instance_sizes)
    if max_n_bases > len(full_bases) or max_n_water > len(full_water):
        parser.error(
            f"requested instance sizes need up to {max_n_bases} bases / {max_n_water} water points, "
            f"but only {len(full_bases)} bases / {len(full_water)} water points are available."
        )

    base_scenarios = read_scenarios_json(args.scenarios)
    base_scenarios = base_scenarios[: args.max_scenarios]
    for scenario in base_scenarios:
        # Same renormalization as run_instance.py/run_real_instance.py: a
        # truncated bootstrap draw's original per-scenario probabilities no
        # longer sum to 1, which milp.build_model rejects outright.
        scenario.probability = 1.0 / len(base_scenarios)
    enrich_scenarios_with_ros_and_value_at_risk(
        base_scenarios,
        worldcover_tile_paths=args.worldcover_tiles,
        srtm_tile_paths=args.srtm_tiles,
        worldpop_raster_path=args.worldpop_raster,
        ros_scale=args.ros_scale,
    )

    results: list[InstanceResult] = []
    for n_bases, n_water in instance_sizes:
        bases = full_bases.head(n_bases)
        water_points = full_water.head(n_water)

        # t_arrival depends on the base set (CLAUDE.md section 5.3): recomputed
        # fresh per instance size against THIS size's truncated bases (see
        # module docstring's disclosed truncation-consistency compromise).
        enrich_t_arrival(base_scenarios, bases, speed=SPEED)
        model_scenarios, dropped = to_model_scenarios(base_scenarios, on_missing="drop")
        if dropped:
            print(f"WARNING: {len(dropped)} fire(s) dropped, incomplete data: {dropped}")
        n_fires = sum(len(s.fires) for s in model_scenarios)

        params = assemble_model_params(
            bases,
            water_points,
            model_scenarios,
            budget=args.budget,
            window=args.window,
            ops_time=FIREHAWK_OPS_TIME_H,
            cvar_alpha=args.cvar_alpha,
            mean_risk_weight=args.mean_risk_weight,
            initial_fire_area=args.initial_fire_area,
            liters_per_sqm=args.liters_per_sqm,
            cost_base=uniform_cost(list(bases["site_id"]), args.cost_base),
            cost_aircraft=COST_AIRCRAFT,
            cost_water=uniform_cost(list(water_points["site_id"]), args.cost_water),
            tank=TANK,
            speed=SPEED,
        )
        pre = precompute(params)

        print(f"\n=== Instance: {n_bases} bases, {n_water} water points, {len(model_scenarios)} scenarios, {n_fires} fires ===")

        print("Solving pure Gurobi (direct, full MILP)...")
        gurobi_status, gurobi_obj, gurobi_gap, gurobi_timed_out, gurobi_time = _solve_pure_gurobi(
            params, pre, time_limit_s=args.gurobi_time_limit, gap_rel=args.gurobi_gap_rel
        )
        print(f"  status={gurobi_status} objective={gurobi_obj} mip_gap={gurobi_gap} timed_out={gurobi_timed_out} time={gurobi_time:.2f}s")

        print("Solving matheuristic (fix-and-optimize/LNS)...")
        math_obj, math_time, math_iters, math_accepted = _solve_matheuristic(
            params,
            bases[["site_id", "x_utm", "y_utm"]],
            water_points[["site_id", "x_utm", "y_utm"]],
            n_bases_per_neighborhood=args.n_bases_per_neighborhood,
            n_water_per_neighborhood=args.n_water_per_neighborhood,
            max_iterations=args.max_iterations,
            no_improve_limit=args.no_improve_limit,
            seed=args.seed,
            random_destroy_prob=args.random_destroy_prob,
        )
        print(f"  objective={math_obj} iterations={math_iters} accepted={math_accepted} time={math_time:.2f}s")

        # quality_gap_abs is always reported when a Gurobi objective exists,
        # even when gurobi_obj == 0 (a perfect-containment optimum): dividing
        # by zero to get a percentage is undefined there, but the absolute
        # gap is not, and silently reporting quality_gap_pct=None in that
        # case must never be read as "no gap" (an earlier version of this
        # script did exactly that and hid a real, large quality gap where
        # pure Gurobi found the true optimum, 0.0, and the matheuristic did
        # not; see src/experiments/README.md).
        quality_gap_abs = None
        quality_gap_pct = None
        if gurobi_obj is not None:
            quality_gap_abs = math_obj - gurobi_obj
            if gurobi_obj != 0:
                quality_gap_pct = 100.0 * quality_gap_abs / gurobi_obj
            elif quality_gap_abs != 0:
                print(
                    f"  WARNING: pure Gurobi found objective 0.0 but the matheuristic found "
                    f"{math_obj}, a real gap of {quality_gap_abs} that cannot be expressed as a "
                    "percentage (division by zero); see quality_gap_abs, not quality_gap_pct."
                )

        results.append(
            InstanceResult(
                n_bases=n_bases,
                n_water=n_water,
                n_scenarios=len(model_scenarios),
                n_fires=n_fires,
                gurobi_status=gurobi_status,
                gurobi_objective=gurobi_obj,
                gurobi_mip_gap=gurobi_gap,
                gurobi_timed_out=gurobi_timed_out,
                gurobi_time_s=gurobi_time,
                matheuristic_objective=math_obj,
                matheuristic_time_s=math_time,
                matheuristic_iterations=math_iters,
                matheuristic_accepted=math_accepted,
                quality_gap_abs=quality_gap_abs,
                quality_gap_pct=quality_gap_pct,
            )
        )

    print("\n=== Summary ===")
    header = [f.name for f in fields(InstanceResult)]
    print(", ".join(header))
    for r in results:
        print(", ".join(str(getattr(r, h)) for h in header))

    with open(args.output_csv, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(header)
        for r in results:
            writer.writerow([getattr(r, h) for h in header])
    print(f"\nWrote {args.output_csv}")


if __name__ == "__main__":
    main()
