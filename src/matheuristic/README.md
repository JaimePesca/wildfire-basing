# src/matheuristic

Fix-and-optimize (Helber and Sahling 2010, International Journal of
Production Economics 123(2):247-256) with LNS (Shaw 1998, CP98, LNCS 1520,
pp. 417-431) over first-stage variables (CLAUDE.md section 3, FROZEN
method choice). Neighborhoods are geographic (decided 2026-08-30, CLAUDE.md
section 10): each LNS iteration frees the candidate sites nearest a random
seed site, Shaw's own "relatedness" destroy principle, matching this
paper's own central insight that base-water coupling is a cycle-time/
distance relationship (CLAUDE.md section 2).

## Why this exists

CLAUDE.md section 10/src/model/README.md's "First real-data solve" note
found the real candidate water point set (5,449 sites) intractable for an
exact, all-at-once MILP solve: the McCormick linearization adds
`|I|*|K|` `serve[i,f,k,m,s]` auxiliary variables per fire per scenario,
over 650,000 per fire per scenario at the real 120-base scale. This
package is the actual answer: each LNS iteration solves a REDUCED
sub-MILP containing only the current neighborhood's sites plus whatever
sites are already open in the incumbent, dropping every closed,
out-of-neighborhood site entirely. This is exact, not an approximation
(see `fix_and_optimize.py`'s module docstring for the full argument: a
dropped site is mathematically identical to one with `base_open`/
`water_open` forced to 0), so every accepted iteration is a genuine,
verified improvement to the real first-stage problem.

## Modules

| Module | What |
|---|---|
| `neighborhoods.py` | `pick_neighborhood`: the LNS destroy operator. Picks a random seed site (base or water point) from the real candidate coordinates, returns the n nearest bases and n nearest water points to it. |
| `fix_and_optimize.py` | `run_fix_and_optimize`: the full loop. `FirstStageSolution` (the only state carried between iterations), `build_reduced_params` (constructs each iteration's reduced `ModelParams`), `fix_non_neighborhood_variables` (locks non-neighborhood sites to their incumbent values via PuLP variable bounds), `IterationRecord`/`FixAndOptimizeResult` (full iteration history for diagnostics). |

## Usage

```python
from src.matheuristic.fix_and_optimize import run_fix_and_optimize
import pulp

result = run_fix_and_optimize(
    params,            # a schema.ModelParams, the FULL real candidate set
    bases_df,          # site_id/x_utm/y_utm, e.g. data/processed/candidate_bases.csv
    water_points_df,   # site_id/x_utm/y_utm, e.g. data/processed/candidate_water.csv
    n_bases_per_neighborhood=5,
    n_water_per_neighborhood=10,
    max_iterations=200,
    no_improve_limit=50,
    seed=0,
    solver_factory=lambda: pulp.GUROBI(msg=False),  # a FRESH instance per call, see hazard note below
)
print(result.objective_value, result.incumbent.base_open)
```

`solver_factory` must be a zero-argument callable, not a solver instance.

## GUROBI() reuse hazard (read before changing solver_factory)

CLAUDE.md section 10 and `src/model/milp.py`'s `solve()` docstring: a
single `pulp.GUROBI()` instance accumulates every `LpProblem` solved with
it into one underlying `gurobipy.Model`, silently corrupting every solve
after the first. An LNS run calls the solver once per iteration, often
hundreds of times, so this is not a hypothetical risk here, it is the
exact scenario the warning was written for. `run_fix_and_optimize` calls
`solver_factory()` fresh inside the loop for this reason; never pass an
already-constructed `pulp.GUROBI()` object as if it were the factory
itself (`solver_factory=pulp.GUROBI(msg=False)` is wrong, it must be
`solver_factory=lambda: pulp.GUROBI(msg=False)`).

## Deliberately unchanged, and one deliberate scope limit

Every constraint, the objective, and the full scenario/fire set are
unchanged from CLAUDE.md section 5.2/`milp.py`. LNS here only ever
restricts which first-stage SITES a sub-MILP may reconsider; it does not
subset scenarios (CLAUDE.md section 3 says "LNS ... over first-stage
variables", not over the recourse problem). Every sub-MILP therefore still
solves the complete scenario set. If the real scenario/fire counts turn
out to be large enough that this becomes its own performance bottleneck,
that is a separate, not-yet-addressed concern, distinct from the
water-point tractability problem this package solves.

## Testing

`tests/test_matheuristic_neighborhoods.py` and
`tests/test_matheuristic_fix_and_optimize.py` use small, hand-verifiable
synthetic instances, never real Colombian data. The main correctness
checks compare `run_fix_and_optimize`'s result against `milp.solve_model`
on the same full instance directly: since the reduced-sub-MILP trick is
exact, the matheuristic must find the identical optimal objective value,
both when one neighborhood already covers every candidate site (a
single-iteration, seed-independent check) and when neighborhoods are
strictly smaller than the full candidate set (requiring the search to
actually explore across iterations to find the one base that can help,
verified robust across 10+ random seeds during development, not just the
one seed committed in the test). Also parametrized across CBC and Gurobi,
same pattern as `tests/test_model_milp.py`.

## Real-scale wiring: CONFIRMED WORKING 2026-09-04

`run_real_instance.py` runs `run_fix_and_optimize` against the full,
untruncated real candidate catalog (120 bases, 5,449 water points,
`data/processed/candidate_bases.csv`/`candidate_water.csv`) and a real
bootstrap scenario draw (`data/processed/scenarios_2024full.json`), the
real-data counterpart to `src/model/run_instance.py` (which truncates the
candidate sets to prove the plain MILP's plumbing, since the full water set
is intractable for it, see that module's own docstring).

Two runs, same illustrative smoke-test parameters as
`src/model/README.md`'s own `run_instance.py` example (`--ros-scale 1.0
--initial-fire-area 5.0 --liters-per-sqm 3.0 --cost-base 1e9 --cost-water
5e7 --budget 1e11 --cvar-alpha 0.95 --mean-risk-weight 0.5 --window 8.0`):

1. `--max-scenarios 2` (15 fires), `n_bases_per_neighborhood=5`,
   `n_water_per_neighborhood=10`, `max_iterations=20`,
   `no_improve_limit=10`: converged in **2.5 s over 11 iterations** with
   Gurobi, **36.2 s over 11 iterations** with CBC. Both found objective
   **73.847...**, matching (to displayed precision) the value
   `run_instance.py`'s own real-data example already established by solving
   the full MILP directly on a 3-base/3-water-point truncation of the same
   two scenarios. This is a genuine cross-check, not a coincidence of
   rounding: same scenarios, same illustrative parameters, one true optimum
   value, found two different ways (direct truncated MILP vs. the
   untruncated real catalog run through LNS). CBC and Gurobi again open
   different specific sites for the identical objective value, the same
   alternate-optima pattern already documented in `tests/test_model_milp.py`
   and `src/model/README.md`.
2. `--max-scenarios 10` (81 fires), `n_bases_per_neighborhood=8`,
   `n_water_per_neighborhood=20`, `max_iterations=60`,
   `no_improve_limit=25`, Gurobi: **946.8 s (about 15.8 min) over 60
   iterations**, 5 accepted improvements, 0 infeasible sub-solves, final
   objective 10752.68. About 15.8 s/iteration average at this
   fire/neighborhood size, the first real runtime data point for tuning
   neighborhood size and iteration budgets against real experiment
   scale (not yet tuned beyond this one data point).

**Disclosed limitation found during this run, not a correctness bug**: the
10-scenario run's final incumbent had about 100 water points open. This
package's acceptance rule (`run_fix_and_optimize`) only replaces the
incumbent on a STRICT objective improvement (`objective_value <
incumbent_objective - 1e-9`). Since `cost_water[k]` enters only the budget
constraint, not the objective (CLAUDE.md section 5.2), a sub-MILP solve
that closes a now-redundant water point produces the exact same objective
value as keeping it open, a tie, which this acceptance rule never takes.
Consequently, once a site is opened it is never closed again unless a later
neighborhood's reduced sub-MILP finds a STRICTLY better configuration that
happens to exclude it. The objective value itself is unaffected (already
cross-checked exact above), but the specific site COUNT/portfolio the
matheuristic reports is an upper bound, not necessarily the most parsimonious
one, which matters if the paper wants to report "how many water points are
actually needed" as a policy result, not just the objective. This is a
direct, expected consequence of the standard strict-improvement
fix-and-optimize acceptance rule (Helber and Sahling 2010 do not include a
tie-breaking consolidation pass either), not a departure from the cited
method, but is disclosed here since it was not obvious before running this
at real scale. Whether to add a periodic tie-accepting "shrink" pass is a
methodological choice for the paper, not decided here.

## Random destroy operator: ADDED 2026-09-04, fixes a real, confirmed local optimum

Running `experiment2_matheuristic_vs_gurobi.py` (see
`src/experiments/README.md`) at a 20-base/50-water-point instance found the
pure-geographic operator can get permanently stuck strictly short of the
true optimum: the true optimum needed base `aero_SKEF`, 174 km from
`aero_SQUV`, the base the matheuristic had already opened; since only one
Firehawk was ever affordable under the test budget, reaching the true
optimum required CLOSING `aero_SQUV` and OPENING `aero_SKEF` in the same
LNS iteration, a trade `pick_neighborhood`'s single geographic seed can
never propose when the two sites are this far apart (confirmed directly:
200 iterations, 101 run, zero additional improvement past the first).

Fix: `neighborhoods.pick_neighborhood` gained a `random_destroy_prob`
parameter (default 0.0, preserving the original behavior for every
existing caller/test), passed through `run_fix_and_optimize`. With that
probability, an iteration frees `n_bases`/`n_water` sites drawn uniformly
at random from the whole candidate set instead of the geographic operator,
standard ALNS practice for exactly this failure mode (Ropke and Pisinger
2006, "An Adaptive Large Neighborhood Search Heuristic for the Pickup and
Delivery Problem with Time Windows," Transportation Science 40(4):455-472,
DOI 10.1287/trsc.1050.0135, verified 2026-09-04 against the publisher page:
existence, year, venue and page numbers all confirmed).

**Correctness, proven**: `tests/test_matheuristic_fix_and_optimize.py`'s
`_far_bases_trap_case` reproduces the exact failure structure (two base
clusters placed far apart in coordinate space, only one aircraft
affordable) in a small, hand-verified synthetic instance.
`test_pure_geographic_operator_gets_permanently_stuck_short_of_the_true_optimum`
confirms `random_destroy_prob=0.0` never escapes the trap even over 100
iterations with no early stop; `test_random_destroy_prob_escapes_the_geographic_local_optimum`
(parametrized over 5 seeds, all passing) confirms `random_destroy_prob=0.4`
reliably finds the true optimum within 300 iterations every time.

**Real scale: fix confirmed correct, NOT yet confirmed to reliably escape
within a practical iteration budget.** Re-running the exact 20-base/50-water
case that surfaced the bug, with `random_destroy_prob=0.3` and up to 100
iterations, still did not find the improvement. Direct inspection of the
iteration history showed the random operator DID draw `aero_SQUV` and
`aero_SKEF` into the same free set twice (iterations 48 and 69), but the
resulting reduced sub-MILP still reported no improvement in both cases,
most likely because the specific water point(s) `aero_SKEF` needs were not
part of the incumbent's open set at that point in the run (the incumbent's
open-water portfolio evolves over iterations; the water point later
confirmed reachable from `aero_SKEF`, `osm_way_41758428`, may not have been
open yet at iteration 48/69). This was not chased down to full certainty on
the real ad hoc run (a one-off script, not a committed test), but the
mechanism's correctness is independently proven above on the isolated
synthetic case where confounds like this are controlled for. Practical
implication: at real scale, escaping a specific local optimum may need
more iterations, a larger `n_water_per_neighborhood`, or a higher
`random_destroy_prob`, than the illustrative defaults
(`run_real_instance.py`/`experiment2_matheuristic_vs_gurobi.py` both
default to `random_destroy_prob=0.3`); none of this has been systematically
tuned.

## Not yet done

- Comparing this against pure Gurobi on small instances (CLAUDE.md section
  9 experiment 2): CLI now exists,
  `src/experiments/experiment2_matheuristic_vs_gurobi.py` (see
  `src/experiments/README.md`), but no systematic sweep across instance
  sizes large enough to show pure Gurobi's runtime actually blow up has
  been run yet, only small smoke-test sizes.
- Tuning: a first systematic sweep RAN 2026-09-09/10
  (src/experiments/tune_matheuristic.py, results/tune_matheuristic.csv,
  24 configs x 5 seeds against the known direct optimum at the DECIDED
  base-case parameters): hit_rate 1.00 everywhere including
  random_destroy_prob=0.0, optimum reached in the first accepted
  iteration in every run, so at the base case the instance does not
  discriminate quality and the sweep's information is runtime scaling
  (n_water_per_neighborhood dominates; the random operator adds ~75%
  overhead). Defaults kept on that evidence: n_bases=5, n_water=10,
  random_destroy_prob=0.3 (the overhead is the insurance premium against
  the proven stuck-forever failure mode above, which lives at parameter
  regimes this easy base case does not probe). Still open: a
  DISCRIMINATING reliability sweep at the trap regime or larger
  instances.
- Deciding whether a tie-accepting consolidation/shrink pass is worth adding
  given the site-accumulation behavior disclosed just above.
