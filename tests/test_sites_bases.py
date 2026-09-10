"""Tests for src/pipeline/sites_bases.py.

No real network call is needed for the Aerocivil download test (HTTP is
mocked, same pattern as tests/test_firms_download.py). The AD 1.3 xlsx parser
is exercised against a small synthetic workbook built inline with openpyxl,
matching the real file's documented column layout (B name/icao, F DMS
coords), not against a real downloaded copy.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import openpyxl
import pandas as pd
import pytest

from src.pipeline.sites_bases import (
    AEROCIVIL_AD13_LOADER_URL,
    CUNDINAMARCA_BBOX,
    build_candidate_bases,
    download_aerocivil_ad13,
    load_aerocivil_aerodromes,
    load_military_bases,
    parse_aerocivil_aerodromes,
    parse_dms_cell,
    split_name_icao,
)
from src.pipeline.sites_schema import CATEGORY_CIVIL_AERODROME, CATEGORY_MILITARY_BASE

# ---------------------------------------------------------------------------
# DMS coordinate parsing
# ---------------------------------------------------------------------------


def test_parse_dms_cell_basic():
    lat, lon = parse_dms_cell("082953.76N\n0771626.45W")
    assert lat == pytest.approx(8.4982667, abs=1e-5)
    assert lon == pytest.approx(-77.2740139, abs=1e-5)


def test_parse_dms_cell_with_trailing_remarks_text():
    # Real cells sometimes have extra remarks appended, per module docstring.
    lat, lon = parse_dms_cell("043500.00N\n0740000.00W RWY 08/26 threshold displaced 200m")
    assert lat == pytest.approx(4.5833333, abs=1e-5)
    assert lon == pytest.approx(-74.0, abs=1e-5)


def test_parse_dms_cell_no_match_returns_none_none():
    lat, lon = parse_dms_cell("no coordinates here")
    assert lat is None
    assert lon is None


def test_parse_dms_cell_none_input():
    assert parse_dms_cell(None) == (None, None)


# ---------------------------------------------------------------------------
# Name / ICAO splitting
# ---------------------------------------------------------------------------


def test_split_name_icao_simple():
    name, icao = split_name_icao("ACANDI / SKAD")
    assert name == "ACANDI"
    assert icao == "SKAD"


def test_split_name_icao_with_newline_whitespace():
    name, icao = split_name_icao("ACANDI\n/ SKAD")
    assert name == "ACANDI"
    assert icao == "SKAD"


def test_split_name_icao_no_slash():
    name, icao = split_name_icao("SOME NAME ONLY")
    assert name == "SOME NAME ONLY"
    assert icao is None


def test_split_name_icao_none_input():
    assert split_name_icao(None) == (None, None)


# ---------------------------------------------------------------------------
# AD 1.3 xlsx parsing (synthetic workbook, real documented column layout)
# ---------------------------------------------------------------------------


def _write_synthetic_ad13(path):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Hoja1"
    # Title/header rows above the data: no valid DMS in column F, must be
    # skipped rather than mis-parsed as data (module docstring).
    ws.append(["", "INDICE DE AERODROMOS NO CONTROLADOS", "", "", "", ""])
    ws.append(["", "Nombre / Indicador", "INTL/NTL", "IFR/VFR", "Tipo", "Coordenadas"])
    # Real data rows, inside the Cundinamarca bbox (west -75.10, south 3.50,
    # east -72.80, north 6.00).
    ws.append(["", "EL LAGO / SKGC", "NTL", "VFR", "G", "045000.00N\n0740500.00W"])
    ws.append(["", "CUATRO VIENTOS / SQCU", "NTL", "VFR", "M", "044500.00N\n0741200.00W"])
    # A row outside the Cundinamarca bbox (Narino-ish), same file, must not
    # be silently included when bbox filtering is requested (module
    # docstring: name matching alone is unsafe, but a real bbox check on
    # parsed coordinates is fine).
    ws.append(["", "MOSQUERA / SKSQ", "NTL", "VFR", "G", "023000.00N\n0781500.00W"])
    # A blank row, must be skipped, not raise.
    ws.append(["", "", "", "", "", ""])
    wb.save(path)


def test_parse_aerocivil_aerodromes_skips_header_and_blank_rows(tmp_path):
    path = tmp_path / "ad13.xlsx"
    _write_synthetic_ad13(path)
    records = parse_aerocivil_aerodromes(str(path))
    assert len(records) == 3  # header rows and blank row skipped
    names = {r["name"] for r in records}
    assert names == {"EL LAGO", "CUATRO VIENTOS", "MOSQUERA"}
    for r in records:
        assert r["category"] == CATEGORY_CIVIL_AERODROME
        assert r["license"] is None  # no dataset-specific license found


def test_load_aerocivil_aerodromes_bbox_filter_excludes_outside_rows(tmp_path):
    path = tmp_path / "ad13.xlsx"
    _write_synthetic_ad13(path)
    df = load_aerocivil_aerodromes(str(path), epsg=9377, bbox=CUNDINAMARCA_BBOX)
    assert set(df["name"]) == {"EL LAGO", "CUATRO VIENTOS"}
    assert "MOSQUERA" not in set(df["name"])


def test_load_aerocivil_aerodromes_no_bbox_returns_all(tmp_path):
    path = tmp_path / "ad13.xlsx"
    _write_synthetic_ad13(path)
    df = load_aerocivil_aerodromes(str(path), epsg=9377, bbox=None)
    assert len(df) == 3


# ---------------------------------------------------------------------------
# Aerocivil xlsx download (mocked HTTP, no real network)
# ---------------------------------------------------------------------------


def test_download_aerocivil_ad13_writes_bytes_and_hits_verified_url(tmp_path):
    fake_bytes = b"PK\x03\x04fake xlsx bytes"
    resp = MagicMock()
    resp.content = fake_bytes
    resp.raise_for_status = MagicMock()

    out_path = tmp_path / "ad13.xlsx"
    with patch("src.pipeline.sites_bases.requests.get", return_value=resp) as mock_get:
        result = download_aerocivil_ad13(str(out_path))

    mock_get.assert_called_once()
    called_url = mock_get.call_args[0][0]
    assert called_url == AEROCIVIL_AD13_LOADER_URL
    assert mock_get.call_args.kwargs.get("allow_redirects") is True
    assert result == out_path
    assert out_path.read_bytes() == fake_bytes


def test_download_aerocivil_ad13_raises_on_error_status(tmp_path):
    resp = MagicMock()
    resp.raise_for_status.side_effect = Exception("boom")
    out_path = tmp_path / "ad13.xlsx"
    with patch("src.pipeline.sites_bases.requests.get", return_value=resp):
        with pytest.raises(Exception):
            download_aerocivil_ad13(str(out_path))
    assert not out_path.exists()


# ---------------------------------------------------------------------------
# Military bases CSV (manual-entry template)
# ---------------------------------------------------------------------------


def test_load_military_bases_synthetic_csv_skips_blank_rows(tmp_path):
    csv_path = tmp_path / "military.csv"
    csv_path.write_text(
        "name,lat,lon,source,source_year,notes\n"
        "Test Base,4.5,-74.5,https://example.invalid/test,2020,synthetic row\n"
        "TODO manual entry,,,TODO,,not yet filled in\n",
        encoding="utf-8",
    )
    df = load_military_bases(str(csv_path), epsg=9377)
    assert len(df) == 1  # the blank TODO row is skipped, not an error
    row = df.iloc[0]
    assert row["name"] == "Test Base"
    assert row["category"] == CATEGORY_MILITARY_BASE
    assert row["source_url"] == "https://example.invalid/test"
    assert row["source_year"] == "2020"


def test_load_military_bases_real_template_parses_without_error():
    # The real, repo-committed template (data/raw/military_bases_template.csv)
    # must always be parseable; it is not gitignored, unlike downloaded data.
    df = load_military_bases("data/raw/military_bases_template.csv", epsg=9377)
    assert len(df) == 1  # only CACOM-4 Melgar is filled in at authoring time
    row = df.iloc[0]
    assert "CACOM-4" in row["name"]
    assert row["lat"] == pytest.approx(4.21644, abs=1e-4)
    assert row["lon"] == pytest.approx(-74.63500, abs=1e-4)


def test_load_military_bases_missing_column_raises(tmp_path):
    csv_path = tmp_path / "bad.csv"
    csv_path.write_text("name,lat,lon\nTest,1,2\n", encoding="utf-8")
    with pytest.raises(ValueError):
        load_military_bases(str(csv_path), epsg=9377)


# ---------------------------------------------------------------------------
# Combined build_candidate_bases
# ---------------------------------------------------------------------------


def test_build_candidate_bases_combines_both_sources(tmp_path):
    ad13_path = tmp_path / "ad13.xlsx"
    _write_synthetic_ad13(ad13_path)

    mil_path = tmp_path / "military.csv"
    mil_path.write_text(
        "name,lat,lon,source,source_year,notes\n"
        "Test Base,4.5,-74.5,https://example.invalid/test,2020,synthetic row\n",
        encoding="utf-8",
    )

    combined = build_candidate_bases(str(ad13_path), str(mil_path), epsg=9377, bbox=CUNDINAMARCA_BBOX)
    assert set(combined["category"]) == {CATEGORY_CIVIL_AERODROME, CATEGORY_MILITARY_BASE}
    assert len(combined) == 3  # 2 aerodromes inside bbox + 1 military base
