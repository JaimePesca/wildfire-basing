"""SAA replication analysis (CLAUDE.md section 3: "Scenarios via Sample
Average Approximation (SAA), reported with optimality gap and confidence
interval"; the manuscript declares this analysis as ongoing work, this
script closes it).

Standard replication scheme \\citep[in the sense of][]{kleywegt2001}:

1. Draw M independent bootstrap scenario sets of N day-scenarios each
   from the real 2024 day pool (independent RNG seeds), plus one larger
   independent evaluation set of N' days.
2. Solve each replication's SAA problem to optimality. For a
   minimization problem, E[v_N] is a lower bound on the true optimal
   value, so the sample mean of the M optimal values, with its
   t-distribution confidence interval, estimates a statistical lower
   bound. Replications that hit the solve time limit are excluded from
   the lower-bound estimate and reported separately (their incumbents
   are upper bounds on their own v_N, so including them would bias the
   LB upward silently; exclusion is disclosed instead).
3. Fix one candidate first-stage solution x_hat (the first
   replication's optimal solution, a pre-registered choice made before
   seeing any evaluation result, to avoid selection bias) and evaluate
   it on the N' independent evaluation scenarios, one small recourse
   MILP per scenario with every first-stage variable fixed. The
   evaluated mean-risk objective (expectation plus empirical CVaR over
   the N' losses, src/model/risk.py) estimates an upper bound on the
   true value of x_hat, hence on the true optimum's achievable value.
4. Report gap = UB - LB with the CI components.

Honest statistical caveats, printed with the results rather than
hidden: with a CVaR term in the objective the classical lower-bound
argument carries additional small-sample bias (the sample CVaR is
itself downward biased for minimization), and the CVaR component of
the upper bound is reported as a point estimate (its CI is not a
simple t interval); the expectation components carry standard t
intervals. With N' = 100 equiprobable evaluation scenarios,
CVaR_0.95 averages the worst five losses.

Same disclosures as the other src/experiments scripts (swept
sensitivity parameters fixed at one sweep point, DECIDED defaults for
budget/alpha/lambda/window, t_arrival against the truncated base set).
"""

from __future__ import annotations

import argparse
import csv
import math
import statistics
import time

import numpy as np
import pandas as pd
import pulp

from src.experiments.common import solve_with_time_limit
from src.model.aircraft import COST_AIRCRAFT, FIREHAWK_OPS_TIME_H, SPEED, TANK
from src.model.costs import uniform_cost
from src.model.milp import build_model, solve
from src.model.precompute import precompute
from src.model.risk import empirical_cvar, expected_loss
from src.model.travel_times import assemble_model_params
from src.scenarios.assemble import enrich_scenarios_with_ros_and_value_at_risk, to_model_scenarios
from src.scenarios.day_scenarios import (
    bootstrap_scenarios,
    build_day_pool,
    enrich_t_arrival,
    load_events,
)
from datetime import date

DEFAULT_WORLDCOVER_TILES = [
    "data/raw/esa_worldcover_2021_N03W075.tif",
    "data/raw/esa_worldcover_2021_N03W078.tif",
]
DEFAULT_SRTM_TILES = [
    f"data/raw/srtm_N0{lat}W07{lon}.tif" for lat in (3, 4, 5, 6) for lon in (3, 4, 5, 6)
]
DEFAULT_WORLDPOP_RASTER = "data/raw/worldpop_col_2020_constrained.tif"

# t critical values, two-sided 95 percent, for small df (df = M - 1).
T_95 = {4: 2.776, 5: 2.571, 6: 2.447, 7: 2.365, 8: 2.306, 9: 2.262, 10: 2.228,
        14: 2.145, 19: 2.093, 24: 2.064, 29: 2.045, 49: 2.010, 99: 1.984}


def t_crit(df: int) -> float:
    if df in T_95:
        return T_95[df]
    keys = sorted(T_95)
    for k in keys:
        if df <= k:
            return T_95[k]
    return 1.96


def _assemble(bases, water_points, model_scenarios, args):
    return assemble_model_params(
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


def _fix_first_stage(v, params, first_stage) -> None:
    """Fix EVERY first-stage variable (bases, water, fleet) to the
    candidate solution via bounds, open or closed, so an evaluation
    solve decides recourse only."""
    base_open, water_open, n_aircraft = first_stage
    for i in params.bases:
        val = 1 if base_open.get(i, False) else 0
        v.base_open[i].lowBound = v.base_open[i].upBound = val
        for m in params.aircraft_types:
            n_val = n_aircraft.get((i, m), 0)
            v.n_aircraft[(i, m)].lowBound = v.n_aircraft[(i, m)].upBound = n_val
    for k in params.water_points:
        val = 1 if water_open.get(k, False) else 0
        v.water_open[k].lowBound = v.water_open[k].upBound = val


def main() -> None:
    parser = argparse.ArgumentParser(
        description="SAA replication analysis: statistical lower bound, candidate evaluation upper "
        "bound, and optimality gap with confidence intervals (see module docstring)."
    )
    parser.add_argument("--events", default="data/processed/events_2024-full.csv")
    parser.add_argument("--bases", default="data/processed/candidate_bases.csv")
    parser.add_argument("--water", default="data/processed/candidate_water.csv")
    parser.add_argument("--n-bases", type=int, default=20)
    parser.add_argument("--n-water", type=int, default=50)
    parser.add_argument("--n-replications", type=int, default=10, help="M, independent SAA replications.")
    parser.add_argument("--n-scenarios", type=int, default=10, help="N, day scenarios per replication.")
    parser.add_argument("--n-eval", type=int, default=100, help="N', independent evaluation scenarios.")
    parser.add_argument("--seed-base", type=int, default=1, help="Replication m uses seed seed_base + m.")
    parser.add_argument("--eval-seed", type=int, default=999)
    parser.add_argument("--worldcover-tiles", nargs="+", default=DEFAULT_WORLDCOVER_TILES)
    parser.add_argument("--srtm-tiles", nargs="+", default=DEFAULT_SRTM_TILES)
    parser.add_argument("--worldpop-raster", default=DEFAULT_WORLDPOP_RASTER)
    parser.add_argument("--ros-scale", type=float, required=True)
    parser.add_argument("--initial-fire-area", type=float, required=True)
    parser.add_argument("--liters-per-sqm", type=float, required=True)
    parser.add_argument("--cost-base", type=float, required=True)
    parser.add_argument("--cost-water", type=float, required=True)
    parser.add_argument("--budget", type=float, default=150_000_000_000.0)
    parser.add_argument("--cvar-alpha", type=float, default=0.95)
    parser.add_argument("--mean-risk-weight", type=float, default=0.5)
    parser.add_argument("--window", type=float, default=2.0)
    parser.add_argument(
        "--illustrative-smoke-test",
        action="store_true",
        help="Required flag: acknowledges the five swept sensitivity parameters are fixed at one "
        "sweep point for this run.",
    )
    parser.add_argument("--gurobi-time-limit", type=float, default=1800.0)
    parser.add_argument("--output-csv", default="results/saa_replication.csv")
    args = parser.parse_args()

    if not args.illustrative_smoke_test:
        parser.error(
            "ros-scale/initial-fire-area/liters-per-sqm/cost-base/cost-water are swept sensitivity "
            "parameters (CLAUDE.md section 3/9); pass --illustrative-smoke-test to acknowledge."
        )
    if not pulp.GUROBI(msg=False).available():
        parser.error("the replication solves need a working Gurobi license.")

    bases = pd.read_csv(args.bases).head(args.n_bases)
    water_points = pd.read_csv(args.water).head(args.n_water)

    print("Building the 2024 day pool and drawing independent scenario sets...")
    events = load_events(args.events)
    pool = build_day_pool(events, date(2024, 1, 1), date(2024, 12, 31))
    replication_draws = [
        bootstrap_scenarios(pool, args.n_scenarios, np.random.default_rng(args.seed_base + m))
        for m in range(args.n_replications)
    ]
    eval_draw = bootstrap_scenarios(pool, args.n_eval, np.random.default_rng(args.eval_seed))

    # One enrichment pass over the union: FireRecord instances are shared
    # between scenarios drawn from the same pool, so ros/value_at_risk are
    # computed once per unique event, and the wind query cache in
    # weather.py deduplicates live NASA POWER calls within the call.
    all_scenarios = [s for draw in replication_draws for s in draw] + eval_draw
    n_fires_total = sum(len(s.fires) for s in all_scenarios)
    print(f"Enriching {n_fires_total} fire slots across {len(all_scenarios)} scenarios (shared events computed once)...")
    enrich_scenarios_with_ros_and_value_at_risk(
        all_scenarios,
        worldcover_tile_paths=args.worldcover_tiles,
        srtm_tile_paths=args.srtm_tiles,
        worldpop_raster_path=args.worldpop_raster,
        ros_scale=args.ros_scale,
    )
    enrich_t_arrival(all_scenarios, bases, speed=SPEED)

    # ---- Lower bound: M independent SAA optima --------------------------
    rep_rows = []
    optima = []
    candidate_first_stage = None
    for m, draw in enumerate(replication_draws):
        model_scenarios, dropped = to_model_scenarios(draw, on_missing="drop")
        if dropped:
            print(f"  replication {m}: WARNING, {len(dropped)} fire(s) dropped: {dropped}")
        params = _assemble(bases, water_points, model_scenarios, args)
        pre = precompute(params)
        timed = solve_with_time_limit(params, pre, time_limit_s=args.gurobi_time_limit)
        n_fires = sum(len(s.fires) for s in model_scenarios)
        print(
            f"  replication {m} (seed {args.seed_base + m}, {n_fires} fires): status={timed.solution.status} "
            f"objective={timed.solution.objective_value} timed_out={timed.timed_out} time={timed.elapsed_s:.1f}s"
        )
        rep_rows.append(
            {
                "replication": m,
                "seed": args.seed_base + m,
                "n_fires": n_fires,
                "status": timed.solution.status,
                "objective": timed.solution.objective_value,
                "timed_out": timed.timed_out,
                "solve_time_s": timed.elapsed_s,
            }
        )
        if not timed.timed_out and timed.solution.status == "Optimal":
            optima.append(timed.solution.objective_value)
            if candidate_first_stage is None:
                candidate_first_stage = (
                    timed.solution.base_open,
                    timed.solution.water_open,
                    timed.solution.n_aircraft,
                )

    if len(optima) < 2 or candidate_first_stage is None:
        raise SystemExit("fewer than two replications solved to proven optimality; no LB/candidate available.")

    lb_mean = statistics.mean(optima)
    lb_sd = statistics.stdev(optima)
    lb_half = t_crit(len(optima) - 1) * lb_sd / math.sqrt(len(optima))
    n_excluded = args.n_replications - len(optima)
    print(f"\nLower bound: mean of {len(optima)} proven optima = {lb_mean:.3f} +- {lb_half:.3f} (95% t-CI)"
          + (f"; {n_excluded} timed-out replication(s) excluded, disclosed" if n_excluded else ""))

    # ---- Upper bound: evaluate x_hat on the independent sample ----------
    print(f"\nEvaluating the candidate first-stage solution on {args.n_eval} independent scenarios...")
    losses = []
    t0 = time.perf_counter()
    for j, scen in enumerate(eval_draw):
        model_scenarios, dropped = to_model_scenarios([scen], on_missing="drop")
        one = model_scenarios[0]
        # A single-scenario evaluation needs probability 1 and, with the
        # first stage fixed, the recourse minimizing loss is identical for
        # any lambda (the CVaR of a point mass is the loss itself), so
        # lambda is set to 0 for a clean per-day loss read-out.
        import dataclasses as _dc

        one = _dc.replace(one, probability=1.0)
        eval_args = argparse.Namespace(**vars(args))
        eval_args.mean_risk_weight = 0.0
        params = _assemble(bases, water_points, [one], eval_args)
        pre = precompute(params)
        model, v = build_model(params, pre)
        _fix_first_stage(v, params, candidate_first_stage)
        status = solve(model, solver=pulp.GUROBI(msg=False))
        if status != "Optimal":
            raise SystemExit(f"evaluation scenario {j} did not solve: {status}")
        losses.append(sum(pulp.value(var) or 0.0 for var in v.loss.values()))
    eval_time = time.perf_counter() - t0

    dist = [(loss, 1.0 / len(losses)) for loss in losses]
    ub_expectation = expected_loss(dist)
    ub_cvar = empirical_cvar(dist, alpha=args.cvar_alpha)
    ub_objective = (1 - args.mean_risk_weight) * ub_expectation + args.mean_risk_weight * ub_cvar
    exp_sd = statistics.stdev(losses)
    exp_half = t_crit(len(losses) - 1) * exp_sd / math.sqrt(len(losses))
    print(f"  evaluated in {eval_time:.1f}s: E[loss] = {ub_expectation:.3f} +- {exp_half:.3f} (95% t-CI), "
          f"CVaR_{args.cvar_alpha} = {ub_cvar:.3f} (point estimate), mean-risk UB = {ub_objective:.3f}")

    gap = ub_objective - lb_mean
    gap_rel = gap / ub_objective if ub_objective else float("nan")
    print(f"\nEstimated optimality gap: {gap:.3f} ({100 * gap_rel:.2f}% of the UB)")
    print("Caveats: the CVaR term biases the SAA lower bound downward in small samples, and the "
          "CVaR component of the UB is a point estimate; expectation components carry t-CIs.")

    with open(args.output_csv, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(rep_rows[0].keys())
        for r in rep_rows:
            writer.writerow(r.values())
    summary_path = args.output_csv.replace(".csv", "_summary.csv")
    with open(summary_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(
            ["n_replications", "n_proven", "n_scenarios", "n_eval", "lb_mean", "lb_ci_half",
             "ub_expectation", "ub_expectation_ci_half", "ub_cvar_point", "ub_mean_risk",
             "gap", "gap_rel"]
        )
        writer.writerow(
            [args.n_replications, len(optima), args.n_scenarios, args.n_eval, lb_mean, lb_half,
             ub_expectation, exp_half, ub_cvar, ub_objective, gap, gap_rel]
        )
    print(f"\nWrote {args.output_csv} and {summary_path}")


if __name__ == "__main__":
    main()
