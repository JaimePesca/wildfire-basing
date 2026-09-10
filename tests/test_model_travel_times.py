"""Tests for src/model/travel_times.py against hand-calculated distances,
using small synthetic site tables shaped like candidate_bases.csv /
candidate_water.csv (site_id, x_utm, y_utm), not real Colombian coordinates.
"""

from __future__ import annotations

import math

import pandas as pd
import pytest

from src.model.schema import Fire
from src.model.travel_times import (
    assemble_model_params,
    compute_t_arrival,
    compute_t_base_fire,
    compute_t_fire_water,
    single_aircraft_speed,
)


def test_single_aircraft_speed_extracts_the_one_value():
    assert single_aircraft_speed({"T1": 100.0}) == 100.0


def test_single_aircraft_speed_raises_for_multiple_types():
    with pytest.raises(ValueError):
        single_aircraft_speed({"T1": 100.0, "T2": 150.0})


def test_compute_t_base_fire_is_distance_over_speed():
    bases = pd.DataFrame({"site_id": ["B1"], "x_utm": [0.0], "y_utm": [0.0]})
    fires = [Fire(fire_id="F1", x_utm=300.0, y_utm=400.0, ros=0.0, t_arrival=0.0, value_at_risk=0.0)]
    result = compute_t_base_fire(bases, fires, "s1", speed={"T1": 100.0})
    # 3-4-5 triangle: distance 500, speed 100 -> 5.0
    assert result[("s1", "B1", "F1")] == pytest.approx(5.0)


def test_compute_t_fire_water_is_distance_over_speed():
    water_points = pd.DataFrame({"site_id": ["W1"], "x_utm": [0.0], "y_utm": [0.0]})
    fires = [Fire(fire_id="F1", x_utm=6.0, y_utm=8.0, ros=0.0, t_arrival=0.0, value_at_risk=0.0)]
    result = compute_t_fire_water(water_points, fires, "s1", speed={"T1": 2.0})
    # 3-4-5 triangle scaled: distance 10, speed 2 -> 5.0
    assert result[("s1", "F1", "W1")] == pytest.approx(5.0)


def test_compute_t_arrival_is_min_over_bases():
    bases = pd.DataFrame(
        {"site_id": ["B_far", "B_near"], "x_utm": [1000.0, 0.0], "y_utm": [0.0, 0.0]}
    )
    fires = [Fire(fire_id="F1", x_utm=30.0, y_utm=40.0, ros=0.0, t_arrival=0.0, value_at_risk=0.0)]
    result = compute_t_arrival(bases, fires, speed={"T1": 10.0})
    # distance to B_near = 50 (3-4-5 triangle x10), to B_far = hypot(970,40) much larger
    assert result["F1"] == pytest.approx(50.0 / 10.0)


def test_compute_t_arrival_empty_bases_raises():
    bases = pd.DataFrame({"site_id": [], "x_utm": [], "y_utm": []})
    fires = [Fire(fire_id="F1", x_utm=0.0, y_utm=0.0, ros=0.0, t_arrival=0.0, value_at_risk=0.0)]
    with pytest.raises(ValueError):
        compute_t_arrival(bases, fires, speed={"T1": 10.0})


def test_assemble_model_params_from_site_tables():
    bases = pd.DataFrame({"site_id": ["B1"], "x_utm": [0.0], "y_utm": [0.0]})
    water_points = pd.DataFrame({"site_id": ["W1"], "x_utm": [0.0], "y_utm": [0.0]})
    fire = Fire(fire_id="F1", x_utm=100.0, y_utm=0.0, ros=0.05, t_arrival=2.0, value_at_risk=500.0)
    from src.model.schema import Scenario

    scenario = Scenario(scenario_id="s1", probability=1.0, fires=[fire])

    params = assemble_model_params(
        bases,
        water_points,
        [scenario],
        budget=10_000.0,
        window=8.0,
        ops_time=0.1,
        cvar_alpha=0.9,
        mean_risk_weight=0.5,
        initial_fire_area=5.0,
        liters_per_sqm=1.5,
        cost_base={"B1": 1000.0},
        cost_aircraft={"T1": 500.0},
        cost_water={"W1": 800.0},
        tank={"T1": 200.0},
        speed={"T1": 50.0},
    )

    assert params.bases == ["B1"]
    assert params.water_points == ["W1"]
    assert params.aircraft_types == ["T1"]
    assert params.t_base_fire[("s1", "B1", "F1")] == pytest.approx(100.0 / 50.0)
    assert params.t_fire_water[("s1", "F1", "W1")] == pytest.approx(100.0 / 50.0)


def test_assemble_model_params_missing_cost_raises():
    bases = pd.DataFrame({"site_id": ["B1", "B2"], "x_utm": [0.0, 1.0], "y_utm": [0.0, 1.0]})
    water_points = pd.DataFrame({"site_id": ["W1"], "x_utm": [0.0], "y_utm": [0.0]})
    with pytest.raises(KeyError):
        assemble_model_params(
            bases,
            water_points,
            [],
            budget=10_000.0,
            window=8.0,
            ops_time=0.1,
            cvar_alpha=0.9,
            mean_risk_weight=0.5,
            initial_fire_area=5.0,
            liters_per_sqm=1.5,
            cost_base={"B1": 1000.0},  # missing B2 on purpose
            cost_aircraft={"T1": 500.0},
            cost_water={"W1": 800.0},
            tank={"T1": 200.0},
            speed={"T1": 50.0},
        )
