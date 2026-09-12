"""Experiment 6 (CLAUDE.md section 9): sensitivity to budget, to the
five magnitude constants with no solid Colombia-specific source (A0,
liters_per_sqm, ros_scale, cost_base, cost_water), and (added
2026-09-09) to the window, on one real-data instance.

Design DECIDED 2026-09-09: one-at-a-time (OAT) around a disclosed
center, not a full factorial (7 axes at 3-4 levels each would be
thousands of direct solves). The center is: the DECIDED values for
budget (150,000M COP) and window (2 h), and illustrative points for
the five swept constants (A0=1 ha, c=3 L/m^2, ros_scale=1.0,
cost_base=1,000M, cost_water=50M), each inside its documented range
(CLAUDE.md section 3). OAT shows each axis's marginal effect on the
optimal plan and objective; interactions between axes are NOT
captured, a disclosed limitation of the design, not an oversight.

A0 RE-ANCHORED 2026-09-12 (CLAUDE.md section 10): center 1 ha, axis
{0.1, 5, 14} ha, replacing the earlier 5 ha center and {1, 15, 30} ha
axis. The old range was chosen while requirement[f] silently lacked
the hectare-to-m^2 conversion (the 2026-09-12 units bug, fixed in
src/model/precompute.py); with correct units the new anchors are NWCG
fire size classes A (0.1 ha) and B (center, 1 ha) at the low end and
the single-VIIRS-pixel localization bound (375 m pixel, about 14 ha,
a sensor bound, not a typical fire size) at the top.

ros_scale subtlety, handled exactly rather than approximately:
ros_scale enters ros[f] at scenario ENRICHMENT time (section 5.3), and
re-running enrichment per sweep point would re-query the live NASA
POWER wind API. Since the section 5.3 formula is LINEAR in ros_scale
(ros = ros_scale * class_rate * slope_factor * wind_factor), the
script enriches ONCE at ros_scale=1.0, snapshots each fire's base ros,
and rescales multiplicatively per sweep point; this is exact, not an
approximation.

Per solve the script records objective, expected loss, empirical
CVaR_alpha (src/model/risk.py), worst-scenario loss, the first-stage
plan summary, and solve time. Instance sizes must stay direct-solvable
(the yardstick is the exact optimum); a matheuristic-based version at
full catalog scale is a separate follow-up.
"""

from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass, fields

import pandas as pd
import pulp

from src.experiments.common import solve_with_time_limit
from src.model.aircraft import COST_AIRCRAFT, FIREHAWK_OPS_TIME_H, SPEED, TANK
from src.model.costs import uniform_cost
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

# The OAT design: center first, then each axis's off-center values.
# Centers: DECIDED budget/window (CLAUDE.md section 10, 2026-09-09);
# documented-range midpoints for the five swept constants (section 3).
CENTER = {
    "budget": 150_000_000_000.0,
    "window": 2.0,
    "initial_fire_area": 1.0,  # ha; re-anchored 2026-09-12, see module docstring
    "liters_per_sqm": 3.0,
    "ros_scale": 1.0,
    "cost_base": 1_000_000_000.0,
    "cost_water": 50_000_000.0,
}
AXES = {
    "budget": [80_000_000_000.0, 225_000_000_000.0, 300_000_000_000.0],
    "window": [1.0, 4.0, 8.0],
    "initial_fire_area": [0.1, 5.0, 14.0],  # ha; re-anchored 2026-09-12
    "liters_per_sqm": [1.5, 6.0, 10.0],
    "ros_scale": [0.5, 2.0],
    "cost_base": [300_000_000.0, 3_000_000_000.0, 6_000_000_000.0],
    "cost_water": [15_000_000.0, 150_000_000.0, 300_000_000.0],
}


@dataclass
class SweepResult:
    axis: str
    value: float
    status: str
    mip_gap: float | None
    timed_out: bool
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
        description="Experiment 6 (CLAUDE.md section 9): OAT sensitivity sweep on one real-data "
        "instance (see module docstring for the design and its disclosed limits)."
    )
    parser.add_argument("--bases", default="data/processed/candidate_bases.csv")
    parser.add_argument("--water", default="data/processed/candidate_water.csv")
    parser.add_argument("--scenarios", default="data/processed/scenarios_2024full.json")
    parser.add_argument("--n-bases", type=int, default=20)
    parser.add_argument("--n-water", type=int, default=50)
    parser.add_argument("--max-scenarios", type=int, default=10)
    parser.add_argument("--worldcover-tiles", nargs="+", default=DEFAULT_WORLDCOVER_TILES)
    parser.add_argument("--srtm-tiles", nargs="+", default=DEFAULT_SRTM_TILES)
    parser.add_argument("--worldpop-raster", default=DEFAULT_WORLDPOP_RASTER)
    parser.add_argument("--cvar-alpha", type=float, default=0.95, help="alpha. DECIDED 2026-09-09; not an OAT axis.")
    parser.add_argument(
        "--mean-risk-weight", type=float, default=0.5,
        help="lambda. DECIDED 2026-09-09 base case; experiment 4 is its own sweep, not repeated here.",
    )
    parser.add_argument(
        "--axes", nargs="+", default=list(AXES.keys()),
        help="Which OAT axes to run (default: all seven).",
    )
    parser.add_argument(
        "--acknowledge-oat-design",
        action="store_true",
        help="Required flag: acknowledges the OAT design (no axis interactions) and the disclosed "
        "illustrative center for the five swept constants (module docstring).",
    )
    parser.add_argument(
        "--gurobi-time-limit",
        type=float,
        default=1800.0,
        help="Wall-clock seconds per solve. ADDED 2026-09-10: the budget axis enters multi-aircraft "
        "regimes where an un-limited direct solve ran ~16 hours without proof (CLAUDE.md section 10); "
        "timed-out solves report the best incumbent (an upper bound) plus the remaining MIP gap.",
    )
    parser.add_argument("--output-csv", default="results/experiment6_sensitivity.csv")
    args = parser.parse_args()

    if not args.acknowledge_oat_design:
        parser.error(
            "this sweep is one-at-a-time around a disclosed illustrative center (module docstring); "
            "pass --acknowledge-oat-design to acknowledge that design and its no-interactions limit."
        )
    unknown = [a for a in args.axes if a not in AXES]
    if unknown:
        parser.error(f"unknown axes {unknown}; valid: {list(AXES.keys())}")
    if not pulp.GUROBI(msg=False).available():
        parser.error("experiment 6 needs a working Gurobi license (direct solves are the yardstick).")

    bases = pd.read_csv(args.bases).head(args.n_bases)
    water_points = pd.read_csv(args.water).head(args.n_water)
    scenarios = read_scenarios_json(args.scenarios)[: args.max_scenarios]
    for scenario in scenarios:
        scenario.probability = 1.0 / len(scenarios)

    # Enrich ONCE at ros_scale=1.0; per-point rescaling below is exact
    # because the section 5.3 formula is linear in ros_scale.
    enrich_scenarios_with_ros_and_value_at_risk(
        scenarios,
        worldcover_tile_paths=args.worldcover_tiles,
        srtm_tile_paths=args.srtm_tiles,
        worldpop_raster_path=args.worldpop_raster,
        ros_scale=1.0,
    )
    enrich_t_arrival(scenarios, bases, speed=SPEED)
    base_ros = {
        fire.fire_id: fire.ros_param for s in scenarios for fire in s.fires if fire.ros_param is not None
    }

    def build_and_solve(config: dict) -> tuple:
        for s in scenarios:
            for fire in s.fires:
                if fire.fire_id in base_ros:
                    fire.ros_param = base_ros[fire.fire_id] * config["ros_scale"]
        model_scenarios, dropped = to_model_scenarios(scenarios, on_missing="drop")
        if dropped:
            print(f"  WARNING: {len(dropped)} fire(s) dropped, incomplete data: {dropped}")
        params = assemble_model_params(
            bases,
            water_points,
            model_scenarios,
            budget=config["budget"],
            window=config["window"],
            ops_time=FIREHAWK_OPS_TIME_H,
            cvar_alpha=args.cvar_alpha,
            mean_risk_weight=args.mean_risk_weight,
            initial_fire_area=config["initial_fire_area"],
            liters_per_sqm=config["liters_per_sqm"],
            cost_base=uniform_cost(list(bases["site_id"]), config["cost_base"]),
            cost_aircraft=COST_AIRCRAFT,
            cost_water=uniform_cost(list(water_points["site_id"]), config["cost_water"]),
            tank=TANK,
            speed=SPEED,
        )
        pre = precompute(params)
        timed = solve_with_time_limit(params, pre, time_limit_s=args.gurobi_time_limit)
        probabilities = {s.scenario_id: s.probability for s in model_scenarios}
        return timed, probabilities

    def record(axis: str, value: float, timed, probabilities) -> SweepResult:
        solution = timed.solution
        elapsed = timed.elapsed_s
        e_loss = cvar = worst = None
        # Metrics come from the incumbent whenever one exists, including
        # timed-out solves (the incumbent is a feasible plan; timed_out
        # in the CSV flags that its objective is an upper bound, not a
        # proven optimum).
        if solution.objective_value is not None:
            dist = [(solution.loss[s_id], p) for s_id, p in probabilities.items()]
            e_loss = expected_loss(dist)
            cvar = empirical_cvar(dist, alpha=args.cvar_alpha)
            worst = max(loss for loss, _ in dist)
        opened = sorted(i for i, open_ in solution.base_open.items() if open_)
        result = SweepResult(
            axis=axis,
            value=value,
            status=solution.status,
            mip_gap=timed.mip_gap,
            timed_out=timed.timed_out,
            objective_value=solution.objective_value,
            expected_loss=e_loss,
            empirical_cvar=cvar,
            worst_scenario_loss=worst,
            n_bases_open=len(opened),
            bases_open=";".join(opened),
            n_aircraft_total=sum(solution.n_aircraft.values()),
            n_water_open=sum(1 for open_ in solution.water_open.values() if open_),
            n_escapes=sum(1 for v in solution.escape.values() if v),
            solve_time_s=elapsed,
        )
        print(
            f"  {axis}={value}: status={result.status} obj={result.objective_value} "
            f"E[loss]={result.expected_loss} CVaR={result.empirical_cvar} bases={result.bases_open} "
            f"aircraft={result.n_aircraft_total} water={result.n_water_open} time={elapsed:.1f}s"
        )
        return result

    n_fires = sum(len(s.fires) for s in scenarios)
    print(f"Instance: {len(bases)} bases, {len(water_points)} water points, {len(scenarios)} scenarios, {n_fires} fires.")
    total_solves = 1 + sum(len(AXES[a]) for a in args.axes)
    print(f"OAT design: 1 center solve + {total_solves - 1} off-center solves.")

    results: list[SweepResult] = []
    print("\n=== center ===")
    timed, probabilities = build_and_solve(dict(CENTER))
    results.append(record("center", 0.0, timed, probabilities))

    for axis in args.axes:
        print(f"\n=== axis: {axis} (center {CENTER[axis]}) ===")
        for value in AXES[axis]:
            config = dict(CENTER)
            config[axis] = value
            timed, probabilities = build_and_solve(config)
            results.append(record(axis, value, timed, probabilities))

    print("\n=== Summary ===")
    header = [f.name for f in fields(SweepResult)]
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
