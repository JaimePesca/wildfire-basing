"""Operational solution report for the base case: solve the DECIDED
20:50:10 instance once and dump WHERE the plan actually puts things, in
real-place terms (aerodrome and water body names), for the manuscript's
operational reading and for policy discussion.

Reported per solve:
- bases opened and aircraft stationed, with catalog names/coordinates;
- per scenario (historical day): which fire is served, from which base,
  refilling at which water point, liters delivered vs. requirement,
  contained or escaped, and the population exposure at stake;
- the set of water points actually USED by some dispatch (refill_at
  active), as opposed to merely opened: under slack budget the solver
  opens alternate-optimal water points at no objective cost (CLAUDE.md
  2026-09-12 review; the manuscript's Section 6 preamble discloses
  this), so only the USED set is operationally meaningful.

Alternate optima caveat, printed with the output: the base-case optimum
is degenerate across several bases (different solver runs of the same
instance have returned aero_SQIB, aero_SKSO, aero_SQUV, aero_SQCO, ...),
so the specific open base is a representative of an equivalence class,
not a unique recommendation; the report therefore also lists, for the
served fires, every base whose (base, water) pair could deliver the same
containments (same drops at the chosen water point), i.e. the bases that
tie operationally for this scenario draw.
"""

from __future__ import annotations

import argparse
import json

import pandas as pd
import pulp

from src.experiments.common import solve_with_time_limit
from src.model.aircraft import COST_AIRCRAFT, FIREHAWK_OPS_TIME_H, SPEED, TANK
from src.model.costs import uniform_cost
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
        description="Solve the DECIDED base case once and report the operational plan with real "
        "place names (see module docstring for the alternate-optima caveat)."
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
    parser.add_argument("--ros-scale", type=float, required=True)
    parser.add_argument("--initial-fire-area", type=float, required=True, help="A0, hectares.")
    parser.add_argument("--liters-per-sqm", type=float, required=True, help="c, L/m^2.")
    parser.add_argument("--cost-base", type=float, required=True)
    parser.add_argument("--cost-water", type=float, required=True)
    parser.add_argument("--budget", type=float, default=150_000_000_000.0)
    parser.add_argument("--cvar-alpha", type=float, default=0.95)
    parser.add_argument("--mean-risk-weight", type=float, default=0.5)
    parser.add_argument("--window", type=float, default=2.0)
    parser.add_argument("--gurobi-time-limit", type=float, default=1800.0)
    parser.add_argument(
        "--illustrative-smoke-test",
        action="store_true",
        help="Required flag: acknowledges the five swept sensitivity parameters are fixed at one "
        "sweep point for this run.",
    )
    parser.add_argument("--output-json", default="results/base_case_solution.json")
    args = parser.parse_args()

    if not args.illustrative_smoke_test:
        parser.error(
            "ros-scale/initial-fire-area/liters-per-sqm/cost-base/cost-water are swept sensitivity "
            "parameters (CLAUDE.md section 3/9); pass --illustrative-smoke-test to acknowledge."
        )
    if not pulp.GUROBI(msg=False).available():
        parser.error("this report needs a working Gurobi license.")

    bases = pd.read_csv(args.bases).head(args.n_bases)
    water_points = pd.read_csv(args.water).head(args.n_water)
    base_names = dict(zip(bases["site_id"], bases["name"]))
    water_names = dict(zip(water_points["site_id"], water_points["name"]))

    scenarios = read_scenarios_json(args.scenarios)[: args.max_scenarios]
    for scenario in scenarios:
        scenario.probability = 1.0 / len(scenarios)
    source_dates = {s.scenario_id: s.source_date for s in scenarios}
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

    print("Solving the base case (direct Gurobi)...")
    timed = solve_with_time_limit(params, pre, time_limit_s=args.gurobi_time_limit)
    sol = timed.solution
    print(f"status={sol.status} objective={sol.objective_value} gap={timed.mip_gap} "
          f"timed_out={timed.timed_out} time={timed.elapsed_s:.1f}s")

    open_bases = [i for i, o in sol.base_open.items() if o]
    fleet = {i_m[0]: n for i_m, n in sol.n_aircraft.items() if n > 0}
    print("\n=== First stage ===")
    for i in open_bases:
        print(f"  base {i} ({base_names.get(i, '?')}), aircraft: {fleet.get(i, 0)}")

    fire_by_id = {
        (sc.scenario_id, f.fire_id): f for sc in model_scenarios for f in sc.fires
    }
    used_water: dict[str, int] = {}
    days = []
    for sc in model_scenarios:
        s = sc.scenario_id
        served = []
        for (s2, i, f_id, m), x in sol.dispatch.items():
            if s2 == s and x > 0:
                k_used = next(
                    (k for (s3, f3, k) in sol.refill_at
                     if s3 == s and f3 == f_id and sol.refill_at[(s3, f3, k)]),
                    None,
                )
                fire = fire_by_id[(s, f_id)]
                req = pre.requirement[(s, f_id)]
                delivered = sol.delivered.get((s, f_id), 0.0)
                contained = not sol.escape.get((s, f_id), True)
                if k_used:
                    used_water[k_used] = used_water.get(k_used, 0) + 1
                # bases that tie operationally: same-or-more drops at k_used
                ties = []
                if k_used and contained:
                    drops_chosen = pre.drops[(s, i, f_id, k_used, m)]
                    ties = sorted(
                        j for j in params.bases
                        if pre.drops[(s, j, f_id, k_used, m)] >= drops_chosen and j != i
                    )
                served.append(
                    {
                        "fire": f_id,
                        "from_base": i,
                        "aircraft": x,
                        "water_point": k_used,
                        "water_name": water_names.get(k_used),
                        "delivered_l": round(delivered, 1),
                        "requirement_l": round(req, 1),
                        "contained": contained,
                        "population_at_stake": round(fire.value_at_risk, 1),
                        "bases_tying_at_this_water_point": ties,
                    }
                )
        n_esc = sum(1 for (s2, _f), e in sol.escape.items() if s2 == s and e)
        days.append(
            {
                "scenario": s,
                "source_date": source_dates.get(s),
                "n_fires": len(sc.fires),
                "n_escaped": n_esc,
                "loss": round(sol.loss.get(s, 0.0), 2),
                "served": served,
            }
        )
        print(f"\n  day {s} ({source_dates.get(s)}): {len(sc.fires)} fires, {n_esc} escape, loss {sol.loss.get(s, 0.0):.1f}")
        for entry in served:
            tag = "CONTAINED" if entry["contained"] else "not contained"
            print(
                f"    fire {entry['fire']}: {entry['aircraft']} acft from {entry['from_base']} "
                f"({base_names.get(entry['from_base'], '?')}), refill at {entry['water_point']} "
                f"({entry['water_name']}), {entry['delivered_l']:.0f} L vs req {entry['requirement_l']:.0f} L, "
                f"{tag}, population {entry['population_at_stake']}"
            )

    print("\n=== Water points actually USED (vs merely opened) ===")
    n_open_water = sum(1 for o in sol.water_open.values() if o)
    for k, times in sorted(used_water.items(), key=lambda kv: -kv[1]):
        print(f"  {k} ({water_names.get(k)}): used on {times} day(s)")
    print(f"  ({n_open_water} water points opened in this solution; only the {len(used_water)} above "
          "are used; the rest are alternate-optimal slack, see the Section 6 preamble disclosure)")

    payload = {
        "status": sol.status,
        "objective": sol.objective_value,
        "mip_gap": timed.mip_gap,
        "timed_out": timed.timed_out,
        "solve_time_s": timed.elapsed_s,
        "open_bases": [
            {"site_id": i, "name": base_names.get(i), "aircraft": fleet.get(i, 0)} for i in open_bases
        ],
        "n_water_opened": n_open_water,
        "water_used": [
            {"site_id": k, "name": water_names.get(k), "days_used": t} for k, t in sorted(used_water.items())
        ],
        "days": days,
    }
    with open(args.output_json, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)
    print(f"\nWrote {args.output_json}")


if __name__ == "__main__":
    main()
