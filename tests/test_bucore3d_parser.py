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


def test_parses_currentUse():
    fixture = b"""<?xml version="1.0"?>
    <root xmlns:gml="http://www.opengis.net/gml/3.2"
          xmlns:bu-core3d="http://inspire.ec.europa.eu/schemas/bu-core3d/4.0"
          xmlns:bu-base="http://inspire.ec.europa.eu/schemas/bu-base/4.0"
          xmlns:xlink="http://www.w3.org/1999/xlink">
      <bu-core3d:Building gml:id="DENW_1">
        <bu-base:currentUse>
          <bu-base:CurrentUse>
            <bu-base:currentUse xlink:href="http://inspire.ec.europa.eu/codelist/CurrentUseValue/residential"/>
          </bu-base:CurrentUse>
        </bu-base:currentUse>
        <gml:LinearRing><gml:posList>50 8 100 50.001 8 100 50.001 8.001 100 50 8.001 100 50 8 100</gml:posList></gml:LinearRing>
      </bu-core3d:Building>
    </root>
    """
    from io import BytesIO
    from bake.sources._bucore3d import parse_bucore3d_gml
    parsed = list(parse_bucore3d_gml(BytesIO(fixture)))
    assert len(parsed) == 1
    assert parsed[0].raw_attrs.get("currentUse") == "residential"


def test_parses_heightAboveGround():
    fixture = b"""<?xml version="1.0"?>
    <root xmlns:gml="http://www.opengis.net/gml/3.2"
          xmlns:bu-core3d="http://inspire.ec.europa.eu/schemas/bu-core3d/4.0"
          xmlns:bu-base="http://inspire.ec.europa.eu/schemas/bu-base/4.0">
      <bu-core3d:Building gml:id="DENW_2">
        <bu-base:heightAboveGround>
          <bu-base:HeightAboveGround>
            <bu-base:value uom="m">18.4</bu-base:value>
          </bu-base:HeightAboveGround>
        </bu-base:heightAboveGround>
        <gml:LinearRing><gml:posList>50 8 100 50.001 8 100 50.001 8.001 100 50 8 100</gml:posList></gml:LinearRing>
      </bu-core3d:Building>
    </root>
    """
    from io import BytesIO
    from bake.sources._bucore3d import parse_bucore3d_gml
    parsed = list(parse_bucore3d_gml(BytesIO(fixture)))
    assert parsed[0].height_m == 18.4


def test_parses_no_attrs_yields_empty_raw():
    fixture = b"""<?xml version="1.0"?>
    <root xmlns:gml="http://www.opengis.net/gml/3.2"
          xmlns:bu-core3d="http://inspire.ec.europa.eu/schemas/bu-core3d/4.0">
      <bu-core3d:Building gml:id="X">
        <gml:LinearRing><gml:posList>50 8 0 50.001 8 0 50.001 8.001 0 50 8 0</gml:posList></gml:LinearRing>
      </bu-core3d:Building>
    </root>
    """
    from io import BytesIO
    from bake.sources._bucore3d import parse_bucore3d_gml
    parsed = list(parse_bucore3d_gml(BytesIO(fixture)))
    assert parsed[0].raw_attrs == {}
    assert parsed[0].height_m is None


def test_parses_buildingNature():
    fixture = b"""<?xml version="1.0"?>
    <root xmlns:gml="http://www.opengis.net/gml/3.2"
          xmlns:bu-core3d="http://inspire.ec.europa.eu/schemas/bu-core3d/4.0"
          xmlns:bu-base="http://inspire.ec.europa.eu/schemas/bu-base/4.0"
          xmlns:xlink="http://www.w3.org/1999/xlink">
      <bu-core3d:Building gml:id="X">
        <bu-base:buildingNature xlink:href="https://registry.gdi-de.org/codelist/de.adv-online.inspire/BuildingNatureValue/bruecke"/>
        <gml:LinearRing><gml:posList>50 8 0 50.001 8 0 50.001 8.001 0 50 8 0</gml:posList></gml:LinearRing>
      </bu-core3d:Building>
    </root>
    """
    from io import BytesIO
    from bake.sources._bucore3d import parse_bucore3d_gml
    parsed = list(parse_bucore3d_gml(BytesIO(fixture)))
    assert parsed[0].raw_attrs.get("buildingNature") == "bruecke"
