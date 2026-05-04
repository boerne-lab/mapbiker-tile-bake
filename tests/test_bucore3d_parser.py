from pathlib import Path
from bake.sources._bucore3d import parse_bucore3d_gml

FIXTURE = Path(__file__).parent / "fixtures" / "inspire-bu-core3d-frankfurt.xml"


def test_parses_at_least_one_building():
    with FIXTURE.open("rb") as f:
        buildings = list(parse_bucore3d_gml(f))
    assert len(buildings) >= 1, (
        f"expected >= 1 building, got {len(buildings)}")


def test_each_building_has_source_id_and_polygons():
    with FIXTURE.open("rb") as f:
        buildings = list(parse_bucore3d_gml(f))
    for b in buildings:
        assert isinstance(b.source_id, str) and len(b.source_id) > 0
        assert len(b.polygons) >= 1


def test_each_polygon_is_closed_ring_in_dach_range():
    """A closed ring has >= 4 vertices (first == last). Coordinates
    must look like DACH WGS84 lat/lon, with NHN-plausible altitudes."""
    with FIXTURE.open("rb") as f:
        buildings = list(parse_bucore3d_gml(f))
    for b in buildings:
        for poly in b.polygons:
            assert len(poly) >= 4, (
                f"closed ring needs >=4 vertices, got {len(poly)}")
            for v in poly:
                lat, lon, alt = v
                assert 47.0 < lat < 55.0, (
                    f"lat {lat} outside DACH range")
                assert 5.0 < lon < 16.0, (
                    f"lon {lon} outside DACH range")
                assert -100.0 < alt < 4000.0, (
                    f"alt {alt} outside plausible NHN range")


def test_frankfurt_fixture_has_two_buildings():
    """The hand-curated Frankfurt fixture is known to contain exactly 2
    bu-core3d:Building elements. Pinning this catches accidental
    structure changes (e.g. the parser walking into nested Buildings)."""
    with FIXTURE.open("rb") as f:
        buildings = list(parse_bucore3d_gml(f))
    assert len(buildings) == 2
