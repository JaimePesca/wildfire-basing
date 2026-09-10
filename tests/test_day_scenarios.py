"""Tests for src/scenarios/day_scenarios.py using a small synthetic Event
record fixture, not real Colombian fire data."""

from __future__ import annotations

import json
from datetime import date

import numpy as np
import pandas as pd
import pytest

from src.scenarios.day_scenarios import (
    ScenarioRecord,
    bootstrap_scenarios,
    build_day_pool,
    enrich_t_arrival,
    read_scenarios_json,
    write_scenarios_json,
)


def _synthetic_events() -> pd.DataFrame:
    # Three events on 2024-01-05 (two same day), one on 2024-01-07;
    # 2024-01-06 has none, an intentional "quiet day". t_start is parsed to
    # datetime here to match load_events()'s contract (build_day_pool
    # assumes that has already happened, it is not its job to reparse).
    df = pd.DataFrame(
        {
            "event_id": ["evt_1", "evt_2", "evt_3"],
            "centroid_lat": [4.7, 4.8, 5.0],
            "centroid_lon": [-74.0, -74.1, -73.9],
            "x_utm": [1000.0, 2000.0, 3000.0],
            "y_utm": [500.0, 600.0, 700.0],
            "t_start": [
                "2024-01-05 06:00:00+00:00",
                "2024-01-05 18:00:00+00:00",
                "2024-01-07 09:00:00+00:00",
            ],
            "frp_total": [12.5, 30.0, 5.0],
        }
    )
    df["t_start"] = pd.to_datetime(df["t_start"])
    return df


def test_build_day_pool_includes_quiet_days_with_empty_fire_list():
    events = _synthetic_events()
    pool = build_day_pool(events, date(2024, 1, 5), date(2024, 1, 7))

    assert set(pool.keys()) == {date(2024, 1, 5), date(2024, 1, 6), date(2024, 1, 7)}
    assert len(pool[date(2024, 1, 5)]) == 2
    assert len(pool[date(2024, 1, 6)]) == 0
    assert len(pool[date(2024, 1, 7)]) == 1


def test_build_day_pool_fire_fields_and_pending_none():
    events = _synthetic_events()
    pool = build_day_pool(events, date(2024, 1, 5), date(2024, 1, 5))
    fires = pool[date(2024, 1, 5)]
    fire_ids = {f.fire_id for f in fires}
    assert fire_ids == {"evt_1", "evt_2"}
    for f in fires:
        # ros_param/value_at_risk/t_arrival must stay None (pending), not a
        # guessed number, per CLAUDE.md section 5.3.
        assert f.ros_param is None
        assert f.value_at_risk is None
        assert f.t_arrival is None
    evt1 = next(f for f in fires if f.fire_id == "evt_1")
    assert evt1.size_proxy == 12.5


def test_bootstrap_scenarios_respects_count_and_uniform_probability():
    events = _synthetic_events()
    pool = build_day_pool(events, date(2024, 1, 5), date(2024, 1, 7))
    rng = np.random.default_rng(0)
    scenarios = bootstrap_scenarios(pool, n_scenarios=10, rng=rng)

    assert len(scenarios) == 10
    for s in scenarios:
        assert s.probability == pytest.approx(0.1)
        assert s.source_date in {"2024-01-05", "2024-01-06", "2024-01-07"}


def test_bootstrap_scenarios_is_reproducible_with_same_seed():
    events = _synthetic_events()
    pool = build_day_pool(events, date(2024, 1, 5), date(2024, 1, 7))

    scenarios_a = bootstrap_scenarios(pool, n_scenarios=20, rng=np.random.default_rng(42))
    scenarios_b = bootstrap_scenarios(pool, n_scenarios=20, rng=np.random.default_rng(42))

    dates_a = [s.source_date for s in scenarios_a]
    dates_b = [s.source_date for s in scenarios_b]
    assert dates_a == dates_b


def test_bootstrap_scenarios_zero_scenarios_returns_empty_list():
    events = _synthetic_events()
    pool = build_day_pool(events, date(2024, 1, 5), date(2024, 1, 7))
    scenarios = bootstrap_scenarios(pool, n_scenarios=0, rng=np.random.default_rng(0))
    assert scenarios == []


def test_bootstrap_scenarios_can_draw_a_quiet_day_with_no_fires():
    # A day pool that is ALL quiet days: every scenario must still build,
    # with an empty fires list, not an error.
    events = _synthetic_events().iloc[0:0]  # no events at all
    pool = build_day_pool(events, date(2024, 1, 1), date(2024, 1, 2))
    scenarios = bootstrap_scenarios(pool, n_scenarios=5, rng=np.random.default_rng(0))
    assert len(scenarios) == 5
    assert all(s.fires == [] for s in scenarios)


def test_enrich_t_arrival_fills_min_travel_time_and_leaves_others_null():
    events = _synthetic_events()
    pool = build_day_pool(events, date(2024, 1, 5), date(2024, 1, 7))
    scenarios = bootstrap_scenarios(pool, n_scenarios=6, rng=np.random.default_rng(0))

    bases = pd.DataFrame({"site_id": ["B1"], "x_utm": [1000.0], "y_utm": [500.0]})
    enrich_t_arrival(scenarios, bases, speed={"T1": 100.0})

    fires_with_data = [f for s in scenarios for f in s.fires]
    assert fires_with_data, "test setup should draw at least one scenario with fires"
    for fire in fires_with_data:
        expected = ((fire.x_utm - 1000.0) ** 2 + (fire.y_utm - 500.0) ** 2) ** 0.5 / 100.0
        assert fire.t_arrival == pytest.approx(expected)
        # ros_param/value_at_risk are a separate, still-unimplemented decision
        # (section 5.3), enrich_t_arrival must not touch them.
        assert fire.ros_param is None
        assert fire.value_at_risk is None


def test_enrich_t_arrival_no_fires_anywhere_is_a_noop():
    pool = build_day_pool(_synthetic_events().iloc[0:0], date(2024, 1, 1), date(2024, 1, 1))
    scenarios = bootstrap_scenarios(pool, n_scenarios=3, rng=np.random.default_rng(0))
    bases = pd.DataFrame({"site_id": ["B1"], "x_utm": [0.0], "y_utm": [0.0]})
    enrich_t_arrival(scenarios, bases, speed={"T1": 100.0})  # must not raise
    assert all(s.fires == [] for s in scenarios)


def test_write_scenarios_json_round_trips_with_null_pending_fields(tmp_path):
    scenario = ScenarioRecord(
        scenario_id="scn_00000",
        probability=1.0,
        source_date="2024-01-05",
        fires=list(build_day_pool(_synthetic_events(), date(2024, 1, 5), date(2024, 1, 5))[date(2024, 1, 5)]),
    )
    out = tmp_path / "scenarios.json"
    write_scenarios_json([scenario], str(out))

    with open(out, encoding="utf-8") as f:
        payload = json.load(f)

    assert len(payload) == 1
    assert payload[0]["scenario_id"] == "scn_00000"
    assert len(payload[0]["fires"]) == 2
    assert payload[0]["fires"][0]["ros_param"] is None
    assert payload[0]["fires"][0]["value_at_risk"] is None
    assert payload[0]["fires"][0]["t_arrival"] is None


def test_read_scenarios_json_round_trips_write(tmp_path):
    scenario = ScenarioRecord(
        scenario_id="scn_00000",
        probability=0.5,
        source_date="2024-01-05",
        fires=list(build_day_pool(_synthetic_events(), date(2024, 1, 5), date(2024, 1, 5))[date(2024, 1, 5)]),
    )
    scenario.fires[0].ros_param = 0.3
    scenario.fires[0].value_at_risk = 100.0
    scenario.fires[0].t_arrival = 1.5
    out = tmp_path / "scenarios.json"
    write_scenarios_json([scenario], str(out))

    loaded = read_scenarios_json(str(out))

    assert len(loaded) == 1
    assert loaded[0].scenario_id == "scn_00000"
    assert loaded[0].probability == 0.5
    assert len(loaded[0].fires) == 2
    assert loaded[0].fires[0].ros_param == 0.3
    assert loaded[0].fires[0].value_at_risk == 100.0
    assert loaded[0].fires[0].t_arrival == 1.5
    assert loaded[0].fires[1].ros_param is None
