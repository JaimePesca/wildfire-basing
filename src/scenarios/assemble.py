"""Final assembly: turn day_scenarios.py's ScenarioRecord/FireRecord
(events resampled into day-scenarios, CLAUDE.md section 5.3) into fully
populated src/model/schema.py Scenario/Fire objects, ready for a
src.model.milp solve.

Two-step pipeline, deliberately kept separate:

1. day_scenarios.enrich_t_arrival(scenarios, bases, speed) fills
   t_arrival, using real candidate base data plus a real aircraft speed
   (neither fabricated here). A real aircraft speed now exists,
   src.model.aircraft.SPEED (CONFIRMED 2026-08-30, CLAUDE.md section
   4/8/10, Colombia's own Sikorsky S-70i Firehawk); pass it as the speed
   argument, in meters per hour (the units convention decided alongside
   it), not meters per second.
2. enrich_scenarios_with_ros_and_value_at_risk (this module) fills
   ros_param (land cover x slope x wind, ros_formula.py) and value_at_risk
   (WorldPop population buffer, population.py).

Only once both steps have run on every fire can to_model_scenarios convert
them: it raises (by default) rather than silently dropping or defaulting a
fire that is still missing ros_param/value_at_risk/t_arrival, since a
silently-dropped fire would understate that scenario's true risk in the
model. Pass on_missing="drop" to instead exclude incomplete fires and get
their ids back, for a caller that has decided that tradeoff deliberately.
"""

from __future__ import annotations

from .day_scenarios import ScenarioRecord
from .land_cover import sample_land_cover_for_fires
from .population import DEFAULT_BUFFER_RADIUS_M, sum_population_for_fires
from .ros_formula import DEFAULT_SLOPE_COEF, DEFAULT_WIND_COEF, compute_ros_for_fires
from .slope import sample_slope_degrees
from .weather import fetch_wind_speed_for_fires


def enrich_scenarios_with_ros_and_value_at_risk(
    scenarios: list[ScenarioRecord],
    worldcover_tile_paths: list[str],
    srtm_tile_paths: list[str],
    worldpop_raster_path: str,
    ros_scale: float,
    population_buffer_radius_m: float = DEFAULT_BUFFER_RADIUS_M,
    slope_coef: float = DEFAULT_SLOPE_COEF,
    wind_coef: float = DEFAULT_WIND_COEF,
) -> None:
    """Mutates every fire in scenarios in place, filling ros_param and
    value_at_risk (t_arrival is not touched here, see module docstring).
    Land cover/slope/wind are sampled/queried once per distinct fire across
    all scenarios, not once per scenario, even though the same historical
    day (and therefore the same FireRecord instances) can be drawn into
    more than one bootstrap scenario. A fire whose land cover, slope, or
    wind speed cannot be determined gets ros_param=None (see
    ros_formula.compute_ros_for_fires), not a guessed value; such fires
    will make to_model_scenarios raise (or be dropped, if it is called with
    on_missing="drop").
    """
    all_fires = [fire for s in scenarios for fire in s.fires]
    if not all_fires:
        return

    landcover_classes = sample_land_cover_for_fires(all_fires, worldcover_tile_paths)
    slopes = {
        fire.fire_id: sample_slope_degrees(fire.lon, fire.lat, srtm_tile_paths) for fire in all_fires
    }

    dates: dict[str, str] = {}
    for scenario in scenarios:
        date_yyyymmdd = scenario.source_date.replace("-", "")
        for fire in scenario.fires:
            dates[fire.fire_id] = date_yyyymmdd
    wind_speeds = fetch_wind_speed_for_fires(all_fires, dates)

    ros_values = compute_ros_for_fires(
        all_fires, landcover_classes, slopes, wind_speeds, ros_scale, slope_coef, wind_coef
    )
    value_at_risk_values = sum_population_for_fires(
        all_fires, worldpop_raster_path, population_buffer_radius_m
    )

    for fire in all_fires:
        fire.ros_param = ros_values[fire.fire_id]
        fire.value_at_risk = value_at_risk_values[fire.fire_id]


def to_model_scenarios(
    scenarios: list[ScenarioRecord], on_missing: str = "raise"
) -> tuple[list, list[str]]:
    """Convert fully-enriched ScenarioRecord/FireRecord into
    src.model.schema.Scenario/Fire. Returns (model_scenarios,
    dropped_fire_ids); dropped_fire_ids is only ever non-empty when
    on_missing="drop", and a caller must not silently ignore it, a dropped
    fire understates that scenario's risk in the model.

    on_missing="raise" (default): raise ValueError naming the first fire
    still missing ros_param, value_at_risk, or t_arrival, rather than
    fabricate a value or silently exclude it.
    on_missing="drop": exclude such fires from their scenario instead,
    collecting their ids to return.
    """
    if on_missing not in ("raise", "drop"):
        raise ValueError(f"on_missing must be 'raise' or 'drop', got {on_missing!r}")

    # Local import: avoids a hard top-level dependency from src.scenarios
    # on src.model, mirroring day_scenarios.enrich_t_arrival's own lazy
    # import of src.model.travel_times.
    from src.model.schema import Fire as ModelFire
    from src.model.schema import Scenario as ModelScenario

    model_scenarios = []
    dropped_fire_ids: list[str] = []
    for scenario in scenarios:
        model_fires = []
        for fire in scenario.fires:
            missing = [
                name
                for name, value in (
                    ("ros_param", fire.ros_param),
                    ("value_at_risk", fire.value_at_risk),
                    ("t_arrival", fire.t_arrival),
                )
                if value is None
            ]
            if missing:
                if on_missing == "raise":
                    raise ValueError(
                        f"fire {fire.fire_id!r} in scenario {scenario.scenario_id!r} is "
                        f"missing {missing}, cannot convert to a model Fire without "
                        "fabricating a value (pass on_missing='drop' to exclude it instead)"
                    )
                dropped_fire_ids.append(fire.fire_id)
                continue
            model_fires.append(
                ModelFire(
                    fire_id=fire.fire_id,
                    x_utm=fire.x_utm,
                    y_utm=fire.y_utm,
                    ros=fire.ros_param,
                    t_arrival=fire.t_arrival,
                    value_at_risk=fire.value_at_risk,
                )
            )
        model_scenarios.append(
            ModelScenario(
                scenario_id=scenario.scenario_id,
                probability=scenario.probability,
                fires=model_fires,
            )
        )
    return model_scenarios, dropped_fire_ids
