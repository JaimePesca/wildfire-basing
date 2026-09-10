# Candidate site data: bases (set I) and water points (set K)

This documents `sites_schema.py`, `sites_bases.py` and `sites_water.py`,
which build candidate first-stage sites for the optimization model
(CLAUDE.md section 4, sets `bases` and `water_points`). See
`src/pipeline/README.md` for the fire-event pipeline (FIRMS to Event
records); this is a separate, parallel data source.

## Schema

`sites_schema.py` defines the candidate-site record (new; CLAUDE.md section 6
does not yet cover this): `site_id`, `name`, `lat`, `lon`, `x_utm`, `y_utm`,
`category` (`civil_aerodrome` / `military_base` / `water_body`),
`source_name`, `source_url`, `source_year`, `license`, `notes`. `x_utm`/
`y_utm` are computed by reusing `project.py`'s `project_to_crs`, so bases,
water points and fire events all share the same configured EPSG
(`config/parameters.yaml`, currently 9377).

**Fixed costs are not in this schema.** `cost_base[i]` and `cost_water[k]`
(CLAUDE.md section 4) have no per-site source under CLAUDE.md section 8;
DECIDED 2026-08-30 (section 3/8/10, after a real web search found no
Colombia-specific source) to treat both as swept sensitivity parameters,
uniform across sites, see `src/model/costs.py`. No loader here fabricates
a per-site cost.

## What is automated right now

| Source | Module / function | How |
|---|---|---|
| Aerocivil AD 1.3 (civil aerodromes/heliports) | `sites_bases.download_aerocivil_ad13`, `load_aerocivil_aerodromes` | Real HTTP download (redirect-following GET), then xlsx parse. Confirmed 2026-08-18: this endpoint 403s without a browser-like User-Agent and intermittently 500s even with one; the loader retries with backoff, do not remove that. |
| OSM named water bodies | `sites_water.load_osm_water_bodies` | Real Overpass API POST query. |
| CAR (Corporacion Autonoma Regional de Cundinamarca) Laguna layer | `sites_water.load_car_lagunas` | Real ArcGIS REST GET queries, paginated (`resultOffset`), server-side reprojection to the configured EPSG. Found and verified 2026-08-18 after the IGAC route (below) turned out to be undownloadable; CAR is the actual regional water authority for Cundinamarca, so its own layer is already close to the area this project needs. 5024 polygons pulled live 2026-08-18, 118 with a real name (the rest are unnamed but still real geometry). Does not include the San Rafael reservoir (checked: zero rows match `NMG` containing "RAFAEL"), so it complements OSM rather than replacing it. License not confirmed against a primary CAR page (left `None`, see `sites_water.py` module docstring), do not fill it in from an unverified secondary claim. |
| Military bases (manual template) | `sites_bases.load_military_bases` | Parses a committed CSV, one verified row pre-filled. |

### Aerocivil AD 1.3 (civil aerodromes / heliports)

```bash
python -m src.pipeline.sites_bases download --out data/raw/aerocivil_ad13_aerodromos.xlsx
python -m src.pipeline.sites_bases build \
    --aerocivil-xlsx data/raw/aerocivil_ad13_aerodromos.xlsx \
    --military-csv data/raw/military_bases_template.csv \
    --out data/processed/candidate_bases.csv
```

`download` fetches `AEROCIVIL_AD13_LOADER_URL` (a `loader.php?...idFile=25010`
anchor on https://www.aerocivil.gov.co/documentos/1118/conjunto-de-datos-aip/)
which 302-redirects to a short-lived signed URL; `requests` follows this with
no login needed. `build` parses the downloaded xlsx (sheet `Hoja1`, column B
name/ICAO, column F DMS coordinates) and combines it with the military bases
CSV.

**Caveat, load-bearing:** the AD 1.3 file has no department/municipality
column. `load_aerocivil_aerodromes` offers a Cundinamarca bounding-box filter
(`CUNDINAMARCA_BBOX`, the same box `firms_download.py` uses) as a
convenience, but this is coordinate-bbox filtering, not a real
point-in-polygon join against a DIVIPOLA/IGAC administrative boundary. It can
include slivers of neighboring departments. Name-based filtering was tested
during verification and found actively unsafe (this same file has entries
literally named "MOSQUERA" and "SAN RAFAEL" that sit in Narino and Putumayo,
not Cundinamarca) so this module never filters on name. Do the real boundary
join before treating any output of this loader as a final Cundinamarca-only
candidate list.

No dataset-specific license or terms are shown on the AD 1.3 page; `license`
is left `None` for every Aerocivil row, not guessed.

### Military bases

`data/raw/military_bases_template.csv` (committed, not gitignored) has
columns `name,lat,lon,source,source_year,notes`. One row is pre-filled:
CACOM-4 Melgar (SKME), coordinates cross-verified across Wikipedia (ES/EN),
SkyVector, Great Circle Mapper, OpenNav and OurAirports (see the row's own
`source`/`notes` for the full citation list and the Tolima-vs-Cundinamarca
department caveat). All other rows are explicit `TODO` placeholders, never a
plausible-looking guess. `load_military_bases` skips any row with a blank
`lat`/`lon` rather than erroring, so the template can be filled in
incrementally.

Blind scraping of AD 2 aeronautical-chart PDFs for other military bases is
explicitly out of scope (fragile); add verified rows to the template
manually as they are researched, following the same citation-in-`source`
pattern as the CACOM-4 row.

### OSM named water bodies

```bash
python -m src.pipeline.sites_water \
    --west -75.10 --south 3.50 --east -72.80 --north 6.00 \
    --out data/raw/osm_water_bodies_2026-07-23.csv
```

Queries the Overpass API for named `natural=water`, `water=reservoir` and
`landuse=reservoir` features (nodes/ways/relations) inside the given bbox,
using `out center;` so ways/relations return a centroid rather than full
geometry. Default endpoint is the `.fr` community mirror
(`overpass.openstreetmap.fr`), found more reliable than `overpass-api.de`
during verification (the main instance intermittently returned HTTP 406 on
repeated requests in the same session); pass `--endpoint` to override.
`--timeout` sets the Overpass-side `[timeout:]` (default 180s, confirmed
empirically to be enough headroom for a full Cundinamarca-bbox query that
took ~59s of actual server-side work; 60s failed).

License: ODbL 1.0, verified directly against
https://www.openstreetmap.org/copyright at the time this module was written
("OpenStreetMap is open data, licensed under the Open Data Commons Open
Database License (ODbL) by the OpenStreetMap Foundation (OSMF)").

### CAR (Corporacion Autonoma Regional de Cundinamarca) Laguna layer

```bash
python -m src.pipeline.sites_water --source car --out data/raw/car_water_bodies_2026-08-18.csv
```

Pages through `https://sig.car.gov.co/arcgis/rest/services/visor/Agua1/MapServer/112`
(layer "Laguna", polygons), `maxRecordCount` 2000 confirmed from the
service's own descriptor, requesting GeoJSON already reprojected to the
configured EPSG server-side (`outSR`), so no client-side forward
reprojection is needed, only the centroid and the shared inverse
reprojection (`project.project_from_crs`, same as `load_igac_water_bodies`).
5024 features confirmed live 2026-08-18, only 118 with a non-blank `NMG`
(name) field, the rest are unnamed but real polygons.

**Local environment note, not a code issue:** on the machine this was
verified on, `requests`'s default `certifi` CA bundle could not verify
`sig.car.gov.co`'s real DigiCert EV certificate chain
(`SSLCertVerificationError: unable to get local issuer certificate`), while
Python's own `ssl.create_default_context()` (which uses the Windows
certificate store on this box) verified it without issue. This is a gap in
that specific certifi bundle on that machine, not a problem with the site or
with this module; do not add a Windows-specific SSL workaround to this file.
If it recurs, either upgrade certifi, or install `pip-system-certs` (or the
`truststore` package) so Python uses the OS trust store, on the affected
machine, not in this code.

Other layers on the same MapServer worth knowing about, not yet loaded here:
watershed boundaries (`Cuencas CAR`, `Subcuencas CAR`, `Area Hidrografica`)
and various monitoring/permit point layers; only the water-body polygon
layer (Laguna) was built, since that is what CLAUDE.md section 4's water
points (set K) needs.

## What still needs a manual step

### IGAC "Capa Digital Cuerpos de Agua", 1:100.000

No working WFS or direct-download URL was found for this layer, despite
substantial effort (the metadata record declares WFS/download availability
but its own linkage field is empty; `geoportal.igac.gov.co` returned
`ECONNREFUSED` from the environment this was verified in on every attempt;
an ArcGIS Hub item that looked like a match resolves to an unrelated 2024
hydrometeorological product; IGAC's own ArcGIS Server has no 1:100.000
water-bodies service). **Do not** invent a WFS endpoint; none is fabricated
here.

**Confirmed 2026-07-24 (live browser session, second independent pass):**
`geoportal.igac.gov.co` redirects to `colombiaenmapas.gov.co` as the real
search tool. There is no standalone "Cuerpos de Agua" download anywhere in
the catalog (checked against the full backend service list on
`serviciosgeovisor.igac.gov.co`, no service named "Cuerpos de Agua" exists).
The only downloadable product that contains it is the bundle "Base de datos
vectorial basica. Colombia. Escala 1:100.000. Ano 2022" (internal name
`Carto100000_Colombia_DI_2022`, servicio 205), at
https://www.colombiaenmapas.gov.co/?b=igac&u=0&t=23&servicio=205, offered as
GDB, GeoPackage or Shapefile; GeoPackage is the format to pick (single file,
matches this pipeline's geopandas/pyogrio stack). Extracting only the water
layers via a REST service was tried and confirmed not viable: `mapas2.igac.gov.co`,
`mapas.igac.gov.co` and `geoservicios.igac.gov.co` all time out
(`ERR_CONNECTION_TIMED_OUT`) from a live browser. Clicking the GeoPackage
download requires signing in through a third-party SSO wall (Google,
Facebook, email, Apple, Microsoft, Yahoo); this needs the user's own account
and was correctly left for a human to complete, not automated.

**License discrepancy found, not resolved, do not silently pick one:** the
ICDE metadata record for the standalone "Cuerpos de Agua" layer states CC
BY-SA 4.0 (as recorded below). The Colombia en Mapas product page for the
BDVB 1:100.000 bundle that actually contains the water layer states
literally "Licencia: CC BY 4.0" (no ShareAlike). These may legitimately be
two different products with two different licenses (the bundle is a
different, broader product than the standalone layer), or one page may be
stale; cite whichever license the manuscript ultimately relies on by
checking the specific download's own terms page again at time of writing,
do not assume the two are interchangeable.

**Expected internal layer structure, from the live MapServer catalog:**
water is not one aggregate layer at the service level, it is split across
many named sub-layers (Laguna, Embalse, Cienaga, Pantano, Madrevieja,
Jaguey, Morichal, Manglar, Humedal, Drenaje Doble, Canal Doble,
Otros_Cuerpos_Agua). The aggregated layer name `CuerpoDeAgua` is reported to
exist only inside the downloadable BDVB package itself, not as a live
service; once the GeoPackage is obtained, look for a layer literally named
`CuerpoDeAgua` first (`fiona.listlayers(path)`), falling back to unioning
the named sub-layers above if it is absent.

Manual step (updated): the file cannot be reached by a plain download link,
a human must sign in via the SSO wall linked above and download the
GeoPackage themselves, then place it at
`data/raw/igac_cuerpos_agua_100k.gpkg` (or point `load_igac_water_bodies` at
wherever it ends up).

**Confirmed 2026-08-18, blocking: the servicio 205 download is capped at
exactly 124,780,544 bytes (119.0 MiB), a hard infrastructure limit, not a
network or format problem.** Two independent full downloads (one via
GeoPackage, one via Shapefile, different internal file layouts confirmed
from each zip's header) both truncated at that exact byte count, with no
end-of-central-directory record, i.e. neither zip is usable. Same result
whether triggered by browser automation or a plain manual save. Further
investigation (live browser session, including reading the portal's own
`/js/index.js`) found no way around this:
- No area/bbox narrowing exists anywhere. The "Filtros > Area" tool only
  filters which catalog *entries* are shown (a search aid), it does not
  clip a download. The download endpoint's own request parameters (`cmd`,
  `tipo`, `id`, `formato`/`tipo_descarga`, `token`) have no bbox/geometry
  field at all, confirmed by reading the source, not guessed.
- No layer/theme selection exists. The package is pre-built server-side,
  not generated on demand; there is no per-layer download option.
- Only three BDVB 1:100.000 packages exist in the entire catalog: servicio
  205 (all of Colombia), 724 (Guainia), 1774 (Colombia-Ecuador border
  zone). None is scoped to Cundinamarca. Finer-scale packages exist (four
  1:10.000 municipal sets, ~150 urban 1:1.000 sets) but none covers the
  whole department.
- The WFS route is not just slow, it is down: `mapas2.igac.gov.co` still
  times out (confirmed again, ~20s), and the viewer's own "Agregar al mapa"
  for servicio 205 hangs indefinitely because the portal itself depends on
  that same host.

**Practical conclusion:** do not keep retrying this download, the cap is
structural. `load_osm_water_bodies` (already implemented, already verified
live, 424 named Cundinamarca water bodies pulled successfully) is the
working primary source for now. Two backup options identified but not yet
tried: (a) servicio 204, BDVB Colombia 1:500.000 (2014), much smaller,
likely under the cap, coarser scale; (b) email
servicioalciudadano@igac.gov.co reporting the 119 MiB cap as a bug and
requesting the layer scoped to Cundinamarca. Neither has been attempted yet
as of this writing.

Once the file is in place:

```python
from src.pipeline.sites_water import load_igac_water_bodies
df = load_igac_water_bodies("data/raw/igac_cuerpos_agua_100k.gpkg", epsg=9377)
```

Requires `geopandas`, `pyogrio` and `fiona` (added to `requirements.txt` for
this module only; the fire-event pipeline stays on its lighter CSV-only
stack). The loader reprojects to the configured metric CRS, takes the
centroid there (never in degrees), and converts back to lat/lon. It refuses
to guess a CRS if the file has none attached (raises `ValueError`).

**The real attribute schema (in particular, which column holds a name) was
never independently confirmed**, since no working download was found during
this research pass. `load_igac_water_bodies` searches a short list of
plausible column names (`nombre`, `nombre_geo`, `name`, `etiqueta`, `rotulo`,
`nom_geo`) and leaves `name` as `None`, not a guess, if none match.

License/year/scale/holder (verified against the record's ISO-19139 XML,
https://metadatos.icde.gov.co/geonetwork/srv/api/records/2ae17c2c-b793-4463-815c-76f36c2564de/formatters/xml):
CC BY-SA 4.0 (share-alike, not public domain); data created 2020, metadata
last refreshed 2025-12-19; scale 1:100.000; holder IGAC, Subdireccion de
Geografia y Cartografia.

### Additional military bases beyond CACOM-4 Melgar

Any base not in the six-entry official AD 2 "AERODROMOS AVIACION DE ESTADO"
list and not independently cross-verifiable via Wikipedia/aviation
databases (the method used for CACOM-4) needs individual manual research.
Add a row to `data/raw/military_bases_template.csv` with a real citation in
`source`, following the CACOM-4 row's pattern; do not fill in a coordinate
without one.

### Cundinamarca boundary join

Both the Aerocivil bbox filter and (if applicable) any future OSM/IGAC bbox
filtering are coordinate-box approximations. A real DIVIPOLA/IGAC
administrative-boundary polygon and a point-in-polygon join are needed
before any candidate list here should be called "Cundinamarca sites" without
qualification. This is the same open item as the `municipality` field in the
Event record schema (`src/pipeline/README.md`).
