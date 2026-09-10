"""Experiment 4 (CLAUDE.md section 9): expectation vs CVaR. Solves the
SAME real-data instance across a sweep of mean_risk_weight (lambda, 0 =
risk neutral through 1 = pure CVaR) and reports how the first-stage
plan and the loss distribution shift with risk attitude.

For every lambda the script records, from the solved instance:
- the optimizer's own objective value (NOT comparable across lambdas,
  the objective itself changes with lambda; kept for reference only),
- expected loss and empirical CVaR_alpha of the scenario loss
  distribution (src/model/risk.py, recomputed identically for every
  lambda; the solved var_level variable is meaningless at lambda = 0,
  see risk.py's docstring for why empirical recomputation is required),
- worst-scenario loss, first-stage decisions (bases opened, aircraft
  placement, water points opened), and escapes.

The paper's expected story: as lambda grows, expected loss can only get
worse (weakly) while CVaR improves (weakly), and the first-stage plan
shifts toward hedging the tail scenarios; with few SAA scenarios,
CVaR_0.95 is effectively worst-case (risk.py's documented
few-scenarios behavior, an SAA caveat to state, not hide).

Same disclosures as the other src/experiments scripts: the five swept
sensitivity parameters are fixed at one sweep point per run
(--illustrative-smoke-test acknowledges this); budget/cvar_alpha/window
default to the DECIDED 2026-09-09 values (CLAUDE.md section 10);
mean_risk_weight is the swept axis here, so it has no single default;
t_arrival is recomputed for the truncated base set, the established
precedent.
"""

from __future__ import annotations

import argparse
import csv
import time
from dataclasses import dataclass, fields

import pandas as pd
import pulp

from src.model.aircraft import COST_AIRCRAFT, FIREHAWK_OPS_TIME_H, SPEED, TANK
from src.model.costs import uniform_cost
from src.model.milp import solve_model
from src.model.precompute import precompute
from src.model.risk import empirical_cvar, expected_loss
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
DEFAULT_LAMBDAS = [0.0, 0.25, 0.5, 0.75, 1.0]


@dataclass
class LambdaResult:
    mean_risk_weight: float
    status: str
    objective_value: float | None
    expected_loss: float | None
    empirical_cvar: float | None
    worst_scenario_loss: float | None
    n_bases_open: int
    bases_open: str
    n_aircraft_total: int
    n_water_open: int
    n_escapes: int
    solve_time_s: float


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Experiment 4 (CLAUDE.md section 9): expectation vs CVaR, sweeping mean_risk_weight "
        "on one real-data instance."
    )
    parser.add_argument("--bases", default="data/processed/candidate_bases.csv")
    parser.add_argument("--water", default="data/processed/candidate_water.csv")
    parser.add_argument("--scenarios", default="data/processed/scenarios_2024full.json")
    parser.add_argument("--n-bases", type=int, default=20, help="Instance size: candidate bases (direct-solvable).")
    parser.add_argument("--n-water", type=int, default=50, help="Instance size: candidate water points (direct-solvable).")
    parser.add_argument("--max-scenarios", type=int, default=10)
    parser.add_argument("--lambdas", nargs="+", type=float, default=DEFAULT_LAMBDAS)
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
    parser.add_argument("--window", type=float, default=2.0, help="W, hours. DECIDED 2026-09-09.")
    parser.add_argument(
        "--illustrative-smoke-test",
        action="store_true",
        help="Required flag: acknowledges ros-scale/initial-fire-area/liters-per-sqm/cost-base/"
        "cost-water are swept sensitivity parameters fixed at one sweep point for this run.",
    )
    parser.add_argument("--solver", choices=["cbc", "gurobi"], default="gurobi")
    parser.add_argument("--output-csv", default="results/experiment4_expectation_vs_cvar.csv")
    args = parser.parse_args()

    if not args.illustrative_smoke_test:
        parser.error(
            "ros-scale/initial-fire-area/liters-per-sqm/cost-base/cost-water are swept sensitivity "
            "parameters (CLAUDE.md section 3/9); pass --illustrative-smoke-test to acknowledge."
        )
    if args.solver == "gurobi" and not pulp.GUROBI(msg=False).available():
        parser.error("no working Gurobi license found; pass --solver cbc or fix the license.")
    solver_factory = (
        (lambda: pulp.GUROBI(msg=False)) if args.solver == "gurobi" else (lambda: pulp.PULP_CBC_CMD(msg=False))
    )

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

    probabilities = {s.scenario_id: s.probability for s in model_scenarios}

    results: list[LambdaResult] = []
    for lam in args.lambdas:
        params = assemble_model_params(
            bases,
            water_points,
            model_scenarios,
            budget=args.budget,
            window=args.window,
            ops_time=FIREHAWK_OPS_TIME_H,
            cvar_alpha=args.cvar_alpha,
            mean_risk_weight=lam,
            initial_fire_area=args.initial_fire_area,
            liters_per_sqm=args.liters_per_sqm,
            cost_base=uniform_cost(list(bases["site_id"]), args.cost_base),
            cost_aircraft=COST_AIRCRAFT,
            cost_water=uniform_cost(list(water_points["site_id"]), args.cost_water),
            tank=TANK,
            speed=SPEED,
        )
        pre = precompute(params)

        print(f"\n=== lambda = {lam} ===")
        t0 = time.perf_counter()
        solution = solve_model(params, pre, solver=solver_factory())
        elapsed = time.perf_counter() - t0

        e_loss = cvar = worst = None
        if solution.status == "Optimal":
            dist = [(solution.loss[s_id], p) for s_id, p in probabilities.items()]
            e_loss = expected_loss(dist)
            cvar = empirical_cvar(dist, alpha=args.cvar_alpha)
            worst = max(loss for loss, _ in dist)
        opened = sorted(i for i, open_ in solution.base_open.items() if open_)
        n_aircraft_total = sum(solution.n_aircraft.values())
        n_water_open = sum(1 for open_ in solution.water_open.values() if open_)
        n_escapes = sum(1 for v in solution.escape.values() if v)
        print(
            f"  status={solution.status} E[loss]={e_loss} CVaR_{args.cvar_alpha}={cvar} worst={worst} "
            f"bases={opened} aircraft={n_aircraft_total} water={n_water_open} escapes={n_escapes} time={elapsed:.1f}s"
        )

        results.append(
            LambdaResult(
                mean_risk_weight=lam,
                status=solution.status,
                objective_value=solution.objective_value,
                expected_loss=e_loss,
                empirical_cvar=cvar,
                worst_scenario_loss=worst,
                n_bases_open=len(opened),
                bases_open=";".join(opened),
                n_aircraft_total=n_aircraft_total,
                n_water_open=n_water_open,
                n_escapes=n_escapes,
                solve_time_s=elapsed,
            )
        )

    print("\n=== Summary ===")
    header = [f.name for f in fields(LambdaResult)]
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
