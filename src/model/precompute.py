"""Precomputation (CLAUDE.md section 5.2, "Precomputation"): every input to
these formulas is a parameter, not a decision variable, which is exactly why
they are computed once, offline, as constant lookup tables rather than
needing SOS2 or any other piecewise linearization (section 4/10 decision).

Formulas, verbatim from section 5.2, for every i in bases, f in fires[s],
k in water_points, m in aircraft_types, s in scenarios:

    cycle_time[f,k,m] = 2 * t_fire_water[f,k] + ops_time
    drops[i,f,k,m]    = max(0, floor((window - t_base_fire[i,f]) / cycle_time[f,k,m]))
    liters[i,f,k,m]   = drops[i,f,k,m] * tank[m]
    requirement[f]    = liters_per_sqm * initial_fire_area * exp(ros[f] * t_arrival[f])
    Mbig[m]           = floor(budget / cost_aircraft[m])

The max(0, ...) clip on drops is explicit in section 5.2 (the section 4
sketch omitted it): a base too far to complete even one round trip within
the window contributes zero drops, not a negative one.

Every fire-indexed quantity here (t_base_fire, t_fire_water, ros,
t_arrival, drops, liters, requirement) is scoped to its scenario per
schema.py's ModelParams (keyed by scenario_id), consistent with section
5.2's notation convention that a bare f in CLAUDE.md's tables means "for f
in fires[s], within scenario s".
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from .schema import ModelParams


@dataclass(frozen=True)
class Precomputed:
    # keyed (scenario_id, fire_id, k, m)
    cycle_time: dict[tuple[str, str, str, str], float]
    # keyed (scenario_id, i, fire_id, k, m)
    drops: dict[tuple[str, str, str, str, str], int]
    # keyed (scenario_id, i, fire_id, k, m)
    liters: dict[tuple[str, str, str, str, str], float]
    # keyed (scenario_id, fire_id)
    requirement: dict[tuple[str, str], float]
    # keyed m
    Mbig: dict[str, int]


def compute_cycle_time(params: ModelParams) -> dict[tuple[str, str, str, str], float]:
    cycle_time: dict[tuple[str, str, str, str], float] = {}
    for scenario in params.scenarios:
        for fire in scenario.fires:
            for k in params.water_points:
                t_fw = params.t_fire_water[(scenario.scenario_id, fire.fire_id, k)]
                for m in params.aircraft_types:
                    cycle_time[(scenario.scenario_id, fire.fire_id, k, m)] = (
                        2.0 * t_fw + params.ops_time
                    )
    return cycle_time


def compute_drops(
    params: ModelParams, cycle_time: dict[tuple[str, str, str, str], float]
) -> dict[tuple[str, str, str, str, str], int]:
    drops: dict[tuple[str, str, str, str, str], int] = {}
    for scenario in params.scenarios:
        for i in params.bases:
            for fire in scenario.fires:
                t_bf = params.t_base_fire[(scenario.scenario_id, i, fire.fire_id)]
                for k in params.water_points:
                    for m in params.aircraft_types:
                        cyc = cycle_time[(scenario.scenario_id, fire.fire_id, k, m)]
                        raw = math.floor((params.window - t_bf) / cyc)
                        drops[(scenario.scenario_id, i, fire.fire_id, k, m)] = max(0, raw)
    return drops


def compute_liters(
    params: ModelParams, drops: dict[tuple[str, str, str, str, str], int]
) -> dict[tuple[str, str, str, str, str], float]:
    liters: dict[tuple[str, str, str, str, str], float] = {}
    for scenario in params.scenarios:
        for i in params.bases:
            for fire in scenario.fires:
                for k in params.water_points:
                    for m in params.aircraft_types:
                        key = (scenario.scenario_id, i, fire.fire_id, k, m)
                        liters[key] = drops[key] * params.tank[m]
    return liters


def compute_requirement(params: ModelParams) -> dict[tuple[str, str], float]:
    requirement: dict[tuple[str, str], float] = {}
    for scenario in params.scenarios:
        for fire in scenario.fires:
            requirement[(scenario.scenario_id, fire.fire_id)] = (
                params.liters_per_sqm
                * params.initial_fire_area
                * math.exp(fire.ros * fire.t_arrival)
            )
    return requirement


def compute_mbig(params: ModelParams) -> dict[str, int]:
    return {m: math.floor(params.budget / params.cost_aircraft[m]) for m in params.aircraft_types}


def precompute(params: ModelParams) -> Precomputed:
    """Run every section 5.2 precomputation step and return the constant
    lookup tables milp.py needs. Call this once per solve (once per sweep
    point, when initial_fire_area/liters_per_sqm are swept over experiment
    6, section 9), it is cheap relative to solving the MILP."""
    cycle_time = compute_cycle_time(params)
    drops = compute_drops(params, cycle_time)
    liters = compute_liters(params, drops)
    requirement = compute_requirement(params)
    Mbig = compute_mbig(params)
    return Precomputed(
        cycle_time=cycle_time, drops=drops, liters=liters, requirement=requirement, Mbig=Mbig
    )
