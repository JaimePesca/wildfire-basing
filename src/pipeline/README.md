# src/pipeline

FIRMS to Event pipeline: load, clean, project, cluster (ST-DBSCAN), derive
event attributes. See CLAUDE.md section 5 for the design and section 6 for
the output schema this package must produce exactly.

## Expected FIRMS CSV input columns

`load_firms_csv` (in `io.py`) expects a standard FIRMS CSV export (VIIRS or
MODIS active fire product) with at least these columns:

| Column | Meaning |
|---|---|
| `latitude` | decimal degrees |
| `longitude` | decimal degrees |
| `acq_date` | acquisition date, `YYYY-MM-DD` |
| `acq_time` | acquisition time, `HHMM` (UTC), possibly without leading zeros |
| `confidence` | VIIRS: categorical `low`/`nominal`/`high`; MODIS: numeric `0` to `100` |
| `frp` | fire radiative power |
| `satellite`, `instrument`, `daynight`, `version` | carried through, optional |

`latitude`, `longitude`, `acq_date`, `acq_time` are required; the loader
raises a clear `ValueError` if any are missing rather than guessing. A
`timestamp` column (UTC, parsed from `acq_date` + `acq_time`) is added.

## Running the pipeline

```bash
python -m src.pipeline.run_pipeline \
    --input data/raw/firms_export.csv \
    --output data/processed/events.csv \
    --config config/parameters.yaml
```

Run from the repository root so the `src` package resolves. Output is one
row per detected fire event, matching the Event record schema in CLAUDE.md
section 6 (`event_id`, `centroid_lat`, `centroid_lon`, `x_utm`, `y_utm`,
`t_start`, `t_end`, `duration_h`, `n_detections`, `frp_total`, `frp_peak`,
`extent`, `confidence_mix`, `municipality`).

Pipeline steps, in order: `io.load_firms_csv`, `clean.clean_firms`,
`project.project_to_crs` (reprojects to the configured EPSG, currently 9377,
MAGNA-SIRGAS 2018 / Origen-Nacional CTM12), `st_dbscan.cluster_detections`
(ST-DBSCAN, see `st_dbscan.py` docstring for exactly how the Birant and Kut
citation is being used and where this implementation departs from it), and
`events.build_events`.

## Downloading real FIRMS data

Register a free MAP_KEY (email only, no Earthdata account needed) at
https://firms.modaps.eosdis.nasa.gov/api/map_key/, then set it as the
`FIRMS_MAP_KEY` environment variable (copy `.env.example` to `.env` and fill
it in; `.env` is gitignored, never commit a real key).

Example CLI invocation, Cundinamarca, January 2024 (chunks the range into
5-day Area API calls automatically and writes one raw CSV per chunk into
`data/raw`):

```bash
python -m src.pipeline.firms_download \
    --start 2024-01-01 --end 2024-01-31 \
    --source VIIRS_SNPP_SP \
    --out-dir data/raw
```

See `src/scenarios/eps_sensitivity.py` for the mandatory eps_spatial /
eps_temporal sensitivity analysis (CLAUDE.md section 5), and
`tests/test_jan2024_validation.py` for the January 2024 chaining validation
hook that activates automatically once real raw data lands at the path it
documents.

## Open items (not silently resolved)

- **Municipality join is pending.** `events.build_events` leaves
  `municipality` as `None` for every event. Wiring it in needs a Colombian
  municipality boundary layer (DIVIPOLA or IGAC, see CLAUDE.md section 8),
  which is not present in `data/raw` yet, and doing that spatial join
  properly likely means bringing in a geometry library beyond this first
  pass's deliberately lightweight stack (pandas, numpy, scipy, pyproj).
- **The January 2024 validation is not done.** CLAUDE.md section 5 asks the
  pipeline to recover the January 2024 Colombian fires as coherent, separate
  events, as a check against the chaining risk. That needs real FIRMS/VIIRS
  raw data for that window, which is not in this repo (`data/raw` is
  gitignored and empty by design). `tests/test_pipeline.py` documents this
  as an explicit TODO rather than skipping it silently; only synthetic
  fixtures are exercised so far.
