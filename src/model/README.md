# src/model

The big-M linearized MILP from CLAUDE.md section 5.2 (FROZEN, derived
2026-08-18). See that section for the full mathematical derivation this
package implements; every constraint in `milp.py` is labeled with its
section 5.2 number so it can be checked directly against the document.

## What is implemented

| Module | What |
|---|---|
| `schema.py` | Input dataclasses (`ModelParams`, `Scenario`, `Fire`), field names matching CLAUDE.md section 4's code identifiers exactly. |
| `precompute.py` | The section 5.2 precomputation: `cycle_time`, `drops` (with the `max(0, ...)` clip), `liters`, `requirement`, `Mbig`. |
| `milp.py` | The linearized MILP itself, built with [PuLP](https://coin-or.github.io/pulp/) and solved on its bundled CBC solver by default. `solve_model(params, pre)` builds, solves, and extracts a `SolveResult` in one call. |
| `travel_times.py` | Computes `t_base_fire`/`t_fire_water` from real projected coordinates (the `x_utm`/`y_utm` columns already in `data/processed/candidate_bases.csv` and `candidate_water.csv`), and assembles a full `ModelParams` from them plus a caller-supplied fires list. |
| `aircraft.py` | Real, sourced `cost_aircraft`/`tank`/`speed` for the single-aircraft-type scope: Colombia's own Sikorsky S-70i FIREHAWK (FAC/UNGRD acquisition), CONFIRMED 2026-08-30, see its module docstring and CLAUDE.md section 4/8/10 for the full citation chain and the units convention (meters, hours) it made explicit. |
| `costs.py` | `cost_base[i]`/`cost_water[k]`: no Colombia-specific source exists (a real web search was done, see the module docstring), DECIDED 2026-08-30 to treat both as swept sensitivity parameters, uniform across sites, same honesty pattern as A0/c/ros_scale. |
| `run_instance.py` | CLI that wires every real-data stage together (candidate sites, a bootstrap scenario draw, the aircraft/cost modules above) into one `ModelParams` and solves it. CONFIRMED WORKING 2026-08-30 end to end on real data; see "First real-data solve" below for the two real bugs this run surfaced and fixed. |
| `bilinear.py` | The literal bilinear/quadratic formulation (experiment 1's other half), built directly against `gurobipy`. CONFIRMED WORKING 2026-08-30, see "bilinear.py" below. |

Run the tests: `pytest tests/test_model_*.py`. They use small, hand-verified
synthetic instances (documented inline with the hand calculation), never
real Colombian data.

## Why PuLP, not gurobipy, for `milp.py`

CLAUDE.md section 3 names Gurobi as the benchmark solver ("pure Gurobi on
small instances"). `milp.py` is written against PuLP so the linearized
MILP does not hard-depend on a Gurobi license: `build_model()` returns a
plain `pulp.LpProblem`; `solve()` takes an optional `solver` argument,
defaulting to `pulp.PULP_CBC_CMD()`.

Gurobi (academic license) CONFIRMED WORKING 2026-08-30: pass
`solver=pulp.GUROBI(msg=False)` (or `pulp.GUROBI_CMD()`), no change to
`build_model` or the constraint-building code is needed. All of
`tests/test_model_milp.py` is parametrized to run against both CBC and
Gurobi automatically whenever a license is available.

**GUROBI() reuse hazard, found during this verification**: a single
`pulp.GUROBI()` instance accumulates every `LpProblem` ever solved with it
into one underlying `gurobipy.Model`, silently corrupting every solve
after the first. Always construct a fresh `pulp.GUROBI()` per solve, never
share one across a loop; see `solve()`'s docstring and
`tests/test_model_milp.py`'s module docstring for the confirmed
reproduction and why this will matter for experiment 6's sweeps and the
matheuristic's per-iteration sub-MILP solves.

## `bilinear.py` (experiment 1): CONFIRMED WORKING 2026-08-30

CLAUDE.md section 9 experiment 1 compares this linearized MILP against the
literal bilinear formulation (`delivered[f,s]` as the direct product
`dispatch * refill_at * liters`, no `serve` auxiliary, no big-M). PuLP and
its bundled CBC have no native quadratic/bilinear support, so `bilinear.py`
is built directly against `gurobipy`, not PuLP: `dispatch * refill_at` is a
genuine (possibly indefinite) bilinear term, requiring Gurobi's
`NonConvex=2` parameter (set inside `build_bilinear_model`). Every other
constraint (1-5, 7, 8, 9) is identical to `milp.py`, labeled with the same
section 5.2 numbers; only constraint 6 differs.

`build_bilinear_model`/`solve`/`solve_bilinear_model`/`BilinearSolveResult`
deliberately mirror `milp.py`'s `build_model`/`solve`/`solve_model`/
`SolveResult` shape, so experiment 1's actual comparison code can call both
on the same `(params, pre)` and diff the results directly.
`tests/test_model_bilinear.py` checks the two formulations agree, not just
that each is individually correct: `test_bilinear_objective_matches_
linearized_milp_exactly` asserts identical optimal objective values on the
same hand-verified synthetic instances already used by
`tests/test_model_milp.py`.

`bilinear.py`'s own `gp.Model` is always freshly constructed inside
`build_bilinear_model`, so the `pulp.GUROBI()` reuse hazard above does not
apply to it directly; still construct a fresh `(params, pre)` call per
solve if used in a loop, never mutate and re-solve the same `gp.Model`.

## First real-data solve: CONFIRMED WORKING 2026-08-30

`run_instance.py` wires every real-data stage together and solves. Example
(a small tractability subsample, see below, `--illustrative-smoke-test`
required, `budget`/`cvar_alpha`/`mean_risk_weight`/`window` are still the
user's own real decision for any actual experiment, CLAUDE.md section
4/10):

```bash
python -m src.model.run_instance \
    --max-bases 3 --max-water-points 3 --max-scenarios 2 \
    --ros-scale 1.0 --initial-fire-area 5.0 --liters-per-sqm 3.0 \
    --cost-base 1000000000 --cost-water 50000000 \
    --budget 100000000000 --cvar-alpha 0.95 --mean-risk-weight 0.5 --window 8.0 \
    --illustrative-smoke-test --solver gurobi
```

Verified on 100% real data (real 2024 events, a real bootstrap scenario
draw, real land cover/slope/wind/population, the real Firehawk aircraft):
`Optimal`, objective 73.847, cross-checked identical (to displayed
precision) between CBC and Gurobi (they open a different specific base/
water-point combination, an alternate-optima situation like the CVaR test
in `tests/test_model_milp.py`, not a bug).

Getting here surfaced two real, previously-latent bugs, both now fixed:

1. **Scenario probabilities must sum to 1.** Slicing a subset of scenarios
   out of a larger bootstrap draw (`read_scenarios_json(...)[:n]`) without
   renormalizing leaves each scenario at its original probability (e.g.
   1/200): the CVaR objective's convexity depends on `sum_s p_s = 1`, and
   violating it does not just skew results, it makes the MILP genuinely
   `Unbounded` (confirmed via Gurobi's own unbounded-ray diagnostics: `
   var_level` and `cvar_excess` can move together at no net objective
   cost once the probabilities don't sum to 1). `milp.build_model` now
   validates this and raises a clear `ValueError` instead
   (`_validate_scenario_probabilities`); `run_instance.py` renormalizes
   after `--max-scenarios`. This matters directly for the matheuristic:
   any LNS neighborhood or reduced-scenario subproblem must renormalize
   too.
2. **The real candidate water point set (5,449 sites, OSM+CAR combined) is
   not tractable for the exact McCormick linearization as written.**
   `serve[i,f,k,m,s]` adds `|I|*|K|` auxiliary variables per (fire,
   scenario) pair; at the real scale (120 bases) that is over 650,000
   per fire per scenario. `--max-bases`/`--max-water-points` truncate for
   testing the pipeline plumbing only, disclosed prominently in
   `run_instance.py`'s own docstring; they are not a proposed real
   experimental design. Reducing the real candidate water set to a
   tractable size (clustering nearby bodies, or restricting to named/
   significant ones) is a separate, not-yet-solved open item, needed
   before any real (non-smoke-test) experiment can use the full water
   layer.

`cost_base[i]`/`cost_water[k]` are DECIDED (2026-08-30, CLAUDE.md section
3/8/10): no Colombia-specific source exists, so they are swept sensitivity
parameters, uniform across sites, `costs.py` (`uniform_cost` plus the
documented `COST_BASE_RANGE_COP`/`COST_WATER_RANGE_COP`). Do not pass a
fabricated `budget`/`cvar_alpha`/`mean_risk_weight`/`window` to
`assemble_model_params`/`run_instance.py` outside of an explicitly-flagged
smoke test; use the synthetic fixtures in the tests, or wait for the real
decision, otherwise.
