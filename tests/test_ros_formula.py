"""Tests for src/scenarios/ros_formula.py against hand-calculated values."""

from __future__ import annotations

import math
from dataclasses import dataclass

import pytest

from src.scenarios.ros_formula import (
    CLASS_RELATIVE_RATE,
    compute_ros,
    compute_ros_for_fires,
)


@dataclass
class _Fire:
    fire_id: str


def test_compute_ros_matches_hand_formula_for_grassland():
    # Grassland (30) relative rate 1.0, slope 20 deg, wind 3 m/s,
    # ros_scale=2.0, default coefficients.
    result = compute_ros(landcover_class=30, slope_degrees=20.0, wind_speed=3.0, ros_scale=2.0)
    expected = 2.0 * 1.0 * math.exp(0.05 * 20.0) * (1.0 + 0.1 * 3.0)
    assert result == pytest.approx(expected)


def test_compute_ros_flat_no_wind_reduces_to_scale_times_class_rate():
    result = compute_ros(landcover_class=10, slope_degrees=0.0, wind_speed=0.0, ros_scale=5.0)
    # exp(0)=1, (1+0)=1 -> just ros_scale * class_relative_rate[10]
    assert result == pytest.approx(5.0 * CLASS_RELATIVE_RATE[10])


def test_compute_ros_grassland_faster_than_forest_same_conditions():
    grass = compute_ros(landcover_class=30, slope_degrees=10.0, wind_speed=1.0, ros_scale=1.0)
    forest = compute_ros(landcover_class=10, slope_degrees=10.0, wind_speed=1.0, ros_scale=1.0)
    assert grass > forest


def test_compute_ros_built_up_is_zero():
    result = compute_ros(landcover_class=50, slope_degrees=15.0, wind_speed=5.0, ros_scale=10.0)
    assert result == pytest.approx(0.0)


def test_compute_ros_unknown_class_raises():
    with pytest.raises(ValueError):
        compute_ros(landcover_class=999, slope_degrees=0.0, wind_speed=0.0, ros_scale=1.0)


def test_compute_ros_steeper_slope_increases_rate():
    flat = compute_ros(landcover_class=20, slope_degrees=0.0, wind_speed=0.0, ros_scale=1.0)
    steep = compute_ros(landcover_class=20, slope_degrees=30.0, wind_speed=0.0, ros_scale=1.0)
    assert steep > flat
    assert steep == pytest.approx(flat * math.exp(0.05 * 30.0))


def test_compute_ros_for_fires_missing_input_yields_none():
    fires = [_Fire(fire_id="f1"), _Fire(fire_id="f2")]
    landcover = {"f1": 30, "f2": None}  # f2 missing land cover
    slopes = {"f1": 10.0, "f2": 5.0}
    winds = {"f1": 1.0, "f2": 1.0}

    result = compute_ros_for_fires(fires, landcover, slopes, winds, ros_scale=1.0)

    assert result["f2"] is None
    assert result["f1"] is not None
    assert result["f1"] == pytest.approx(compute_ros(30, 10.0, 1.0, ros_scale=1.0))
