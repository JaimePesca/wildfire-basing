"""Downloading raw FIRMS/VIIRS detections via the Area CSV API (section 5, first step).

Verified against the live FIRMS API pages (not from memory, see CLAUDE.md
section 11 citation discipline):

- Registration (free, email only, no Earthdata account needed):
  https://firms.modaps.eosdis.nasa.gov/api/map_key/
- Area CSV API template:
  https://firms.modaps.eosdis.nasa.gov/api/area/csv/MAP_KEY/SOURCE/AREA_COORDINATES/DAY_RANGE/DATE
  where AREA_COORDINATES is "west,south,east,north" (not north/south/east/west,
  the FIRMS docs call this out explicitly) and DATE (YYYY-MM-DD, optional) is
  the last day of the returned window; DAY_RANGE days are returned ending on
  DATE (or ending today if DATE is omitted).
- DAY_RANGE is capped at 5 days per call. To cover a longer span this module
  issues one call per 5-day (or shorter, for the final partial window) chunk.

The MAP_KEY is read from the FIRMS_MAP_KEY environment variable only. It is
never hardcoded, never logged, and never written to any file this module
writes (see CLAUDE.md hard rule on secrets).
"""

from __future__ import annotations

import argparse
import os
from datetime import date, datetime, timedelta
from pathlib import Path

import requests

AREA_CSV_URL_TEMPLATE = "https://firms.modaps.eosdis.nasa.gov/api/area/csv/{map_key}/{source}/{area}/{day_range}/{date}"

MAP_KEY_ENV_VAR = "FIRMS_MAP_KEY"
MAP_KEY_REGISTRATION_URL = "https://firms.modaps.eosdis.nasa.gov/api/map_key/"

# Confirmed on the live /api/area/ page: "DAY_RANGE: 1 .. 5".
MAX_DAY_RANGE = 5


def get_map_key() -> str:
    """Read the FIRMS MAP_KEY from the environment.

    Never hardcode a key here and never log its value. Raises a clear,
    actionable error naming the registration URL if the env var is missing
    or empty, rather than letting requests fail later with an opaque 401.
    """
    map_key = os.environ.get(MAP_KEY_ENV_VAR)
    if not map_key:
        raise RuntimeError(
            f"Environment variable {MAP_KEY_ENV_VAR} is not set. Register a free "
            f"MAP_KEY (email only, no Earthdata account needed) at "
            f"{MAP_KEY_REGISTRATION_URL}, then set {MAP_KEY_ENV_VAR} in your "
            "environment (e.g. via a local .env file, see .env.example; never "
            "commit the real key)."
        )
    return map_key


def _parse_date(d) -> date:
    if isinstance(d, date) and not isinstance(d, datetime):
        return d
    if isinstance(d, datetime):
        return d.date()
    return datetime.strptime(str(d), "%Y-%m-%d").date()


def chunk_date_range(start_date, end_date, max_day_range: int = MAX_DAY_RANGE) -> list[tuple[date, date]]:
    """Split [start_date, end_date] (inclusive) into chunks of at most
    max_day_range days each, in order, with no gaps and no overlap.

    Returns a list of (chunk_start, chunk_end) date pairs.
    """
    start = _parse_date(start_date)
    end = _parse_date(end_date)
    if start > end:
        raise ValueError(f"start_date {start} is after end_date {end}.")
    if max_day_range < 1:
        raise ValueError(f"max_day_range must be >= 1, got {max_day_range}.")

    chunks = []
    current = start
    while current <= end:
        chunk_end = min(current + timedelta(days=max_day_range - 1), end)
        chunks.append((current, chunk_end))
        current = chunk_end + timedelta(days=1)
    return chunks


def build_area_csv_url(map_key: str, source: str, west, south, east, north, day_range: int, end_date) -> str:
    """Build one Area CSV API request URL for a single chunk.

    AREA_COORDINATES order is west,south,east,north (confirmed on the live
    FIRMS docs, which explicitly warn this is not the more common
    north/south/east/west ordering).
    """
    area = f"{west},{south},{east},{north}"
    date_str = _parse_date(end_date).strftime("%Y-%m-%d")
    return AREA_CSV_URL_TEMPLATE.format(
        map_key=map_key,
        source=source,
        area=area,
        day_range=day_range,
        date=date_str,
    )


def download_firms(
    map_key: str,
    west: float,
    south: float,
    east: float,
    north: float,
    start_date,
    end_date,
    source: str,
    out_dir: str,
) -> list[Path]:
    """Download FIRMS detections for [start_date, end_date] over the given
    bounding box, chunked into calls no longer than MAX_DAY_RANGE days, and
    write each chunk's raw CSV response into out_dir.

    Parameters
    ----------
    map_key : FIRMS MAP_KEY (pass get_map_key() from the caller, this function
        does not read the environment itself, to keep it testable without env
        state).
    west, south, east, north : bounding box in decimal degrees (note the
        west,south,east,north order the FIRMS API requires).
    start_date, end_date : inclusive date range, "YYYY-MM-DD" strings or
        datetime.date objects.
    source : a FIRMS Area API source, e.g. "VIIRS_SNPP_SP" or "VIIRS_NOAA20_NRT".
    out_dir : directory to write raw CSV files into (created if missing).

    Returns
    -------
    List of paths written, one per date chunk, in chronological order.
    """
    out_path = Path(out_dir)
    out_path.mkdir(parents=True, exist_ok=True)

    written = []
    for chunk_start, chunk_end in chunk_date_range(start_date, end_date):
        day_range = (chunk_end - chunk_start).days + 1
        url = build_area_csv_url(map_key, source, west, south, east, north, day_range, chunk_end)

        response = requests.get(url, timeout=60)
        response.raise_for_status()

        filename = (
            f"firms_{source}_{chunk_start.isoformat()}_{chunk_end.isoformat()}.csv"
        )
        chunk_path = out_path / filename
        chunk_path.write_text(response.text, encoding="utf-8")
        written.append(chunk_path)

    return written


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Download raw FIRMS/VIIRS detections via the Area CSV API into data/raw."
    )
    parser.add_argument("--start", required=True, help="Start date, YYYY-MM-DD (inclusive).")
    parser.add_argument("--end", required=True, help="End date, YYYY-MM-DD (inclusive).")
    parser.add_argument(
        "--source",
        default="VIIRS_SNPP_SP",
        help="FIRMS Area API source (default: VIIRS_SNPP_SP; use a *_NRT source for recent dates).",
    )
    parser.add_argument("--out-dir", default="data/raw", help="Directory to write raw CSV files into (default: data/raw).")
    # Cundinamarca bounding box (WGS84 degrees), verified against OpenStreetMap
    # administrative boundary relation 1305533 (admin_level=4, ISO3166-2
    # CO-CUN), https://www.openstreetmap.org/relation/1305533. Overridable
    # for other areas.
    parser.add_argument("--west", type=float, default=-75.10)
    parser.add_argument("--south", type=float, default=3.50)
    parser.add_argument("--east", type=float, default=-72.80)
    parser.add_argument("--north", type=float, default=6.00)
    args = parser.parse_args()

    map_key = get_map_key()
    written = download_firms(
        map_key=map_key,
        west=args.west,
        south=args.south,
        east=args.east,
        north=args.north,
        start_date=args.start,
        end_date=args.end,
        source=args.source,
        out_dir=args.out_dir,
    )
    print(f"Wrote {len(written)} file(s) to {args.out_dir}:")
    for path in written:
        print(f"  {path}")


if __name__ == "__main__":
    main()
