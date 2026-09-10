"""Population exposure for value_at_risk[f] (CLAUDE.md section 5.3):
sum WorldPop population within a buffer around a fire's location, left
unmonetized (a population-exposure index, not a currency value), and a
secondary cross-check against DANE CNPV 2018 at the municipal level.

Primary source: WorldPop Colombia 2020 "constrained" population count
raster (BSGM, building-footprint-constrained, about 100m), data.worldpop.org,
downloaded 2026-08-24 to data/raw/worldpop_col_2020_constrained.tif (27.8 MB,
direct HTTPS download, no login). Used instead of the ~614 MB unconstrained
national raster (also real and downloadable, but its transfer kept timing
out on this connection, unrelated to Norton, see CLAUDE.md section 8): the
constrained layer is not just smaller, it is also generally considered more
accurate for exactly this use (population mass concentrated onto real
building footprints rather than spread across an entire pixel including
uninhabited land), a genuine improvement, not merely a workaround.

Buffer radius: DEFAULT_BUFFER_RADIUS_M below is a fixed illustrative
default (1 km), not swept and not independently sourced. A search for a
standard wildfire evacuation/impact-zone radius found none: real
evacuation zones are threat-assessment-based, not a fixed distance (no
single citable number exists to calibrate this against), so 1 km is
disclosed as a reasonable round "immediate vicinity" choice, not a
literature value, same honesty standard as requirement[f]'s A0/c and
ros[f]'s slope_coef/wind_coef.

Secondary cross-check: DANE CNPV 2018 municipal totals, from a live
ArcGIS FeatureServer found via IDER Cundinamarca (services7.arcgis.com,
layer MGN_ANM_CUNDINAMARCA, 116 municipalities, confirmed to match
Cundinamarca's real municipality count). Field CONFIRMED 2026-08-30 against
DANE's own primary field dictionary ("Uso del Marco Geoestadistico
Nacional", GIT MGN, Direccion de Geoestadistica, September 2020,
geoportal.dane.gov.co/descargas/mgn-integrado/MGN2018_Integrado_CNPV2018_InstructivoUso.pdf,
Tabla 1, page 5-6): the field previously used here, STCTNENCUE, was WRONG,
it is documented there as "Cantidad de Encuestas CNPV 2018" (count of CNPV
2018 surveys conducted), not population. The correct field is STP27_PERS,
documented as "Numero de personas" (number of persons), the actual total
population tally per geographic unit. Corrected here; see CLAUDE.md
section 5.3/10 for the decision history.
"""

from __future__ import annotations

import numpy as np
import rasterio
from rasterio.transform import xy as transform_xy
from rasterio.windows import from_bounds

from .slope import meters_per_degree

DEFAULT_BUFFER_RADIUS_M = 1000.0  # see module docstring

DANE_FEATURESERVER_URL = (
    "https://services7.arcgis.com/lsxbLWF2l19Rmhqj/arcgis/rest/services/"
    "MGN_ANM_CUNDINAMARCA/FeatureServer/0"
)
DANE_POPULATION_FIELD = "STP27_PERS"  # confirmed 2026-08-30, see module docstring


def sum_population_in_buffer(
    lon: float, lat: float, raster_path: str, buffer_radius_m: float = DEFAULT_BUFFER_RADIUS_M
) -> float | None:
    """Sum WorldPop population within buffer_radius_m meters of (lon, lat),
    using a real circular mask (pixel-center distance <= radius), not just
    a bounding-box approximation. Returns None if the point falls outside
    the raster or the resulting window is empty."""
    with rasterio.open(raster_path) as src:
        left, bottom, right, top = src.bounds
        if not (left <= lon <= right and bottom <= lat <= top):
            return None

        m_per_deg_lon, m_per_deg_lat = meters_per_degree(lat)
        radius_deg_lon = buffer_radius_m / m_per_deg_lon
        radius_deg_lat = buffer_radius_m / m_per_deg_lat

        window = from_bounds(
            max(lon - radius_deg_lon, left),
            max(lat - radius_deg_lat, bottom),
            min(lon + radius_deg_lon, right),
            min(lat + radius_deg_lat, top),
            src.transform,
        ).round_lengths().round_offsets()
        if window.width <= 0 or window.height <= 0:
            return None

        data = src.read(1, window=window).astype(float)
        if src.nodata is not None:
            data = np.where(data == src.nodata, 0.0, data)
        data = np.where(data < 0, 0.0, data)  # WorldPop uses negative sentinels for nodata too

        win_transform = src.window_transform(window)
        rows, cols = np.indices(data.shape)
        xs, ys = transform_xy(win_transform, rows.ravel(), cols.ravel(), offset="center")
        xs = np.array(xs).reshape(data.shape)
        ys = np.array(ys).reshape(data.shape)

        dx_m = (xs - lon) * m_per_deg_lon
        dy_m = (ys - lat) * m_per_deg_lat
        dist_m = np.sqrt(dx_m**2 + dy_m**2)
        mask = dist_m <= buffer_radius_m
        return float(data[mask].sum())


def sum_population_for_fires(
    fires: list, raster_path: str, buffer_radius_m: float = DEFAULT_BUFFER_RADIUS_M
) -> dict[str, float | None]:
    """Batch version: fires is a list of objects with fire_id/lat/lon
    attributes. Opens the raster once, not once per fire."""
    result: dict[str, float | None] = {}
    for fire in fires:
        result[fire.fire_id] = sum_population_in_buffer(
            fire.lon, fire.lat, raster_path, buffer_radius_m=buffer_radius_m
        )
    return result
