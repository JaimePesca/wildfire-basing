"""Build SAA scenarios by bootstrap-resampling historical calendar days from
real Event records (CLAUDE.md section 5.3: scenario = one historical fire
day, decided 2026-08-18, not a full season, see that section for why).

ros_param and value_at_risk are left as None (JSON null) for every fire this
module produces. Their formulas are decided in form (section 5.3) but not
yet numerically implemented: the per-CORINE-class ROS base rate table, the
wind factor, the population buffer radius, and the raw CORINE/DTM/weather/
WorldPop/DANE sources themselves do not exist in this repo yet. Do not fill
these with a guessed number here; a Scenario record with None fields there
is the honest state until that data lands. size_proxy (frp_total) needs no
such decision, FRP is already a standard fire intensity measure Event
records carry, so it is filled in directly. t_arrival is also computable
now (section 5.3, decided 2026-08-20: min travel time to the closest
candidate base, needs no new data source, see enrich_t_arrival below and
src/model/travel_times.py.compute_t_arrival, which this reuses).

Building a day pool that correctly represents "most days have no fire" (not
just resampling among days that had one) requires explicitly enumerating
every calendar day in the requested date range, including the ones with
zero Event records, not inferring the range from the events themselves.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timedelta

import numpy as np
import pandas as pd


@dataclass
class FireRecord:
    """One fire within a day-scenario (CLAUDE.md section 6 Scenario
    record's per-fire fields). ros_param, value_at_risk, t_arrival: see
    module docstring, left None until their upstream data/formulas exist."""

    fire_id: str
    lat: float
    lon: float
    x_utm: float
    y_utm: float
    size_proxy: float  # frp_total, a standard FIRMS fire-intensity measure
    ros_param: float | None = None
    value_at_risk: float | None = None
    t_arrival: float | None = None


@dataclass
class ScenarioRecord:
    scenario_id: str
    probability: float
    source_date: str  # the historical day this scenario was resampled from, for traceability
    fires: list[FireRecord] = field(default_factory=list)


def load_events(path: str) -> pd.DataFrame:
    """Read a persisted Event record CSV (src/pipeline/events.py output),
    parsing t_start to a timezone-aware timestamp."""
    df = pd.read_csv(path)
    df["t_start"] = pd.to_datetime(df["t_start"])
    return df


def build_day_pool(
    events: pd.DataFrame, start_date: date, end_date: date
) -> dict[date, list[FireRecord]]:
    """Map every calendar day in [start_date, end_date] (inclusive) to the
    Event records whose t_start falls on that day. Days with no events get
    an empty list, they are real, informative "quiet day" outcomes, not
    missing data, and must stay in the pool so bootstrap sampling reflects
    how often nothing happens, not just how often something does."""
    events = events.copy()
    events["_date"] = events["t_start"].dt.date

    pool: dict[date, list[FireRecord]] = {}
    day = start_date
    while day <= end_date:
        day_events = events[events["_date"] == day]
        fires = [
            FireRecord(
                fire_id=row["event_id"],
                lat=row["centroid_lat"],
                lon=row["centroid_lon"],
                x_utm=row["x_utm"],
                y_utm=row["y_utm"],
                size_proxy=row["frp_total"],
            )
            for _, row in day_events.iterrows()
        ]
        pool[day] = fires
        day = day + timedelta(days=1)
    return pool


def bootstrap_scenarios(
    day_pool: dict[date, list[FireRecord]],
    n_scenarios: int,
    rng: np.random.Generator,
) -> list[ScenarioRecord]:
    """Draw n_scenarios days with replacement, uniformly over the day pool
    (plain SAA, CLAUDE.md section 6: "probability p_s uniform 1/|S|").
    Each draw becomes one ScenarioRecord carrying that day's real fires."""
    if n_scenarios <= 0:
        return []
    days = sorted(day_pool.keys())
    drawn_idx = rng.integers(0, len(days), size=n_scenarios)
    probability = 1.0 / n_scenarios

    scenarios = []
    for i, idx in enumerate(drawn_idx):
        day = days[idx]
        scenarios.append(
            ScenarioRecord(
                scenario_id=f"scn_{i:05d}",
                probability=probability,
                source_date=day.isoformat(),
                fires=list(day_pool[day]),  # each fire's own dataclass instance is reused, not mutated
            )
        )
    return scenarios


def enrich_t_arrival(
    scenarios: list[ScenarioRecord], bases: pd.DataFrame, speed: dict[str, float]
) -> None:
    """Fill in t_arrival for every fire across all scenarios (CLAUDE.md
    section 5.3, decided 2026-08-20): min travel time to the closest
    candidate base. Mutates the FireRecord objects in place (safe: the same
    historical day, and therefore the same FireRecord instances, can appear
    in more than one bootstrap-drawn scenario, but t_arrival only depends on
    fire location and the fixed base set, so it is the same value
    regardless of which scenario is asking). Reuses
    src.model.travel_times.compute_t_arrival rather than a second
    implementation of the distance/speed formula.
    """
    from src.model.travel_times import compute_t_arrival

    all_fires = {fire.fire_id: fire for s in scenarios for fire in s.fires}
    if not all_fires:
        return
    t_arrival = compute_t_arrival(bases, list(all_fires.values()), speed)
    for fire in all_fires.values():
        fire.t_arrival = t_arrival[fire.fire_id]


def write_scenarios_json(scenarios: list[ScenarioRecord], path: str) -> None:
    payload = [asdict(s) for s in scenarios]
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)


def read_scenarios_json(path: str) -> list[ScenarioRecord]:
    """Inverse of write_scenarios_json: reload a persisted scenario draw
    (e.g. data/processed/scenarios_2024full.json) into ScenarioRecord/
    FireRecord objects, so a bootstrap draw can be reused across multiple
    runs (matheuristic iterations, experiment repeats) instead of
    re-resampling randomly each time."""
    with open(path, "r", encoding="utf-8") as f:
        payload = json.load(f)
    return [
        ScenarioRecord(
            scenario_id=s["scenario_id"],
            probability=s["probability"],
            source_date=s["source_date"],
            fires=[FireRecord(**fire) for fire in s["fires"]],
        )
        for s in payload
    ]


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Bootstrap SAA scenarios (one historical fire day each) from real Event records."
    )
    parser.add_argument("--events", required=True, help="Path to a persisted Event record CSV.")
    parser.add_argument("--start-date", required=True, help="YYYY-MM-DD, first day of the pool.")
    parser.add_argument("--end-date", required=True, help="YYYY-MM-DD, last day of the pool (inclusive).")
    parser.add_argument("--n-scenarios", type=int, required=True, help="Number of scenarios to draw.")
    parser.add_argument("--seed", type=int, default=0, help="RNG seed, for reproducible sampling.")
    parser.add_argument(
        "--bases",
        default=None,
        help="Path to candidate_bases.csv (site_id/x_utm/y_utm). If given with --speed, "
        "fills t_arrival[f] = min travel time to the closest base; otherwise t_arrival stays null.",
    )
    parser.add_argument(
        "--speed",
        type=float,
        default=None,
        help="Single aircraft type speed (same units as x_utm/y_utm per hour), required with --bases.",
    )
    parser.add_argument("--out", required=True, help="Output JSON path.")
    args = parser.parse_args()

    if (args.bases is None) != (args.speed is None):
        parser.error("--bases and --speed must be given together, or not at all")

    events = load_events(args.events)
    start = datetime.strptime(args.start_date, "%Y-%m-%d").date()
    end = datetime.strptime(args.end_date, "%Y-%m-%d").date()
    pool = build_day_pool(events, start, end)

    rng = np.random.default_rng(args.seed)
    scenarios = bootstrap_scenarios(pool, args.n_scenarios, rng)

    if args.bases is not None:
        bases = pd.read_csv(args.bases)
        enrich_t_arrival(scenarios, bases, speed={"T1": args.speed})
        print(f"t_arrival filled in from {len(bases)} candidate bases in {args.bases}")

    write_scenarios_json(scenarios, args.out)

    n_days_with_fires = sum(1 for fires in pool.values() if fires)
    print(
        f"Day pool: {len(pool)} days ({n_days_with_fires} with at least one fire). "
        f"Wrote {len(scenarios)} scenarios to {args.out}"
    )


if __name__ == "__main__":
    main()
