"""Tests for src/pipeline/firms_download.py.

No real network call and no real MAP_KEY is needed to pass these tests: the
HTTP call is mocked throughout. See CLAUDE.md hard rule: the MAP_KEY must
only ever come from the FIRMS_MAP_KEY environment variable, never hardcoded.
"""

from __future__ import annotations

from datetime import date
from unittest.mock import MagicMock, patch

import pytest

from src.pipeline.firms_download import (
    MAP_KEY_ENV_VAR,
    MAP_KEY_REGISTRATION_URL,
    build_area_csv_url,
    chunk_date_range,
    download_firms,
    get_map_key,
)


# ---------------------------------------------------------------------------
# Date chunking
# ---------------------------------------------------------------------------


def test_chunk_date_range_splits_into_5_day_windows():
    chunks = chunk_date_range("2024-01-01", "2024-01-31")
    # 31 days -> ceil(31 / 5) = 7 chunks, all but the last exactly 5 days.
    assert len(chunks) == 7
    for chunk_start, chunk_end in chunks[:-1]:
        assert (chunk_end - chunk_start).days == 4  # 5 days inclusive
    # Chunks are contiguous, no gaps, no overlap, and cover the full range.
    assert chunks[0][0] == date(2024, 1, 1)
    assert chunks[-1][1] == date(2024, 1, 31)
    for (s1, e1), (s2, e2) in zip(chunks, chunks[1:]):
        assert s2 == e1 + (s2 - e1)  # sanity: s2 is after e1
        assert (s2 - e1).days == 1  # no gap, no overlap


def test_chunk_date_range_single_short_window():
    chunks = chunk_date_range("2024-01-01", "2024-01-03")
    assert chunks == [(date(2024, 1, 1), date(2024, 1, 3))]


def test_chunk_date_range_exact_multiple_of_five():
    chunks = chunk_date_range("2024-01-01", "2024-01-10")
    assert chunks == [
        (date(2024, 1, 1), date(2024, 1, 5)),
        (date(2024, 1, 6), date(2024, 1, 10)),
    ]


def test_chunk_date_range_start_after_end_raises():
    with pytest.raises(ValueError):
        chunk_date_range("2024-01-10", "2024-01-01")


def test_chunk_date_range_respects_custom_max_day_range():
    chunks = chunk_date_range("2024-01-01", "2024-01-06", max_day_range=3)
    assert chunks == [
        (date(2024, 1, 1), date(2024, 1, 3)),
        (date(2024, 1, 4), date(2024, 1, 6)),
    ]


# ---------------------------------------------------------------------------
# URL construction, matches the verified Area CSV API template.
# ---------------------------------------------------------------------------


def test_build_area_csv_url_matches_verified_template():
    url = build_area_csv_url(
        map_key="TESTKEY123",
        source="VIIRS_SNPP_SP",
        west=-75.10,
        south=3.50,
        east=-72.80,
        north=6.00,
        day_range=5,
        end_date=date(2024, 1, 5),
    )
    expected = (
        "https://firms.modaps.eosdis.nasa.gov/api/area/csv/"
        "TESTKEY123/VIIRS_SNPP_SP/-75.1,3.5,-72.8,6.0/5/2024-01-05"
    )
    assert url == expected


def test_build_area_csv_url_area_order_is_west_south_east_north():
    # The FIRMS docs explicitly warn this is NOT north/south/east/west.
    url = build_area_csv_url(
        map_key="K", source="MODIS_NRT", west=1, south=2, east=3, north=4, day_range=1, end_date="2024-01-01"
    )
    assert "/1,2,3,4/" in url


# ---------------------------------------------------------------------------
# MAP_KEY from environment only.
# ---------------------------------------------------------------------------


def test_get_map_key_reads_env_var(monkeypatch):
    monkeypatch.setenv(MAP_KEY_ENV_VAR, "abc123")
    assert get_map_key() == "abc123"


def test_get_map_key_missing_raises_actionable_error(monkeypatch):
    monkeypatch.delenv(MAP_KEY_ENV_VAR, raising=False)
    with pytest.raises(RuntimeError) as exc_info:
        get_map_key()
    message = str(exc_info.value)
    assert MAP_KEY_ENV_VAR in message
    assert MAP_KEY_REGISTRATION_URL in message


def test_get_map_key_empty_string_raises(monkeypatch):
    monkeypatch.setenv(MAP_KEY_ENV_VAR, "")
    with pytest.raises(RuntimeError):
        get_map_key()


# ---------------------------------------------------------------------------
# download_firms: mocked HTTP, no real network, writes chunked files.
# ---------------------------------------------------------------------------


def _mock_response(text: str = "latitude,longitude\n4.6,-74.1\n"):
    resp = MagicMock()
    resp.text = text
    resp.raise_for_status = MagicMock()
    return resp


def test_download_firms_writes_one_file_per_chunk(tmp_path):
    with patch("src.pipeline.firms_download.requests.get", return_value=_mock_response()) as mock_get:
        written = download_firms(
            map_key="FAKEKEY",
            west=-75.10,
            south=3.50,
            east=-72.80,
            north=6.00,
            start_date="2024-01-01",
            end_date="2024-01-10",
            source="VIIRS_SNPP_SP",
            out_dir=str(tmp_path),
        )

    assert mock_get.call_count == 2  # 10 days -> two 5-day chunks
    assert len(written) == 2
    for path in written:
        assert path.exists()
        assert path.read_text(encoding="utf-8") == "latitude,longitude\n4.6,-74.1\n"
    names = sorted(p.name for p in written)
    assert names == [
        "firms_VIIRS_SNPP_SP_2024-01-01_2024-01-05.csv",
        "firms_VIIRS_SNPP_SP_2024-01-06_2024-01-10.csv",
    ]


def test_download_firms_calls_verified_url_template(tmp_path):
    with patch("src.pipeline.firms_download.requests.get", return_value=_mock_response()) as mock_get:
        download_firms(
            map_key="FAKEKEY",
            west=-75.10,
            south=3.50,
            east=-72.80,
            north=6.00,
            start_date="2024-01-01",
            end_date="2024-01-03",
            source="VIIRS_SNPP_SP",
            out_dir=str(tmp_path),
        )

    called_url = mock_get.call_args[0][0]
    assert called_url == (
        "https://firms.modaps.eosdis.nasa.gov/api/area/csv/"
        "FAKEKEY/VIIRS_SNPP_SP/-75.1,3.5,-72.8,6.0/3/2024-01-03"
    )


def test_download_firms_creates_out_dir(tmp_path):
    out_dir = tmp_path / "nested" / "raw"
    with patch("src.pipeline.firms_download.requests.get", return_value=_mock_response()):
        download_firms(
            map_key="FAKEKEY",
            west=-75.10,
            south=3.50,
            east=-72.80,
            north=6.00,
            start_date="2024-01-01",
            end_date="2024-01-01",
            source="VIIRS_SNPP_SP",
            out_dir=str(out_dir),
        )
    assert out_dir.exists()
