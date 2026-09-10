"""Assemble and solve a real-data instance end to end: real candidate bases
and water points (src/pipeline/sites_*.py output), a real bootstrap
scenario draw (src/scenarios/day_scenarios.py output), real aircraft
parameters (aircraft.py), and real land cover/slope/wind/population rasters
(src/scenarios/*.py), wired through src/scenarios/assemble.py and
src/model/travel_times.py into a schema.ModelParams, then solved with
milp.py.

This is the first script in the repo that touches every real-data stage at
once (CLAUDE.md's various "what's left before this is a real, runnable
instance" notes, src/model/README.md and src/scenarios/README.md). Two
things it does NOT resolve, both flagged loudly rather than silently
defaulted:

1. budget/cvar_alpha/mean_risk_weight/window are the user's own call
   (CLAUDE.md section 4/10, config/parameters.yaml explicitly says "do not
   invent values for entries marked PENDING"). This script requires them as
   CLI arguments with no built-in default, and --illustrative-smoke-test
   must be passed explicitly to acknowledge that a given run is not using
   sourced/decided values (mirroring the aircraft-speed-placeholder
   precedent already used once in src/scenarios/assemble.py's own
   verification history).
2. The real candidate water point set is 5,449 sites (src/pipeline,
   OSM+CAR combined). The exact McCormick linearization in milp.py adds a
   serve[i,f,k,m,s] auxiliary variable per (base, fire, water point,
   aircraft type, scenario) combination, i.e. |I|*|K| per (f,s) pair: at
   the real scale (120 bases, 5,449 water points) that is over 650,000
   auxiliary variables per fire per scenario, not tractable for an exact
   solve. --max-bases/--max-water-points truncate the candidate sets for
   testing that the pipeline plumbing itself is correct; they are NOT a
   proposed real experimental design, and this truncation is disclosed
   prominently, not silently applied. Reducing the real candidate water set
   to a tractable size (e.g. clustering nearby water bodies, or restricting
   to named/significant ones) is a separate, not-yet-solved open item.
"""

from __future__ import annotations

import argparse

import pandas as pd
import pulp

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


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Assemble a real-data instance and solve it (see module docstring for what is "
        "and is not resolved by this script)."
    )
    parser.add_argument("--bases", default="data/processed/candidate_bases.csv")
    parser.add_argument("--water", default="data/processed/candidate_water.csv")
    parser.add_argument("--scenarios", default="data/processed/scenarios_2024full.json")
    parser.add_argument(
        "--max-bases", type=int, default=None, help="Truncate candidate bases for tractability (see module docstring)."
    )
    parser.add_argument(
        "--max-water-points",
        type=int,
        default=None,
        help="Truncate candidate water points for tractability (see module docstring).",
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
        "values for this run, only a smoke test of the pipeline plumbing.",
    )
    parser.add_argument("--solver", choices=["cbc", "gurobi"], default="cbc")
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
        # Each scenario still carries its probability from the ORIGINAL,
        # larger bootstrap draw (e.g. 1/200); over this truncated subset
        # those no longer sum to 1, which build_model's own validation will
        # now reject outright (CONFIRMED 2026-08-30: left unrenormalized,
        # this does not just skew results, it makes the CVaR objective
        # genuinely unbounded, see milp.py's _validate_scenario_probabilities).
        # Renormalizing here is a tractability-subsample concession, same
        # spirit as --max-bases/--max-water-points, not a real SAA resample.
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
    pre = precompute(params)

    solver = pulp.GUROBI(msg=False) if args.solver == "gurobi" else pulp.PULP_CBC_CMD(msg=False)
    result = solve_model(params, pre, solver=solver)

    print(f"\nStatus: {result.status}")
    print(f"Objective value: {result.objective_value}")
    print(f"Bases opened: {[i for i, open_ in result.base_open.items() if open_]}")
    print(f"Water points opened: {[k for k, open_ in result.water_open.items() if open_]}")
    print(f"Aircraft stationed: {[(k, n) for k, n in result.n_aircraft.items() if n > 0]}")
    n_escaped = sum(1 for v in result.escape.values() if v)
    print(f"Fires escaped: {n_escaped} / {len(result.escape)}")


if __name__ == "__main__":
    main()
