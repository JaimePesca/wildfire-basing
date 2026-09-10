"""Tests for src/scenarios/assemble.py. The underlying sampling/query
functions (land cover, slope, wind, population) are mocked, no real
rasters or network calls needed here, matching how the layers being
combined are each already tested individually.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from src.scenarios.assemble import (
    enrich_scenarios_with_ros_and_value_at_risk,
    to_model_scenarios,
)
from src.scenarios.day_scenarios import FireRecord, ScenarioRecord


def _scenario_with_fires(scenario_id, source_date, fire_ids):
    fires = [
        FireRecord(fire_id=fid, lat=4.7, lon=-74.0, x_utm=1000.0, y_utm=2000.0, size_proxy=1.0)
        for fid in fire_ids
    ]
    return ScenarioRecord(scenario_id=scenario_id, probability=0.5, source_date=source_date, fires=fires)


def test_enrich_fills_ros_and_value_at_risk_leaves_t_arrival_untouched():
    scenarios = [_scenario_with_fires("s1", "2024-01-05", ["f1", "f2"])]
    for fire in scenarios[0].fires:
        fire.t_arrival = 1.5  # pretend day_scenarios.enrich_t_arrival already ran

    with (
        patch("src.scenarios.assemble.sample_land_cover_for_fires", return_value={"f1": 30, "f2": 30}),
        patch("src.scenarios.assemble.sample_slope_degrees", return_value=10.0),
        patch("src.scenarios.assemble.fetch_wind_speed_for_fires", return_value={"f1": 2.0, "f2": 2.0}),
        patch(
            "src.scenarios.assemble.compute_ros_for_fires",
            return_value={"f1": 0.5, "f2": 0.5},
        ) as mock_ros,
        patch(
            "src.scenarios.assemble.sum_population_for_fires",
            return_value={"f1": 100.0, "f2": 200.0},
        ) as mock_pop,
    ):
        enrich_scenarios_with_ros_and_value_at_risk(
            scenarios,
            worldcover_tile_paths=["fake_wc.tif"],
            srtm_tile_paths=["fake_srtm.tif"],
            worldpop_raster_path="fake_pop.tif",
            ros_scale=1.0,
        )

    f1, f2 = scenarios[0].fires
    assert f1.ros_param == 0.5
    assert f2.value_at_risk == 200.0
    assert f1.t_arrival == 1.5  # untouched by this function
    mock_ros.assert_called_once()
    mock_pop.assert_called_once()


def test_enrich_no_fires_is_a_noop():
    scenarios = [ScenarioRecord(scenario_id="s_empty", probability=1.0, source_date="2024-01-01", fires=[])]
    # Should not raise even though it would otherwise call the (unmocked) network/raster functions.
    enrich_scenarios_with_ros_and_value_at_risk(
        scenarios,
        worldcover_tile_paths=[],
        srtm_tile_paths=[],
        worldpop_raster_path="unused.tif",
        ros_scale=1.0,
    )


def test_to_model_scenarios_converts_complete_fires():
    scenario = _scenario_with_fires("s1", "2024-01-05", ["f1"])
    scenario.fires[0].ros_param = 0.3
    scenario.fires[0].value_at_risk = 500.0
    scenario.fires[0].t_arrival = 2.0

    model_scenarios, dropped = to_model_scenarios([scenario])

    assert dropped == []
    assert len(model_scenarios) == 1
    model_fire = model_scenarios[0].fires[0]
    assert model_fire.fire_id == "f1"
    assert model_fire.ros == 0.3
    assert model_fire.value_at_risk == 500.0
    assert model_fire.t_arrival == 2.0
    assert model_fire.x_utm == 1000.0


def test_to_model_scenarios_raises_by_default_on_missing_field():
    scenario = _scenario_with_fires("s1", "2024-01-05", ["f1"])
    scenario.fires[0].ros_param = 0.3
    scenario.fires[0].value_at_risk = None  # still missing
    scenario.fires[0].t_arrival = 2.0

    with pytest.raises(ValueError, match="f1"):
        to_model_scenarios([scenario])


def test_to_model_scenarios_drop_mode_excludes_incomplete_fires():
    scenario = _scenario_with_fires("s1", "2024-01-05", ["f1", "f2"])
    scenario.fires[0].ros_param = 0.3
    scenario.fires[0].value_at_risk = 500.0
    scenario.fires[0].t_arrival = 2.0
    # f2 stays incomplete (ros_param/value_at_risk/t_arrival all None).

    model_scenarios, dropped = to_model_scenarios([scenario], on_missing="drop")

    assert dropped == ["f2"]
    assert len(model_scenarios[0].fires) == 1
    assert model_scenarios[0].fires[0].fire_id == "f1"


def test_to_model_scenarios_invalid_on_missing_raises():
    scenario = _scenario_with_fires("s1", "2024-01-05", ["f1"])
    with pytest.raises(ValueError):
        to_model_scenarios([scenario], on_missing="ignore")
