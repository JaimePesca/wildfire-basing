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
"""

from __future__ import annotations

import requests

POWER_DAILY_POINT_URL = "https://power.larc.nasa.gov/api/temporal/daily/point"
# NASA POWER's own sentinel for a missing/unavailable value (confirmed in
# the module docstring's live test response: "fill_value":-999.0).
FILL_VALUE = -999.0

DEFAULT_COMMUNITY = "AG"  # Agroclimatology, the closest fit for a land/wildfire application
WIND_SPEED_PARAMETER = "WS10M"  # Wind Speed at 10 Meters, m/s


def fetch_wind_speed(
    lat: float, lon: float, date: str, community: str = DEFAULT_COMMUNITY, timeout_s: int = 30
) -> float | None:
    """Wind speed at 10 m (m/s) for one point and one date (YYYYMMDD).
    Returns None if NASA POWER reports FILL_VALUE (no data for that
    point/date), never a guessed number.
    """
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
    payload = response.json()
    value = payload["properties"]["parameter"][WIND_SPEED_PARAMETER][date]
    return None if value == FILL_VALUE else float(value)


def fetch_wind_speed_for_fires(
    fires: list, dates: dict[str, str], community: str = DEFAULT_COMMUNITY
) -> dict[str, float | None]:
    """Batch helper: fires is a list of objects with fire_id/lat/lon
    attributes (e.g. src.scenarios.day_scenarios.FireRecord); dates maps
    fire_id to a YYYYMMDD string (the fire's own t_start date, the caller's
    responsibility to supply, this module does not infer a date). Caches by
    (rounded lat/lon to 2 decimals, ~1km, date) so fires sharing a location/
    date (e.g. two detections resolved as separate Event records on the
    same day and place) do not trigger duplicate NASA POWER calls, per the
    fair-use note in the module docstring.
    """
    cache: dict[tuple[float, float, str], float | None] = {}
    result: dict[str, float | None] = {}
    for fire in fires:
        date = dates[fire.fire_id]
        key = (round(fire.lat, 2), round(fire.lon, 2), date)
        if key not in cache:
            cache[key] = fetch_wind_speed(fire.lat, fire.lon, date, community=community)
        result[fire.fire_id] = cache[key]
    return result
