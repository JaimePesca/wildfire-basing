# src/scenarios

## day_scenarios.py: events to SAA scenarios

Implements CLAUDE.md section 5.3 (scenario = one historical fire day,
decided 2026-08-18): bootstrap-resamples calendar days, with replacement,
from a real Event record catalog (src/pipeline output), each draw becomes
one Scenario record (section 6) carrying that day's real fires.

```bash
python -m src.scenarios.day_scenarios \
    --events data/processed/events_2024-01.csv \
    --start-date 2024-01-01 --end-date 2024-01-31 \
    --n-scenarios 100 --seed 0 \
    --out data/processed/scenarios_jan2024.json
```

`--start-date`/`--end-date` must be given explicitly and cover the real
range of the events file (or wider): the day pool needs every calendar day
in range, including days with zero events, so bootstrap sampling reflects
how often nothing happens, not just how often something does. Do not infer
the range from the data.

Straight out of this CLI, `ros_param` and `value_at_risk` come out `null`
and `t_arrival` needs `--bases`/`--speed` (real candidate base data plus a
real aircraft speed, neither fabricated here); see `assemble.py` below for
how all three actually get filled in from real data. `size_proxy` (FRP
total) is filled in directly by this module, it needed no such decision.

UPDATE 2026-08-30: the full calendar year 2024 is now downloaded and
processed (`data/processed/events_2024-full.csv`, 4689 real raw VIIRS
detections, 2413 events, 366-day pool with 282 days having at least one
fire), replacing the January-only pool (src/pipeline/README.md):

```bash
python -m src.scenarios.day_scenarios \
    --events data/processed/events_2024-full.csv \
    --start-date 2024-01-01 --end-date 2024-12-31 \
    --n-scenarios 200 --seed 0 \
    --out data/processed/scenarios_2024full.json
```

This is one full year's seasonality, a real improvement over one month,
but still a single year; multiple years of real FIRMS data (for
interannual variability, e.g. dry-year vs wet-year fire seasons) are still
a documented next step, not yet done.

## land_cover.py: ESA WorldCover sampling (ros[f] input)

Samples the land cover class at a fire's location, from local ESA
WorldCover 10m GeoTIFF tiles (`data/raw/esa_worldcover_2021_N03W075.tif`,
`..._N03W078.tif`, covering Cundinamarca, downloaded 2026-08-21). Used
instead of IDEAM CORINE (CLAUDE.md section 8 originally named it) after
CORINE proved unreachable four independent times, see section 5.3/8 for the
full list of dead ends and why WorldCover was adopted, same pattern as the
OSM/CAR substitution already used for water.

```python
from src.scenarios.land_cover import sample_land_cover_for_fires
classes = sample_land_cover_for_fires(fires, [
    "data/raw/esa_worldcover_2021_N03W075.tif",
    "data/raw/esa_worldcover_2021_N03W078.tif",
])
```

Returns the raw WorldCover class code (10=Tree cover, 20=Shrubland, ...,
see `WORLDCOVER_CLASSES`) per fire, `None` if a fire falls outside both
tiles or on a nodata pixel. **This is only the land-cover half of ros[f].**
The per-class base ROS rate table (needed to turn a class code into an
actual spread-rate number) and the exact wind factor form (turning a wind
speed number into a multiplier) are still open, see CLAUDE.md section
5.3/10. Slope and wind data acquisition are both done, see slope.py and
weather.py below.

## slope.py: SRTM slope sampling (ros[f] input)

Computes terrain slope (Horn 1981 method) from local SRTM GL1 30m GeoTIFF
tiles (`data/raw/srtm_N0{3,4,5,6}W07{3,4,5,6}.tif`, 16 tiles covering
Cundinamarca, downloaded 2026-08-21 from OpenTopography's public S3 mirror,
no login required). Used instead of IGAC's own DTM (CLAUDE.md section 8
originally named it): not even attempted, given this repo's track record
with IGAC infrastructure across water, CORINE and Aerocivil.

```python
from src.scenarios.slope import sample_slope_degrees
import glob
tiles = glob.glob("data/raw/srtm_*.tif")
slope_deg = sample_slope_degrees(lon, lat, tiles)
```

Verified against real January 2024 fire locations: 50/50 sampled
successfully, slope range 0.7-36.7 degrees, mean about 9 degrees, plausible
for Cundinamarca's mixed Andean-foothill and savanna terrain. Returns
`None` (not a guess) if a point falls outside all tiles or its 3x3
elevation window touches nodata.

## weather.py: NASA POWER wind speed (ros[f] input)

Queries NASA POWER's live point API (no login, no download) for wind speed
at 10 m (m/s) for one fire's location and date. Used instead of IDEAM
(CLAUDE.md section 8 originally named it): not a confirmed dead end (a real
IDEAM wind dataset with named Cundinamarca stations exists on datos.gov.co,
resource sgfv-3yp8), just a better architectural fit, since we need a wind
value per specific fire location/date, not a full raster or a sparse
station network needing interpolation.

```python
from src.scenarios.weather import fetch_wind_speed_for_fires
dates = {fire.fire_id: fire_start_date_yyyymmdd for fire in fires}  # caller supplies
wind = fetch_wind_speed_for_fires(fires, dates)
```

Verified against 10 real January 2024 fires: all returned real values
(0.75-2.09 m/s), and the (rounded location, date) cache correctly reused
one API call across fires sharing a location/day, per NASA POWER's own
fair-use note against repeated identical-location queries.

## ros_formula.py: the full ros[f] formula

Combines land_cover.py + slope.py + weather.py's outputs into the actual
ros[f] value (CLAUDE.md section 5.3, decided 2026-08-21):

```python
from src.scenarios.ros_formula import compute_ros_for_fires
ros = compute_ros_for_fires(fires, landcover_classes, slopes, wind_speeds, ros_scale=1.0)
```

`ros_scale` is swept in experiment 6 alongside A0/c, same reasoning (no
solid primary source for an absolute magnitude). `class_relative_rate` is a
fixed table, ordinally grounded in NWCG's Anderson (1982) fuel-model
spread-rate ratings but not independently calibrated in magnitude, see the
module docstring for the full disclosure. A fire maps to `None` if any of
its three inputs could not be sampled/queried, never a guessed value.

## population.py: WorldPop population exposure (value_at_risk[f])

```python
from src.scenarios.population import sum_population_for_fires
value_at_risk = sum_population_for_fires(fires, "data/raw/worldpop_col_2020_constrained.tif")
```

Sums WorldPop population (data/raw/worldpop_col_2020_constrained.tif, the
building-footprint-"constrained" layer, about 100m, 27.8 MB, downloaded
2026-08-24) within a real circular 1 km buffer (pixel-center distance, not
a bounding-box approximation) around each fire, left unmonetized. Used the
constrained layer instead of the ~614 MB unconstrained national raster: not
just smaller, generally considered more accurate for this use too (its
transfer also kept timing out on this connection regardless, unrelated to
a separate Norton interception found and fixed for data.worldpop.org along
the way). The 1 km radius is a fixed illustrative default, not
independently sourced (no standard wildfire evacuation-zone radius exists
to calibrate against). A DANE CNPV 2018 cross-check is available
(`DANE_FEATURESERVER_URL`, `DANE_POPULATION_FIELD`), field CONFIRMED
2026-08-30 against DANE's own primary field dictionary: `STP27_PERS`
("Numero de personas"), not the previously used `STCTNENCUE` (which turned
out to be a survey count, "Cantidad de Encuestas CNPV 2018", not
population), see the module docstring for the live-query verification.

## assemble.py: full assembly into src/model/ Scenario/Fire objects

```python
from src.scenarios.day_scenarios import enrich_t_arrival
from src.scenarios.assemble import enrich_scenarios_with_ros_and_value_at_risk, to_model_scenarios
from src.model.aircraft import SPEED  # real Firehawk speed, CONFIRMED 2026-08-30

enrich_t_arrival(scenarios, bases, speed=SPEED)
enrich_scenarios_with_ros_and_value_at_risk(
    scenarios, worldcover_tiles, srtm_tiles, "data/raw/worldpop_col_2020_constrained.tif", ros_scale=1.0
)
model_scenarios, dropped = to_model_scenarios(scenarios)  # raises if any fire is still incomplete
```

Verified end to end 2026-08-24 against the real January 2024 catalog: 20
bootstrap scenarios, 266 real fires, **all 266 completed** (land cover,
slope, wind and population all sampled successfully, zero dropped). At
that time t_arrival was the one piece not real, enriched with a placeholder
speed purely to exercise the code path end to end. UPDATE 2026-08-30: a
real aircraft speed now exists (`src.model.aircraft.SPEED`, see
CLAUDE.md section 4/8/10), so t_arrival can be computed for real; note the
units convention decided alongside it, speed is meters per hour, not
meters per second (the 2026-08-24 placeholder was in m/s and must not be
reused as-is under the new convention).

`to_model_scenarios` raises by default (`on_missing="raise"`) naming the
first fire still missing ros_param/value_at_risk/t_arrival, rather than
silently drop or default it, since a dropped fire would understate that
scenario's risk. Pass `on_missing="drop"` to instead exclude incomplete
fires and get their ids back, for a caller that accepts that tradeoff
deliberately.

## What's left before this is a real, runnable instance

Both remaining gaps from earlier drafts of this section are now closed
(2026-08-30): a real aircraft type (`src/model/aircraft.py`) and
cost_base[i]/cost_water[k] (no Colombia-specific source exists, DECIDED to
treat as swept sensitivity parameters, `src/model/costs.py`). What is left
is choosing real `budget`/`cvar_alpha`/`mean_risk_weight` and a sweep point
within the documented cost ranges, both explicitly the user's own call
(`config/parameters.yaml`), and multi-year FIRMS data (see above).
- Multiple years of real FIRMS data, for a bootstrap pool that captures
  interannual variability (full calendar year 2024 is downloaded and
  processed, see above, but that is still one year).
- A real ros_scale (and A0, c): swept in experiment 6, not a single fixed
  value, see CLAUDE.md section 3/9.

## eps_sensitivity.py

Unrelated to scenario generation: sweeps ST-DBSCAN's eps_spatial/
eps_temporal (CLAUDE.md section 5) to check how sensitive the fire-event
clustering itself is to those parameters. See src/pipeline/README.md.
