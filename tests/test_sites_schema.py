"""Tests for src/pipeline/sites_schema.py (unified candidate-site schema)."""

from __future__ import annotations

import pytest

from src.pipeline.sites_schema import (
    CANDIDATE_SITE_COLUMNS,
    CATEGORY_CIVIL_AERODROME,
    CATEGORY_WATER_BODY,
    assemble_candidate_sites,
    empty_candidate_sites,
)


def test_empty_candidate_sites_has_exact_columns():
    df = empty_candidate_sites()
    assert list(df.columns) == CANDIDATE_SITE_COLUMNS
    assert len(df) == 0


def test_assemble_candidate_sites_projects_and_orders_columns():
    records = [
        {
            "site_id": "test_1",
            "name": "Test Site",
            "lat": 4.7020511,
            "lon": -73.9922274,
            "category": CATEGORY_WATER_BODY,
            "source_name": "unit test",
            "source_url": "https://example.invalid",
            "source_year": 2024,
            "license": "CC BY-SA 4.0",
            "notes": "synthetic",
        }
    ]
    df = assemble_candidate_sites(records, epsg=9377)
    assert list(df.columns) == CANDIDATE_SITE_COLUMNS
    assert len(df) == 1
    row = df.iloc[0]
    assert row["site_id"] == "test_1"
    assert row["category"] == CATEGORY_WATER_BODY
    # Projected coordinates should be real finite numbers, not passthrough
    # lat/lon (i.e. reprojection actually ran).
    assert abs(row["x_utm"]) > 1000
    assert abs(row["y_utm"]) > 1000


def test_assemble_candidate_sites_fills_missing_optional_fields_with_none():
    records = [
        {
            "site_id": "test_2",
            "lat": 4.6,
            "lon": -74.1,
            "category": CATEGORY_CIVIL_AERODROME,
        }
    ]
    df = assemble_candidate_sites(records, epsg=9377)
    row = df.iloc[0]
    assert row["name"] is None
    assert row["license"] is None
    assert row["source_url"] is None


def test_assemble_candidate_sites_rejects_invalid_category():
    records = [{"site_id": "x", "lat": 1.0, "lon": 1.0, "category": "not_a_real_category"}]
    with pytest.raises(ValueError):
        assemble_candidate_sites(records, epsg=9377)


def test_assemble_candidate_sites_rejects_missing_latlon():
    records = [{"site_id": "x", "lat": None, "lon": -74.0, "category": CATEGORY_WATER_BODY}]
    with pytest.raises(ValueError):
        assemble_candidate_sites(records, epsg=9377)


def test_assemble_candidate_sites_empty_input_raises():
    with pytest.raises(ValueError):
        assemble_candidate_sites([], epsg=9377)
