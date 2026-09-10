"""Experiment 1 (CLAUDE.md section 9, renamed 2026-08-18): the literal
bilinear formulation vs its big-M linearized MILP, on the SAME real-data
instance.

What is being tested (section 5.2, "What experiment 1 now compares"):
constraints 6a-6d are an EXACT reformulation of the bilinear
dispatch * refill_at product, not an approximation, so both formulations
must reach the SAME optimal objective value; the practical payoff is the
runtime difference between solving the linearized MILP and handing
Gurobi the literal bilinear product under NonConvex=2.
tests/test_model_bilinear.py already proves the exact-match claim on
hand-verified synthetic instances; this script measures it, and the
runtime ratio, on real Cundinamarca data across instance sizes.

Instance sizes here should stay SMALL: the bilinear/NonConvex solve is
the expensive arm (that asymmetry is the experiment's expected result,
not a nuisance), and the exact-match check needs both arms to reach
proven optimality. objective_match uses a relative tolerance (1e-6) on
top of an absolute one, since real objectives can be large.

Same disclosures as the other src/experiments scripts: the five swept
sensitivity parameters are fixed at one sweep point per run
(--illustrative-smoke-test acknowledges this); budget/cvar_alpha/
mean_risk_weight/window default to the DECIDED 2026-09-09 values
(CLAUDE.md section 10); t_arrival is recomputed per truncated instance
size, the established precedent.
"""

from __future__ import annotations

import argparse
import csv
import time
from dataclasses import dataclass, fields

import pandas as pd
import pulp

from src.model.aircraft import COST_AIRCRAFT, FIREHAWK_OPS_TIME_H, SPEED, TANK
from src.model.bilinear import solve_bilinear_model
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
DEFAULT_INSTANCE_SIZES = [(3, 5), (5, 10), (8, 15)]


@dataclass
class InstanceResult:
    n_bases: int
    n_water: int
    n_scenarios: int
    n_fires: int
    milp_status: str
    milp_objective: float | None
    milp_time_s: float
    bilinear_status: str
    bilinear_objective: float | None
    bilinear_time_s: float
    objective_match: bool | None
    time_ratio_bilinear_over_milp: float | None


def _parse_instance_sizes(raw: list[str]) -> list[tuple[int, int]]:
    return [(int(b), int(w)) for b, w in (item.split(":") for item in raw)]


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Experiment 1 (CLAUDE.md section 9): literal bilinear formulation vs the big-M "
        "linearized MILP, same instance, objective match and runtime ratio."
    )
    parser.add_argument("--bases", default="data/processed/candidate_bases.csv")
    parser.add_argument("--water", default="data/processed/candidate_water.csv")
    parser.add_argument("--scenarios", default="data/processed/scenarios_2024full.json")
    parser.add_argument("--max-scenarios", type=int, default=2)
    parser.add_argument(
        "--instance-sizes",
        nargs="+",
        default=[f"{b}:{w}" for b, w in DEFAULT_INSTANCE_SIZES],
        help="List of n_bases:n_water_points pairs; keep SMALL, the bilinear arm is the expensive one.",
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
    parser.add_argument("--output-csv", default="results/experiment1_bilinear_vs_milp.csv")
    args = parser.parse_args()

    if not args.illustrative_smoke_test:
        parser.error(
            "ros-scale/initial-fire-area/liters-per-sqm/cost-base/cost-water are swept sensitivity "
            "parameters (CLAUDE.md section 3/9, experiment 6); a single run fixes them at one sweep "
            "point. Pass --illustrative-smoke-test to acknowledge that. budget/cvar-alpha/"
            "mean-risk-weight/window have DECIDED defaults (2026-09-09, CLAUDE.md section 10)."
        )
    if not pulp.GUROBI(msg=False).available():
        parser.error(
            "experiment 1 needs a working Gurobi license: the bilinear arm is gurobipy NonConvex=2, "
            "and the MILP arm should use the same solver for a fair runtime comparison."
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

        print("Solving linearized MILP (Gurobi)...")
        t0 = time.perf_counter()
        milp = solve_model(params, pre, solver=pulp.GUROBI(msg=False))
        milp_time = time.perf_counter() - t0
        print(f"  status={milp.status} objective={milp.objective_value} time={milp_time:.2f}s")

        print("Solving literal bilinear formulation (gurobipy, NonConvex=2)...")
        t0 = time.perf_counter()
        bilinear = solve_bilinear_model(params, pre)
        bilinear_time = time.perf_counter() - t0
        print(f"  status={bilinear.status} objective={bilinear.objective_value} time={bilinear_time:.2f}s")

        match = None
        if milp.objective_value is not None and bilinear.objective_value is not None:
            diff = abs(milp.objective_value - bilinear.objective_value)
            scale = max(1.0, abs(milp.objective_value))
            match = diff <= 1e-6 * scale
            if not match:
                print(
                    f"  WARNING: objectives DIFFER (milp={milp.objective_value}, "
                    f"bilinear={bilinear.objective_value}, diff={diff}); the linearization exactness "
                    "claim (section 5.2) says they must match at optimality, investigate before "
                    "trusting either result."
                )

        results.append(
            InstanceResult(
                n_bases=n_bases,
                n_water=n_water,
                n_scenarios=len(model_scenarios),
                n_fires=n_fires,
                milp_status=milp.status,
                milp_objective=milp.objective_value,
                milp_time_s=milp_time,
                bilinear_status=bilinear.status,
                bilinear_objective=bilinear.objective_value,
                bilinear_time_s=bilinear_time,
                objective_match=match,
                time_ratio_bilinear_over_milp=(bilinear_time / milp_time) if milp_time > 0 else None,
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
