"""Combined ros[f] formula (CLAUDE.md section 5.3, decided 2026-08-21):

    ros[f] = ros_scale * class_relative_rate[landcover_class]
             * exp(slope_coef * slope_degrees) * (1 + wind_coef * wind_speed)

Same treatment as A0/c (requirement[f]'s calibration constants, section 3):
no solid primary source exists for absolute rate-of-spread magnitudes
applicable to Colombia, so ros_scale is a swept sensitivity parameter
(section 9 experiment 6), the caller supplies it per solve/sweep point,
this module never chooses one.

CLASS_RELATIVE_RATE is a fixed, ordinally-grounded table (not
independently calibrated in magnitude, only in ranking), based on NWCG's
published Anderson (1982) 13 fire behavior fuel models' qualitative
spread-rate ratings (grass fastest, shrub moderate to fast, timber litter
slower, non-burnable near zero), mapped onto ESA WorldCover's 11 classes.
The original Anderson (1982) report's own numeric reference-condition
spread rates were not obtained, only its qualitative ratings via NWCG/
LANDFIRE secondary sources, so these are disclosed as illustrative,
ordinally-motivated values, not literature numbers. Revisit if the primary
Anderson (1982) tables are found later.

slope_coef and wind_coef are fixed illustrative defaults (not swept, see
section 5.3 for why the sweep is limited to A0/c/ros_scale). A real primary
source for Sandberg, Ottmar and Cushon's simplified wind-exponent
reformulation (fixed B=1.2 for all fuel types) was searched for and not
fully confirmed (only found via secondary citation, the primary 2007 paper
was not read), so this module uses a simpler linear wind factor instead of
adopting that unconfirmed exponent.
"""

from __future__ import annotations

import math

# Illustrative relative rates, grassland = 1.0 is the fastest reference.
# See module docstring: ordinally grounded, not a literature-sourced
# absolute magnitude.
CLASS_RELATIVE_RATE = {
    10: 0.3,  # Tree cover
    20: 0.6,  # Shrubland
    30: 1.0,  # Grassland
    40: 0.8,  # Cropland
    50: 0.0,  # Built-up
    60: 0.05,  # Bare / sparse vegetation
    70: 0.0,  # Snow and ice
    80: 0.0,  # Permanent water bodies
    90: 0.4,  # Herbaceous wetland
    95: 0.3,  # Mangrove
    100: 0.2,  # Moss and lichen
}

DEFAULT_SLOPE_COEF = 0.05  # per degree, see module docstring
DEFAULT_WIND_COEF = 0.1  # per m/s, see module docstring


def compute_ros(
    landcover_class: int,
    slope_degrees: float,
    wind_speed: float,
    ros_scale: float,
    slope_coef: float = DEFAULT_SLOPE_COEF,
    wind_coef: float = DEFAULT_WIND_COEF,
) -> float:
    """ros[f] for one fire, given its already-sampled land cover class,
    slope and wind speed. Raises ValueError for an unrecognized class code
    rather than silently defaulting its relative rate."""
    if landcover_class not in CLASS_RELATIVE_RATE:
        raise ValueError(
            f"unknown WorldCover class code {landcover_class!r}, "
            f"expected one of {sorted(CLASS_RELATIVE_RATE)}"
        )
    class_rate = CLASS_RELATIVE_RATE[landcover_class]
    slope_factor = math.exp(slope_coef * slope_degrees)
    wind_factor = 1.0 + wind_coef * wind_speed
    return ros_scale * class_rate * slope_factor * wind_factor


def compute_ros_for_fires(
    fires: list,
    landcover_classes: dict[str, int | None],
    slopes: dict[str, float | None],
    wind_speeds: dict[str, float | None],
    ros_scale: float,
    slope_coef: float = DEFAULT_SLOPE_COEF,
    wind_coef: float = DEFAULT_WIND_COEF,
) -> dict[str, float | None]:
    """Batch version. A fire maps to None if any of its three inputs
    (land cover class, slope, wind speed) is None, i.e. could not be
    sampled/queried for that fire, rather than silently substituting a
    default and computing a misleading ros[f]."""
    result: dict[str, float | None] = {}
    for fire in fires:
        fire_id = fire.fire_id
        cls = landcover_classes.get(fire_id)
        slope = slopes.get(fire_id)
        wind = wind_speeds.get(fire_id)
        if cls is None or slope is None or wind is None:
            result[fire_id] = None
            continue
        result[fire_id] = compute_ros(cls, slope, wind, ros_scale, slope_coef, wind_coef)
    return result
