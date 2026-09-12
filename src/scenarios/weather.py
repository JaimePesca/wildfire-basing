"""Query wind speed for a fire's location and date (CLAUDE.md section 5.3:
ros[f]'s wind factor input; the wind FACTOR formula itself, how a wind
speed number turns into a multiplier, is still PENDING, this module only
gets the real wind speed value).

Source switched 2026-08-21 from IDEAM (named in CLAUDE.md section 8) to
NASA POWER, a live point-query API (no login, no download, no raster
processing): verified directly, a real query for a Cundinamarca point and
one of the real January 2024 fire dates returned WS10M=2.01 m/s (source
MERRA2 reanalysis). This fits the actual need better than IDEAM's sparse
station network would have: a wind value per specific fire (lat/lon and
date), not a full raster of Colombia, so a live per-point API avoids
needing spatial interpolation between real IDEAM stations. IDEAM itself was
not exhaustively ruled out the way CORINE was (a real "Velocidad del
Viento" dataset with named Cundinamarca stations was found on datos.gov.co,
resource sgfv-3yp8, not pursued further once NASA POWER's fit proved
better), so this is a deliberate substitution, not a confirmed dead end.

Fair-use note from NASA POWER's own docs: repeatedly requesting the exact
same location is discouraged (risk of being blocked); this module is
expected to be called once per distinct (rounded location, date) pair, not
in a tight repeated-query loop, callers should not defeat that by adding
retries-on-success or similar.

Resilience ADDED 2026-09-12 after a real mid-run failure (the SAA
replication enrichment of 1,244 fire slots died on a NASA POWER
RemoteDisconnected halfway through, losing all progress):
1. fetch_wind_speed retries transient failures (connection errors,
   timeouts, HTTP 5xx/429) with exponential backoff. These are
   retries-on-FAILURE, which the fair-use note above does not discourage;
   there are still no retries on success.
2. fetch_wind_speed_for_fires keeps a persistent on-disk cache
   (data/interim/wind_cache.json by default, the gitignored interim
   area), flushed incrementally, so a crashed or interrupted run resumes
   from what it already fetched instead of re-querying NASA POWER from
   zero, which also serves the fair-use note.
"""

from __future__ import annotations

import json
import pathlib
import time

import requests

POWER_DAILY_POINT_URL = "https://power.larc.nasa.gov/api/temporal/daily/point"
# NASA POWER's own sentinel for a missing/unavailable value (confirmed in
# the module docstring's live test response: "fill_value":-999.0).
FILL_VALUE = -999.0

DEFAULT_COMMUNITY = "AG"  # Agroclimatology, the closest fit for a land/wildfire application
WIND_SPEED_PARAMETER = "WS10M"  # Wind Speed at 10 Meters, m/s


def fetch_wind_speed(
    lat: float,
    lon: float,
    date: str,
    community: str = DEFAULT_COMMUNITY,
    timeout_s: int = 30,
    retries: int = 4,
    backoff_s: float = 2.0,
) -> float | None:
    """Wind speed at 10 m (m/s) for one point and one date (YYYYMMDD).
    Returns None if NASA POWER reports FILL_VALUE (no data for that
    point/date), never a guessed number.

    Transient failures (connection errors, timeouts, HTTP 5xx and 429)
    are retried up to `retries` times with exponential backoff
    (backoff_s, 2*backoff_s, 4*backoff_s, ...); other HTTP errors and
    exhausted retries raise. Retries only ever happen on failure, per
    the module docstring's fair-use note."""
    attempt = 0
    while True:
        try:
            response = requests.get(
                POWER_DAILY_POINT_URL,
                params={
                    "parameters": WIND_SPEED_PARAMETER,
                    "community": community,
                    "longitude": lon,
                    "latitude": lat,
                    "start": date,
                    "end": date,
                    "format": "JSON",
                },
                timeout=timeout_s,
            )
            response.raise_for_status()
            break
        except (requests.exceptions.ConnectionError, requests.exceptions.Timeout):
            attempt += 1
            if attempt > retries:
                raise
        except requests.exceptions.HTTPError as err:
            status = err.response.status_code if err.response is not None else None
            if status is not None and (status >= 500 or status == 429):
                attempt += 1
                if attempt > retries:
                    raise
            else:
                raise
        time.sleep(backoff_s * 2 ** (attempt - 1))
    payload = response.json()
    value = payload["properties"]["parameter"][WIND_SPEED_PARAMETER][date]
    return None if value == FILL_VALUE else float(value)


DEFAULT_WIND_CACHE_PATH = "data/interim/wind_cache.json"
_CACHE_FLUSH_EVERY = 25


def _load_disk_cache(path: str) -> dict[str, float | None]:
    p = pathlib.Path(path)
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def _flush_disk_cache(path: str, cache: dict[str, float | None]) -> None:
    p = pathlib.Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(cache, indent=0), encoding="utf-8")


def fetch_wind_speed_for_fires(
    fires: list,
    dates: dict[str, str],
    community: str = DEFAULT_COMMUNITY,
    cache_path: str | None = DEFAULT_WIND_CACHE_PATH,
) -> dict[str, float | None]:
    """Batch helper: fires is a list of objects with fire_id/lat/lon
    attributes (e.g. src.scenarios.day_scenarios.FireRecord); dates maps
    fire_id to a YYYYMMDD string (the fire's own t_start date, the caller's
    responsibility to supply, this module does not infer a date). Caches by
    (rounded lat/lon to 2 decimals, ~1km, date) so fires sharing a location/
    date (e.g. two detections resolved as separate Event records on the
    same day and place) do not trigger duplicate NASA POWER calls, per the
    fair-use note in the module docstring.

    The cache is PERSISTENT when cache_path is not None (default
    data/interim/wind_cache.json): previously fetched values, including
    genuine None results, are reused across runs, and new values are
    flushed to disk incrementally (every few fetches and at the end,
    including on the error path), so an interrupted run resumes instead
    of re-querying from zero."""
    cache: dict[str, float | None] = _load_disk_cache(cache_path) if cache_path else {}
    result: dict[str, float | None] = {}
    new_since_flush = 0
    try:
        for fire in fires:
            date = dates[fire.fire_id]
            key = f"{round(fire.lat, 2)},{round(fire.lon, 2)},{date}"
            if key not in cache:
                cache[key] = fetch_wind_speed(fire.lat, fire.lon, date, community=community)
                new_since_flush += 1
                if cache_path and new_since_flush >= _CACHE_FLUSH_EVERY:
                    _flush_disk_cache(cache_path, cache)
                    new_since_flush = 0
            result[fire.fire_id] = cache[key]
    finally:
        if cache_path and new_since_flush:
            _flush_disk_cache(cache_path, cache)
    return result
