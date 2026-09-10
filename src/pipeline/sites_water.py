"""Candidate water refill point sites (set K, CLAUDE.md section 4).

Two independent sub-sources, both categorized "water_body" in the unified
candidate-site schema (sites_schema.py):

1. OpenStreetMap, via the Overpass API (load_osm_water_bodies). Fully
   scriptable, verified with real POST queries against a live Overpass
   endpoint, not just a read of the docs.

   Query pattern (bbox order for Overpass QL is south,west,north,east, the
   opposite convention from the FIRMS Area API used in firms_download.py;
   build_overpass_query below takes the same west/south/east/north argument
   order as the rest of this repo and reorders internally):

       [out:json][timeout:180];
       (
         node["natural"="water"]["name"](south,west,north,east);
         way["natural"="water"]["name"](south,west,north,east);
         relation["natural"="water"]["name"](south,west,north,east);
         node["water"="reservoir"]["name"](south,west,north,east);
         way["water"="reservoir"]["name"](south,west,north,east);
         relation["water"="reservoir"]["name"](south,west,north,east);
         node["landuse"="reservoir"]["name"](south,west,north,east);
         way["landuse"="reservoir"]["name"](south,west,north,east);
         relation["landuse"="reservoir"]["name"](south,west,north,east);
       );
       out center;

   Confirmed against the Cundinamarca bounding box (the same box used in
   firms_download.py and sites_bases.py): HTTP 200, 424 named water elements,
   ~59s wall time, including relation 4000410 "Embalse de San Rafael" at
   4.7020511, -73.9922274 (the expected La Calera reservoir) and other named
   features (Laguna Chingaza, Represa del Chivor, Lago de La Florida, Embalse
   La Copa, Sochagota, Siecha Lakes).

   Two operational caveats found empirically, both reflected below:
   - The declared [timeout:] must be set well above the expected wall-clock
     runtime, not just above the HTTP client timeout: a [timeout:60] query
     that needed ~59s of real Overpass-side work failed with "Query timed
     out"; [timeout:180] succeeded. DEFAULT_OVERPASS_TIMEOUT_S below is the
     value actually confirmed to work, not a guess.
   - The main instance (overpass-api.de) intermittently returned HTTP 406 on
     repeated requests in the same session, while the community mirror
     overpass.openstreetmap.fr answered every request with HTTP 200 on the
     identical query. DEFAULT_OVERPASS_ENDPOINT below is the .fr mirror for
     that reason; overpass-api.de is offered as an explicit fallback
     argument, not the default.

   Fair-use norms (OSM wiki, Overpass_API page, corroborated by the observed
   406 behavior): roughly under 10,000 queries/day and under 1 GB/day, and a
   real identifying User-Agent expected on requests. OSM_USER_AGENT below
   sets one; do not strip it.

   License: OpenStreetMap data is published under the Open Data Commons Open
   Database License (ODbL) by the OpenStreetMap Foundation (OSMF); verified
   directly against https://www.openstreetmap.org/copyright ("OpenStreetMap
   is open data, licensed under the Open Data Commons Open Database License
   (ODbL) by the OpenStreetMap Foundation (OSMF)"), not assumed from memory.

2. CAR (Corporacion Autonoma Regional de Cundinamarca) ArcGIS REST service
   (load_car_lagunas). Fully scriptable, found and verified live 2026-08-18
   after IGAC's national bundle turned out to be undownloadable (see item 3
   below): CAR is the actual regional environmental authority for
   Cundinamarca, not a national agency, so its own water layer is already
   scoped close to the area this project needs, with no national-bundle size
   problem.

   Service root: https://sig.car.gov.co/arcgis/rest/services/visor/Agua1/MapServer
   ("Capas con informacion relacionada con el recurso Agua"). Layer 112,
   "Laguna" (polygon), is the one used here; confirmed live via
   MapServer/112/query?returnCountOnly=true: 5024 features. Standard ArcGIS
   REST query API, confirmed to support outSR (server-side reprojection,
   tested directly with outSR=9377, this project's configured CRS, returning
   valid GeoJSON in that CRS) and pagination (maxRecordCount=2000, confirmed
   from the service's own JSON descriptor; load_car_lagunas below pages
   through resultOffset until the full count is retrieved).

   Name field is "NMG" (only 118 of 5024 features have a non-blank value,
   the rest are "" or whitespace-only, confirmed by a live query; treat a
   blank/whitespace NMG as no name, not literally an empty string). A search
   for "RAFAEL" in NMG returned zero rows: this layer does not include the
   San Rafael reservoir (likely operated by Bogota's water utility, EAB, not
   CAR), so it complements load_osm_water_bodies rather than replacing it.

   License: NOT independently confirmed against a primary CAR source page.
   The MapServer's own copyrightText field is empty. A web search suggested
   CAR Cundinamarca's open geographic data is CC BY 4.0, but no primary CAR
   page stating this was directly read in this session, so CAR_LICENSE below
   is left None (per sites_schema.py: None means unknown, never guessed),
   not filled in from that secondary claim.

3. IGAC "Capa Digital Cuerpos de Agua", 1:100.000 (load_igac_water_bodies).
   NOT scriptable: substantial effort went into finding a working WFS or
   direct-download URL and none was found (the metadata record declares WFS
   availability but its own download-linkage field is empty; geoportal.igac.
   gov.co returned ECONNREFUSED from this environment on every attempt; an
   ArcGIS Hub item that looked promising ("IGAC-OIT::cuerpos-de-agua")
   resolves to an unrelated 2024 hydrometeorological-hazard product, not this
   layer; IGAC's own ArcGIS Server has no 1:100.000 water-bodies service,
   only an unrelated _500k variant). No WFS endpoint is fabricated here. This
   loader instead reads a local vector file (Shapefile/GPKG/GDB) that a user
   must obtain manually from geoportal.igac.gov.co's "Buscador de Datos
   Abiertos" search tool (see the README for the exact path), and requires
   geopandas/pyogrio/fiona (added to requirements.txt for this module).

   License/year/scale/holder, verified against the record's ISO-19139 XML
   (https://metadatos.icde.gov.co/geonetwork/srv/api/records/
   2ae17c2c-b793-4463-815c-76f36c2564de/formatters/xml): Creative Commons
   Reconocimiento-CompartirIgual 4.0 Internacional (CC BY-SA 4.0); data
   created 2020, metadata last refreshed 2025-12-19; scale 1:100.000; holder
   Instituto Geografico Agustin Codazzi (IGAC), Subdireccion de Geografia y
   Cartografia. CC BY-SA is share-alike (attribution plus identical-terms
   redistribution), not public domain.

   The exact attribute schema of the real file (in particular, which column
   holds a name) was never independently confirmed, since no working
   download was found. load_igac_water_bodies searches a short list of
   plausible column names and leaves "name" as None, not guessed, if none of
   them is present; see its docstring.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import requests

from .project import project_from_crs
from .sites_schema import CATEGORY_WATER_BODY, assemble_candidate_sites, empty_candidate_sites

# --- OpenStreetMap / Overpass -------------------------------------------------

DEFAULT_OVERPASS_ENDPOINT = "https://overpass.openstreetmap.fr/api/interpreter"
FALLBACK_OVERPASS_ENDPOINT = "https://overpass-api.de/api/interpreter"

# Confirmed empirically: 60s was not enough for a full Cundinamarca-bbox
# 9-branch union query (~59s of actual Overpass-side work); 180s succeeded.
DEFAULT_OVERPASS_TIMEOUT_S = 180
# HTTP client timeout must exceed the declared Overpass-side timeout.
DEFAULT_HTTP_TIMEOUT_S = 220

OSM_SOURCE_NAME = "OpenStreetMap"
OSM_LICENSE = "ODbL 1.0"  # verified against https://www.openstreetmap.org/copyright

# Overpass fair-use norms (OSM wiki) expect a real identifying User-Agent.
OSM_USER_AGENT = "wildfire-basing-research/0.1 (+contact: jaime.e.pesca.s@gmail.com)"

_WATER_TAG_BRANCHES = [
    ('natural', 'water'),
    ('water', 'reservoir'),
    ('landuse', 'reservoir'),
]
_ELEMENT_TYPES = ("node", "way", "relation")


def build_overpass_query(
    west: float, south: float, east: float, north: float, timeout_s: int = DEFAULT_OVERPASS_TIMEOUT_S
) -> str:
    """Build the verified named-water-body Overpass QL query for a bbox.

    Overpass QL bbox order is (south, west, north, east); west/south/east/
    north is this repo's own convention (matches firms_download.py), so the
    reordering happens here, once, rather than at every call site.
    """
    bbox = f"{south},{west},{north},{east}"
    lines = [f"[out:json][timeout:{timeout_s}];", "("]
    for key, value in _WATER_TAG_BRANCHES:
        for elem_type in _ELEMENT_TYPES:
            lines.append(f'  {elem_type}["{key}"="{value}"]["name"]({bbox});')
    lines.append(");")
    lines.append("out center;")
    return "\n".join(lines)


class OverpassQueryError(RuntimeError):
    """Raised when an Overpass API response signals a server-side failure.

    Overpass can return HTTP 200 (so requests' raise_for_status() passes)
    while the query itself failed server-side, e.g. on a timeout; the
    failure then shows up only as a "remark" field in the JSON body, with
    "elements" missing or empty. Confirmed empirically (module docstring): a
    too-short [timeout:] produced exactly this response shape. That is a
    real error, not "zero water bodies found", and must not be silently
    treated as an empty result.
    """


def query_overpass(
    query: str,
    endpoint: str = DEFAULT_OVERPASS_ENDPOINT,
    http_timeout_s: int = DEFAULT_HTTP_TIMEOUT_S,
) -> dict:
    """POST an Overpass QL query and return the parsed JSON response.

    Raises OverpassQueryError if the response body carries a "remark" field
    (Overpass's own error/timeout channel, distinct from the HTTP status) or
    has no "elements" key at all; see OverpassQueryError.
    """
    response = requests.post(
        endpoint,
        data={"data": query},
        headers={"User-Agent": OSM_USER_AGENT},
        timeout=http_timeout_s,
    )
    response.raise_for_status()
    payload = response.json()

    remark = payload.get("remark")
    if remark:
        raise OverpassQueryError(
            "Overpass API returned HTTP 200 but the response body carries a "
            f"'remark' field, its error/timeout channel: {remark!r}. This is "
            "not '0 water bodies found'; increase timeout_s (see "
            "DEFAULT_OVERPASS_TIMEOUT_S, and note the declared [timeout:] "
            "must exceed the actual wall-clock time, not just the HTTP "
            "client timeout) or otherwise resolve the underlying issue "
            "before retrying."
        )
    if "elements" not in payload:
        raise OverpassQueryError(
            "Overpass API response has no 'elements' key and no 'remark' "
            f"field either; unexpected response shape, refusing to treat "
            f"this as zero results: {payload!r}"
        )
    return payload


def _element_lat_lon(element: dict) -> tuple[float | None, float | None]:
    if element.get("type") == "node":
        return element.get("lat"), element.get("lon")
    center = element.get("center") or {}
    return center.get("lat"), center.get("lon")


def parse_overpass_elements(elements: list[dict], source_year: int | None = None) -> list[dict]:
    """Turn raw Overpass "elements" (from an ["out:json"] response) into
    raw candidate-site dicts (category water_body).

    Nodes carry lat/lon directly; ways and relations carry a "center"
    lat/lon because the query uses "out center;" rather than full geometry.
    Elements without a resolvable lat/lon (should not happen given "out
    center;", but checked rather than assumed) are skipped.
    """
    records = []
    for el in elements:
        lat, lon = _element_lat_lon(el)
        if lat is None or lon is None:
            continue
        tags = el.get("tags", {}) or {}
        name = tags.get("name")
        elem_type = el.get("type")
        elem_id = el.get("id")
        water_kind = tags.get("water") or tags.get("natural") or tags.get("landuse")
        records.append(
            {
                "site_id": f"osm_{elem_type}_{elem_id}",
                "name": name,
                "lat": float(lat),
                "lon": float(lon),
                "category": CATEGORY_WATER_BODY,
                "source_name": OSM_SOURCE_NAME,
                "source_url": f"https://www.openstreetmap.org/{elem_type}/{elem_id}",
                "source_year": source_year,
                "license": OSM_LICENSE,
                "notes": f"osm_tag={water_kind}; wikidata={tags.get('wikidata')}",
            }
        )
    return records


def load_osm_water_bodies(
    west: float,
    south: float,
    east: float,
    north: float,
    epsg: int,
    endpoint: str = DEFAULT_OVERPASS_ENDPOINT,
    timeout_s: int = DEFAULT_OVERPASS_TIMEOUT_S,
) -> pd.DataFrame:
    """Query Overpass for named water bodies in a bbox and return the unified schema.

    source_year is set to the UTC year the query was actually run: OSM data
    has no single publication vintage (it is continuously edited), so the
    fetch date is the best-verified vintage marker available, not a guess at
    an edition year.
    """
    query = build_overpass_query(west, south, east, north, timeout_s=timeout_s)
    response = query_overpass(query, endpoint=endpoint, http_timeout_s=timeout_s + 40)
    fetch_year = datetime.now(timezone.utc).year
    records = parse_overpass_elements(response.get("elements", []), source_year=fetch_year)
    if not records:
        return empty_candidate_sites()
    return assemble_candidate_sites(records, epsg=epsg)


# --- CAR (Corporacion Autonoma Regional de Cundinamarca) ArcGIS REST --------

CAR_AGUA_MAPSERVER = "https://sig.car.gov.co/arcgis/rest/services/visor/Agua1/MapServer"
CAR_LAGUNA_LAYER_ID = 112
CAR_LAGUNA_LAYER_URL = f"{CAR_AGUA_MAPSERVER}/{CAR_LAGUNA_LAYER_ID}"
CAR_SOURCE_NAME = "CAR (Corporacion Autonoma Regional de Cundinamarca), capa Laguna"
# See module docstring: not independently confirmed, left None rather than
# filled in from an unverified secondary claim.
CAR_LICENSE = None
# Confirmed live 2026-08-18 via the MapServer's own JSON descriptor.
DEFAULT_CAR_PAGE_SIZE = 2000
CAR_USER_AGENT = OSM_USER_AGENT


def query_car_feature_count(layer_url: str = CAR_LAGUNA_LAYER_URL, http_timeout_s: int = 60) -> int:
    """Return the total feature count for a CAR ArcGIS layer (returnCountOnly)."""
    response = requests.get(
        f"{layer_url}/query",
        params={"where": "1=1", "returnCountOnly": "true", "f": "json"},
        headers={"User-Agent": CAR_USER_AGENT},
        timeout=http_timeout_s,
    )
    response.raise_for_status()
    payload = response.json()
    if "count" not in payload:
        raise RuntimeError(
            f"Unexpected response querying feature count from {layer_url}: {payload!r}"
        )
    return int(payload["count"])


def query_car_feature_page(
    layer_url: str,
    epsg: int,
    offset: int,
    page_size: int = DEFAULT_CAR_PAGE_SIZE,
    http_timeout_s: int = 60,
) -> list[dict]:
    """Fetch one page of features as GeoJSON, already reprojected to epsg server-side."""
    params = {
        "where": "1=1",
        "outFields": "*",
        "outSR": epsg,
        "f": "geojson",
        "resultRecordCount": page_size,
        "resultOffset": offset,
    }
    response = requests.get(
        f"{layer_url}/query",
        params=params,
        headers={"User-Agent": CAR_USER_AGENT},
        timeout=http_timeout_s,
    )
    response.raise_for_status()
    payload = response.json()
    if "features" not in payload:
        raise RuntimeError(
            f"Unexpected response paging {layer_url} at offset {offset}: {payload!r}"
        )
    return payload["features"]


def parse_car_laguna_features(features: list[dict], epsg: int, source_year: int | None = None) -> list[dict]:
    """Turn CAR GeoJSON features (already in the target metric CRS) into
    raw candidate-site dicts.

    Centroids are computed with shapely on the coordinates as returned
    (already metric, since the caller requests outSR=epsg), never in
    degrees. lon/lat are then derived via project.project_from_crs, the same
    shared inverse-reprojection path load_igac_water_bodies uses (do not
    hand-roll a second Transformer here).
    """
    from shapely.geometry import shape

    xs: list[float] = []
    ys: list[float] = []
    names: list[str | None] = []
    object_ids: list[object] = []
    for feat in features:
        geom = feat.get("geometry")
        if not geom:
            continue
        centroid = shape(geom).centroid
        xs.append(centroid.x)
        ys.append(centroid.y)
        props = feat.get("properties", {}) or {}
        raw_name = props.get("NMG")
        name = raw_name.strip() if isinstance(raw_name, str) and raw_name.strip() else None
        names.append(name)
        object_ids.append(props.get("OBJECTID"))

    if not xs:
        return []

    coords = pd.DataFrame({"x_utm": xs, "y_utm": ys})
    coords = project_from_crs(coords, epsg=epsg, x_col="x_utm", y_col="y_utm")

    records = []
    for i, oid in enumerate(object_ids):
        records.append(
            {
                "site_id": f"car_laguna_{oid}",
                "name": names[i],
                "lat": float(coords.iloc[i]["lat"]),
                "lon": float(coords.iloc[i]["lon"]),
                "x_utm": float(coords.iloc[i]["x_utm"]),
                "y_utm": float(coords.iloc[i]["y_utm"]),
                "category": CATEGORY_WATER_BODY,
                "source_name": CAR_SOURCE_NAME,
                "source_url": CAR_LAGUNA_LAYER_URL,
                "source_year": source_year,
                "license": CAR_LICENSE,
                "notes": f"centroid of source polygon; CAR OBJECTID={oid}",
            }
        )
    return records


def load_car_lagunas(
    epsg: int,
    layer_url: str = CAR_LAGUNA_LAYER_URL,
    page_size: int = DEFAULT_CAR_PAGE_SIZE,
    http_timeout_s: int = 60,
) -> pd.DataFrame:
    """Page through CAR's Laguna layer and return the unified candidate-site schema.

    source_year is the UTC year the query was actually run: the service does
    not expose its own data vintage in the layer metadata (checked, not
    assumed), so the fetch date is the best-verified marker available, the
    same convention load_osm_water_bodies uses for the same reason.
    """
    total = query_car_feature_count(layer_url, http_timeout_s=http_timeout_s)
    fetch_year = datetime.now(timezone.utc).year
    all_records: list[dict] = []
    offset = 0
    while offset < total:
        features = query_car_feature_page(
            layer_url, epsg=epsg, offset=offset, page_size=page_size, http_timeout_s=http_timeout_s
        )
        if not features:
            break
        all_records.extend(parse_car_laguna_features(features, epsg=epsg, source_year=fetch_year))
        offset += page_size

    if not all_records:
        return empty_candidate_sites()
    return assemble_candidate_sites(all_records, epsg=epsg)


# --- IGAC Cuerpos de Agua (manual local file) --------------------------------

IGAC_SOURCE_NAME = "IGAC Capa Digital Cuerpos de Agua 1:100.000"
IGAC_METADATA_URL = (
    "https://metadatos.icde.gov.co/geonetwork/srv/api/records/"
    "2ae17c2c-b793-4463-815c-76f36c2564de"
)
IGAC_LICENSE = "CC BY-SA 4.0"
IGAC_SOURCE_YEAR = 2020  # data created; metadata last refreshed 2025-12-19, see module docstring

# Plausible name-like attribute columns; the real schema was never
# independently confirmed (no working download was found), so this is a
# best-effort search, not an assumption. See module docstring.
_IGAC_NAME_CANDIDATES = ["nombre", "nombre_geo", "name", "etiqueta", "rotulo", "nom_geo"]


def load_igac_water_bodies(path: str, epsg: int) -> pd.DataFrame:
    """Read a manually-obtained IGAC water-bodies vector file (SHP/GPKG/GDB).

    Requires geopandas, pyogrio and fiona (requirements.txt). Reprojects to
    the configured metric CRS first and takes the centroid in that metric
    space (not in degrees, for the same reason project.py never clusters in
    degrees), then derives lon/lat for the unified schema via
    project.project_from_crs, the single shared inverse-reprojection code
    path (sites_schema.py: "Never reprojected ad hoc with a different EPSG
    in a loader"; do not hand-roll a second pyproj Transformer here). The
    resulting x_utm/y_utm are passed straight through to
    assemble_candidate_sites (they are already in the target epsg), which
    skips its own forward reprojection for records that already carry them,
    avoiding an unnecessary forward/inverse/forward CRS round trip.

    Raises a clear ImportError if geopandas is not installed, and a clear
    ValueError if the file has no CRS recorded (refusing to assume one,
    rather than silently guessing a datum/projection for real spatial data).
    """
    try:
        import geopandas as gpd
    except ImportError as exc:  # pragma: no cover, exercised only without geopandas installed
        raise ImportError(
            "load_igac_water_bodies requires geopandas (and pyogrio or fiona) to "
            "read vector files; install the packages listed in requirements.txt."
        ) from exc

    gdf = gpd.read_file(path)
    if gdf.crs is None:
        raise ValueError(
            f"{path} has no CRS recorded; refusing to assume one. Confirm the "
            "real CRS from the IGAC metadata/portal and pass a file with a "
            "CRS attached (e.g. re-save with the correct .prj/CRS set)."
        )

    gdf_metric = gdf.to_crs(epsg=epsg)
    centroids = gdf_metric.geometry.centroid

    name_col = next((c for c in _IGAC_NAME_CANDIDATES if c in gdf.columns), None)

    coords = pd.DataFrame({"x_utm": centroids.x.to_numpy(), "y_utm": centroids.y.to_numpy()})
    coords = project_from_crs(coords, epsg=epsg, x_col="x_utm", y_col="y_utm")

    records = []
    for i in range(len(gdf)):
        name = str(gdf.iloc[i][name_col]) if name_col else None
        records.append(
            {
                "site_id": f"igac_water_{i:06d}",
                "name": name,
                "lat": float(coords.iloc[i]["lat"]),
                "lon": float(coords.iloc[i]["lon"]),
                "x_utm": float(coords.iloc[i]["x_utm"]),
                "y_utm": float(coords.iloc[i]["y_utm"]),
                "category": CATEGORY_WATER_BODY,
                "source_name": IGAC_SOURCE_NAME,
                "source_url": IGAC_METADATA_URL,
                "source_year": IGAC_SOURCE_YEAR,
                "license": IGAC_LICENSE,
                "notes": (
                    "centroid of source polygon/geometry, projected metric "
                    f"CRS EPSG:{epsg}; name column "
                    + (f"'{name_col}'" if name_col else "not found, left None")
                ),
            }
        )

    if not records:
        return empty_candidate_sites()
    return assemble_candidate_sites(records, epsg=epsg)


# --- CLI -----------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Fetch candidate water body sites (OSM Overpass or CAR ArcGIS) and write them to data/raw."
    )
    parser.add_argument("--source", choices=["osm", "car"], default="osm", help="Which source to query (default: osm).")
    parser.add_argument("--west", type=float, default=-75.10, help="OSM only.")
    parser.add_argument("--south", type=float, default=3.50, help="OSM only.")
    parser.add_argument("--east", type=float, default=-72.80, help="OSM only.")
    parser.add_argument("--north", type=float, default=6.00, help="OSM only.")
    parser.add_argument("--epsg", type=int, default=9377, help="Projected CRS EPSG code (default: 9377).")
    parser.add_argument("--endpoint", default=DEFAULT_OVERPASS_ENDPOINT, help="Overpass API endpoint (OSM only).")
    parser.add_argument("--timeout", type=int, default=DEFAULT_OVERPASS_TIMEOUT_S, help="Overpass [timeout:] seconds (OSM only).")
    parser.add_argument("--car-layer-url", default=CAR_LAGUNA_LAYER_URL, help="CAR ArcGIS layer URL (CAR only).")
    parser.add_argument(
        "--out",
        default=None,
        help="Output CSV path (default: data/raw/<source>_water_bodies_<UTC fetch date>.csv).",
    )
    args = parser.parse_args()

    out_path = args.out or f"data/raw/{args.source}_water_bodies_{datetime.now(timezone.utc).date().isoformat()}.csv"

    if args.source == "car":
        df = load_car_lagunas(epsg=args.epsg, layer_url=args.car_layer_url)
    else:
        df = load_osm_water_bodies(
            west=args.west,
            south=args.south,
            east=args.east,
            north=args.north,
            epsg=args.epsg,
            endpoint=args.endpoint,
            timeout_s=args.timeout,
        )

    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(out, index=False)
    print(f"Wrote {len(df)} water body candidates to {out}")


if __name__ == "__main__":
    main()
