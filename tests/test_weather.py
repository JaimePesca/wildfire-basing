"""Tests for src/scenarios/weather.py. HTTP mocked (no real network needed),
same pattern as tests/test_firms_download.py.
"""

from __future__ import annotations

from dataclasses import dataclass
from unittest.mock import MagicMock, patch

from src.scenarios.weather import (
    FILL_VALUE,
    fetch_wind_speed,
    fetch_wind_speed_for_fires,
)


@dataclass
class _Fire:
    fire_id: str
    lat: float
    lon: float


def _mock_response(date: str, value: float):
    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()
    mock_response.json.return_value = {
        "properties": {"parameter": {"WS10M": {date: value}}},
        "header": {"fill_value": FILL_VALUE},
    }
    return mock_response


def test_fetch_wind_speed_returns_real_value():
    with patch("src.scenarios.weather.requests.get", return_value=_mock_response("20240105", 2.01)) as mock_get:
        result = fetch_wind_speed(lat=4.7, lon=-74.0, date="20240105")

    assert result == 2.01
    called_args, called_kwargs = mock_get.call_args
    assert called_args[0] == "https://power.larc.nasa.gov/api/temporal/daily/point"
    assert called_kwargs["params"]["latitude"] == 4.7
    assert called_kwargs["params"]["longitude"] == -74.0
    assert called_kwargs["params"]["start"] == "20240105"
    assert called_kwargs["params"]["end"] == "20240105"


def test_fetch_wind_speed_fill_value_returns_none():
    with patch("src.scenarios.weather.requests.get", return_value=_mock_response("20240105", FILL_VALUE)):
        result = fetch_wind_speed(lat=4.7, lon=-74.0, date="20240105")
    assert result is None


def test_fetch_wind_speed_for_fires_caches_by_rounded_location_and_date():
    fires = [
        _Fire(fire_id="f1", lat=4.70001, lon=-74.00001),
        _Fire(fire_id="f2", lat=4.70002, lon=-74.00002),  # rounds to same key as f1
        _Fire(fire_id="f3", lat=5.20000, lon=-73.50000),  # different location
    ]
    dates = {"f1": "20240105", "f2": "20240105", "f3": "20240105"}

    with patch(
        "src.scenarios.weather.fetch_wind_speed", side_effect=[1.5, 3.0]
    ) as mock_fetch:
        result = fetch_wind_speed_for_fires(fires, dates)

    assert mock_fetch.call_count == 2  # f1/f2 share a cache entry, f3 is separate
    assert result["f1"] == result["f2"] == 1.5
    assert result["f3"] == 3.0
