"""Run the fix-and-optimize/LNS matheuristic (fix_and_optimize.py) against
the real candidate site catalog (data/processed/candidate_bases.csv,
candidate_water.csv, 120 bases and 5,449 water points) and a real bootstrap
scenario draw (data/processed/scenarios_2024full.json), the real-data
counterpart to src/model/run_instance.py, which does the same assembly but
solves the full, untruncated MILP directly.

Why this script exists, distinct from run_instance.py: run_instance.py's own
"First real-data solve" note (CLAUDE.md section 10, src/model/README.md)
found the full candidate water point set intractable for an exact,
all-at-once MILP solve, and needed --max-bases/--max-water-points to
truncate the candidate sets just to prove the pipeline plumbing worked. This
script is the actual answer to that scale problem: it does NOT truncate the
candidate sets (every real base and water point is passed to
run_fix_and_optimize), because the matheuristic's own reduced-sub-MILP trick
(src/matheuristic/fix_and_optimize.py's module docstring) is what makes the
real scale tractable, one geographic neighborhood at a time.

Same two caveats as run_instance.py, not resolved here either:

1. budget/cvar_alpha/mean_risk_weight/window are the user's own call
   (CLAUDE.md section 4/10). --illustrative-smoke-test must be passed
   explicitly to acknowledge a given run is not using sourced/decided
   values.
2. --n-bases-per-neighborhood/--n-water-per-neighborhood/--max-iterations are
   this script's own tractability/runtime knobs, not a proposed real
   experimental design; they are not sourced or tuned against real solve
   times yet (that tuning is itself a not-yet-done follow-up, see
   src/matheuristic/README.md).
"""

from __future__ import annotations

import argparse
import time

import pandas as pd
import pulp

from src.matheuristic.fix_and_optimize import run_fix_and_optimize
from src.model.aircraft import COST_AIRCRAFT, FIREHAWK_OPS_TIME_H, SPEED, TANK
from src.model.costs import uniform_cost
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


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run the fix-and-optimize/LNS matheuristic against the real candidate catalog "
        "(see module docstring for what is and is not resolved by this script)."
    )
    parser.add_argument("--bases", default="data/processed/candidate_bases.csv")
    parser.add_argument("--water", default="data/processed/candidate_water.csv")
    parser.add_argument("--scenarios", default="data/processed/scenarios_2024full.json")
    parser.add_argument(
        "--max-bases", type=int, default=None, help="Optional truncation, for a faster dev-time run only."
    )
    parser.add_argument(
        "--max-water-points", type=int, default=None, help="Optional truncation, for a faster dev-time run only."
    )
    parser.add_argument(
        "--max-scenarios", type=int, default=None, help="Use only the first N scenarios from --scenarios."
    )
    parser.add_argument("--worldcover-tiles", nargs="+", default=DEFAULT_WORLDCOVER_TILES)
    parser.add_argument("--srtm-tiles", nargs="+", default=DEFAULT_SRTM_TILES)
    parser.add_argument("--worldpop-raster", default=DEFAULT_WORLDPOP_RASTER)
    parser.add_argument(
        "--ros-scale", type=float, required=True, help="CLAUDE.md section 3/9, swept in experiment 6."
    )
    parser.add_argument(
        "--initial-fire-area", type=float, required=True, help="A0, hectares, CLAUDE.md section 3/9."
    )
    parser.add_argument(
        "--liters-per-sqm", type=float, required=True, help="c, L/m^2, CLAUDE.md section 3/9."
    )
    parser.add_argument(
        "--cost-base",
        type=float,
        required=True,
        help="Uniform cost_base[i] sweep point, COP, see src/model/costs.py's documented range.",
    )
    parser.add_argument(
        "--cost-water",
        type=float,
        required=True,
        help="Uniform cost_water[k] sweep point, COP, see src/model/costs.py's documented range.",
    )
    parser.add_argument("--budget", type=float, required=True, help="B, COP. The user's own call.")
    parser.add_argument("--cvar-alpha", type=float, required=True, help="alpha. The user's own call.")
    parser.add_argument("--mean-risk-weight", type=float, required=True, help="lambda. The user's own call.")
    parser.add_argument("--window", type=float, required=True, help="W, hours. The user's own call.")
    parser.add_argument(
        "--illustrative-smoke-test",
        action="store_true",
        help="Required flag: acknowledges budget/cvar-alpha/mean-risk-weight/window are not sourced/decided "
        "values for this run, only a smoke test of the pipeline plumbing and matheuristic runtime.",
    )
    parser.add_argument("--solver", choices=["cbc", "gurobi"], default="cbc")
    parser.add_argument("--n-bases-per-neighborhood", type=int, default=5)
    parser.add_argument("--n-water-per-neighborhood", type=int, default=10)
    parser.add_argument("--max-iterations", type=int, default=50)
    parser.add_argument("--no-improve-limit", type=int, default=20)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument(
        "--random-destroy-prob",
        type=float,
        default=0.3,
        help="Probability of a uniformly-random (not geographic) destroy move each iteration. ADDED "
        "2026-09-04 (CLAUDE.md section 10, src/matheuristic/neighborhoods.py): a real run against this "
        "exact catalog found the pure-geographic operator (--random-destroy-prob 0) can get permanently "
        "stuck strictly short of the true optimum when the best move needs to trade two geographically "
        "distant sites at once. Not yet independently tuned beyond confirming 0.3 fixes the specific case "
        "found (see src/matheuristic/README.md).",
    )
    args = parser.parse_args()

    if not args.illustrative_smoke_test:
        parser.error(
            "budget/cvar-alpha/mean-risk-weight/window are the user's own call (CLAUDE.md section 4/10), "
            "not to be treated as defaults. Pass --illustrative-smoke-test to acknowledge this run is a "
            "pipeline smoke test only, not a real experiment."
        )

    bases = pd.read_csv(args.bases)
    water_points = pd.read_csv(args.water)
    if args.max_bases is not None:
        bases = bases.head(args.max_bases)
    if args.max_water_points is not None:
        water_points = water_points.head(args.max_water_points)
    print(f"Using {len(bases)} candidate bases, {len(water_points)} candidate water points.")

    scenarios = read_scenarios_json(args.scenarios)
    if args.max_scenarios is not None:
        scenarios = scenarios[: args.max_scenarios]
        # See run_instance.py's identical comment: truncating a bootstrap
        # draw without renormalizing leaves probabilities that no longer sum
        # to 1, which milp.build_model's own validation rejects outright
        # (CONFIRMED 2026-08-30, makes the CVaR objective genuinely
        # unbounded, not just skewed). This is a tractability-subsample
        # concession, not a real SAA resample.
        for scenario in scenarios:
            scenario.probability = 1.0 / len(scenarios)
    n_fires = sum(len(s.fires) for s in scenarios)
    print(f"Using {len(scenarios)} scenarios, {n_fires} total fires.")

    enrich_t_arrival(scenarios, bases, speed=SPEED)
    enrich_scenarios_with_ros_and_value_at_risk(
        scenarios,
        worldcover_tile_paths=args.worldcover_tiles,
        srtm_tile_paths=args.srtm_tiles,
        worldpop_raster_path=args.worldpop_raster,
        ros_scale=args.ros_scale,
    )
    model_scenarios, dropped = to_model_scenarios(scenarios, on_missing="drop")
    if dropped:
        print(f"WARNING: {len(dropped)} fire(s) dropped, incomplete data: {dropped}")

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

    solver_factory = (
        (lambda: pulp.GUROBI(msg=False)) if args.solver == "gurobi" else (lambda: pulp.PULP_CBC_CMD(msg=False))
    )

    print(
        f"\nRunning fix-and-optimize: n_bases_per_neighborhood={args.n_bases_per_neighborhood}, "
        f"n_water_per_neighborhood={args.n_water_per_neighborhood}, max_iterations={args.max_iterations}, "
        f"no_improve_limit={args.no_improve_limit}, solver={args.solver}"
    )
    start = time.perf_counter()
    result = run_fix_and_optimize(
        params,
        bases[["site_id", "x_utm", "y_utm"]],
        water_points[["site_id", "x_utm", "y_utm"]],
        n_bases_per_neighborhood=args.n_bases_per_neighborhood,
        n_water_per_neighborhood=args.n_water_per_neighborhood,
        max_iterations=args.max_iterations,
        no_improve_limit=args.no_improve_limit,
        seed=args.seed,
        solver_factory=solver_factory,
        random_destroy_prob=args.random_destroy_prob,
    )
    elapsed = time.perf_counter() - start

    n_iterations = len(result.history)
    n_accepted = sum(1 for record in result.history if record.accepted)
    n_infeasible = sum(1 for record in result.history if record.status != "Optimal")

    print(f"\nElapsed: {elapsed:.1f} s over {n_iterations} iterations ({n_iterations / elapsed:.2f} it/s)")
    print(f"Iterations accepted (strict improvement): {n_accepted} / {n_iterations}")
    print(f"Iterations with non-Optimal sub-MILP status: {n_infeasible} / {n_iterations}")
    print(f"Final objective value: {result.objective_value}")
    print(f"Bases opened: {[i for i, open_ in result.incumbent.base_open.items() if open_]}")
    print(f"Water points opened: {[k for k, open_ in result.incumbent.water_open.items() if open_]}")
    print(f"Aircraft stationed: {[(key, n) for key, n in result.incumbent.n_aircraft.items() if n > 0]}")


if __name__ == "__main__":
    main()
