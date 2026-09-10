"""Compute t_base_fire[i,f] and t_fire_water[f,k] (CLAUDE.md section 4) from
real projected coordinates, and assemble a schema.ModelParams from the real
candidate site data this repo already has (data/processed/candidate_bases.csv,
data/processed/candidate_water.csv).

Departure from section 4's literal notation, disclosed, not silently papered
over: t_base_fire[i,f] and t_fire_water[f,k] are written without an m
(aircraft type) index, even though travel time is physically distance over
speed[m], which does depend on type. This is fine under the current
single-aircraft-type scope (CLAUDE.md section 4/10, decided 2026-07-23): with
exactly one type, "the type's speed" is unambiguous. If multiple types are
added later, these parameters need to become t_base_fire[i,f,m] /
t_fire_water[f,k,m], and this module's single_aircraft_speed() guard below is
exactly the place that will need to change first.

No fire/scenario data source exists yet in this repo (CLAUDE.md section 10:
src/scenarios/ only has eps_sensitivity.py so far, the events-to-SAA-scenarios
step is not built). assemble_model_params() therefore takes a caller-supplied
list of schema.Scenario, it does not fabricate one.
"""

from __future__ import annotations

import math

import pandas as pd

from .schema import Fire, ModelParams, Scenario


def single_aircraft_speed(speed: dict[str, float]) -> float:
    """Extract the one speed value under the current single-aircraft-type
    scope. Raises if speed has anything other than exactly one entry, so a
    future multi-type extension fails loudly here instead of silently using
    an arbitrary type's speed for every base-fire/fire-water pair."""
    if len(speed) != 1:
        raise ValueError(
            "t_base_fire/t_fire_water are computed with a single aircraft "
            "speed (CLAUDE.md section 4 defines them without an m index), "
            f"but speed has {len(speed)} entries: {sorted(speed)}. This "
            "module needs to be extended to index by m before multiple "
            "aircraft types can be used (see this module's docstring)."
        )
    return next(iter(speed.values()))


def _euclidean_travel_time(x1: float, y1: float, x2: float, y2: float, speed: float) -> float:
    distance = math.hypot(x2 - x1, y2 - y1)
    return distance / speed


def compute_t_base_fire(
    bases: pd.DataFrame, fires: list[Fire], scenario_id: str, speed: dict[str, float]
) -> dict[tuple[str, str, str], float]:
    """bases must have site_id, x_utm, y_utm columns (candidate_bases.csv
    schema, src/pipeline/sites_schema.py). Returns t_base_fire keyed
    (scenario_id, i, fire_id), matching precompute.py's key convention."""
    v = single_aircraft_speed(speed)
    t_base_fire: dict[tuple[str, str, str], float] = {}
    for _, row in bases.iterrows():
        i = row["site_id"]
        for fire in fires:
            t_base_fire[(scenario_id, i, fire.fire_id)] = _euclidean_travel_time(
                row["x_utm"], row["y_utm"], fire.x_utm, fire.y_utm, v
            )
    return t_base_fire


def compute_t_arrival(bases: pd.DataFrame, fires: list, speed: dict[str, float]) -> dict[str, float]:
    """t_arrival[f] = min_i t_base_fire[i,f] (CLAUDE.md section 5.3, decided
    2026-08-20): the travel time of the closest candidate base. Stays
    exogenous to the dispatch decision (a minimum over the fixed candidate
    set I, not over whichever base ends up actually dispatching), see
    section 5.3 for why this was chosen over t_arrival[f] = 0.

    bases must have site_id, x_utm, y_utm columns. fires may be any objects
    with fire_id/x_utm/y_utm attributes (schema.Fire or
    src.scenarios.day_scenarios.FireRecord both satisfy this, duck typed
    deliberately so this one function serves both). Returns a plain
    dict[fire_id, float], not scenario-keyed: unlike t_base_fire/
    t_fire_water, t_arrival is a per-fire quantity independent of scenario
    scoping concerns beyond whatever fire_id uniqueness the caller already
    guarantees within its own scenario.

    Raises ValueError if bases is empty: a minimum over zero candidates is
    undefined, not silently 0 or infinity.
    """
    if bases.empty:
        raise ValueError("compute_t_arrival requires at least one candidate base, bases is empty")
    v = single_aircraft_speed(speed)
    t_arrival: dict[str, float] = {}
    for fire in fires:
        best = min(
            _euclidean_travel_time(row["x_utm"], row["y_utm"], fire.x_utm, fire.y_utm, v)
            for _, row in bases.iterrows()
        )
        t_arrival[fire.fire_id] = best
    return t_arrival


def compute_t_fire_water(
    water_points: pd.DataFrame, fires: list[Fire], scenario_id: str, speed: dict[str, float]
) -> dict[tuple[str, str, str], float]:
    """water_points must have site_id, x_utm, y_utm columns (candidate_water.csv
    schema). Returns t_fire_water keyed (scenario_id, fire_id, k)."""
    v = single_aircraft_speed(speed)
    t_fire_water: dict[tuple[str, str, str], float] = {}
    for _, row in water_points.iterrows():
        k = row["site_id"]
        for fire in fires:
            t_fire_water[(scenario_id, fire.fire_id, k)] = _euclidean_travel_time(
                fire.x_utm, fire.y_utm, row["x_utm"], row["y_utm"], v
            )
    return t_fire_water


def assemble_model_params(
    bases: pd.DataFrame,
    water_points: pd.DataFrame,
    scenarios: list[Scenario],
    *,
    budget: float,
    window: float,
    ops_time: float,
    cvar_alpha: float,
    mean_risk_weight: float,
    initial_fire_area: float,
    liters_per_sqm: float,
    cost_base: dict[str, float],
    cost_aircraft: dict[str, float],
    cost_water: dict[str, float],
    tank: dict[str, float],
    speed: dict[str, float],
) -> ModelParams:
    """Assemble a ModelParams from real candidate site data (bases,
    water_points: site_id/x_utm/y_utm at minimum, e.g. read straight from
    data/processed/candidate_bases.csv and candidate_water.csv) plus a
    caller-supplied scenarios list (schema.Scenario/Fire), computing
    t_base_fire/t_fire_water from real coordinates. cost_base/cost_water
    must have an entry for every site_id present in bases/water_points
    respectively; this raises KeyError rather than silently defaulting a
    missing cost to 0, since CLAUDE.md section 4/10 explicitly flags that no
    section 8 source provides these costs yet, a missing entry is a real
    data gap, not an implicit "free"."""
    base_ids = list(bases["site_id"])
    water_ids = list(water_points["site_id"])
    aircraft_types = list(speed.keys())

    missing_base_costs = [i for i in base_ids if i not in cost_base]
    if missing_base_costs:
        raise KeyError(f"cost_base missing entries for base ids: {missing_base_costs}")
    missing_water_costs = [k for k in water_ids if k not in cost_water]
    if missing_water_costs:
        raise KeyError(f"cost_water missing entries for water point ids: {missing_water_costs}")

    t_base_fire: dict[tuple[str, str, str], float] = {}
    t_fire_water: dict[tuple[str, str, str], float] = {}
    for scenario in scenarios:
        t_base_fire.update(
            compute_t_base_fire(bases, scenario.fires, scenario.scenario_id, speed)
        )
        t_fire_water.update(
            compute_t_fire_water(water_points, scenario.fires, scenario.scenario_id, speed)
        )

    return ModelParams(
        bases=base_ids,
        water_points=water_ids,
        aircraft_types=aircraft_types,
        scenarios=scenarios,
        budget=budget,
        window=window,
        ops_time=ops_time,
        cvar_alpha=cvar_alpha,
        mean_risk_weight=mean_risk_weight,
        initial_fire_area=initial_fire_area,
        liters_per_sqm=liters_per_sqm,
        cost_base=cost_base,
        cost_aircraft=cost_aircraft,
        cost_water=cost_water,
        tank=tank,
        speed=speed,
        t_base_fire=t_base_fire,
        t_fire_water=t_fire_water,
    )
