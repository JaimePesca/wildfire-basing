"""Sanity checks for src/model/aircraft.py's real Firehawk reference
values, and that they slot into travel_times.assemble_model_params
correctly (CLAUDE.md section 4/10 aircraft gap, closed 2026-08-30)."""

from __future__ import annotations

import pandas as pd

from src.model.aircraft import (
    COST_AIRCRAFT,
    FIREHAWK_ID,
    FIREHAWK_OPS_TIME_H,
    SPEED,
    TANK,
)
from src.model.schema import Fire, Scenario
from src.model.travel_times import assemble_model_params


def test_tank_capacity_matches_sourced_1000_gallons():
    assert TANK[FIREHAWK_ID] == 1000 * 3.785411784


def test_cost_matches_sourced_150_billion_cop_for_two_units():
    assert COST_AIRCRAFT[FIREHAWK_ID] * 2 == 150_000_000_000.0


def test_speed_is_positive_and_in_meters_per_hour_order_of_magnitude():
    # 150 knots cruise should land near 277,800 m/h, not m/s (~77) or km/h (~278).
    assert 200_000 < SPEED[FIREHAWK_ID] < 300_000


def test_ops_time_is_sourced_refill_plus_illustrative_drop_overhead():
    assert FIREHAWK_OPS_TIME_H == (60 / 3600) + (30 / 3600)


def test_assemble_model_params_accepts_real_aircraft_dicts():
    bases = pd.DataFrame([{"site_id": "B1", "x_utm": 0.0, "y_utm": 0.0}])
    water_points = pd.DataFrame([{"site_id": "W1", "x_utm": 1000.0, "y_utm": 0.0}])
    fire = Fire(fire_id="f1", x_utm=500.0, y_utm=0.0, ros=0.1, t_arrival=0.01, value_at_risk=100.0)
    scenarios = [Scenario(scenario_id="s1", probability=1.0, fires=[fire])]

    params = assemble_model_params(
        bases,
        water_points,
        scenarios,
        budget=1.0,
        window=8.0,
        ops_time=FIREHAWK_OPS_TIME_H,
        cvar_alpha=0.95,
        mean_risk_weight=0.5,
        initial_fire_area=5.0,
        liters_per_sqm=3.0,
        cost_base={"B1": 1.0},
        cost_aircraft=COST_AIRCRAFT,
        cost_water={"W1": 1.0},
        tank=TANK,
        speed=SPEED,
    )

    assert params.aircraft_types == [FIREHAWK_ID]
    # distance 500 m / speed (m/h) should be a small fraction of an hour, not
    # a huge number (would signal a units mismatch, e.g. speed in m/s).
    assert 0 < params.t_base_fire[("s1", "B1", "f1")] < 1.0
