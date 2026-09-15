"""Experiment 3b: integrated vs sequential in the THREE-AIRCRAFT regime
(budget 300G by default), with the matheuristic as the integrated arm.

Closes the manuscript's one remaining ongoing item ("measuring, rather
than bounding, the integrated-versus-sequential gap in the
three-aircraft, high-budget-slack regimes, with the matheuristic as the
integrated arm"). The direct MILP cannot certify this regime (experiment
6: essentially 100 percent MIP gap at the 1,800 s limit), so BOTH arms
here are upper bounds on the unknown true optimum. What this experiment
therefore measures, stated honestly in the output and to be stated in
the paper, is whether integrated SEARCH finds a strictly better plan
than the best-case sequential planner, not the gap to the optimum:

- sequential arm: solve_sequential_best_phi (phase A water-blind at
  phi*B, phase B full model with bases/fleet fixed), the same baseline
  as experiment 3;
- integrated arm, cold: run_fix_and_optimize from the empty solution;
- integrated arm, warm: run_fix_and_optimize seeded with the sequential
  winner's complete first stage, which operationalizes the manuscript's
  own "sequential as a warm start" observation; any accepted iteration
  is then a verified strict improvement OVER the sequential plan, so
  warm-start improvement > 0 is a direct, certificate-free proof of a
  strictly positive integrated-vs-sequential gap on this instance.

The experiment 6 direct-solve incumbent at the same budget is printed as
a reference upper bound (read from its CSV if present, not re-solved).

Same disclosures as the other src/experiments scripts: swept sensitivity
parameters fixed at one sweep point (--illustrative-smoke-test), DECIDED
defaults for alpha/lambda/window, t_arrival against the truncated base
set, scenario probabilities renormalized over the subset.
"""

from __future__ import annotations

import argparse
import csv
import time
from dataclasses import dataclass, fields

import pandas as pd
import pulp

from src.matheuristic.fix_and_optimize import FirstStageSolution, run_fix_and_optimize
from src.model.aircraft import COST_AIRCRAFT, FIREHAWK_OPS_TIME_H, SPEED, TANK
from src.model.costs import uniform_cost
from src.model.precompute import precompute
from src.model.sequential import solve_sequential_best_phi
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
DEFAULT_PHIS = [0.5, 0.6, 0.7, 0.8, 0.9, 0.95, 1.0]


@dataclass
class ArmResult:
    arm: str
    objective: float | None
    time_s: float
    iterations: int | None
    accepted: int | None
    detail: str


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Experiment 3b: integrated (matheuristic) vs sequential in the multi-aircraft "
        "regime the direct MILP cannot certify (see module docstring for what is and is not measured)."
    )
    parser.add_argument("--bases", default="data/processed/candidate_bases.csv")
    parser.add_argument("--water", default="data/processed/candidate_water.csv")
    parser.add_argument("--scenarios", default="data/processed/scenarios_2024full.json")
    parser.add_argument("--n-bases", type=int, default=20)
    parser.add_argument("--n-water", type=int, default=50)
    parser.add_argument("--max-scenarios", type=int, default=10)
    parser.add_argument("--phis", nargs="+", type=float, default=DEFAULT_PHIS)
    parser.add_argument("--worldcover-tiles", nargs="+", default=DEFAULT_WORLDCOVER_TILES)
    parser.add_argument("--srtm-tiles", nargs="+", default=DEFAULT_SRTM_TILES)
    parser.add_argument("--worldpop-raster", default=DEFAULT_WORLDPOP_RASTER)
    parser.add_argument("--ros-scale", type=float, required=True)
    parser.add_argument("--initial-fire-area", type=float, required=True, help="A0, hectares.")
    parser.add_argument("--liters-per-sqm", type=float, required=True, help="c, L/m^2.")
    parser.add_argument("--cost-base", type=float, required=True)
    parser.add_argument("--cost-water", type=float, required=True)
    parser.add_argument(
        "--budget", type=float, default=300_000_000_000.0,
        help="B, COP. Default 300G, the three-aircraft point of experiment 6's budget axis.",
    )
    parser.add_argument("--cvar-alpha", type=float, default=0.95)
    parser.add_argument("--mean-risk-weight", type=float, default=0.5)
    parser.add_argument("--window", type=float, default=2.0)
    parser.add_argument("--n-bases-per-neighborhood", type=int, default=5)
    parser.add_argument("--n-water-per-neighborhood", type=int, default=10)
    parser.add_argument("--max-iterations", type=int, default=150)
    parser.add_argument("--no-improve-limit", type=int, default=60)
    parser.add_argument("--random-destroy-prob", type=float, default=0.3)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument(
        "--sequential-time-limit", type=float, default=1800.0,
        help="Wall-clock seconds per sequential-arm Gurobi solve (phases A and B).",
    )
    parser.add_argument(
        "--illustrative-smoke-test",
        action="store_true",
        help="Required flag: acknowledges the five swept sensitivity parameters are fixed at one "
        "sweep point for this run.",
    )
    parser.add_argument("--output-csv", default="results/experiment3_multiaircraft_matheuristic.csv")
    args = parser.parse_args()

    if not args.illustrative_smoke_test:
        parser.error(
            "ros-scale/initial-fire-area/liters-per-sqm/cost-base/cost-water are swept sensitivity "
            "parameters (CLAUDE.md section 3/9); pass --illustrative-smoke-test to acknowledge."
        )
    if not pulp.GUROBI(msg=False).available():
        parser.error("this experiment needs a working Gurobi license (sequential arm and sub-solves).")

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
    print(
        f"Instance: {len(bases)} bases, {len(water_points)} water points, "
        f"{len(model_scenarios)} scenarios, {n_fires} fires, budget {args.budget:.0f}."
    )

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
    precompute(params)  # fail fast on any data problem before the long arms run

    results: list[ArmResult] = []

    # ---- Sequential arm (same baseline as experiment 3) -----------------
    print(f"\nSequential arm (bases first, water second), phi in {args.phis}...")
    seq_factory = lambda: pulp.GUROBI(msg=False, timeLimit=args.sequential_time_limit)  # noqa: E731
    t0 = time.perf_counter()
    best_seq, all_seq = solve_sequential_best_phi(params, phis=args.phis, solver_factory=seq_factory)
    seq_time = time.perf_counter() - t0
    for r in all_seq:
        print(f"  phi={r.phi}: phase A spend={r.phase_a.spend:.0f}, phase B objective={r.objective_value}")
    print(f"  BEST sequential: phi={best_seq.phi}, objective={best_seq.objective_value}, time={seq_time:.1f}s")
    results.append(
        ArmResult(
            arm="sequential_best",
            objective=best_seq.objective_value,
            time_s=seq_time,
            iterations=None,
            accepted=None,
            detail=f"phi={best_seq.phi}",
        )
    )

    bases_df = bases[["site_id", "x_utm", "y_utm"]]
    water_df = water_points[["site_id", "x_utm", "y_utm"]]
    mh_factory = lambda: pulp.GUROBI(msg=False)  # noqa: E731

    def run_arm(name: str, initial: FirstStageSolution | None, detail: str) -> None:
        print(f"\nIntegrated arm ({name}): matheuristic, {args.max_iterations} iterations, "
              f"patience {args.no_improve_limit}, destroy {args.random_destroy_prob}...")
        t0 = time.perf_counter()
        res = run_fix_and_optimize(
            params,
            bases_df,
            water_df,
            n_bases_per_neighborhood=args.n_bases_per_neighborhood,
            n_water_per_neighborhood=args.n_water_per_neighborhood,
            max_iterations=args.max_iterations,
            no_improve_limit=args.no_improve_limit,
            seed=args.seed,
            solver_factory=mh_factory,
            initial=initial,
            random_destroy_prob=args.random_destroy_prob,
        )
        elapsed = time.perf_counter() - t0
        n_accepted = sum(1 for rec in res.history if rec.accepted)
        print(f"  objective={res.objective_value} iterations={len(res.history)} "
              f"accepted={n_accepted} time={elapsed:.1f}s")
        results.append(
            ArmResult(
                arm=name,
                objective=res.objective_value,
                time_s=elapsed,
                iterations=len(res.history),
                accepted=n_accepted,
                detail=detail,
            )
        )

    # ---- Integrated arm, cold start --------------------------------------
    run_arm("matheuristic_cold", None, "empty initial solution")

    # ---- Integrated arm, warm start from the sequential winner -----------
    warm = FirstStageSolution(
        base_open=dict(best_seq.phase_b.base_open),
        water_open=dict(best_seq.phase_b.water_open),
        n_aircraft=dict(best_seq.phase_b.n_aircraft),
    )
    run_arm("matheuristic_warm", warm, f"seeded with sequential phi={best_seq.phi}")

    print("\n=== Reading (both integrated arms are upper bounds; no optimality certificate exists "
          "in this regime) ===")
    # An improvement only counts as a PROVEN positive gap if it exceeds what
    # the sub-solves' default relative MIP gap (1e-4) can fabricate at this
    # magnitude; anything smaller is solver tolerance noise, not a result
    # (lesson from the first 300G run, 2026-09-13: a 5e-8 relative
    # "improvement" tripped a naive 1e-6 absolute threshold).
    seq_obj = best_seq.objective_value
    tol = max(1e-6, 1e-4 * abs(seq_obj)) if seq_obj is not None else 1e-6
    for r in results:
        if r.arm == "sequential_best" or r.objective is None or seq_obj is None:
            continue
        diff = seq_obj - r.objective
        rel = 100.0 * diff / seq_obj if seq_obj else float("nan")
        if diff > tol:
            verdict = "STRICTLY BETTER than sequential (positive gap beyond solver tolerance)"
        elif diff > -tol:
            verdict = "matches sequential to solver tolerance (no gap shown at this budget)"
        else:
            verdict = "worse than sequential (search budget insufficient)"
        print(f"  {r.arm}: {r.objective:.3f} vs sequential {seq_obj:.3f} -> difference {diff:.6f} "
              f"({rel:.6f}%), tolerance {tol:.3f}: {verdict}")

    header = [f.name for f in fields(ArmResult)]
    with open(args.output_csv, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(header)
        for r in results:
            writer.writerow([getattr(r, h) for h in header])
    print(f"\nWrote {args.output_csv}")


if __name__ == "__main__":
    main()
