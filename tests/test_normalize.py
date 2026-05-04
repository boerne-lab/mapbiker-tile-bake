from bake.sources._bucore3d import ParsedBuilding
from bake.normalize import to_schema_building


def test_passes_through_already_wgs84():
    parsed = ParsedBuilding(
        source_id="he_001",
        polygons=[[
            (50.110, 8.682, 110.0),
            (50.110, 8.683, 110.0),
            (50.111, 8.683, 110.0),
            (50.111, 8.682, 110.0),
            (50.110, 8.682, 110.0),
        ]],
    )
    out = to_schema_building(parsed)
    assert out is not None
    assert out.source_id == "he_001"
    assert len(out.polygons) == 1
    assert len(out.polygons[0].vertices) == 5
    v = out.polygons[0].vertices[0]
    assert v.lat == 50.110 and v.lon == 8.682 and v.alt == 110.0


def test_drops_buildings_with_zero_polygons():
    parsed = ParsedBuilding(source_id="empty", polygons=[])
    out = to_schema_building(parsed)
    assert out is None


def test_preserves_multiple_polygons():
    parsed = ParsedBuilding(
        source_id="he_002",
        polygons=[
            [(50.1, 8.6, 100.0), (50.1, 8.7, 100.0),
             (50.2, 8.7, 100.0), (50.2, 8.6, 100.0),
             (50.1, 8.6, 100.0)],
            [(50.3, 8.8, 105.0), (50.3, 8.9, 105.0),
             (50.4, 8.9, 105.0), (50.4, 8.8, 105.0),
             (50.3, 8.8, 105.0)],
        ],
    )
    out = to_schema_building(parsed)
    assert out is not None
    assert len(out.polygons) == 2
    assert out.polygons[0].vertices[0].lat == 50.1
    assert out.polygons[1].vertices[0].lat == 50.3
