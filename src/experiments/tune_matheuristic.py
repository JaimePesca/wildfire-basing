"""Matheuristic tuning sweep (src/matheuristic/README.md's "not yet
done" list, item: "tuning neighborhood size, iteration/no-improve
budgets, and random_destroy_prob against real runtime and real escape
reliability"). Runs run_fix_and_optimize over a grid of
(random_destroy_prob, n_bases_per_neighborhood, n_water_per_neighborhood)
x seeds, on a real-data instance small enough that the TRUE optimum is
known from a direct Gurobi solve, and measures, per configuration:

- hit_rate: fraction of seeds whose final objective matches the direct
  optimum (within 1e-6), the escape-reliability number that
  random_destroy_prob was added for (CLAUDE.md section 10, 2026-09-04:
  the pure-geographic operator got permanently stuck on exactly this
  kind of instance).
- mean/median iterations to first reach the optimum (among hits).
- mean wall time per run.

no_improve_limit is deliberately NOT used here (every run executes the
full --max-iterations): early stopping would confound escape reliability
with patience, which is exactly the mistake that made the first
random_destroy_prob=0.3 real-scale check look like a failure
(src/matheuristic/README.md, 2026-09-04 account).

The output CSV ranks configurations by (hit_rate desc, mean_time asc);
the intended use is picking evidence-backed defaults for
run_real_instance.py and the experiment scripts, replacing the current
illustrative ones. Same real-data assembly and disclosures as the other
src/experiments scripts.
"""

from __future__ import annotations

import argparse
import csv
import itertools
import statistics
import time
from dataclasses import dataclass, fields

import pandas as pd
import pulp

from src.matheuristic.fix_and_optimize import run_fix_and_optimize
from src.model.aircraft import COST_AIRCRAFT, FIREHAWK_OPS_TIME_H, SPEED, TANK
from src.model.costs import uniform_cost
from src.model.milp import solve_model
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


@dataclass
class ConfigResult:
    random_destroy_prob: float
    n_bases_per_neighborhood: int
    n_water_per_neighborhood: int
    n_seeds: int
    hit_rate: float
    mean_iterations_to_optimum: float | None
    median_iterations_to_optimum: float | None
    mean_time_s: float
    mean_final_gap_abs: float


def _iterations_to_optimum(history, optimum: float, tol: float = 1e-6) -> int | None:
    for record in history:
        if record.accepted and record.objective_value is not None and record.objective_value <= optimum + tol:
            return record.iteration + 1
    return None


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Tuning sweep for the fix-and-optimize/LNS matheuristic against the known true "
        "optimum of a real-data instance (see module docstring)."
    )
    parser.add_argument("--bases", default="data/processed/candidate_bases.csv")
    parser.add_argument("--water", default="data/processed/candidate_water.csv")
    parser.add_argument("--scenarios", default="data/processed/scenarios_2024full.json")
    parser.add_argument("--n-bases", type=int, default=20, help="Instance size: candidate bases (must stay direct-solvable).")
    parser.add_argument("--n-water", type=int, default=50, help="Instance size: candidate water points (must stay direct-solvable).")
    parser.add_argument("--max-scenarios", type=int, default=2)
    parser.add_argument("--worldcover-tiles", nargs="+", default=DEFAULT_WORLDCOVER_TILES)
    parser.add_argument("--srtm-tiles", nargs="+", default=DEFAULT_SRTM_TILES)
    parser.add_argument("--worldpop-raster", default=DEFAULT_WORLDPOP_RASTER)
    parser.add_argument("--ros-scale", type=float, required=True, help="CLAUDE.md section 3/9, swept in experiment 6.")
    parser.add_argument("--initial-fire-area", type=float, required=True, help="A0, hectares, CLAUDE.md section 3/9.")
    parser.add_argument("--liters-per-sqm", type=float, required=True, help="c, L/m^2, CLAUDE.md section 3/9.")
    parser.add_argument("--cost-base", type=float, required=True, help="Uniform cost_base[i] sweep point, COP.")
    parser.add_argument("--cost-water", type=float, required=True, help="Uniform cost_water[k] sweep point, COP.")
    parser.add_argument(
        "--budget", type=float, default=150_000_000_000.0,
        help="B, COP. DECIDED 2026-09-09 (CLAUDE.md section 10).",
    )
    parser.add_argument("--cvar-alpha", type=float, default=0.95, help="alpha. DECIDED 2026-09-09.")
    parser.add_argument("--mean-risk-weight", type=float, default=0.5, help="lambda. DECIDED 2026-09-09.")
    parser.add_argument("--window", type=float, default=2.0, help="W, hours. DECIDED 2026-09-09.")
    parser.add_argument(
        "--illustrative-smoke-test",
        action="store_true",
        help="Required flag: acknowledges ros-scale/initial-fire-area/liters-per-sqm/cost-base/"
        "cost-water are swept sensitivity parameters fixed at one sweep point for this run.",
    )
    parser.add_argument("--random-destroy-probs", nargs="+", type=float, default=[0.0, 0.2, 0.4, 0.6])
    parser.add_argument("--n-bases-per-neighborhood-grid", nargs="+", type=int, default=[5, 10])
    parser.add_argument("--n-water-per-neighborhood-grid", nargs="+", type=int, default=[10, 25, 50])
    parser.add_argument("--seeds", nargs="+", type=int, default=[0, 1, 2, 3, 4])
    parser.add_argument("--max-iterations", type=int, default=100)
    parser.add_argument("--output-csv", default="results/tune_matheuristic.csv")
    args = parser.parse_args()

    if not args.illustrative_smoke_test:
        parser.error(
            "ros-scale/initial-fire-area/liters-per-sqm/cost-base/cost-water are swept sensitivity "
            "parameters (CLAUDE.md section 3/9); pass --illustrative-smoke-test to acknowledge."
        )
    if not pulp.GUROBI(msg=False).available():
        parser.error("this sweep needs a working Gurobi license (direct-optimum yardstick and sub-solves).")

    bases = pd.read_csv(args.bases).head(args.n_bases)
    water_points = pd.read_csv(args.water).head(args.n_water)
    scenarios = read_scenarios_json(args.scenarios)[: args.max_scenarios]
    for scenario in scenarios:
        scenario.probability = 1.0 / len(scenarios)
    enrich_scenarios_with_ros_and_value_at_risk(
        scenarios,
        worldcover_tile_paths=args.worldcover_tiles,
        srtm_tile_paths=args.srtm_tiles,
        worldpop_raster_path=args.worldpop_raster,
        ros_scale=args.ros_scale,
    )
    enrich_t_arrival(scenarios, bases, speed=SPEED)
    model_scenarios, dropped = to_model_scenarios(scenarios, on_missing="drop")
    if dropped:
        print(f"WARNING: {len(dropped)} fire(s) dropped, incomplete data: {dropped}")
    n_fires = sum(len(s.fires) for s in model_scenarios)
    print(f"Instance: {len(bases)} bases, {len(water_points)} water points, {len(model_scenarios)} scenarios, {n_fires} fires.")

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

    print("Computing the true optimum (direct Gurobi solve, the yardstick)...")
    direct = solve_model(params, pre, solver=pulp.GUROBI(msg=False))
    if direct.status != "Optimal":
        raise SystemExit(f"direct solve failed ({direct.status}); shrink the instance so the yardstick exists.")
    optimum = direct.objective_value
    print(f"True optimum: {optimum}")

    bases_df = bases[["site_id", "x_utm", "y_utm"]]
    water_df = water_points[["site_id", "x_utm", "y_utm"]]

    grid = list(
        itertools.product(
            args.random_destroy_probs, args.n_bases_per_neighborhood_grid, args.n_water_per_neighborhood_grid
        )
    )
    print(f"Sweeping {len(grid)} configurations x {len(args.seeds)} seeds, {args.max_iterations} iterations each...")

    results: list[ConfigResult] = []
    for cfg_idx, (rdp, nb, nw) in enumerate(grid):
        hits = 0
        iters_to_opt: list[int] = []
        times: list[float] = []
        gaps: list[float] = []
        for seed in args.seeds:
            t0 = time.perf_counter()
            run = run_fix_and_optimize(
                params,
                bases_df,
                water_df,
                n_bases_per_neighborhood=nb,
                n_water_per_neighborhood=nw,
                max_iterations=args.max_iterations,
                no_improve_limit=None,
                seed=seed,
                solver_factory=lambda: pulp.GUROBI(msg=False),
                random_destroy_prob=rdp,
            )
            times.append(time.perf_counter() - t0)
            gaps.append(run.objective_value - optimum)
            if run.objective_value <= optimum + 1e-6:
                hits += 1
                it = _iterations_to_optimum(run.history, optimum)
                if it is not None:
                    iters_to_opt.append(it)
        result = ConfigResult(
            random_destroy_prob=rdp,
            n_bases_per_neighborhood=nb,
            n_water_per_neighborhood=nw,
            n_seeds=len(args.seeds),
            hit_rate=hits / len(args.seeds),
            mean_iterations_to_optimum=statistics.mean(iters_to_opt) if iters_to_opt else None,
            median_iterations_to_optimum=statistics.median(iters_to_opt) if iters_to_opt else None,
            mean_time_s=statistics.mean(times),
            mean_final_gap_abs=statistics.mean(gaps),
        )
        results.append(result)
        print(
            f"[{cfg_idx + 1}/{len(grid)}] rdp={rdp} nb={nb} nw={nw}: hit_rate={result.hit_rate:.2f} "
            f"mean_time={result.mean_time_s:.1f}s mean_gap={result.mean_final_gap_abs:.4f}"
        )

    results.sort(key=lambda r: (-r.hit_rate, r.mean_time_s))
    header = [f.name for f in fields(ConfigResult)]
    print("\n=== Ranking (hit_rate desc, mean_time asc) ===")
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
