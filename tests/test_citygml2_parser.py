"""Tests for the CityGML 2.0 parser (shared by Bayern + NRW bulk)."""
from pathlib import Path
from bake.sources._citygml2 import parse_citygml2_gml

BY_FIXTURE = Path(__file__).parent / "fixtures" / "by-sample.gml"
NRW_FIXTURE = Path(__file__).parent / "fixtures" / "nrw-sample.gml"


def test_bayern_fixture_yields_at_least_one_building():
    with BY_FIXTURE.open("rb") as f:
        buildings = list(parse_citygml2_gml(f))
    assert len(buildings) >= 1


def test_bayern_fixture_building_has_dach_wgs84_polygons():
    """The Bayern fixture's München-area UTM coords (~691 km E, 5335 km N)
    must transform to plausible München lat/lon (48.13°N, 11.57°E)."""
    with BY_FIXTURE.open("rb") as f:
        buildings = list(parse_citygml2_gml(f))
    b = buildings[0]
    assert isinstance(b.source_id, str) and len(b.source_id) > 0
    assert len(b.polygons) >= 1
    poly = b.polygons[0]
    assert len(poly) >= 4  # closed ring
    for v in poly:
        lat, lon, alt = v
        # München bbox ish: lat 48.0-48.3, lon 11.4-11.8
        assert 47.0 < lat < 51.0, f"lat {lat} not in DACH range"
        assert 8.0 < lon < 14.0, f"lon {lon} not in DACH range"
        # Altitude from the fixture's posList (520.0 m for München)
        assert -100.0 < alt < 4000.0


def test_nrw_fixture_yields_at_least_one_building():
    """NRW's synthetic CityGML 2.0 fixture should parse just like
    Bayern's — same format, same parser."""
    with NRW_FIXTURE.open("rb") as f:
        buildings = list(parse_citygml2_gml(f))
    assert len(buildings) >= 1


def test_handles_alternative_groundsurface_wrapper():
    """Real Bayern data uses bldg:boundedBy → bldg:GroundSurface
    instead of bldg:lod2Solid (per the M1 spec). The parser must
    handle both. Construct an in-memory CityGML with the alternative
    wrapper and verify it parses."""
    import io
    citygml_alt = b"""<?xml version="1.0" encoding="UTF-8"?>
<core:CityModel xmlns:core="http://www.opengis.net/citygml/2.0"
                xmlns:bldg="http://www.opengis.net/citygml/building/2.0"
                xmlns:gml="http://www.opengis.net/gml">
  <core:cityObjectMember>
    <bldg:Building gml:id="DEBY_ALT_001">
      <bldg:boundedBy>
        <bldg:GroundSurface>
          <bldg:lod2MultiSurface>
            <gml:MultiSurface>
              <gml:surfaceMember>
                <gml:Polygon>
                  <gml:exterior>
                    <gml:LinearRing>
                      <gml:posList srsDimension="3">
                        691400 5335870 520.0
                        691410 5335870 520.0
                        691410 5335880 520.0
                        691400 5335880 520.0
                        691400 5335870 520.0
                      </gml:posList>
                    </gml:LinearRing>
                  </gml:exterior>
                </gml:Polygon>
              </gml:surfaceMember>
            </gml:MultiSurface>
          </bldg:lod2MultiSurface>
        </bldg:GroundSurface>
      </bldg:boundedBy>
    </bldg:Building>
  </core:cityObjectMember>
</core:CityModel>"""
    buildings = list(parse_citygml2_gml(io.BytesIO(citygml_alt)))
    assert len(buildings) == 1
    assert buildings[0].source_id == "DEBY_ALT_001"
    assert len(buildings[0].polygons) == 1
    assert len(buildings[0].polygons[0]) == 5  # closed ring
