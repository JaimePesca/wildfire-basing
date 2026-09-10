"""Experiment 3 (CLAUDE.md section 9): integrated vs sequential, the
star experiment. Solves the SAME real-data instance two ways:

1. Integrated: the full section 5.2 MILP (src/model/milp.py), one Gurobi
   solve, joint base/water/fleet decisions.
2. Sequential: the bases-first/water-second baseline
   (src/model/sequential.py), sweeping the exogenous budget split phi and
   reporting the BEST sequential result, so the comparison is against a
   best-case sequential planner, not a straw man. See sequential.py's
   module docstring for the full design and why it reuses milp.build_model
   unchanged (no formula drift possible).

The paper's claim this quantifies: bases-first planning cannot see the
base-water cycle coupling or the budget split (CLAUDE.md section 2), so
its solutions can be strictly worse than the integrated optimum, and no
budget split can always repair that (tests/test_model_sequential.py
proves the strict case on a hand-built instance; this script measures
the gap on real Cundinamarca data).

Same disclosures as experiment 2's script: the five swept sensitivity
parameters are fixed at one sweep point per run (--illustrative-smoke-test
acknowledges this); budget/cvar_alpha/mean_risk_weight/window default to
the DECIDED 2026-09-09 values (CLAUDE.md section 10); t_arrival is
recomputed per truncated instance size, the established precedent.
Instance sizes must stay tractable for the DIRECT integrated solve, since
that is the yardstick here; a matheuristic-based integrated arm at full
catalog scale is a separate follow-up.
"""

from __future__ import annotations

import argparse
import csv
import time
from dataclasses import dataclass, fields

import pandas as pd
import pulp

from src.experiments.common import solve_with_time_limit
from src.model.aircraft import COST_AIRCRAFT, FIREHAWK_OPS_TIME_H, SPEED, TANK
from src.model.costs import uniform_cost
from src.model.milp import solve_model
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
DEFAULT_INSTANCE_SIZES = [(5, 10), (10, 25), (20, 50)]
DEFAULT_PHIS = [0.5, 0.6, 0.7, 0.8, 0.9, 1.0]


@dataclass
class InstanceResult:
    n_bases: int
    n_water: int
    n_scenarios: int
    n_fires: int
    integrated_status: str
    integrated_objective: float | None
    integrated_mip_gap: float | None
    integrated_timed_out: bool
    integrated_time_s: float
    sequential_best_phi: float | None
    sequential_best_objective: float | None
    sequential_time_s: float
    sequential_gap_abs: float | None
    sequential_gap_pct: float | None


def _parse_instance_sizes(raw: list[str]) -> list[tuple[int, int]]:
    return [(int(b), int(w)) for b, w in (item.split(":") for item in raw)]


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Experiment 3 (CLAUDE.md section 9): integrated vs best-case sequential "
        "(bases first, water second), across a sweep of candidate-catalog sizes."
    )
    parser.add_argument("--bases", default="data/processed/candidate_bases.csv")
    parser.add_argument("--water", default="data/processed/candidate_water.csv")
    parser.add_argument("--scenarios", default="data/processed/scenarios_2024full.json")
    parser.add_argument("--max-scenarios", type=int, default=2)
    parser.add_argument(
        "--instance-sizes",
        nargs="+",
        default=[f"{b}:{w}" for b, w in DEFAULT_INSTANCE_SIZES],
        help="List of n_bases:n_water_points pairs, e.g. 5:10 10:25 20:50.",
    )
    parser.add_argument(
        "--phis",
        nargs="+",
        type=float,
        default=DEFAULT_PHIS,
        help="Budget split fractions swept for the sequential baseline's phase A.",
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
    parser.add_argument(
        "--budget", type=float, default=150_000_000_000.0,
        help="B, COP. DECIDED 2026-09-09 (CLAUDE.md section 10): the real FAC/UNGRD Firehawk program "
        "spend; experiment 6 sweeps it.",
    )
    parser.add_argument(
        "--cvar-alpha", type=float, default=0.95,
        help="alpha. DECIDED 2026-09-09: standard academic CVaR level (Rockafellar-Uryasev 2000).",
    )
    parser.add_argument(
        "--mean-risk-weight", type=float, default=0.5,
        help="lambda. DECIDED 2026-09-09: disclosed midpoint convention; experiment 4 sweeps it.",
    )
    parser.add_argument(
        "--window", type=float, default=2.0,
        help="W, hours. DECIDED 2026-09-09: NWCG PMS 205 initial-attack containment standard.",
    )
    parser.add_argument(
        "--illustrative-smoke-test",
        action="store_true",
        help="Required flag: acknowledges ros-scale/initial-fire-area/liters-per-sqm/cost-base/"
        "cost-water are swept sensitivity parameters (CLAUDE.md section 3/9) fixed at one sweep point "
        "for this run.",
    )
    parser.add_argument("--solver", choices=["cbc", "gurobi"], default="gurobi")
    parser.add_argument(
        "--gurobi-time-limit",
        type=float,
        default=1800.0,
        help="Wall-clock seconds per Gurobi solve (integrated arm AND each sequential phase). ADDED "
        "2026-09-10 after an un-limited two-aircraft-regime integrated solve ran ~16 hours without "
        "proving optimality (CLAUDE.md section 10); a timed-out integrated arm still reports its best "
        "incumbent and remaining MIP gap.",
    )
    parser.add_argument("--output-csv", default="results/experiment3_integrated_vs_sequential.csv")
    args = parser.parse_args()

    if not args.illustrative_smoke_test:
        parser.error(
            "ros-scale/initial-fire-area/liters-per-sqm/cost-base/cost-water are swept sensitivity "
            "parameters (CLAUDE.md section 3/9, experiment 6); a single run fixes them at one sweep "
            "point. Pass --illustrative-smoke-test to acknowledge that. budget/cvar-alpha/"
            "mean-risk-weight/window have DECIDED defaults (2026-09-09, CLAUDE.md section 10)."
        )
    if args.solver == "gurobi" and not pulp.GUROBI(msg=False).available():
        parser.error("no working Gurobi license found; pass --solver cbc or fix the license.")

    solver_factory = (
        (lambda: pulp.GUROBI(msg=False, timeLimit=args.gurobi_time_limit))
        if args.solver == "gurobi"
        else (lambda: pulp.PULP_CBC_CMD(msg=False))
    )
    instance_sizes = _parse_instance_sizes(args.instance_sizes)

    full_bases = pd.read_csv(args.bases)
    full_water = pd.read_csv(args.water)

    base_scenarios = read_scenarios_json(args.scenarios)[: args.max_scenarios]
    for scenario in base_scenarios:
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

        print("Solving integrated (full MILP)...")
        integrated_mip_gap = None
        integrated_timed_out = False
        if args.solver == "gurobi":
            timed = solve_with_time_limit(params, pre, time_limit_s=args.gurobi_time_limit)
            integrated = timed.solution
            integrated_time = timed.elapsed_s
            integrated_mip_gap = timed.mip_gap
            integrated_timed_out = timed.timed_out
        else:
            t0 = time.perf_counter()
            integrated = solve_model(params, pre, solver=solver_factory())
            integrated_time = time.perf_counter() - t0
        print(
            f"  status={integrated.status} objective={integrated.objective_value} "
            f"mip_gap={integrated_mip_gap} timed_out={integrated_timed_out} time={integrated_time:.2f}s"
        )
        if integrated_timed_out:
            print(
                "  NOTE: integrated arm hit the time limit; its objective is the best incumbent, an "
                "UPPER bound on the true optimum, so a sequential result below it would only bound the "
                "gap, not measure it exactly."
            )

        print(f"Solving sequential (bases first, water second), phi in {args.phis}...")
        t0 = time.perf_counter()
        best, all_results = solve_sequential_best_phi(params, phis=args.phis, solver_factory=solver_factory)
        sequential_time = time.perf_counter() - t0
        for r in all_results:
            print(
                f"  phi={r.phi}: phase A spend={r.phase_a.spend:.0f}, "
                f"phase B status={r.phase_b.status}, objective={r.objective_value}"
            )
        print(f"  BEST sequential: phi={best.phi}, objective={best.objective_value}, time(all phis)={sequential_time:.2f}s")

        gap_abs = None
        gap_pct = None
        if integrated.objective_value is not None and best.objective_value is not None:
            gap_abs = best.objective_value - integrated.objective_value
            if integrated.objective_value != 0:
                gap_pct = 100.0 * gap_abs / integrated.objective_value
            elif gap_abs != 0:
                print(
                    f"  WARNING: integrated objective is 0.0 but sequential best is {best.objective_value}; "
                    "gap cannot be expressed as a percentage, see sequential_gap_abs."
                )

        results.append(
            InstanceResult(
                n_bases=n_bases,
                n_water=n_water,
                n_scenarios=len(model_scenarios),
                n_fires=n_fires,
                integrated_status=integrated.status,
                integrated_objective=integrated.objective_value,
                integrated_mip_gap=integrated_mip_gap,
                integrated_timed_out=integrated_timed_out,
                integrated_time_s=integrated_time,
                sequential_best_phi=best.phi,
                sequential_best_objective=best.objective_value,
                sequential_time_s=sequential_time,
                sequential_gap_abs=gap_abs,
                sequential_gap_pct=gap_pct,
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
