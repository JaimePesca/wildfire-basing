"""Candidate aerial base sites (set I, CLAUDE.md section 4): civil aerodromes
plus military bases.

Two independent sub-sources feed set I, matched to the categories in
sites_schema.py:

1. Civil aerodromes and heliports, Aerocivil AD 1.3 index (category
   "civil_aerodrome"). Verified by actually downloading the file, not just
   reading the landing page:

   - Landing page: https://www.aerocivil.gov.co/documentos/1118/conjunto-de-datos-aip/
     (AIP dataset page, hosts "AD 1.3 Indice de aerodromos no controlados.xlsx",
     a live recurring publication, not a one-off; last shown update
     16/06/2025 at verification time).
   - Direct download (redirect-based, no login): a GET on
     AEROCIVIL_AD13_LOADER_URL below returns HTTP 302 to a short-lived signed
     URL (~1h JWT expiry) which then returns HTTP 200 with the real .xlsx
     (verified: PK zip / "Microsoft Excel 2007+", Content-Disposition
     attachment). requests.get with default redirect-following handles this
     with zero interaction; the idFile= URL is the stable anchor, the signed
     URL it redirects to is not stable or cacheable and regenerates per hit.
   - Content actually inspected (openpyxl): single sheet "Hoja1", 835 data
     rows. Column B combines free-text name and 4-letter ICAO indicator in
     one cell (e.g. "ACANDI / SKAD"). Column F holds coordinates as DMS text,
     e.g. "082953.76N\\n0771626.45W", occasionally with extra remarks text
     appended in the same cell, which breaks a naive split and needs a
     regex search, not a clean parse. There is no department/municipality
     column and no separate decimal lat/lon columns.
   - No dataset-specific license or terms are shown on the AIP dataset page;
     only a generic footer link to a copyright policy. License is left None
     here, not guessed.
   - Caveat carried into load_aerocivil_aerodromes: this file alone does not
     carry a Cundinamarca boundary. A bounding-box filter (CUNDINAMARCA_BBOX,
     the same box firms_download.py uses) is offered as a convenience, but it
     is coordinate-bbox filtering, not a real point-in-polygon join against a
     DIVIPOLA/IGAC boundary, so it can include slivers of neighboring
     departments and is not a substitute for that join. Name-based filtering
     was tried during verification and found unsafe: this same file has a
     "MOSQUERA/SKSQ" at 02.5N/78.25W (Narino) and a "SAN RAFAEL/SKFA" at
     02.14N/75.65W (Putumayo), both far from the Cundinamarca places sharing
     those names. Do not filter on name alone.

2. Military bases (category "military_base"). PDF scraping of AIP AD 2
   aeronautical charts is explicitly out of scope (fragile, per task spec).
   Instead this module reads data/raw/military_bases_template.csv, a manual
   entry template pre-populated with the one base independently verified
   during this research pass:

   - CACOM-4 Melgar (Base Aerea TC Luis Francisco Pinto Parra, ICAO SKME),
     Comando Aereo de Combate No. 4, Fuerza Aeroespacial Colombiana. FAC's
     own page (https://www.fac.mil.co/cacom4) states the address as
     "Km 1 via Melgar - Bogota, Melgar, Tolima" -- administratively in
     Tolima, near the Cundinamarca border, not inside Cundinamarca.
     OurAirports mis-tags this airport's region as Cundinamarca (a
     community-maintained, non-authoritative field); do not trust that field.
     Coordinates 4.21644 N, -74.63500 W (elevation 313 m) are cross-verified
     across four independent sources that all agree: Spanish Wikipedia,
     English Wikipedia (citing DAFIF/World Aero Data, Great Circle Mapper,
     Google Maps, archived FAC/CACOM-4 pages), SkyVector, Great Circle
     Mapper, OpenNav, and OurAirports' public CSV. No authoritative
     Colombian government AD 2 chart coordinate was found for SKME; the
     public no-login AD 2 "AERODROMOS AVIACION DE ESTADO" page at
     https://www.aerocivil.gov.co/proveedor_servicios/publicaciones/3572/
     aip-publicacion-de-informacion-aeronautica/ lists exactly six state
     aerodromes (SKUA, SKPQ, SKTQ, SKAP, SKGB, SKJC) and Melgar/SKME is not
     one of them. Treat this coordinate as well-sourced by convergence of
     independent aviation databases, not as primary-government-sourced.
   - SKPQ Palanquero (CT. German Olano, Puerto Salgar, Cundinamarca) IS one
     of the six official AD 2 state aerodromes and is genuinely in
     Cundinamarca, but its coordinate was not independently fetched during
     this pass (the AD 2 PDF was located, not opened and parsed here); it is
     left as an empty template row rather than a guessed value.
   - All other candidate military bases: left as empty template rows, for
     manual completion, since blind PDF scraping is out of scope and no
     other base's coordinates were independently verified in this pass.

Fixed costs (cost_base[i], CLAUDE.md section 4) are never fabricated here;
see sites_schema.py module docstring.
"""

from __future__ import annotations

import argparse
import re
import time
from pathlib import Path

import pandas as pd
import requests

from .sites_schema import (
    CATEGORY_CIVIL_AERODROME,
    CATEGORY_MILITARY_BASE,
    assemble_candidate_sites,
)

# --- Aerocivil AD 1.3 (civil aerodromes / heliports) ------------------------

AEROCIVIL_LANDING_URL = "https://www.aerocivil.gov.co/documentos/1118/conjunto-de-datos-aip/"
AEROCIVIL_AD13_LOADER_URL = (
    "https://www.aerocivil.gov.co/loader.php?lServicio=Tools2&lTipo=descargas"
    "&lFuncion=descargar&idFile=25010"
)
AEROCIVIL_SOURCE_NAME = "Aerocivil AD 1.3 Indice de aerodromos no controlados"
# Last shown "update" date on the landing page at verification time
# (16/06/2025); this is a recurring live publication, not a fixed-vintage
# dataset, so treat this as "best known snapshot year", not an edition year.
AEROCIVIL_SOURCE_YEAR = 2025

# Cundinamarca bounding box (WGS84 degrees), the same box firms_download.py
# uses, verified there against OpenStreetMap administrative boundary
# relation 1305533 (admin_level=4, ISO3166-2 CO-CUN). See module docstring:
# this is a coordinate bbox, not an administrative polygon join.
CUNDINAMARCA_BBOX = (-75.10, 3.50, -72.80, 6.00)  # west, south, east, north

_LAT_DMS_RE = re.compile(r"(\d{2})(\d{2})(\d{2}(?:\.\d+)?)\s*([NS])")
_LON_DMS_RE = re.compile(r"(\d{3})(\d{2})(\d{2}(?:\.\d+)?)\s*([EW])")


AEROCIVIL_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"
)


def download_aerocivil_ad13(out_path: str, timeout: int = 120, attempts: int = 4) -> Path:
    """Download the AD 1.3 index xlsx via the verified redirect chain.

    A plain GET on AEROCIVIL_AD13_LOADER_URL 302s to a short-lived signed
    URL; requests follows that redirect by default and this function writes
    whatever bytes come back. Raises via response.raise_for_status() on the
    final failed attempt rather than silently writing an error page.

    Two failure modes confirmed empirically (2026-08-18), not assumed: (1)
    the default requests User-Agent ("python-requests/...") gets a bare 403
    from this endpoint, a browser-like User-Agent is required; (2) even with
    that, the endpoint intermittently returns a transient
    {"detail":"Error interno del servidor"} 500 that succeeds on a bare
    retry a few seconds later (confirmed: same 59868-byte file on repeated
    successful attempts). Retry a handful of times with a short backoff
    before giving up, rather than failing on the first transient 500.
    """
    headers = {"User-Agent": AEROCIVIL_USER_AGENT}
    last_error: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            response = requests.get(
                AEROCIVIL_AD13_LOADER_URL, timeout=timeout, allow_redirects=True, headers=headers
            )
            response.raise_for_status()
            out = Path(out_path)
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_bytes(response.content)
            return out
        except requests.exceptions.HTTPError as exc:
            last_error = exc
            if attempt < attempts:
                time.sleep(3 * attempt)
    raise RuntimeError(
        f"Aerocivil AD 1.3 download failed after {attempts} attempts, last error: {last_error}"
    ) from last_error


def _dms_to_decimal(deg: str, minutes: str, seconds: str, hemisphere: str) -> float:
    value = float(deg) + float(minutes) / 60.0 + float(seconds) / 3600.0
    if hemisphere in ("S", "W"):
        value = -value
    return value


def parse_dms_cell(cell) -> tuple[float | None, float | None]:
    """Extract (lat, lon) decimal degrees from an AD 1.3 column-F style cell.

    Searches for the lat and lon DMS patterns anywhere in the cell text
    (rather than requiring an exact full-cell match), since real cells
    sometimes carry extra remarks text appended after the coordinates. A
    2-digit degree group is latitude, a 3-digit degree group is longitude;
    this disambiguates the two without relying on cell layout (newline
    position, ordering).
    """
    text = "" if cell is None else str(cell)
    lat_match = _LAT_DMS_RE.search(text)
    lon_match = _LON_DMS_RE.search(text)
    lat = _dms_to_decimal(*lat_match.groups()) if lat_match else None
    lon = _dms_to_decimal(*lon_match.groups()) if lon_match else None
    return lat, lon


def split_name_icao(cell) -> tuple[str | None, str | None]:
    """Split an AD 1.3 column-B style cell into (name, icao_code).

    Cell format is free text name, a slash, and a 4-letter ICAO location
    indicator, with inconsistent whitespace/newlines around the slash (e.g.
    "ACANDI / SKAD"). Whitespace (including newlines) is collapsed first,
    then the cell is split on the last "/", since the name itself never
    contains a slash but is otherwise unconstrained free text.
    """
    if cell is None:
        return None, None
    normalized = " ".join(str(cell).split())
    if not normalized:
        return None, None
    if "/" not in normalized:
        return normalized, None
    name_part, _, code_part = normalized.rpartition("/")
    name = name_part.strip() or None
    code = code_part.strip() or None
    return name, code


def parse_aerocivil_aerodromes(path: str) -> list[dict]:
    """Parse a locally-saved AD 1.3 xlsx into raw candidate-site dicts.

    Reads sheet "Hoja1" with no assumed header row: the exact number of
    title/header rows above the data was not independently verified in this
    pass, so instead of hardcoding a skiprows count, every row is attempted
    and rows whose column-F cell does not contain a parseable DMS coordinate
    pair (title rows, header rows, blank rows) are silently skipped. This is
    a disclosed design choice, not a silent assumption: verify against a
    real downloaded copy if the skipped-row count looks wrong.

    Columns used, by position (0-indexed): B (index 1) name/ICAO, C (index
    2) INTL/NTL, D (index 3) IFR/VFR, E (index 4) traffic-type code, F
    (index 5) DMS coordinates. Traffic-type "M" (military) rows are still
    returned with category civil_aerodrome, since they come from Aerocivil's
    civil aerodrome registry, not the FAC military base list; the
    traffic-type code is preserved in the "notes" field so callers can filter
    on it if they want to.
    """
    df = pd.read_excel(path, sheet_name="Hoja1", header=None, engine="openpyxl")

    records = []
    for _, row in df.iterrows():
        if len(row) <= 5:
            continue
        name, icao = split_name_icao(row.iloc[1])
        lat, lon = parse_dms_cell(row.iloc[5])
        if lat is None or lon is None:
            continue  # header/title/blank row, not a data row

        intl_ntl = row.iloc[2] if len(row) > 2 else None
        ifr_vfr = row.iloc[3] if len(row) > 3 else None
        traffic_type = row.iloc[4] if len(row) > 4 else None

        site_id = f"aero_{icao}" if icao else f"aero_{re.sub(r'[^A-Za-z0-9]+', '_', str(name)).strip('_').lower()}"

        records.append(
            {
                "site_id": site_id,
                "name": name,
                "lat": lat,
                "lon": lon,
                "category": CATEGORY_CIVIL_AERODROME,
                "source_name": AEROCIVIL_SOURCE_NAME,
                "source_url": AEROCIVIL_LANDING_URL,
                "source_year": AEROCIVIL_SOURCE_YEAR,
                "license": None,  # no dataset-specific license found, see module docstring
                "notes": (
                    f"icao={icao}; INTL/NTL={intl_ntl}; IFR/VFR={ifr_vfr}; "
                    f"traffic_type={traffic_type}"
                ),
            }
        )
    return records


def load_aerocivil_aerodromes(
    path: str,
    epsg: int,
    bbox: tuple[float, float, float, float] | None = CUNDINAMARCA_BBOX,
) -> pd.DataFrame:
    """Parse the AD 1.3 xlsx and return it in the unified candidate-site schema.

    bbox, if given, is (west, south, east, north) and filters to rows whose
    lat/lon fall inside it; pass None to skip filtering and return all 835
    rows. See module docstring for why this is a coordinate bbox, not an
    administrative boundary join, and should not be treated as a final
    Cundinamarca-only list.
    """
    records = parse_aerocivil_aerodromes(path)
    if bbox is not None:
        west, south, east, north = bbox
        records = [r for r in records if west <= r["lon"] <= east and south <= r["lat"] <= north]
    if not records:
        from .sites_schema import empty_candidate_sites

        return empty_candidate_sites()
    return assemble_candidate_sites(records, epsg=epsg)


# --- Military bases (manual-entry template) ---------------------------------

MILITARY_BASES_TEMPLATE_COLUMNS = ["name", "lat", "lon", "source", "source_year", "notes"]
MILITARY_SOURCE_NAME = "manual entry (military bases template)"

_URL_RE = re.compile(r"https?://\S+")


def load_military_bases(path: str, epsg: int) -> pd.DataFrame:
    """Read data/raw/military_bases_template.csv and return it in the unified schema.

    Rows with a blank lat or lon are treated as not-yet-completed template
    rows and are skipped (not an error): this file is meant to be filled in
    over time, one verified base per row. See sites_bases.py module
    docstring for which row is pre-populated and why, and CLAUDE.md hard
    rule: never fill a blank row with a guessed coordinate.
    """
    df = pd.read_csv(path, dtype=str, keep_default_na=False)
    missing = [c for c in MILITARY_BASES_TEMPLATE_COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(
            f"military bases CSV at {path} is missing required columns: {missing}; "
            f"expected {MILITARY_BASES_TEMPLATE_COLUMNS}."
        )

    records = []
    for i, row in df.iterrows():
        lat_str = str(row["lat"]).strip()
        lon_str = str(row["lon"]).strip()
        if not lat_str or not lon_str:
            continue  # unfilled template row, not a data row

        source_text = str(row["source"]).strip() or None
        url_match = _URL_RE.search(source_text) if source_text else None
        source_year = str(row["source_year"]).strip() or None

        name = str(row["name"]).strip() or None
        site_id = "mil_" + (re.sub(r"[^A-Za-z0-9]+", "_", name).strip("_").lower() if name else f"row{i}")

        records.append(
            {
                "site_id": site_id,
                "name": name,
                "lat": float(lat_str),
                "lon": float(lon_str),
                "category": CATEGORY_MILITARY_BASE,
                "source_name": MILITARY_SOURCE_NAME,
                "source_url": url_match.group(0) if url_match else None,
                "source_year": source_year,
                "license": None,
                "notes": f"source={source_text}; " + str(row.get("notes", "")).strip(),
            }
        )

    if not records:
        from .sites_schema import empty_candidate_sites

        return empty_candidate_sites()
    return assemble_candidate_sites(records, epsg=epsg)


# --- Combine -----------------------------------------------------------------


def build_candidate_bases(
    aerocivil_xlsx_path: str,
    military_csv_path: str,
    epsg: int,
    bbox: tuple[float, float, float, float] | None = CUNDINAMARCA_BBOX,
) -> pd.DataFrame:
    """Combine the Aerocivil and military-bases loaders into one candidate-base table.

    Returns the unified candidate-site schema (sites_schema.py), category
    civil_aerodrome or military_base, covering set I (CLAUDE.md section 4).
    """
    aerocivil_df = load_aerocivil_aerodromes(aerocivil_xlsx_path, epsg=epsg, bbox=bbox)
    military_df = load_military_bases(military_csv_path, epsg=epsg)
    return pd.concat([aerocivil_df, military_df], ignore_index=True)


# --- CLI ----------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Download and/or build the candidate aerial base table (set I)."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    download_parser = subparsers.add_parser(
        "download", help="Download the Aerocivil AD 1.3 xlsx into data/raw."
    )
    download_parser.add_argument(
        "--out",
        default="data/raw/aerocivil_ad13_aerodromos.xlsx",
        help="Path to write the downloaded xlsx to (default: data/raw/aerocivil_ad13_aerodromos.xlsx).",
    )

    build_parser = subparsers.add_parser(
        "build", help="Parse a locally-downloaded AD 1.3 xlsx plus the military bases CSV into one candidate-base table."
    )
    build_parser.add_argument("--aerocivil-xlsx", required=True, help="Path to a locally-downloaded AD 1.3 xlsx.")
    build_parser.add_argument(
        "--military-csv",
        default="data/raw/military_bases_template.csv",
        help="Path to the military bases CSV (default: data/raw/military_bases_template.csv).",
    )
    build_parser.add_argument("--out", default="data/processed/candidate_bases.csv", help="Output CSV path.")
    build_parser.add_argument("--epsg", type=int, default=9377, help="Projected CRS EPSG code (default: 9377).")
    build_parser.add_argument(
        "--no-bbox-filter",
        action="store_true",
        help="Do not filter Aerocivil rows to the Cundinamarca bounding box (returns all 835 rows).",
    )

    args = parser.parse_args()

    if args.command == "download":
        out = download_aerocivil_ad13(args.out)
        print(f"Wrote {out}")
    elif args.command == "build":
        bbox = None if args.no_bbox_filter else CUNDINAMARCA_BBOX
        combined = build_candidate_bases(
            args.aerocivil_xlsx, args.military_csv, epsg=args.epsg, bbox=bbox
        )
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        combined.to_csv(out, index=False)
        print(f"Wrote {len(combined)} candidate base records to {out}")


if __name__ == "__main__":
    main()
