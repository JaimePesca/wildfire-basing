# CLAUDE.md

Repository contract for the paper on joint aerial suppression base and water
refill point location under uncertainty. This file is the single source of truth
for naming conventions and decisions. Code in this repo and the manuscript must
use the same symbols. If a symbol changes here, it changes in both places.

Status legend used throughout: [FROZEN] decided, do not change without updating
this file and the paper; [PROPOSED] working choice awaiting sign-off; [PENDING]
open, not yet decided.

---

## 1. Project

Working title: The Cycle-Constrained Aerial Suppression Base and Water Point
Location Problem.

Target venue: ITOR special issue on Operations Research in Wildfire Management.
Deadline 30 September 2026.

Division of labor:
- Thinking, writing, literature: Claude.ai project (not this repo).
- Code, data pipeline, model, experiments: this repo.

Preferences that apply to everything here:
- Conversation in Spanish, manuscript in English.
- Never use em dashes or en dashes, in prose or in code comments.

---

## 2. Central insight [FROZEN]

Aerial suppression productivity depends on a three-leg cycle, not on base-to-fire
distance alone. The aircraft flies base to fire once (positioning), then repeats
the fire to water refill cycle many times. The base-to-fire leg is paid once; the
fire-to-water leg is paid on every cycle and therefore dominates as the number of
cycles grows. This couples base location and water point location, makes aircraft
productivity endogenous, and raises a budget split question between bases and
water points. A p-median cannot represent this tradeoff.

---

## 3. Methodological decisions [FROZEN]

- Two-stage stochastic program. First stage strategic and pre-season; second
  stage operational per scenario.
- Objective: mean-risk, convex combination of expectation and CVaR
  (Rockafellar-Uryasev).
- Cycle productivity (drops[i,f,k,m], see section 4) is precomputed as a
  constant parameter table, not a decision-dependent nonlinear term: DECIDED
  2026-08-18, every input to it (window, t_base_fire, cycle_time) is a
  parameter under the current single-aircraft-type, discrete-candidate-site
  scope, so no SOS2 or other piecewise linearization is needed for it (see
  section 10 history for the reasoning; a previous draft of this section
  said "MINLP reformulated to MILP via SOS2 piecewise linearization of the
  cycle productivity term", that was superseded by this decision). The
  remaining nonlinearity is a bilinear coupling in constraint block 6
  (dispatch[i,f,m,s] times refill_at[f,k,s], both decision variables,
  multiplying the precomputed constant), reformulated to MILP with a
  standard big-M/McCormick linearization, not SOS2.
- Scenarios via Sample Average Approximation (SAA), reported with optimality gap
  and confidence interval.
- Solution: fix-and-optimize matheuristic (Helber and Sahling 2010, International
  Journal of Production Economics 123(2):247-256, not Fischetti and Lodi 2003,
  which is local branching, a related but distinct technique) with LNS (Shaw
  1998, CP98, LNCS 1520, pp. 417-431) over first-stage variables.
- Benchmarks: pure Gurobi on small instances, and a sequential baseline (bases
  first, water second) as the star comparison.
- Excluded: fuzzy methods. Robust optimization is not a central axis (to avoid
  overlap with the guest editor).

Physical containment logic [FROZEN]: a fire is contained if liters delivered
within the critical window exceed a physical requirement that grows with
arrival time and propagation rate. This avoids dependence on historical
outcome data, which does not exist for Colombia. Functional form DECIDED 2026-08-18: simple exponential area growth,
requirement[f] = c * A0 * exp(ros[f] * t_arrival[f]). Two other candidate
forms (elliptical/perimeter growth per Van Wagner 1969 and the Fried and
Fried containment model; linear/affine approximation) were surveyed and set
aside, not because they are wrong, but because this one fits the notation
table's existing single-scalar ros[f] without new shape parameters; a
fourth (econometric fireline-production-function) was ruled out for
conflicting with the no-historical-data rationale above. Citation caveat,
verified 2026-08-18, do not overclaim: Ramachandran (1986), "Exponential
Model of Fire Growth," Fire Safety Science 1:657-666, is a real, confirmed
source for the exponential area-vs-duration assumption, but it is
structural/building fire science (fires attended by fire brigades), not
wildland fire science; searching specifically for wildland fire growth
literature found Van Wagner's elliptical model as the actual domain-specific
canonical approach, and real wildfire data shows variable growth patterns
(some fires linear, some quadratic), not a clean dominant exponential. This
paper's exponential choice is disclosed as a phenomenological simplification
for tractability, not as a wildfire-validated model; do not cite Ramachandran
(1986) in the manuscript as if it validates the wildland case.

t_arrival[f] is deliberately defined as time from FIRMS detection to the
start of the critical window, exogenous and independent of which base ends
up dispatching (decided 2026-08-18, see section 4 parameters), so
requirement[f] stays a pure per-fire parameter, not requirement[i,f].

Calibration constants A0 and c: DECIDED 2026-08-18, not fixed values, swept
as a sensitivity range in experiment 6 (section 9), consistent with this
section's own no-historical-data rationale above, since Colombia has no
outcome data to calibrate a single point value against. A search for primary
sources found nothing solid enough to fix a single number: the only
wildland-relevant application-rate figures found (1.5 to 4 L/m^2 for
fixed-wing air tankers, over 10 L/m^2 for helicopters) come from an aviation
industry article (aero-space.eu) that itself discloses no academic or
technical citation, not a verified primary source. Illustrative sweep ranges
(section 9 experiment 6 will use these, not treat them as calibrated):
A0 roughly 1 to 30 hectares (anchored on the VIIRS 375 m detection
resolution already used in section 5, a geometric anchor, not a fire-science
value); c roughly 1.5 to 10 L/m^2 (the unverified aviation-industry range
above, chosen for lack of a better source, not because it is confirmed).

Candidate site costs cost_base[i] and cost_water[k]: DECIDED 2026-08-30,
same treatment, same rationale. A real web search (fac.mil.co,
presidencia.gov.co, USDA Forest Service, industry dip-tank suppliers,
CLAUDE.md section 8/10) found no Colombia-specific source, only U.S.
benchmarks for greenfield construction and purpose-built equipment that do
not match this repo's candidate sites, which are already-EXISTING
aerodromes/military bases and water bodies (section 8), not raw land.
Swept as sensitivity ranges in experiment 6 (section 9), src/model/costs.py:
cost_base[i] roughly 300 million to 6,000 million COP per base;
cost_water[k] roughly 15 million to 300 million COP per water point, both
uniform across all candidate sites of that kind (no per-site cost source
exists), see src/model/costs.py's docstring for the full benchmark
derivation and its own disclosed scaling-down judgment call.

---

## 4. Notation [FROZEN, signed off 2026-08-18]

This is the contract. The four open decisions blocking sign-off (functional
form of requirement[f]; whether drops[i,f,k,m] needs SOS2; single vs
multiple water points per fire; the definition of t_arrival[f]) were all
closed on 2026-08-18, see section 10 history. The constraint blocks below
are a sketch/summary; the exact LP/MILP inequalities are in section 5.2
(written 2026-08-18).

### Sets

| Symbol | Code identifier | Meaning |
|---|---|---|
| I | `bases` | candidate aerial base or heliport sites, index i |
| K | `water_points` | candidate water refill points, index k |
| M | `aircraft_types` | aircraft types, index m (start with one type) |
| S | `scenarios` | SAA scenario sample, index s, probability p_s |
| F_s | `fires[s]` | fires (ignition events) in scenario s, index f |

Units convention DECIDED 2026-08-30 (previously undocumented and
ambiguous, made explicit once src/model/aircraft.py became the first place
a real, externally-sourced speed value entered the codebase): distance in
meters (matching the EPSG:9377 projected CRS already used throughout this
repo, section 5), time in hours throughout (window, ops_time, cycle_time,
t_base_fire, t_fire_water, t_arrival). speed[m] is therefore meters per
hour, not meters per second or km/h. Budget and every cost_* parameter are
in Colombian pesos (COP), matching the currency of the real sourced
aircraft cost below; do not silently mix in USD figures without an
explicit, disclosed conversion.

### Parameters

| Symbol | Code identifier | Meaning |
|---|---|---|
| B | `budget` | total first-stage budget, COP |
| c_base_i | `cost_base[i]` | fixed cost to open base i, COP; no per-site source exists, swept sensitivity parameter (uniform across bases) DECIDED 2026-08-30, see section 3/8/10 and src/model/costs.py |
| c_air_m | `cost_aircraft[m]` | cost to acquire one aircraft of type m, COP; real value sourced 2026-08-30, see section 8/10 |
| c_water_k | `cost_water[k]` | fixed cost to enable water point k, COP; no per-site source exists, swept sensitivity parameter (uniform across water points) DECIDED 2026-08-30, see section 3/8/10 and src/model/costs.py |
| Q_m | `tank[m]` | water tank capacity of type m (liters per drop); real value sourced 2026-08-30, see section 8/10 |
| speed_m | `speed[m]` | flight speed of type m, meters per hour; real value sourced 2026-08-30, see section 8/10 |
| W | `window` | critical suppression window length |
| delta | `ops_time` | per-cycle operational overhead (fill plus drop) |
| tau_bf_if | `t_base_fire[i,f]` | one-way base-to-fire travel time |
| tau_fw_fk | `t_fire_water[f,k]` | one-way fire-to-water travel time |
| D_f | `value_at_risk[f]` | value or damage exposed at fire f |
| rho_f | `ros[f]` | propagation rate for fire f; DECIDED 2026-08-21 this is itself formula-derived (land cover class times slope times wind), not a raw input, see section 5.3 and ros_scale below |
| t_arr_f | `t_arrival[f]` | time from FIRMS detection to start of the critical window (exogenous, independent of dispatch base; decided 2026-08-18, see requirement[f] below) |
| A0 | `initial_fire_area` | global constant, initial fire area at detection for the requirement[f] exponential; not fixed, swept over roughly 1-30 ha in the section 9 experiment 6 sensitivity sweep, see section 3 |
| c | `liters_per_sqm` | global constant, liters per square meter to control a fire, for requirement[f]; not fixed, swept over roughly 1.5-10 L/m^2 in the section 9 experiment 6 sensitivity sweep, see section 3 |
| -- | `ros_scale` | global constant, overall magnitude of ros[f]; not fixed, third parameter swept in the section 9 experiment 6 sensitivity sweep, see section 5.3 |
| alpha | `cvar_alpha` | CVaR confidence level (e.g. 0.95) |
| lambda | `mean_risk_weight` | mean-risk weight (0 risk neutral, 1 pure CVaR) |

### Derived quantities

| Symbol | Code identifier | Meaning |
|---|---|---|
| cyc_fkm | `cycle_time[f,k,m]` | 2 * t_fire_water[f,k] + ops_time |
| d_ifkm | `drops[i,f,k,m]` | floor((window - t_base_fire[i,f]) / cycle_time); DECIDED 2026-08-18: every input here is a parameter, so this is precomputed as a constant table, not linearized via SOS2 (see section 3) |
| L_ifkm | `liters[i,f,k,m]` | drops * tank[m], liters delivered per aircraft; also a precomputed constant, feeds the bilinear coupling in constraint block 6 |
| R_f | `requirement[f]` | c * A0 * exp(ros[f] * t_arrival[f]), physical liters to contain fire f; functional form DECIDED 2026-08-18 (see section 3), A0 and c are swept sensitivity parameters, not fixed constants |

### First-stage variables (here and now)

| Symbol | Code identifier | Meaning |
|---|---|---|
| y_i | `base_open[i]` | 1 if base i is opened |
| w_k | `water_open[k]` | 1 if water point k is enabled |
| n_im | `n_aircraft[i,m]` | number of aircraft of type m at base i (integer) |

### Second-stage variables (recourse, per scenario s)

| Symbol | Code identifier | Meaning |
|---|---|---|
| x_ifms | `dispatch[i,f,m,s]` | aircraft of type m sent from base i to fire f (integer) |
| z_fks | `refill_at[f,k,s]` | 1 if fire f refills at water point k |
| q_fs | `delivered[f,s]` | liters delivered to fire f |
| e_fs | `escape[f,s]` | 1 if fire f is not contained |
| Loss_s | `loss[s]` | scenario loss, sum over f of value_at_risk[f] * escape[f,s] |
| eta | `var_level` | CVaR auxiliary (value at risk level) |
| t_s | `cvar_excess[s]` | CVaR auxiliary, t_s >= loss[s] - var_level, t_s >= 0 |

### Objective [FROZEN structure]

min (1 - lambda) * sum_s p_s * loss[s]
    + lambda * (var_level + (1 / (1 - alpha)) * sum_s p_s * cvar_excess[s])

### Constraint blocks [sketch/summary; exact form in section 5.2, FROZEN]

1. Budget: sum_i cost_base[i] y_i + sum_{i,m} cost_aircraft[m] n_aircraft[i,m]
   + sum_k cost_water[k] w_k <= budget.
2. Aircraft only at open bases: n_aircraft[i,m] <= Mbig * base_open[i].
3. Refill only at enabled points: refill_at[f,k,s] <= water_open[k].
4. One refill point per served fire: sum_k refill_at[f,k,s] <= 1.
5. Dispatch limited by stationed fleet: sum_f dispatch[i,f,m,s] <= n_aircraft[i,m].
6. Delivered liters: delivered[f,s] links dispatch, refill_at and the
   precomputed liters[i,f,k,m] constant table (see section 4 derived
   quantities and section 3). The coupling is bilinear (dispatch times
   refill_at, both decision variables), linearized with a standard big-M
   reformulation, not SOS2, via one new auxiliary variable serve[i,f,k,m,s];
   exact inequalities in section 5.2 (constraints 6a-6e).
7. Containment: delivered[f,s] >= requirement[f] * (1 - escape[f,s]).
8. CVaR linking, nonnegativity, integrality.

Decided 2026-07-23: single aircraft type for this paper (multiple types stays a
possible sensitivity/extension later, not core scope; see section 10 history).

Decided 2026-08-18: a fire is served by exactly one water point for the
whole episode (constraint block 4 as already written, sum_k refill_at[f,k,s]
<= 1 stays a hard equality-or-less-than-one, not relaxed). No open notation
questions remain; see section 10 for the decision history.

---

## 5. Data pipeline (section 5.1) [FROZEN design]

Flow: FIRMS/VIIRS detections, clean and filter, project to metric CRS, cluster
into events with ST-DBSCAN, derive event attributes, sample events into SAA
scenarios.

ST-DBSCAN parameters and rationale:
- Project first to a metric MAGNA-SIRGAS CRS. Do not cluster in degrees.
  CRS decision [FROZEN]: use EPSG:9377, MAGNA-SIRGAS 2018 / Origen-Nacional
  (CTM12), not a classic UTM zone. Colombia straddles UTM zones 17N, 18N and
  19N, so a single UTM zone would either not cover the whole country or would
  distort distances badly near its zone boundary; CTM12 is IGAC's current
  national single-zone metric standard (Resolucion 471 de 2020), designed to
  replace the old six-zone Gauss-Kruger family (e.g. EPSG:3116) for exactly
  this reason, and it keeps the whole country in one flat metric frame for
  ST-DBSCAN. This is the config/parameters.yaml default (crs.epsg: 9377) and
  is intentional, not a divergence from the "project to UTM" phrasing above;
  read that phrasing as "project to a metric MAGNA-SIRGAS CRS", not literally
  as a UTM zone requirement.
- eps_spatial about 750 to 1000 m, anchored on VIIRS 375 m resolution.
- eps_temporal about 1 to 2 days, anchored on satellite revisit and fire
  persistence.
- min_pts low. In an initial-attack context, single-detection fires can be the
  ones that matter. Use the confidence filter, not min_pts, to control false
  positives.

Two documented risks:
- Chaining. Density clustering is transitive, so many close and continuous
  ignitions can merge distinct fires into one blob. Keep eps tight; if needed add
  cuts on temporal gaps or FRP drops. Validate explicitly on the January 2024
  fires: the pipeline should recover them as coherent, separate events.
- Non-unique event definition. eps_spatial and eps_temporal change the number and
  size of events. Sensitivity analysis over both is part of the method, not
  optional, and is what makes the pipeline a replicable contribution.

Caveats to state in the paper: Colombia is cloudy, so VIIRS misses detections and
biases duration and completeness downward; FIRMS detects active fire, not
ignition, so event start lags true ignition. UNGRD municipal reports validate
completeness at municipality level, not cluster geometry.

Canonical method names to cite (verify against sources before citing, per the
citation discipline below): ST-DBSCAN (Birant and Kut); Global Fire Atlas (Andela
and coauthors) as a burned-area alternative.

---

## 5.2 Full mathematical derivation [FROZEN, derived 2026-08-18]

Translates the section 4 decisions into exact LP/MILP constraints. Notation
convention: every fire-indexed quantity is implicitly scoped to its scenario,
wherever section 4 writes a bare f (e.g. requirement[f]), read it as "for f
in fires[s], within scenario s", evaluated with that fire's own attributes;
fires are not assumed to repeat identically across scenarios.

### Precomputation (offline, before the MILP is built)

Every input below is a parameter, not a decision variable (section 4/10:
this is why no SOS2 or other piecewise linearization is needed). For every
i in bases, f in fires[s], k in water_points, m in aircraft_types, s in
scenarios:

- cycle_time[f,k,m] = 2 * t_fire_water[f,k] + ops_time
- drops[i,f,k,m] = max(0, floor((window - t_base_fire[i,f]) / cycle_time[f,k,m]))
  (clipped at 0, made explicit here: a base too far to complete even one
  round trip within the window contributes zero drops, not a negative one;
  the section 4 sketch omitted this clip)
- liters[i,f,k,m] = drops[i,f,k,m] * tank[m]
- requirement[f] = liters_per_sqm * initial_fire_area * exp(ros[f] * t_arrival[f])
  (initial_fire_area and liters_per_sqm are swept per experiment 6, not
  fixed, section 3/9; requirement[f] is still a precomputed constant within
  any single MILP solve, recomputed once per sweep point)
- Mbig[m] = floor(budget / cost_aircraft[m]), a valid, budget-derived upper
  bound on how many aircraft of type m could ever be fielded under the whole
  budget. Used in constraints 2 and 6 below; this is the "Mbig" constraint
  block 2 already named in section 4 without formally defining it.

### Decision variables

As section 4 (base_open[i], water_open[k], n_aircraft[i,m]; per scenario s:
dispatch[i,f,m,s], refill_at[f,k,s], delivered[f,s], escape[f,s], loss[s],
var_level, cvar_excess[s]), plus one new auxiliary needed only for
linearization, not itself a modeling decision:

- serve[i,f,k,m,s] >= 0, continuous: "dispatch of type m from base i to fire
  f, conditional on fire f actually refilling at water point k", the
  linearized form of the bilinear product dispatch[i,f,m,s] * refill_at[f,k,s].

### Constraints

1. Budget:
   sum_i cost_base[i] * base_open[i] + sum_{i,m} cost_aircraft[m] * n_aircraft[i,m]
   + sum_k cost_water[k] * water_open[k] <= budget

2. Aircraft only at open bases, for all i, m:
   n_aircraft[i,m] <= Mbig[m] * base_open[i]

3. Refill only at enabled points, for all f, k, s:
   refill_at[f,k,s] <= water_open[k]

4. One refill point per served fire, for all f, s:
   sum_k refill_at[f,k,s] <= 1

5. Dispatch limited by stationed fleet, for all i, m, s:
   sum_f dispatch[i,f,m,s] <= n_aircraft[i,m]

6. Delivered liters, linearized. The McCormick envelope below is exact, not
   a relaxation, because refill_at is binary and dispatch[i,f,m,s] <= Mbig[m]
   is a valid bound (chained through constraints 2 and 5). For all i, f, k,
   m, s:
   - 6a. serve[i,f,k,m,s] <= dispatch[i,f,m,s]
   - 6b. serve[i,f,k,m,s] <= Mbig[m] * refill_at[f,k,s]
   - 6c. serve[i,f,k,m,s] >= dispatch[i,f,m,s] - Mbig[m] * (1 - refill_at[f,k,s])
   - 6d. serve[i,f,k,m,s] >= 0

   and, for all f, s:
   - 6e. delivered[f,s] = sum_i sum_k sum_m liters[i,f,k,m] * serve[i,f,k,m,s]

7. Containment, for all f, s:
   delivered[f,s] >= requirement[f] * (1 - escape[f,s])

8. Scenario loss and CVaR linking, for all s:
   - 8a. loss[s] = sum_f value_at_risk[f] * escape[f,s]
   - 8b. cvar_excess[s] >= loss[s] - var_level
   - 8c. cvar_excess[s] >= 0

9. Nonnegativity and integrality (restating section 4's variable types):
   base_open[i], water_open[k] in {0,1}; n_aircraft[i,m] in Z+;
   dispatch[i,f,m,s] in Z+; refill_at[f,k,s], escape[f,s] in {0,1};
   delivered[f,s], loss[s], cvar_excess[s], serve[i,f,k,m,s] >= 0;
   var_level free.

### Objective (restated from section 4, unchanged)

min (1 - lambda) * sum_s p_s * loss[s]
    + lambda * (var_level + (1 / (1 - alpha)) * sum_s p_s * cvar_excess[s])

### Size and correctness notes

serve[i,f,k,m,s] adds |I| * |K| * |M| auxiliary continuous variables per
(f,s) pair; since M is a single type for this paper (section 4, decided
2026-07-23), this is |I| * |K| per (f,s), not a combinatorial blow-up across
types. Constraints 6a-6d are an exact reformulation, not an approximation,
the textbook linearization of a binary-times-bounded-integer product,
distinct from the piecewise-linear (approximate for a discontinuous
function) SOS2 route the original section 3 sketch had named and which
section 3/10 history records as superseded.

### What experiment 1 now compares

Since drops and liters are precomputed constants, not decision-dependent,
there is no general continuous nonlinear function to approximate. The
paper's experiment 1 (renamed 2026-08-18, section 9) compares this
big-M-linearized MILP (constraints 6a-6d) against the same model with the
literal bilinear product delivered[f,s] = sum(...) dispatch * refill_at *
liters solved directly as a bilinear/quadratic MIP (e.g. via a solver's
native quadratic support), not against a classical continuous-nonlinear
MINLP.

---

## 5.3 Scenario generation methodology [decided 2026-08-18 in form, numeric details PENDING]

Fills in how the Scenario record's ros_param and value_at_risk fields
(section 6) are actually computed, and what a "scenario" is. Three
decisions, form closed 2026-08-18, exact numeric coefficients still open.

**Scenario definition.** One scenario = one historical calendar day.
fires[s] is the set of Event records (section 6) whose t_start falls on
that day, often empty. Scenarios are built by bootstrap resampling days,
with replacement, from the real historical Event catalog (src/pipeline,
FIRMS/VIIRS); p_s = 1/|S| under plain SAA. Chosen over a full-season
scenario unit for two reasons: (1) it matches the stochastic unit used by
Wei, Bevers and Belval (2015), the nearest comparator already selected in
the gap table (section 10 history); (2) a full-season scenario would break
constraint 5 of section 5.2 as written: sum_f dispatch[i,f,m,s] <=
n_aircraft[i,m] implicitly assumes the whole scenario is one short episode
with no aircraft reuse over time, but a season has fires on different dates
where the same aircraft could legitimately be reused, which section 5.2 has
no temporal logic for. Day-level scenarios keep section 5.2 valid as
written, without reopening a FROZEN section. Caveat, to state in the paper,
not silently: day scenarios assume fleet availability resets each day, no
cross-day dynamics (multi-day fire persistence, crew fatigue, maintenance
downtime) are modeled. UPDATE 2026-08-30: the full calendar year 2024
(2024-01-01 to 2024-12-31, not just January) has now been downloaded and
run through the pipeline, data/processed/events_2024-full.csv, 4689 real
raw VIIRS detections, 2413 events, 366-day pool (282 days with at least one
fire). This is a real improvement over the January-only pool (one full
year's seasonality, not one month), but is still a single year, not
multiple years; a genuinely representative bootstrap pool for interannual
variability (dry-year vs wet-year fire seasons, ENSO effects) still needs
multi-year FIRMS data, not yet acquired, see section 8.

**ros[f] (rate of spread).** Form: a base rate of spread by land cover
class, multiplied by a slope factor and a wind factor. Land cover source
UPDATED 2026-08-21: ESA WorldCover 10m v200 (2021), not IDEAM CORINE as
section 8 originally named. Reason: after four confirmed dead ends trying
to reach a real Cundinamarca-covering IDEAM CORINE product (SINCHI's
version is Amazon-only; a Parques Nacionales Naturales 100k service turned
out to be protected-areas-only, every feature tied to a named park; IDER
Cundinamarca's own CORINE service, the exact source section 8 named, is on
a dead subdomain, DNS does not resolve; a Cauca-department dataset surfaced
on datos.gov.co is the wrong department), ESA WorldCover was adopted the
same way OSM and CAR were adopted for water in section 8: an internationally
hosted alternative once the named Colombian source proved structurally
unreachable. Downloaded and verified 2026-08-21: two tiles (N03W075,
N03W078) from the public AWS Open Data bucket (s3://esa-worldcover/, no
login, no signing required), covering the full Cundinamarca bounding box,
10m resolution, EPSG:4326, 11 land cover classes (fewer than CORINE's ~44,
which also makes the per-class base-rate literature research below more
tractable). data/raw/esa_worldcover_2021_N03W075.tif,
data/raw/esa_worldcover_2021_N03W078.tif.

The slope factor follows the well-established exponential relationship
between rate of spread and slope angle (Rothermel 1972; the exponential
form is also corroborated by Cheney (1981), "Fire Behaviour," in Gill,
Groves and Noble (eds.), Fire and the Australian Biota, pp. 151-175,
Australian Academy of Science, Canberra, confirmed via secondary citation
so far, not read directly; Cheney also cautions the Rothermel slope
relation is unreliable past about 30 degrees, where fuel discontinuities
interrupt spread, note this if a hard cap is implemented). Chosen over full
Rothermel (needs a fuel-model crosswalk from land cover classes to
Rothermel's own parameters, load, packing ratio, particle density,
moisture, with no verified source for Colombia) and over a no-fuel
slope-and-weather-only proxy (would not use a fuel/land-cover source at
all). Slope source: SRTM GL1 30m (not IGAC's own DTM, see section 8),
16 tiles downloaded and verified 2026-08-21, src/scenarios/slope.py
implements Horn's (1981) method for slope magnitude. Wind data source:
NASA POWER (not IDEAM, see section 8), a live point-query API, verified
2026-08-21, src/scenarios/weather.py.

Full formula, DECIDED 2026-08-21:

  ros[f] = ros_scale * class_relative_rate[landcover_class]
           * exp(slope_coef * slope_degrees) * (1 + wind_coef * wind_speed)

Same treatment as A0/c (section 3): no solid primary source exists for
absolute rate-of-spread magnitudes applicable to Colombia, so ros_scale is
a third swept sensitivity parameter (experiment 6, section 9), not a fixed
constant. class_relative_rate is a fixed, ordinally-grounded table (not
independently calibrated in magnitude, only in ranking), based on NWCG's
published Anderson (1982) 13 fire behavior fuel models, which qualitatively
rate spread rate (very low to very high) per fuel type: grass fuels
consistently rate fastest, shrub moderate to fast depending on load, timber
litter slower, non-burnable near zero. Mapped onto ESA WorldCover's 11
classes (illustrative relative values, grassland=1.0 as the fastest
reference): tree cover 0.3, shrubland 0.6, grassland 1.0, cropland 0.8,
built-up 0.0, bare/sparse vegetation 0.05, snow/ice 0.0, permanent water
bodies 0.0, herbaceous wetland 0.4, mangrove 0.3, moss/lichen 0.2. The
original Anderson (1982) report's own numeric reference-condition spread
rates were not obtained (only its qualitative very-low-to-very-high fuel
model ratings, via NWCG/LANDFIRE secondary sources), so these are
disclosed as illustrative, ordinally-motivated values, not literature
numbers, revisit if the primary Anderson (1982) tables are found later.

slope_coef and wind_coef are fixed illustrative defaults (not swept, to
keep the section 9 experiment 6 sweep to the three genuinely uncertain
magnitude constants: A0, c, ros_scale): slope_coef = 0.05 per degree
(exp(0.05*30 deg) is about 4.5x at a 30 degree slope, a plausible-looking
but not independently verified acceleration); wind_coef = 0.1 per m/s
(1 + 0.1*2 m/s = 1.2x at a modest 2 m/s wind, also not independently
verified). A real primary source for Sandberg, Ottmar and Cushon's
simplified wind-exponent reformulation (B=1.2 for all fuel types) was
searched for and not fully confirmed (only found via secondary citation in
Andrews 2013, USDA RMRS; the primary 2007 paper itself was not read), so
the simpler linear wind_coef form here was chosen over adopting that
unconfirmed exponent. Implemented in src/scenarios/ros_formula.py.

**value_at_risk[f].** Population exposed within a buffer around the fire,
from the WorldPop Colombia raster, left unmonetized, a population-exposure
index, not a currency value, cross-checked at the municipal level against
DANE CNPV 2018. Matches established practice: FEMA's Wildfire Risk Index
uses population at risk as one of three official exposure components, and
WorldPop is separately validated against census totals for this exact use.
Chosen over a monetized version (no verified per-capita or per-asset value
source for Colombia, the same problem already hit with the requirement[f]
calibration constants A0/c in section 3) and over a structure-count version
(DANE CNPV dwelling counts, a legitimate close alternative, not chosen, may
be revisited).

DECIDED 2026-08-21: buffer radius fixed at 1 km, a round "immediate
vicinity" choice, not independently sourced (a search for a standard
wildfire evacuation/impact-zone radius found none, real evacuation zones
are threat-assessment-based, not a fixed distance), same honesty standard
as slope_coef/wind_coef. Implemented in src/scenarios/population.py, real
circular buffer (pixel-center distance, not a bounding-box approximation).
WorldPop Colombia 2020 "constrained" raster (BSGM, building-footprint
constrained, about 100m, data.worldpop.org, 27.8 MB, generally more
accurate than the unconstrained ~614 MB national raster for this use, not
merely smaller) downloaded 2026-08-24 to
data/raw/worldpop_col_2020_constrained.tif (the unconstrained raster's
transfer kept timing out on this connection over several attempts,
unrelated to Norton, which was also found intercepting data.worldpop.org
and fixed, but did not by itself resolve the slow transfer). DANE
cross-check: a real
live ArcGIS FeatureServer for Cundinamarca's 116 municipalities (found via
IDER Cundinamarca, services7.arcgis.com). Field CONFIRMED 2026-08-30
against DANE's own primary field dictionary ("Uso del Marco Geoestadistico
Nacional", GIT MGN, Direccion de Geoestadistica, September 2020,
geoportal.dane.gov.co/descargas/mgn-integrado/MGN2018_Integrado_CNPV2018_
InstructivoUso.pdf, Tabla 1, pages 5-6): the field previously used here,
STCTNENCUE, was WRONG, it is documented there as "Cantidad de Encuestas
CNPV 2018" (count of CNPV 2018 surveys conducted), not population. The
correct field is STP27_PERS, documented as "Numero de personas" (number of
persons); a live query against Chipaque confirms it exactly, STP27_PERS
(8633) equals STPERSON_S (8624, persons in private households) plus
STPERSON_L (9, persons in special lodging establishments), the genuine
total-population identity, versus STCTNENCUE's unrelated 7964.
src/scenarios/population.py's DANE_POPULATION_FIELD corrected to
STP27_PERS.

**t_arrival[f].** DECIDED 2026-08-20: t_arrival[f] = min_i t_base_fire[i,f],
the travel time of the closest candidate base to the fire. Needs no new
external data, only the candidate base coordinates and travel-time
computation this repo already has (src/model/travel_times.py). Stays
exogenous to the dispatch decision (it is a minimum over the fixed candidate
set I, not over whichever base ends up actually dispatching), consistent
with the section 4 requirement that requirement[f] remain a pure per-fire
parameter, not requirement[i,f]. Rejected alternative: t_arrival[f] = 0 for
every fire, which would collapse requirement[f] to a constant (c * A0,
independent of ros[f]), defeating the point of making the requirement grow
with both arrival time and propagation rate (section 3).

---

## 6. Output contracts (schemas) [FROZEN]

### Event record (one per detected fire event)

- event_id
- centroid_lat, centroid_lon, and projected x_utm, y_utm
- t_start, t_end, duration_h
- n_detections
- frp_total, frp_peak
- extent (convex hull area or bounding box)
- confidence_mix
- municipality (for UNGRD cross-check)

### Scenario record (SAA input)

- scenario_id
- probability p_s (uniform 1/|S| under plain SAA)
- fires: list, each with fire_id, location, size or intensity proxy,
  ros_param, value_at_risk (how a scenario is defined and how ros_param and
  value_at_risk are computed: section 5.3)

The model in section 4 consumes only the scenario record. The pipeline can be
built now against these two contracts without the optimization model existing yet.

---

## 7. Repository structure [FROZEN]

```
.
|- CLAUDE.md            this file
|- README.md
|- config/             parameters, CRS, eps values, budget, alpha, lambda
|- data/
|   |- raw/            FIRMS downloads, source layers as received
|   |- interim/        cleaned, projected
|   |- processed/      events, scenarios
|- src/
|   |- pipeline/       FIRMS clean, project, ST-DBSCAN, event attributes
|   |- scenarios/      events to SAA scenarios, sensitivity on eps
|   |- model/          bilinear formulation and its big-M linearized MILP
|   |- matheuristic/   fix-and-optimize with LNS
|   |- experiments/    the six experiments, benchmarks
|- results/
```

---

## 8. Colombian data sources [FROZEN, verified against sources]

- Candidate bases: Aerocivil aerodrome index (xlsx with coordinates). Military
  bases from AD 2 state aviation PDFs (CACOM-4 Melgar for Cundinamarca).
- Water points: IGAC national water bodies layer, scale 1:100.000
  (SHP/GPKG/GDB/WFS), intended as primary, complemented by OSM for fine detail
  (San Rafael reservoir, pools). UPDATE 2026-08-18: IGAC delivery is
  structurally blocked, confirmed by two independent verification passes.
  The WFS/geoservicios hosts (mapas.igac.gov.co, mapas2.igac.gov.co,
  geoservicios.igac.gov.co) are unreachable. The geoportal search has no
  standalone "Cuerpos de Agua" product; the only download containing it is
  the national BDVB 1:100.000 bundle (servicio 205, colombiaenmapas.gov.co),
  which has no area or layer narrowing anywhere in its UI or backend
  (confirmed by reading its own request parameters in source) and whose
  download is capped at a hard 119.0 MiB server-side limit, well under the
  bundle's real size, in every format tried (GeoPackage, Shapefile). Until
  IGAC fixes this or a Cundinamarca-scoped export is found, two other
  sources are the working primary in practice (src/pipeline/sites_water.py):
  OSM (load_osm_water_bodies, live-verified, 425 named Cundinamarca water
  bodies pulled 2026-08-18) and CAR, Corporacion Autonoma Regional de
  Cundinamarca (load_car_lagunas, found 2026-08-18: CAR is the actual
  regional water authority, not a national agency, so its own ArcGIS REST
  service, sig.car.gov.co, has no national-bundle size problem; 5024 Laguna
  polygons pulled live, 118 with a real name, does not include San Rafael,
  license not independently confirmed so left None). Combined:
  data/processed/candidate_water.csv, 5449 rows. A servicio 204 (Colombia
  1:500.000, 2014, coarser but likely under the size cap) backup and an
  email to servicioalciudadano@igac.gov.co reporting the cap are identified
  next steps, not yet done, and not blocking since OSM plus CAR already give
  working candidate water points.
- Fire events: FIRMS/VIIRS primary. Cross-check with UNGRD Emergencias on
  datos.gov.co (id wwkg-r6te, CSV export) and DNBC reports. Cundinamarca leads the
  country in reported forest fire records (UNGRD/Desinventar 1921 to 2020).
- Fuel: IDEAM CORINE Land Cover (SIAC); IDER Cundinamarca has the departmental
  CLC. UPDATE 2026-08-21: unreachable after four independent attempts (see
  section 5.3 for the full list). ESA WorldCover 10m v200 (2021), AWS Open
  Data, s3://esa-worldcover/, no login required, is the working source in
  practice, same pattern as the OSM/CAR substitution for water above. Two
  tiles downloaded and verified (N03W075, N03W078), covering Cundinamarca.
- Slope for ROS: IGAC digital terrain model (Colombia en Mapas), originally
  named. UPDATE 2026-08-21: not attempted, given this repo's track record
  with IGAC infrastructure (water, CORINE, Aerocivil all needed workarounds
  or substitutions). SRTM GL1 (NASA, 30m, global) used instead, mirrored
  with no login required by OpenTopography's public S3 bucket
  (opentopography.s3.sdsc.edu). 16 tiles downloaded and verified 2026-08-21
  (N03-N06, W073-W076), covering Cundinamarca, ~285 MB total. Slope
  computed with Horn's (1981) method, src/scenarios/slope.py, real fire
  locations from January 2024 sampled successfully with 0 misses (slope
  range 0.7-36.7 degrees, mean about 9 degrees, plausible for
  Cundinamarca's mixed Andean-foothill and savanna terrain).
- Weather covariates: IDEAM series on datos.gov.co (precipitation, stations),
  originally named. UPDATE 2026-08-21: not exhaustively ruled out (a real
  "Velocidad del Viento" IDEAM dataset with named Cundinamarca stations was
  found on datos.gov.co, resource sgfv-3yp8), but NASA POWER was adopted
  instead for wind: a live point-query API (no login, no download, no
  station-interpolation needed), verified directly, real query for a
  Cundinamarca point and a real January 2024 fire date returned WS10M=2.01
  m/s (source MERRA2 reanalysis). Fits the actual need (a wind value per
  specific fire location and date) better than a sparse station network
  would have. src/scenarios/weather.py.
- Value at risk: WorldPop Colombia raster (GeoTIFF) and DANE CNPV 2018.
  CONFIRMED 2026-08-24: WorldPop "constrained" raster downloaded
  (data.worldpop.org, about 100m, 27.8 MB, no login, more accurate than the
  unconstrained ~614 MB raster for this use, not merely smaller/faster),
  1 km buffer, src/scenarios/population.py. DANE CNPV
  2018 found live (services7.arcgis.com, layer MGN_ANM_CUNDINAMARCA, 116
  municipalities), used as a secondary cross-check only, field CONFIRMED
  2026-08-30 against DANE's own primary field dictionary (STP27_PERS, not
  STCTNENCUE), see section 5.3.
- Risk context: IDEAM fire risk zoning and BAICV municipal alerts.
- Current infrastructure baseline (experiment 5): Bogota fire stations
  georeferenced (IDECA, datos.gov.co id 954c-y7xj); DNBC open data (RUE).
- Aircraft type (cost_aircraft[m], tank[m], speed[m]): CONFIRMED 2026-08-30,
  src/model/aircraft.py. Colombia's Fuerza Aeroespacial Colombiana (FAC),
  with UNGRD, is acquiring two Sikorsky S-70i FIREHAWK helicopters
  specifically for wildfire response (the first of this class in Latin
  America), a snorkel-fill fixed-tank helicopter that matches this repo's
  water_points design (fills from any water body at least 45 cm deep in
  under a minute, no long calm-water runway needed the way an amphibious
  fixed-wing scooper like the Air Tractor AT-802F Fire Boss would). Cost:
  150,000 millones de pesos (150 billion COP) for two units (fac.mil.co,
  presidencia.gov.co), i.e. 75,000,000,000 COP per unit, kept in COP as the
  primary-source currency rather than converted to USD. Tank: 1,000 US
  gallons (3,785.41 L), confirmed independently by FAC, Lockheed Martin's
  own Firehawk product page, and militaryfactory.com. Fill time: under 60
  seconds from water at least 45 cm deep (FAC, militaryfactory.com). Cruise
  speed: 150 knots (277,800 m/h), the figure most consistently reported
  across independent secondary sources; other sources give 139 knots
  (Lockheed's own rounded "160 mph") or a 130/150 knot loaded/unloaded
  split not independently confirmed, see src/model/aircraft.py docstring
  for the full disclosure. The drop/positioning half of ops_time (delta)
  has no sourced figure and is an illustrative 30 seconds, same honesty
  standard as ros_formula.py's slope_coef/wind_coef.

Licensing: the IGAC water layer is open. Check the license tag on any other IGAC
layer before redistributing derivatives, and cite year, scale and holder.

---

## 9. Experiments (section 6) [FROZEN]

1. Bilinear formulation vs its big-M linearized MILP (renamed 2026-08-18 from
   "MINLP vs SOS2-linearized MILP", see section 3 and section 10 history:
   the cycle productivity term is precomputed, not SOS2-linearized, and the
   remaining nonlinearity is a bilinear dispatch-refill_at coupling, not a
   general MINLP).
2. Matheuristic vs pure Gurobi.
3. Integrated vs sequential (the star experiment).
4. Expectation vs CVaR.
5. Optimal vs current Colombian infrastructure.
6. Sensitivity to budget, and (added 2026-08-18, extended 2026-08-21 and
   2026-08-30) to five magnitude constants with no solid primary source for
   Colombia, swept as a range rather than fixed at a single unverified
   value: the requirement[f] calibration constants A0 (initial fire area,
   roughly 1-30 ha) and c (liters per square meter to control, roughly
   1.5-10 L/m^2), ros_scale (overall rate-of-spread magnitude, section
   5.3), and cost_base[i]/cost_water[k] (candidate site costs, roughly 300
   million-6,000 million COP per base and 15 million-300 million COP per
   water point, section 3/8/10, src/model/costs.py). "Sensitivity to
   propagation rates" (the original wording of this item) is now this
   ros_scale sweep specifically, not a separate item.

---

## 10. Open items, do not lose these [PENDING]

Carried over from the literature and modeling work. These are the user's calls,
not to be silently resolved:

- Full section 5.2 derivation: DECIDED 2026-08-18, four sub-items closed
  (see sections 3 and 4 for where each landed):
  1. drops[i,f,k,m] needs no SOS2: every input is a parameter under the
     current single-aircraft-type, discrete-candidate-site scope, so it is
     precomputed as a constant table. If a future extension makes any input
     decision-dependent (continuous speed choice, continuous water-point
     siting), this needs revisiting.
  2. The remaining nonlinearity, the dispatch times refill_at bilinear
     coupling in constraint block 6, is linearized with a standard big-M
     reformulation, not SOS2.
  3. requirement[f]'s functional form is simple exponential area growth,
     requirement[f] = c * A0 * exp(ros[f] * t_arrival[f]). Three other
     candidate forms (elliptical/perimeter growth per Van Wagner 1969 and
     the Fried and Fried containment model; linear/affine approximation;
     econometric fireline-production-function, ruled out for conflicting
     with the no-historical-data rationale in section 3) were surveyed and
     set aside in favor of this one, chosen for fitting the existing
     single-scalar ros[f] notation without new shape parameters.
  4. t_arrival[f] is defined as time from FIRMS detection to the start of
     the critical window, exogenous and independent of which base
     dispatches, so requirement[f] stays a pure per-fire parameter, not
     requirement[i,f].
  Calibration constants A0 and c: DECIDED 2026-08-18, not fixed, swept as a
  sensitivity range in experiment 6 (section 9), see section 3 for the
  ranges and why no single value was fixed (no solid primary source found,
  and fixing one would contradict this section's own no-historical-data
  design rationale). The formal LP/MILP inequalities are now written,
  section 5.2 (2026-08-18): the delivered-liters coupling turned out to be a
  binary-times-bounded-integer bilinear product (dispatch times refill_at),
  linearized exactly with one new auxiliary variable (serve[i,f,k,m,s]) and
  a standard big-M/McCormick envelope, not SOS2. src/model/ can now be built
  directly from section 5.2.
- Whether a fire may be served by more than one water point across cycles:
  DECIDED 2026-08-18, no, exactly one water point per fire for the whole
  episode (see section 4).
- Single vs multiple aircraft types: DECIDED 2026-07-23, single type for this
  paper (see section 4). Reasoning: keeps the SOS2/matheuristic scope fixed,
  protects the 30 September 2026 deadline. Huang and Zhao (2025), the nearest
  comparator with multiple types, trades away water/joint/cyclic to afford
  fleet heterogeneity, i.e. no prior work does both at once. Multiple types
  may return later as a section 9 sensitivity extension, not core scope.
- Gap table cells pending full-text reading: RESOLVED 2026-07-23 for Maras et
  al. 2023 (Cyclic=No confirmed from the open-access paper, dagger removed).
  Skorin-Kapov et al. 2024 narrowed to only the Cyclic cell still pending (rest
  of the row confirmed from the abstract; primary text is paywalled). Wang et
  al. 2026 remains fully PENDING and could not be located in two independent
  search passes (see gap_table.tex source comment for every candidate ruled
  out); the user needs to supply the exact DOI/title from their own reference
  manager before this row can be trusted.
- Wei et al. 2015: DECIDED 2026-07-23. The intended citation is Wei, Bevers and
  Belval (2015), "Designing seasonal initial attack resource deployment and
  dispatch rules using a two-stage stochastic programming procedure," Forest
  Science 61(6):1021-1032 (not the other 2015 paper by an overlapping author
  group, Wei, Bevers, Belval and Bird (2015), "A Chance-Constrained
  Programming Model to Allocate Wildfire Initial Attack Resources for a Fire
  Season," Forest Science 61(2):278-288, which remains a plausible near match
  but was not chosen).
- Methodological references: VERIFIED 2026-07-23, all six checked against
  primary sources, per section 11. Two-stage stochastic programming
  (Dantzig 1955, Management Science 1(3-4):197-206, jointly with Beale 1955,
  JRSS-B 17(2):173-184), mean-risk CVaR (Rockafellar and Uryasev 2000, Journal
  of Risk 2(3):21-41), SOS2 (Beale and Tomlin 1970, Proceedings OR 69,
  Tavistock, pp. 447-454), SAA with gap/CI reporting (Kleywegt, Shapiro and
  Homem-de-Mello 2001, SIAM J. Optimization 12(2):479-502), and LNS (Shaw 1998,
  CP98, LNCS 1520, pp. 417-431) were all confirmed correct as attributed. The
  fix-and-optimize attribution was confirmed WRONG as suspected (Fischetti and
  Lodi 2003 is local branching) and has been corrected in section 3 to Helber
  and Sahling (2010), International Journal of Production Economics
  123(2):247-256.
- Scenario generation methodology: DECIDED 2026-08-18 in form, see section
  5.3 for the full reasoning. Scenario = one historical fire day, not a full
  season (a season would break constraint 5 of section 5.2 as written, no
  time-based aircraft reuse is modeled there). ros[f] = land-cover-class base
  rate times a slope factor times a wind factor (not full Rothermel, no
  verified fuel-parameter crosswalk exists for Colombia); land cover source
  UPDATED 2026-08-21 from IDEAM CORINE to ESA WorldCover (CORINE unreachable
  after four independent attempts, see section 5.3/8). value_at_risk[f] =
  unmonetized WorldPop population exposure within a 1 km buffer (fixed
  2026-08-21, no standard evacuation-radius source found), cross-checked
  against DANE CNPV 2018 (field CONFIRMED 2026-08-30, STP27_PERS not
  STCTNENCUE, see section 5.3; not monetized, same no-verified-constant
  problem already hit with
  requirement[f]'s A0/c). t_arrival[f] DECIDED 2026-08-20 = min_i
  t_base_fire[i,f] (closest candidate base), needs no external data, see
  section 5.3. Slope source UPDATED 2026-08-21 from IGAC's DTM to SRTM GL1
  (16 tiles downloaded and verified, section 8). Wind data source UPDATED
  2026-08-21 from IDEAM to NASA POWER (a live point-query API, verified
  live, section 8). Full ros[f] formula DECIDED 2026-08-21 (land cover
  class times slope times wind, ros_scale swept alongside A0/c in
  experiment 6, class_relative_rate table ordinally grounded in NWCG's
  Anderson 1982 fuel-model ratings but not independently calibrated in
  magnitude, see section 5.3), src/scenarios/ros_formula.py. WorldPop
  downloaded and connected (section 8). Full assembly into src/model/
  Scenario/Fire objects DONE 2026-08-24, src/scenarios/assemble.py,
  verified end to end against the real January 2024 catalog (20 bootstrap
  scenarios, 266 fires, all 266 completed with real land cover/slope/wind/
  population, zero dropped). DANE population field CONFIRMED 2026-08-30:
  STP27_PERS ("Numero de personas"), not STCTNENCUE ("Cantidad de
  Encuestas CNPV 2018", a survey count, wrong field), verified against
  DANE's own primary field dictionary and a live query
  (STP27_PERS = STPERSON_S + STPERSON_L exactly for Chipaque); corrected in
  src/scenarios/population.py. Full calendar year 2024 FIRMS data
  DOWNLOADED AND PROCESSED 2026-08-30 (data/processed/events_2024-full.csv,
  2413 events, 366-day pool), replacing the January-only pool; still not
  multi-year, see section 5.3. Real aircraft type CONFIRMED 2026-08-30
  (Sikorsky S-70i FIREHAWK, Colombia's own FAC/UNGRD acquisition,
  src/model/aircraft.py, see section 8 for the full citation chain and
  section 4 for the units convention this made explicit). Candidate site
  costs (cost_base[i], cost_water[k]) DECIDED 2026-08-30: no Colombia-
  specific source was found despite a real web search (section 3/8),
  treated as swept sensitivity parameters like A0/c/ros_scale, uniform
  across all bases (resp. water points), src/model/costs.py. Still
  PENDING: multi-year (multiple calendar years, not just 2024) FIRMS data
  for a bootstrap pool that captures interannual variability.
- Gurobi academic license: CONFIRMED WORKING 2026-08-30 (the pause noted
  earlier in this section is over). `tests/test_model_milp.py` now runs
  every MILP test against both CBC and Gurobi automatically. This
  verification surfaced a real PuLP/Gurobi footgun, documented in
  `solve()`'s docstring (src/model/milp.py) and that test file's module
  docstring: a single `pulp.GUROBI()` instance accumulates every
  `LpProblem` solved with it into one underlying `gurobipy.Model`,
  corrupting every solve after the first; a fresh instance is required per
  solve. This matters directly for the future fix-and-optimize/LNS
  matheuristic (section 3, src/matheuristic/, solves many sub-MILPs per
  run) and experiment 6's sweeps, not just these tests. `bilinear.py`
  (experiment 1's other half, previously blocked on this exact license) is
  now unblocked and IMPLEMENTED 2026-08-30 (src/model/bilinear.py, built
  directly against gurobipy with NonConvex=2, mirroring milp.py's
  build_model/solve/solve_model shape). Verified to agree exactly with the
  linearized MILP's optimal objective value on every hand-verified
  synthetic instance (tests/test_model_bilinear.py), which is the actual
  point of experiment 1.
- First real-data solve: CONFIRMED WORKING 2026-08-30,
  src/model/run_instance.py, wiring every real-data stage (candidate
  sites, a bootstrap scenario draw, aircraft.py, costs.py) into one solve,
  cross-checked identical between CBC and Gurobi. Surfaced two real,
  previously-latent bugs, both now fixed, see src/model/README.md for the
  full detail: (1) scenario probabilities must sum to 1 for the CVaR
  objective to stay bounded, silently violating this (e.g. slicing a
  scenario subset without renormalizing) makes the MILP genuinely
  Unbounded, not just wrong; milp.build_model now validates this and
  raises a clear error, directly relevant to the matheuristic's future
  LNS neighborhoods/reduced-scenario subproblems. (2) The real candidate
  water point set (5,449 sites, section 8) is not tractable for the exact
  McCormick linearization as written (over 650,000 serve[i,f,k,m,s]
  auxiliary variables per fire per scenario at the real 120-base scale);
  reducing it to a tractable size is a new, separate, not-yet-solved open
  item, needed before any real (non-smoke-test) experiment. window (W,
  critical suppression window length) was also found to have no sourced
  value anywhere in this file, unlike budget/cvar_alpha/mean_risk_weight
  it was not even flagged PENDING in config/parameters.yaml; treat it as
  the user's own call too, alongside those three, not yet decided.
- Fix-and-optimize/LNS matheuristic: IMPLEMENTED 2026-08-30,
  src/matheuristic/ (neighborhoods.py, fix_and_optimize.py), directly
  answering the water-point tractability problem noted just above: each
  LNS iteration solves a reduced sub-MILP over only the current
  neighborhood's sites plus whatever the incumbent already has open,
  dropping every other (closed) site entirely, exact not approximate (see
  src/matheuristic/README.md for the full argument). Neighborhood
  structure DECIDED 2026-08-30: geographic proximity (a random seed site,
  then its nearest candidate bases/water points), Shaw's (1998) own
  "relatedness" destroy principle, chosen over pure-random or a fixed
  systematic partition specifically because it matches this paper's
  central base-water cycle-time coupling (section 2), not an arbitrary
  implementation choice. Verified on hand-built synthetic instances
  (tests/test_matheuristic_*.py) against milp.solve_model directly: finds
  the identical true optimum both when one neighborhood already covers
  every candidate site, and when neighborhoods are strictly smaller than
  the full candidate set (robust across 10+ random seeds during
  development). Parametrized across CBC and Gurobi like
  tests/test_model_milp.py, respecting the GUROBI() reuse hazard (a
  solver factory, not a shared instance, is required). Wired to the real
  candidate catalog and CONFIRMED WORKING 2026-09-04,
  src/matheuristic/run_real_instance.py (mirrors run_instance.py, but does
  NOT truncate the water point set, since the whole point of this package
  is making the untruncated real scale tractable): with the full 120-base/
  5,449-water-point catalog and 2 real scenarios (15 fires), converged in
  2.5 s (Gurobi) / 36.2 s (CBC) over 11 iterations, both finding objective
  73.847, matching run_instance.py's own truncated-MILP reference value
  exactly, a genuine cross-check of the reduced-sub-MILP exactness argument
  at real scale, not just on synthetic instances. A larger stress test (10
  scenarios, 81 fires, 60 iterations, Gurobi) ran in about 947 s (roughly
  15.8 s/iteration), the first real runtime data point for tuning
  neighborhood size and iteration budgets, not yet systematically swept.
  That run also surfaced a disclosed, non-bug limitation: with the
  strict-improvement-only acceptance rule, a site opened once is never
  closed again once it becomes redundant, since cost_water only enters the
  budget constraint, not the objective (closing it produces a tied, not
  improved, objective, which this acceptance rule never takes); the
  objective value stays exact, but the specific site count/portfolio
  reported is an upper bound, not necessarily the most parsimonious one
  (see src/matheuristic/README.md for the full argument).

  Experiment 2's benchmark script IMPLEMENTED 2026-09-04,
  src/experiments/experiment2_matheuristic_vs_gurobi.py (see
  src/experiments/README.md): solves the SAME instance both ways (pure
  Gurobi direct on the full MILP, and the matheuristic) across a sweep of
  candidate-catalog sizes. Its first real run (5:10, 10:25, 20:50
  bases:water, 2 real scenarios) found a genuine, important bug: at 20:50,
  pure Gurobi found a strictly better solution (objective 0.0, base
  aero_SKEF) than the matheuristic ever reached (stuck at 73.847, base
  aero_SQUV), even at 200 iterations. Root cause, fully diagnosed:
  aero_SKEF and aero_SQUV are 174 km apart; only one Firehawk was ever
  affordable under the test budget, so reaching the true optimum required
  CLOSING aero_SQUV and OPENING aero_SKEF in the SAME LNS iteration, a
  trade the pure-geographic destroy operator can never propose when the
  two sites are this far apart (confirmed: no single seed's nearest-n
  neighborhood can span two 174-km-apart clusters). FIXED 2026-09-04 by
  adding a random destroy operator: neighborhoods.pick_neighborhood gained
  a random_destroy_prob parameter (default 0.0, preserving prior behavior
  for every existing caller), which with that probability frees sites
  drawn uniformly at random from the WHOLE candidate set instead of the
  geographic operator, standard ALNS practice for exactly this failure
  mode (Ropke and Pisinger 2006, "An Adaptive Large Neighborhood Search
  Heuristic for the Pickup and Delivery Problem with Time Windows,"
  Transportation Science 40(4):455-472, DOI 10.1287/trsc.1050.0135,
  verified 2026-09-04 against the publisher page: existence, year, venue,
  page numbers all confirmed). Correctness of the fix is PROVEN on an
  isolated, hand-verified synthetic instance that reproduces the exact
  failure structure (tests/test_matheuristic_fix_and_optimize.py's
  _far_bases_trap_case: without the fix, permanently stuck over 100
  iterations with no early stop; with random_destroy_prob=0.4, reliably
  finds the true optimum within 300 iterations across all 5 seeds tested).
  Re-running the exact real 20:50 case that surfaced the bug with
  random_destroy_prob=0.3 did NOT yet reliably reproduce the fix within
  100 iterations (direct inspection showed the random operator did draw
  the needed base pair together twice, but the resulting sub-MILP still
  found no improvement, most likely because the specific water point
  aero_SKEF needs was not yet part of the incumbent's open set at that
  point in the run); this was not chased down to full certainty on that
  one-off real run, only proven correct on the controlled synthetic case,
  see src/matheuristic/README.md for the complete, honest account. Still
  not yet done: real budget/cvar_alpha/mean_risk_weight/window (the user's
  own call, unchanged), a systematic neighborhood-size/random_destroy_prob/
  iteration-budget tuning sweep against real escape reliability (not just
  runtime), a systematic instance-size sweep large enough to show pure
  Gurobi's own runtime blow up, and deciding whether a tie-accepting
  consolidation pass is worth adding for the site-accumulation limitation
  above.

---

## 11. Citation discipline [FROZEN]

Do not introduce a citation from memory. Every reference must be verified against
a source (existence, year, venue, and that its content matches the claim) before
it enters the manuscript. Mark each as confirmed, unconfirmed, or probably wrong.
Only confirmed references go into the paper.
