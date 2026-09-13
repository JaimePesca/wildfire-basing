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
3. Evaluate EVERY replication's optimal first-stage solution on the N'
   independent evaluation scenarios (one small recourse MILP per
   scenario and candidate, with every first-stage variable fixed), and
   select the candidate with the best evaluated mean-risk objective,
   the standard SAA candidate-selection step. Because selecting the
   minimum of M evaluated values on the SAME sample introduces a small
   optimistic selection bias, the WINNER is then re-evaluated on a
   SECOND, fresh, independent sample of the same size (its own seed),
   and that fresh evaluation is the reported upper bound (the
   pre-registered first-replication candidate's evaluation is also
   reported, for comparability with the naive protocol).
4. Report gap = UB - LB with the CI components.

Honest statistical caveats, printed with the results rather than
hidden: the sample CVaR inside the objective is downward biased in
small samples, which makes the statistical lower bound LOOSER but
does not invalidate it (E[v_N] <= v* still holds; the bias direction
reinforces validity, wording sharpened 2026-09-12 after peer review);
the CVaR component of the upper bound is reported as a point estimate
(its CI is not a simple t interval); the expectation components carry
standard t intervals. With N' = 100 equiprobable evaluation
scenarios, CVaR_0.95 averages the worst five losses.

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
    parser.add_argument(
        "--fresh-eval-seed", type=int, default=998,
        help="Seed for the second, fresh evaluation sample used to re-evaluate the selected winner "
        "without selection bias (must differ from eval-seed and the replication seeds).",
    )
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
    fresh_draw = bootstrap_scenarios(pool, args.n_eval, np.random.default_rng(args.fresh_eval_seed))

    # One enrichment pass over the union: FireRecord instances are shared
    # between scenarios drawn from the same pool, so ros/value_at_risk are
    # computed once per unique event, and the wind query cache in
    # weather.py deduplicates live NASA POWER calls within the call.
    all_scenarios = [s for draw in replication_draws for s in draw] + eval_draw + fresh_draw
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
    candidates: list[tuple[int, tuple]] = []  # (replication index, first stage)
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
            candidates.append(
                (m, (timed.solution.base_open, timed.solution.water_open, timed.solution.n_aircraft))
            )

    if len(optima) < 2 or not candidates:
        raise SystemExit("fewer than two replications solved to proven optimality; no LB/candidate available.")

    lb_mean = statistics.mean(optima)
    lb_sd = statistics.stdev(optima)
    lb_half = t_crit(len(optima) - 1) * lb_sd / math.sqrt(len(optima))
    n_excluded = args.n_replications - len(optima)
    print(f"\nLower bound: mean of {len(optima)} proven optima = {lb_mean:.3f} +- {lb_half:.3f} (95% t-CI)"
          + (f"; {n_excluded} timed-out replication(s) excluded, disclosed" if n_excluded else ""))

    # ---- Candidate evaluation on independent samples ---------------------
    import dataclasses as _dc

    def evaluate_on(first_stage, draw) -> list[float]:
        """Per-day recourse losses of a fixed first-stage solution over a
        scenario draw: one small MILP per scenario with every first-stage
        variable fixed. lambda is set to 0 per solve because, with the
        first stage fixed and a single scenario, the loss-minimizing
        recourse is identical for any lambda (the CVaR of a point mass
        is the loss itself)."""
        losses: list[float] = []
        for j, scen in enumerate(draw):
            model_scenarios, _dropped = to_model_scenarios([scen], on_missing="drop")
            one = _dc.replace(model_scenarios[0], probability=1.0)
            eval_args = argparse.Namespace(**vars(args))
            eval_args.mean_risk_weight = 0.0
            params = _assemble(bases, water_points, [one], eval_args)
            pre = precompute(params)
            model, v = build_model(params, pre)
            _fix_first_stage(v, params, first_stage)
            status = solve(model, solver=pulp.GUROBI(msg=False))
            if status != "Optimal":
                raise SystemExit(f"evaluation scenario {j} did not solve: {status}")
            losses.append(sum(pulp.value(var) or 0.0 for var in v.loss.values()))
        return losses

    def mean_risk_of(losses: list[float]) -> tuple[float, float, float, float]:
        dist = [(loss, 1.0 / len(losses)) for loss in losses]
        e = expected_loss(dist)
        cv = empirical_cvar(dist, alpha=args.cvar_alpha)
        obj = (1 - args.mean_risk_weight) * e + args.mean_risk_weight * cv
        half = t_crit(len(losses) - 1) * statistics.stdev(losses) / math.sqrt(len(losses))
        return e, cv, obj, half

    print(f"\nEvaluating all {len(candidates)} candidate solutions on {args.n_eval} independent scenarios...")
    t0 = time.perf_counter()
    evaluated = []
    for m, first_stage in candidates:
        e, cv, obj, half = mean_risk_of(evaluate_on(first_stage, eval_draw))
        evaluated.append({"replication": m, "eval_expectation": e, "eval_cvar": cv,
                          "eval_mean_risk": obj, "eval_expectation_ci_half": half})
        print(f"  candidate from replication {m}: E[loss]={e:.3f} CVaR={cv:.3f} mean-risk={obj:.3f}")
    eval_time = time.perf_counter() - t0
    print(f"  ({eval_time:.1f}s total)")

    naive = evaluated[0]  # the pre-registered first-replication candidate
    winner = min(evaluated, key=lambda r: r["eval_mean_risk"])
    winner_first_stage = dict(candidates)[winner["replication"]]

    print(f"\nSelected candidate: replication {winner['replication']} "
          f"(selection sample mean-risk {winner['eval_mean_risk']:.3f}); re-evaluating on a fresh "
          f"independent sample of {args.n_eval} scenarios (selection-bias control)...")
    fe, fcv, fobj, fhalf = mean_risk_of(evaluate_on(winner_first_stage, fresh_draw))
    print(f"  fresh evaluation: E[loss] = {fe:.3f} +- {fhalf:.3f} (95% t-CI), "
          f"CVaR_{args.cvar_alpha} = {fcv:.3f} (point estimate), mean-risk UB = {fobj:.3f}")

    gap = fobj - lb_mean
    gap_rel = gap / fobj if fobj else float("nan")
    naive_gap = naive["eval_mean_risk"] - lb_mean
    print(f"\nEstimated optimality gap (selected candidate, fresh sample): {gap:.3f} "
          f"({100 * gap_rel:.2f}% of the UB)")
    print(f"For comparison, the naive pre-registered candidate's gap on the selection sample: "
          f"{naive_gap:.3f} ({100 * naive_gap / naive['eval_mean_risk']:.2f}% of its UB)")
    print("Caveats: the sample-CVaR term is downward biased in small samples, which keeps the "
          "statistical lower bound VALID but looser (E[v_N] <= v* still holds); the CVaR component "
          "of the UB is a point estimate; expectation components carry t-CIs; the winner's UB comes "
          "from a fresh sample precisely so the min-of-M selection cannot flatter it.")

    with open(args.output_csv, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        eval_by_rep = {r["replication"]: r for r in evaluated}
        header = list(rep_rows[0].keys()) + ["eval_expectation", "eval_cvar", "eval_mean_risk"]
        writer.writerow(header)
        for r in rep_rows:
            ev = eval_by_rep.get(r["replication"], {})
            writer.writerow(list(r.values()) + [ev.get("eval_expectation"), ev.get("eval_cvar"),
                                                ev.get("eval_mean_risk")])
    summary_path = args.output_csv.replace(".csv", "_summary.csv")
    with open(summary_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(
            ["n_replications", "n_proven", "n_scenarios", "n_eval", "lb_mean", "lb_ci_half",
             "selected_replication", "ub_expectation", "ub_expectation_ci_half", "ub_cvar_point",
             "ub_mean_risk", "gap", "gap_rel", "naive_ub_mean_risk", "naive_gap"]
        )
        writer.writerow(
            [args.n_replications, len(optima), args.n_scenarios, args.n_eval, lb_mean, lb_half,
             winner["replication"], fe, fhalf, fcv, fobj, gap, gap_rel,
             naive["eval_mean_risk"], naive_gap]
        )
    print(f"\nWrote {args.output_csv} and {summary_path}")


if __name__ == "__main__":
    main()
