"""Tests for the Bayern Bayernwolke fetcher."""
from bake.sources.bayern import (
    coverage_tiles, tile_url, ENDPOINT_BASE,
)


def test_endpoint_constant_is_bayernwolke():
    assert ENDPOINT_BASE.startswith("https://download1.bayernwolke.de/")


def test_tile_url_format():
    url = tile_url(easting_km=690, northing_km=5334)
    assert url == "https://download1.bayernwolke.de/a/lod2/citygml/690_5334.gml"


def test_coverage_includes_munich_tile():
    """München is at (lat 48.137, lon 11.575). The 690_5334 tile is the
    one we measured at 156 MB during the M0 smoke test — it must
    appear in the coverage for any München-area bbox."""
    tiles = coverage_tiles(min_lat=48.13, min_lon=11.57,
                           max_lat=48.14, max_lon=11.58)
    assert (690, 5334) in tiles


def test_coverage_for_tiny_bbox_returns_at_most_4_tiles():
    """A bbox smaller than 2 km × 2 km can intersect at most 4
    UTM32N 2 km tiles (when it straddles a grid line)."""
    tiles = coverage_tiles(min_lat=48.13, min_lon=11.57,
                           max_lat=48.14, max_lon=11.58)
    assert 1 <= len(tiles) <= 4


def test_coverage_tiles_step_by_2_km():
    """Every (eastingKm, northingKm) pair must have both values even
    (multiples of 2) since UTM32N tiles are 2 km × 2 km."""
    tiles = coverage_tiles(min_lat=48.0, min_lon=11.0,
                           max_lat=48.2, max_lon=11.5)
    for ekm, nkm in tiles:
        assert ekm % 2 == 0, f"easting {ekm} not even"
        assert nkm % 2 == 0, f"northing {nkm} not even"


def test_coverage_for_state_wide_bbox_returns_thousands():
    """Bayern is ~70,500 km². At 4 km² per tile that's >17,000 tiles
    — verify the algorithm scales to state-size bboxes."""
    # Bayern bbox: (47.27, 8.97, 50.56, 13.84)
    tiles = coverage_tiles(min_lat=47.27, min_lon=8.97,
                           max_lat=50.56, max_lon=13.84)
    # Generous bracket: 10000-40000 tiles (AABB includes fringe outside state boundary)
    assert 10000 < len(tiles) < 40000
