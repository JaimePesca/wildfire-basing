"""Input parameter schema for the joint base and water point siting model
(CLAUDE.md section 4, notation FROZEN, signed off 2026-08-18; section 5.2,
full mathematical derivation, FROZEN).

Every field name here is the exact code identifier from section 4's tables,
per CLAUDE.md's own preamble: "Code in this repo and the manuscript must use
the same symbols." Do not rename or abbreviate.

Fire-indexed parameters (t_base_fire, t_fire_water, value_at_risk, ros,
t_arrival) are scoped per scenario, not global: section 5.2's notation
convention is that every bare f in the CLAUDE.md tables means "for f in
fires[s], within scenario s", since fire ids are not assumed to repeat
identically across scenarios. Fire is therefore its own dataclass nested
inside Scenario (mirroring the section 6 Scenario record: scenario_id,
probability p_s, fires: list with fire_id, location, ros_param,
value_at_risk), and t_base_fire/t_fire_water are keyed by
(scenario_id, i, fire_id) / (scenario_id, fire_id, k) respectively, not by a
bare fire_id, to make the scenario scoping explicit and avoid silently
colliding fire ids that happen to repeat across scenarios.

initial_fire_area (A0) and liters_per_sqm (c) are swept sensitivity
parameters (CLAUDE.md section 3/9 experiment 6), not fixed constants: the
caller passes a specific value per solve, this module does not choose one.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Fire:
    """One fire (ignition event) within a scenario (CLAUDE.md section 6
    Scenario record: fire_id, location, size/intensity proxy, ros_param,
    value_at_risk). x_utm/y_utm are the projected location, needed by
    travel_times.py to compute t_base_fire/t_fire_water from real
    coordinates; ros and t_arrival and value_at_risk are the section 4
    parameters ros[f], t_arrival[f], value_at_risk[f]."""

    fire_id: str
    x_utm: float
    y_utm: float
    ros: float
    t_arrival: float
    value_at_risk: float


@dataclass(frozen=True)
class Scenario:
    """One SAA scenario (CLAUDE.md section 6 Scenario record): scenario_id,
    probability p_s, and its fires."""

    scenario_id: str
    probability: float
    fires: list[Fire] = field(default_factory=list)


@dataclass(frozen=True)
class ModelParams:
    """Every parameter from CLAUDE.md section 4's Parameters table, plus the
    sets. Field names match the code identifiers exactly.

    Sets:
    - bases: list of base ids (set I)
    - water_points: list of water point ids (set K)
    - aircraft_types: list of aircraft type ids (set M; single type for this
      paper, CLAUDE.md section 4/10 decision, 2026-07-23, but kept as a list
      so the notation and the code stay general)
    - scenarios: list of Scenario (set S, each carrying its own fires[s])

    Global parameters (not indexed, or indexed only by the sets above):
    - budget (B), window (W), ops_time (delta), cvar_alpha (alpha),
      mean_risk_weight (lambda)
    - initial_fire_area (A0), liters_per_sqm (c): swept sensitivity
      parameters, see module docstring, not fixed here

    Per-base/type/water-point parameters (dicts keyed by the natural id):
    - cost_base[i], cost_aircraft[m], cost_water[k], tank[m], speed[m]

    Per-(scenario, base, fire) and per-(scenario, fire, water point):
    - t_base_fire[(scenario_id, i, fire_id)]
    - t_fire_water[(scenario_id, fire_id, k)]
    (built by travel_times.py from real coordinates plus speed[m]; kept as
    plain dicts here rather than computed inline, so this dataclass can also
    be built directly from synthetic test data without going through
    travel_times.py)
    """

    bases: list[str]
    water_points: list[str]
    aircraft_types: list[str]
    scenarios: list[Scenario]

    budget: float
    window: float
    ops_time: float
    cvar_alpha: float
    mean_risk_weight: float
    initial_fire_area: float
    liters_per_sqm: float

    cost_base: dict[str, float]
    cost_aircraft: dict[str, float]
    cost_water: dict[str, float]
    tank: dict[str, float]
    speed: dict[str, float]

    t_base_fire: dict[tuple[str, str, str], float]
    t_fire_water: dict[tuple[str, str, str], float]

    def fires_in(self, scenario_id: str) -> list[Fire]:
        for sc in self.scenarios:
            if sc.scenario_id == scenario_id:
                return sc.fires
        raise KeyError(f"no scenario {scenario_id!r} in this ModelParams")
