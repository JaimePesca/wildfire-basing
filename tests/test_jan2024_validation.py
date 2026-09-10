"""January 2024 chaining validation (CLAUDE.md section 5).

CLAUDE.md section 5 explicitly requires validating that the pipeline
recovers the January 2024 Colombian fires as coherent, separate events (the
documented check against the "chaining" risk of density clustering merging
distinct fires into one blob). We do not have that real raw data in this
repo yet (data/raw is gitignored and empty by design, see CLAUDE.md sections
7 and 8, and src/pipeline/README.md).

This test is a no-op today (skipped) and requires no further code changes
once the real data is dropped in place: put the raw FIRMS/VIIRS CSV export
covering Cundinamarca, January 2024, at JAN2024_RAW_PATH below, and this test
will start actually running the validation on the next pytest run.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.pipeline.clean import clean_firms
from src.pipeline.events import build_events
from src.pipeline.io import load_firms_csv
from src.pipeline.project import project_to_crs
from src.pipeline.st_dbscan import STDBSCANConfig, cluster_detections

REPO_ROOT = Path(__file__).resolve().parent.parent

# Documented expected location for the real January 2024 raw export. See
# src/pipeline/README.md ("Downloading real FIRMS data") for how to produce
# this file with src/pipeline/firms_download.py, e.g.:
#   python -m src.pipeline.firms_download --start 2024-01-01 --end 2024-01-31 \
#       --source VIIRS_SNPP_SP --out-dir data/raw
# (which writes several date-chunked files; concatenate them into this single
# path, or point this constant at one of the chunk files, before running the
# real validation.)
JAN2024_RAW_PATH = REPO_ROOT / "data" / "raw" / "firms_cundinamarca_2024-01-01_2024-01-31.csv"

CONFIG_PATH = REPO_ROOT / "config" / "parameters.yaml"

# Minimum distinct events expected from a full month of Cundinamarca FIRMS
# detections in January 2024 (a month with well documented, numerous,
# geographically spread wildfires in the department, per CLAUDE.md section 8:
# "Cundinamarca leads the country in reported forest fire records"). This is
# a conservative floor, not a precise expected count (the exact expected
# event list is not known and must not be fabricated, per CLAUDE.md section
# 11 citation/evidence discipline): a pipeline suffering from the chaining
# risk (section 5) would collapse the month into a small handful of
# over-merged blobs, so a healthy event count comfortably above 1 is itself
# informative evidence against gross chaining, even without a ground-truth
# fire list to compare against event-by-event.
MIN_EXPECTED_EVENTS = 5


@pytest.mark.skipif(
    not JAN2024_RAW_PATH.exists(),
    reason=(
        f"Real January 2024 FIRMS raw data not found at {JAN2024_RAW_PATH}. "
        "Download it with src/pipeline/firms_download.py (see "
        "src/pipeline/README.md, 'Downloading real FIRMS data') and place it "
        "at this path to enable the real chaining validation."
    ),
)
def test_january_2024_fires_recovered_as_separate_events():
    """Real validation: run the full pipeline on the January 2024 raw export
    and check that distinct fires are not collapsed into one (or a small
    handful of) chained blob(s).

    Operational definition of "separate" used here, since the exact expected
    fire list is not known and must not be fabricated: the pipeline must
    produce at least MIN_EXPECTED_EVENTS distinct (non-noise) event records,
    and no single event may account for an overwhelming majority of all
    detections (a proxy for "the whole month did not chain into one blob").
    If/when a real ground-truth fire list for this window becomes available
    (e.g. cross-checked against UNGRD/DNBC per CLAUDE.md section 8), replace
    this proxy with an exact per-fire comparison.
    """
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        import yaml

        config = yaml.safe_load(f)

    df = load_firms_csv(str(JAN2024_RAW_PATH))
    df = clean_firms(df, config["firms"]["min_confidence"])
    df = project_to_crs(df, epsg=config["crs"]["epsg"])

    st_config = STDBSCANConfig.from_dict(config["st_dbscan"])
    labels = cluster_detections(df, st_config)
    events = build_events(df, labels)

    assert len(events) >= MIN_EXPECTED_EVENTS, (
        f"expected at least {MIN_EXPECTED_EVENTS} distinct events from January "
        f"2024 Cundinamarca detections, got {len(events)}; this suggests the "
        "chaining risk (CLAUDE.md section 5) is collapsing distinct fires "
        "into one blob"
    )

    total_detections = int(events["n_detections"].sum())
    largest = int(events["n_detections"].max())
    assert largest <= 0.5 * total_detections, (
        f"one event accounts for {largest} of {total_detections} total "
        "detections (over half); this is the chaining risk signature, a "
        "single blob swallowing what should be separate fires"
    )
