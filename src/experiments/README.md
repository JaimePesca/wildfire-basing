# src/experiments

CLAUDE.md section 9's six experiments. Only experiment 2 has a script so
far; the rest are not yet implemented.

## experiment2_matheuristic_vs_gurobi.py

Compares pure Gurobi (direct, full MILP, `src/model/milp.py`) against the
fix-and-optimize/LNS matheuristic (`src/matheuristic/`) on the SAME
instance, across a sweep of candidate-catalog sizes drawn from the real
bases/water/scenario data. See the module's own docstring for the full
design (why build_model()/solve() are called directly instead of
solve_model(), which discards the objective on any non-Optimal status; how
a Gurobi time-limited run's best-found incumbent is still reported).

Usage (`--illustrative-smoke-test` and the four user-decision parameters
are required, same as `src/model/run_instance.py`):

```bash
python -m src.experiments.experiment2_matheuristic_vs_gurobi \
    --instance-sizes 5:10 10:25 20:50 \
    --max-scenarios 2 \
    --ros-scale 1.0 --initial-fire-area 5.0 --liters-per-sqm 3.0 \
    --cost-base 1000000000 --cost-water 50000000 \
    --budget 100000000000 --cvar-alpha 0.95 --mean-risk-weight 0.5 --window 8.0 \
    --illustrative-smoke-test
```

Requires a working Gurobi license (CLAUDE.md section 3 names "pure Gurobi"
as the benchmark itself, not an interchangeable CBC substitute here).

### quality_gap_abs vs quality_gap_pct: a real bug already found and fixed

The output CSV reports both an absolute and a percentage quality gap
(matheuristic objective minus pure-Gurobi objective). An earlier version of
this script reported ONLY a percentage, computed as `None` whenever the
Gurobi objective was exactly 0.0 (division by zero), which silently hid a
real, large quality gap in the very first smoke-test run (see below): a
`None` in that column looks like "not applicable," not "a real gap that
happens to break the percentage formula." Always read `quality_gap_abs`
first; `quality_gap_pct` is `None` precisely when the percentage is
undefined, not when the gap is zero.

### The 20-base/50-water finding that led to neighborhoods.py's random_destroy_prob

The very first real-data run of this script (5:10, 10:25, 20:50 bases:water,
2 scenarios, illustrative smoke-test parameters) found that at 20:50, pure
Gurobi discovered a strictly better solution (objective 0.0, opening base
`aero_SKEF`) than the matheuristic ever found (stuck at 73.847, base
`aero_SQUV`), even after raising the matheuristic's iteration budget to 200.
Root cause (fully diagnosed, see `src/matheuristic/README.md`'s own account):
`aero_SKEF` and `aero_SQUV` are 174 km apart, only one aircraft was ever
affordable under the test budget, and the pure-geographic LNS destroy
operator can never place two sites that far apart in the same free set, so
the beneficial "close one, open the other" trade was never even proposed.
Fixed by adding `neighborhoods.pick_neighborhood`'s `random_destroy_prob`
parameter (ALNS-standard, Ropke and Pisinger 2006, verified), which this
script now exposes as `--random-destroy-prob` (default 0.3). The fix is
proven correct on an isolated synthetic case
(`tests/test_matheuristic_fix_and_optimize.py`), but was NOT yet confirmed
to reliably re-solve this exact real 20:50 case within a practical
iteration budget; treat any single real run's quality gap as informative,
not as evidence the matheuristic is broken or that random_destroy_prob=0.3
is sufficient at every scale, until a real tuning sweep is done.

## Not yet done

- Experiments 1, 3, 4, 5, 6 (CLAUDE.md section 9) have no script yet.
  Experiment 1's two solve paths already exist and are cross-validated
  (`src/model/bilinear.py`, `tests/test_model_bilinear.py`), but no
  comparison/reporting script wraps them the way this file wraps
  experiment 2.
- A systematic instance-size sweep large enough to show pure Gurobi's
  runtime actually blow up (CLAUDE.md's own framing of experiment 2's
  point) has not been run; only small smoke-test sizes so far.
- Tuning `--random-destroy-prob`/`--n-bases-per-neighborhood`/
  `--n-water-per-neighborhood`/`--max-iterations` against real escape
  reliability, not just runtime.
