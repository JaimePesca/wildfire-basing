"""Tests for src/pipeline/sites_water.py.

OSM/Overpass tests mock the HTTP layer (no real network needed), same
pattern as tests/test_firms_download.py. The IGAC loader is exercised
against a small synthetic GeoDataFrame written to a real GPKG file in
tmp_path (geopandas/pyogrio actually read it), not against a real IGAC
download; a separate skip-if-absent test documents where a real manually
obtained IGAC file would go.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.pipeline.sites_bases import CUNDINAMARCA_BBOX
from src.pipeline.sites_schema import CATEGORY_WATER_BODY
from src.pipeline.sites_water import (
    CAR_LAGUNA_LAYER_URL,
    DEFAULT_OVERPASS_ENDPOINT,
    IGAC_LICENSE,
    OSM_LICENSE,
    build_overpass_query,
    load_car_lagunas,
    load_igac_water_bodies,
    load_osm_water_bodies,
    parse_car_laguna_features,
    parse_overpass_elements,
    query_car_feature_count,
    query_car_feature_page,
    query_overpass,
)

# ---------------------------------------------------------------------------
# Overpass query construction
# ---------------------------------------------------------------------------


def test_build_overpass_query_reorders_bbox_to_south_west_north_east():
    west, south, east, north = CUNDINAMARCA_BBOX
    query = build_overpass_query(west, south, east, north, timeout_s=180)
    # Overpass QL bbox order is south,west,north,east, the opposite of this
    # repo's own west,south,east,north convention (module docstring).
    expected_bbox = f"{south},{west},{north},{east}"
    assert expected_bbox in query
    assert "[timeout:180]" in query
    assert 'natural"="water' in query
    assert 'water"="reservoir' in query
    assert 'landuse"="reservoir' in query
    assert "out center;" in query


def test_build_overpass_query_has_nine_branches():
    query = build_overpass_query(-75.10, 3.50, -72.80, 6.00)
    # 3 tag/value pairs x 3 element types (node/way/relation).
    assert query.count("(") - query.count("out center") >= 1
    for elem in ("node", "way", "relation"):
        assert query.count(f"{elem}[") == 3


# ---------------------------------------------------------------------------
# Overpass element parsing
# ---------------------------------------------------------------------------


def test_parse_overpass_elements_node_and_center():
    elements = [
        {
            "type": "node",
            "id": 123,
            "lat": 4.70,
            "lon": -73.99,
            "tags": {"name": "Test Lake", "natural": "water"},
        },
        {
            "type": "relation",
            "id": 4000410,
            "center": {"lat": 4.7020511, "lon": -73.9922274},
            "tags": {"name": "Embalse de San Rafael", "natural": "water", "water": "reservoir"},
        },
        # Element with no resolvable lat/lon (should not happen with "out
        # center;" but must not crash if it does).
        {"type": "way", "id": 999, "tags": {"name": "Broken"}},
    ]
    records = parse_overpass_elements(elements, source_year=2026)
    assert len(records) == 2
    ids = {r["site_id"] for r in records}
    assert ids == {"osm_node_123", "osm_relation_4000410"}
    san_rafael = next(r for r in records if r["site_id"] == "osm_relation_4000410")
    assert san_rafael["name"] == "Embalse de San Rafael"
    assert san_rafael["lat"] == pytest.approx(4.7020511)
    assert san_rafael["category"] == CATEGORY_WATER_BODY
    assert san_rafael["license"] == OSM_LICENSE == "ODbL 1.0"
    assert san_rafael["source_year"] == 2026


def test_query_overpass_posts_with_user_agent(monkeypatch):
    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()
    mock_response.json.return_value = {"elements": []}

    with patch("src.pipeline.sites_water.requests.post", return_value=mock_response) as mock_post:
        result = query_overpass("fake query", endpoint=DEFAULT_OVERPASS_ENDPOINT)

    assert result == {"elements": []}
    mock_post.assert_called_once()
    called_args, called_kwargs = mock_post.call_args
    assert called_args[0] == DEFAULT_OVERPASS_ENDPOINT
    assert called_kwargs["data"] == {"data": "fake query"}
    assert "User-Agent" in called_kwargs["headers"]


def test_load_osm_water_bodies_end_to_end_mocked():
    fake_response = {
        "elements": [
            {
                "type": "relation",
                "id": 4000410,
                "center": {"lat": 4.7020511, "lon": -73.9922274},
                "tags": {"name": "Embalse de San Rafael", "natural": "water", "water": "reservoir"},
            }
        ]
    }
    with patch("src.pipeline.sites_water.query_overpass", return_value=fake_response):
        df = load_osm_water_bodies(
            west=-75.10, south=3.50, east=-72.80, north=6.00, epsg=9377
        )
    assert len(df) == 1
    assert df.iloc[0]["name"] == "Embalse de San Rafael"
    assert df.iloc[0]["category"] == CATEGORY_WATER_BODY
    assert abs(df.iloc[0]["x_utm"]) > 1000


def test_load_osm_water_bodies_no_results_returns_empty_schema():
    with patch("src.pipeline.sites_water.query_overpass", return_value={"elements": []}):
        df = load_osm_water_bodies(west=-75.10, south=3.50, east=-72.80, north=6.00, epsg=9377)
    assert len(df) == 0
    from src.pipeline.sites_schema import CANDIDATE_SITE_COLUMNS

    assert list(df.columns) == CANDIDATE_SITE_COLUMNS


# ---------------------------------------------------------------------------
# CAR (Corporacion Autonoma Regional de Cundinamarca) ArcGIS REST
# ---------------------------------------------------------------------------


def test_query_car_feature_count_parses_count(monkeypatch):
    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()
    mock_response.json.return_value = {"count": 5024}

    with patch("src.pipeline.sites_water.requests.get", return_value=mock_response) as mock_get:
        count = query_car_feature_count(CAR_LAGUNA_LAYER_URL)

    assert count == 5024
    called_args, called_kwargs = mock_get.call_args
    assert called_args[0] == f"{CAR_LAGUNA_LAYER_URL}/query"
    assert called_kwargs["params"]["returnCountOnly"] == "true"


def test_query_car_feature_count_unexpected_response_raises():
    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()
    mock_response.json.return_value = {"error": "something else"}
    with patch("src.pipeline.sites_water.requests.get", return_value=mock_response):
        with pytest.raises(RuntimeError):
            query_car_feature_count(CAR_LAGUNA_LAYER_URL)


def _fake_laguna_geojson_feature(object_id, name, x, y):
    return {
        "type": "Feature",
        "geometry": {"type": "Polygon", "coordinates": [[[x, y], [x + 10, y], [x + 10, y + 10], [x, y + 10], [x, y]]]},
        "properties": {"OBJECTID": object_id, "NMG": name},
    }


def test_query_car_feature_page_requests_geojson_reprojected(monkeypatch):
    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()
    mock_response.json.return_value = {"features": [_fake_laguna_geojson_feature(1, "Laguna Verde", 100.0, 200.0)]}

    with patch("src.pipeline.sites_water.requests.get", return_value=mock_response) as mock_get:
        features = query_car_feature_page(CAR_LAGUNA_LAYER_URL, epsg=9377, offset=0)

    assert len(features) == 1
    called_args, called_kwargs = mock_get.call_args
    assert called_kwargs["params"]["outSR"] == 9377
    assert called_kwargs["params"]["f"] == "geojson"
    assert called_kwargs["params"]["resultOffset"] == 0


def test_parse_car_laguna_features_blank_name_treated_as_none():
    features = [
        _fake_laguna_geojson_feature(1, "Laguna Verde", 4808000.0, 2148000.0),
        _fake_laguna_geojson_feature(2, " ", 4809000.0, 2149000.0),
        _fake_laguna_geojson_feature(3, "", 4810000.0, 2150000.0),
        {"type": "Feature", "geometry": None, "properties": {"OBJECTID": 4, "NMG": "Broken"}},
    ]
    records = parse_car_laguna_features(features, epsg=9377, source_year=2026)
    # The record with no geometry is skipped, not fabricated.
    assert len(records) == 3
    by_id = {r["site_id"]: r for r in records}
    assert by_id["car_laguna_1"]["name"] == "Laguna Verde"
    assert by_id["car_laguna_2"]["name"] is None
    assert by_id["car_laguna_3"]["name"] is None
    assert by_id["car_laguna_1"]["category"] == CATEGORY_WATER_BODY
    assert by_id["car_laguna_1"]["source_year"] == 2026


def test_load_car_lagunas_pages_until_full_count():
    page1 = [_fake_laguna_geojson_feature(i, f"Laguna {i}", 4808000.0 + i, 2148000.0 + i) for i in range(2)]
    page2 = [_fake_laguna_geojson_feature(i, f"Laguna {i}", 4808000.0 + i, 2148000.0 + i) for i in range(2, 3)]

    with patch("src.pipeline.sites_water.query_car_feature_count", return_value=3):
        with patch("src.pipeline.sites_water.query_car_feature_page", side_effect=[page1, page2]) as mock_page:
            df = load_car_lagunas(epsg=9377, page_size=2)

    assert len(df) == 3
    assert mock_page.call_count == 2
    first_call_kwargs = mock_page.call_args_list[0].kwargs
    second_call_kwargs = mock_page.call_args_list[1].kwargs
    assert first_call_kwargs["offset"] == 0
    assert second_call_kwargs["offset"] == 2


def test_load_car_lagunas_no_features_returns_empty_schema():
    with patch("src.pipeline.sites_water.query_car_feature_count", return_value=0):
        df = load_car_lagunas(epsg=9377)
    assert len(df) == 0
    from src.pipeline.sites_schema import CANDIDATE_SITE_COLUMNS

    assert list(df.columns) == CANDIDATE_SITE_COLUMNS


# ---------------------------------------------------------------------------
# IGAC water bodies (local vector file, geopandas)
# ---------------------------------------------------------------------------

geopandas = pytest.importorskip("geopandas")
from shapely.geometry import Polygon  # noqa: E402


def _synthetic_igac_gdf():
    # A small square "reservoir" polygon near La Calera, in WGS84 degrees,
    # with a plausible name column, matching what a real IGAC water-bodies
    # layer would carry (attribute schema not independently confirmed, see
    # module docstring; "nombre" is the first candidate checked).
    polygon = Polygon(
        [
            (-73.995, 4.700),
            (-73.990, 4.700),
            (-73.990, 4.705),
            (-73.995, 4.705),
        ]
    )
    return geopandas.GeoDataFrame(
        {"nombre": ["Embalse Sintetico"], "geometry": [polygon]},
        crs="EPSG:4326",
    )


def test_load_igac_water_bodies_reads_local_file(tmp_path):
    gdf = _synthetic_igac_gdf()
    path = tmp_path / "water.gpkg"
    gdf.to_file(path, driver="GPKG")

    df = load_igac_water_bodies(str(path), epsg=9377)
    assert len(df) == 1
    row = df.iloc[0]
    assert row["name"] == "Embalse Sintetico"
    assert row["category"] == CATEGORY_WATER_BODY
    assert row["license"] == IGAC_LICENSE == "CC BY-SA 4.0"
    assert row["lat"] == pytest.approx(4.7025, abs=1e-2)
    assert row["lon"] == pytest.approx(-73.9925, abs=1e-2)


def test_load_igac_water_bodies_missing_name_column_left_none(tmp_path):
    polygon = Polygon([(-74.0, 4.6), (-73.9, 4.6), (-73.9, 4.7), (-74.0, 4.7)])
    gdf = geopandas.GeoDataFrame({"some_other_col": [1], "geometry": [polygon]}, crs="EPSG:4326")
    path = tmp_path / "water_no_name.gpkg"
    gdf.to_file(path, driver="GPKG")

    df = load_igac_water_bodies(str(path), epsg=9377)
    assert df.iloc[0]["name"] is None


def test_load_igac_water_bodies_missing_crs_raises(tmp_path):
    mock_gdf = MagicMock()
    mock_gdf.crs = None
    with patch("geopandas.read_file", return_value=mock_gdf):
        with pytest.raises(ValueError):
            load_igac_water_bodies(str(tmp_path / "no_crs.gpkg"), epsg=9377)


# Documented real-file path a user must manually populate from
# geoportal.igac.gov.co (see src/pipeline/sites_README.md). Skipped, not
# failed, until that file is actually present.
REPO_ROOT = Path(__file__).resolve().parent.parent
REAL_IGAC_PATH = REPO_ROOT / "data" / "raw" / "igac_cuerpos_agua_100k.gpkg"


@pytest.mark.skipif(
    not REAL_IGAC_PATH.exists(),
    reason=(
        f"Real IGAC Cuerpos de Agua file not found at {REAL_IGAC_PATH}. See "
        "src/pipeline/sites_README.md for the manual download instructions."
    ),
)
def test_load_igac_water_bodies_real_file():
    df = load_igac_water_bodies(str(REAL_IGAC_PATH), epsg=9377)
    assert len(df) > 0
