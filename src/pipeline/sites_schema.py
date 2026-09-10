"""Unified candidate-site record schema for bases (set I) and water points (set K).

CLAUDE.md section 6 defines the Event record and Scenario record schemas but
does not yet define a schema for candidate first-stage sites. This module is
that missing contract: every loader in sites_bases.py and sites_water.py must
return a DataFrame with exactly these columns, in this order.

Candidate site record
----------------------
- site_id : stable string identifier, unique within a category, built by the
  loader from a real source key (e.g. the ICAO indicator, or an OSM
  type/id pair), never an arbitrary row index alone.
- name : site name as given by the source. None (not a guess) if the source
  does not carry a usable name.
- lat, lon : decimal degrees, WGS84 (EPSG:4326).
- x_utm, y_utm : projected meters, using the CRS configured in
  config/parameters.yaml (crs.epsg, currently EPSG:9377, MAGNA-SIRGAS 2018 /
  Origen-Nacional CTM12). Computed by reusing src/pipeline/project.py, the
  same reprojection the fire-event pipeline uses, so bases, water points and
  fire events all live in one consistent metric CRS. Never reprojected ad hoc
  with a different EPSG in a loader.
- category : one of "civil_aerodrome", "military_base", "water_body"
  (CANDIDATE_SITE_CATEGORIES below). This is a loader-level tag, not itself a
  first-stage decision; set I (bases, CLAUDE.md section 4) is the union of
  civil_aerodrome and military_base rows, set K (water_points) is the
  water_body rows.
- source_name : short human-readable name of the dataset/agency the row came
  from (e.g. "Aerocivil AD 1.3 Indice de aerodromos no controlados").
- source_url : the real URL the row was fetched from or documented against.
  Never left as a guess; None only if a row is an explicit manual-entry
  placeholder that has not been filled in yet.
- source_year : the year the underlying data was published, last updated, or
  fetched, whichever is the best-verified vintage marker documented by the
  loader's own docstring. None if not established.
- license : the license string as verified against the source (e.g.
  "CC BY-SA 4.0", "ODbL 1.0"). None if no license was found or verified, never
  guessed. A None here means "unknown", not "public domain" or "no
  restriction".
- notes : free text. Loaders use this for caveats that apply to one specific
  row (provenance detail, cross-check disagreement, "TODO: manual entry
  pending", coordinate source when more than one candidate coordinate exists).

Explicitly out of scope for this schema: cost_base[i] and cost_water[k]
(CLAUDE.md section 4). No per-site source was found under CLAUDE.md
section 8; DECIDED 2026-08-30 (section 3/8/10) to treat both as swept
sensitivity parameters, uniform across sites, see src/model/costs.py. This
module still does not fabricate a per-site cost, and no loader in
sites_bases.py or sites_water.py should add one.
"""

from __future__ import annotations

from typing import Iterable, Mapping

import pandas as pd

from .project import project_to_crs

CATEGORY_CIVIL_AERODROME = "civil_aerodrome"
CATEGORY_MILITARY_BASE = "military_base"
CATEGORY_WATER_BODY = "water_body"

CANDIDATE_SITE_CATEGORIES = frozenset(
    {CATEGORY_CIVIL_AERODROME, CATEGORY_MILITARY_BASE, CATEGORY_WATER_BODY}
)

CANDIDATE_SITE_COLUMNS = [
    "site_id",
    "name",
    "lat",
    "lon",
    "x_utm",
    "y_utm",
    "category",
    "source_name",
    "source_url",
    "source_year",
    "license",
    "notes",
]

# Fields a loader must supply before reprojection; x_utm/y_utm are derived.
_INPUT_FIELDS = [c for c in CANDIDATE_SITE_COLUMNS if c not in ("x_utm", "y_utm")]


def assemble_candidate_sites(records: Iterable[Mapping], epsg: int) -> pd.DataFrame:
    """Turn a list of per-site dicts into the canonical candidate-site DataFrame.

    Each record must at least have "lat", "lon" and "category" (category must
    be one of CANDIDATE_SITE_CATEGORIES); any other missing field in
    CANDIDATE_SITE_COLUMNS is filled with None rather than raising, so a
    loader can supply a partial dict for a manual-entry placeholder row.

    Reprojects lat/lon to x_utm/y_utm via project.project_to_crs (the same
    function the fire-event pipeline uses), so this is the single place all
    candidate-site loaders compute their metric coordinates, EXCEPT when a
    record already carries both x_utm and y_utm (not None): a loader whose
    source data was already in a metric CRS (e.g. load_igac_water_bodies,
    which takes a centroid in metric space and only derives lat/lon for the
    schema, via project.project_from_crs) can pass those through here as-is,
    rather than forcing an unnecessary forward-project/inverse-project/
    forward-project round trip. A batch must be homogeneous: either every
    record supplies x_utm/y_utm, or none do.

    Raises ValueError if records is empty (call the loader, not this
    function, on an empty result; an empty DataFrame with the right columns
    still needs at least the schema, use empty_candidate_sites() for that),
    if any record has an invalid category, or if a batch mixes precomputed
    and non-precomputed x_utm/y_utm.
    """
    records = list(records)
    if not records:
        raise ValueError(
            "assemble_candidate_sites received no records; use "
            "empty_candidate_sites() if you need an empty, schema-correct "
            "DataFrame instead."
        )

    rows = []
    for rec in records:
        category = rec.get("category")
        if category not in CANDIDATE_SITE_CATEGORIES:
            raise ValueError(
                f"invalid category {category!r}; must be one of "
                f"{sorted(CANDIDATE_SITE_CATEGORIES)}"
            )
        if rec.get("lat") is None or rec.get("lon") is None:
            raise ValueError(f"record for site {rec.get('site_id')!r} is missing lat/lon")
        row = {field: rec.get(field) for field in _INPUT_FIELDS}
        row["x_utm"] = rec.get("x_utm")
        row["y_utm"] = rec.get("y_utm")
        rows.append(row)

    df = pd.DataFrame(rows, columns=_INPUT_FIELDS + ["x_utm", "y_utm"])

    has_metric = df["x_utm"].notna() & df["y_utm"].notna()
    if has_metric.all():
        pass  # every record already carries verified metric coordinates
    elif has_metric.any():
        raise ValueError(
            "assemble_candidate_sites received a mixed batch: some records "
            "carry precomputed x_utm/y_utm and some do not. Pass a "
            "homogeneous batch (all precomputed, in this same epsg, or none) "
            "so it is unambiguous which coordinates were actually reprojected."
        )
    else:
        df = project_to_crs(df, epsg=epsg, lon_col="lon", lat_col="lat")

    return df[CANDIDATE_SITE_COLUMNS].reset_index(drop=True)


def empty_candidate_sites() -> pd.DataFrame:
    """An empty DataFrame with exactly the candidate-site schema columns."""
    return pd.DataFrame(columns=CANDIDATE_SITE_COLUMNS)
