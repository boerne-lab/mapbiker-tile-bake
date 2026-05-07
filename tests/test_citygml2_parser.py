"""Tests for the CityGML parser (handles both 1.0 and 2.0).

Real Bayernwolke uses CityGML 1.0 (verified on the 690_5334 München
tile, 2026-05-05). The synthetic fixtures use CityGML 2.0. The parser
must accept both."""
from pathlib import Path
import io
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


def test_handles_citygml_1_0_namespace():
    """Real Bayernwolke uses CityGML 1.0 — different namespace URI
    from CityGML 2.0. Verified by sampling the 690_5334.gml München
    tile on 2026-05-05; the first Bayern bake silently produced 0
    buildings because the parser was hard-coded to 2.0 namespace.

    This synthetic fixture mirrors the real 1.0-namespaced structure:
    default-xmlns=citygml/1.0, bldg=citygml/building/1.0, no `core:`
    prefix on cityObjectMember (it inherits the default namespace)."""
    citygml_v1 = b"""<?xml version="1.0" encoding="UTF-8"?>
<CityModel xmlns="http://www.opengis.net/citygml/1.0"
           xmlns:bldg="http://www.opengis.net/citygml/building/1.0"
           xmlns:gml="http://www.opengis.net/gml">
  <cityObjectMember>
    <bldg:Building gml:id="DEBY_LOD2_v1_001">
      <bldg:measuredHeight uom="urn:adv:uom:m">11.715</bldg:measuredHeight>
      <bldg:roofType>1000</bldg:roofType>
      <bldg:lod2Solid>
        <gml:Solid>
          <gml:exterior>
            <gml:CompositeSurface>
              <gml:surfaceMember>
                <gml:Polygon>
                  <gml:exterior>
                    <gml:LinearRing>
                      <gml:posList srsDimension="3">
                        691478.01 5334825.81 516.71
                        691478.01 5334825.81 528.425
                        691473.38 5334813.05 528.425
                        691473.38 5334813.05 516.71
                        691478.01 5334825.81 516.71
                      </gml:posList>
                    </gml:LinearRing>
                  </gml:exterior>
                </gml:Polygon>
              </gml:surfaceMember>
            </gml:CompositeSurface>
          </gml:exterior>
        </gml:Solid>
      </bldg:lod2Solid>
    </bldg:Building>
  </cityObjectMember>
</CityModel>"""
    buildings = list(parse_citygml2_gml(io.BytesIO(citygml_v1)))
    assert len(buildings) == 1
    assert buildings[0].source_id == "DEBY_LOD2_v1_001"
    assert len(buildings[0].polygons) == 1
    poly = buildings[0].polygons[0]
    assert len(poly) == 5  # closed ring
    # München UTM32N (691478, 5334826) → ~(48.137, 11.575) WGS84
    lat, lon, alt = poly[0]
    assert 48.0 < lat < 48.3, f"lat {lat} not in München range"
    assert 11.4 < lon < 11.7, f"lon {lon} not in München range"
    assert alt == 516.71


def test_parses_function():
    fixture = b"""<?xml version="1.0"?>
    <root xmlns:gml="http://www.opengis.net/gml"
          xmlns:bldg="http://www.opengis.net/citygml/building/2.0"
          xmlns:core="http://www.opengis.net/citygml/2.0">
      <bldg:Building gml:id="X1">
        <bldg:function>31001_2010</bldg:function>
        <bldg:storeysAboveGround>5</bldg:storeysAboveGround>
        <bldg:measuredHeight>18.4</bldg:measuredHeight>
        <bldg:yearOfConstruction>1985</bldg:yearOfConstruction>
        <gml:LinearRing><gml:posList>691000 5334000 100 691010 5334000 100 691010 5334010 100 691000 5334000 100</gml:posList></gml:LinearRing>
      </bldg:Building>
    </root>
    """
    from io import BytesIO
    from bake.sources._citygml2 import parse_citygml2_gml
    parsed = list(parse_citygml2_gml(BytesIO(fixture)))
    assert len(parsed) == 1
    assert parsed[0].raw_attrs.get("function") == "31001_2010"
    assert parsed[0].storeys == 5
    assert parsed[0].height_m == 18.4
    assert parsed[0].year_built == 1985


def test_no_attrs_falls_back_to_none():
    fixture = b"""<?xml version="1.0"?>
    <root xmlns:gml="http://www.opengis.net/gml"
          xmlns:bldg="http://www.opengis.net/citygml/building/1.0">
      <bldg:Building gml:id="Y1">
        <gml:LinearRing><gml:posList>691000 5334000 100 691010 5334000 100 691010 5334010 100 691000 5334000 100</gml:posList></gml:LinearRing>
      </bldg:Building>
    </root>
    """
    from io import BytesIO
    from bake.sources._citygml2 import parse_citygml2_gml
    parsed = list(parse_citygml2_gml(BytesIO(fixture)))
    assert parsed[0].raw_attrs == {}
    assert parsed[0].storeys is None
    assert parsed[0].height_m is None
    assert parsed[0].year_built is None


def test_parses_function_via_v1_namespace():
    """CityGML 1.0 (Bayernwolke) namespace must also resolve."""
    fixture = b"""<?xml version="1.0"?>
    <root xmlns:gml="http://www.opengis.net/gml"
          xmlns:bldg="http://www.opengis.net/citygml/building/1.0"
          xmlns:core="http://www.opengis.net/citygml/1.0">
      <bldg:Building gml:id="V1_X">
        <bldg:function>31007_X</bldg:function>
        <gml:LinearRing><gml:posList>691000 5334000 0 691010 5334000 0 691010 5334010 0 691000 5334000 0</gml:posList></gml:LinearRing>
      </bldg:Building>
    </root>
    """
    from io import BytesIO
    from bake.sources._citygml2 import parse_citygml2_gml
    parsed = list(parse_citygml2_gml(BytesIO(fixture)))
    assert parsed[0].raw_attrs.get("function") == "31007_X"
