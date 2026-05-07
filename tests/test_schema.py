import pytest
import pydantic
from bake.schema import Tile, Building, Polygon, Vertex, BuildingAttributes, TileCoord


def _unknown_attrs() -> BuildingAttributes:
    return BuildingAttributes(building_class="unknown", raw={})


def test_round_trip_minimal_tile():
    tile = Tile(
        schema_version=2,
        state="de_he",
        tile={"z": 15, "x": 17086, "y": 10958},
        generated_at="2026-05-15T14:23:11Z",
        source_dataset_version="hessen-2026-Q1",
        buildings=[
            Building(
                source_id="he_HE_001",
                polygons=[
                    Polygon(vertices=[
                        Vertex(lat=50.110, lon=8.682, alt=110.0),
                        Vertex(lat=50.110, lon=8.683, alt=110.0),
                        Vertex(lat=50.111, lon=8.683, alt=110.0),
                        Vertex(lat=50.111, lon=8.682, alt=110.0),
                        Vertex(lat=50.110, lon=8.682, alt=110.0),
                    ])
                ],
                attributes=_unknown_attrs(),
            )
        ],
    )
    encoded = tile.model_dump_json()
    decoded = Tile.model_validate_json(encoded)
    assert decoded == tile
    assert decoded.buildings[0].polygons[0].vertices[0].lat == 50.110


def test_rejects_invalid_schema_version():
    with pytest.raises(pydantic.ValidationError):
        Tile.model_validate({
            "schema_version": 1,  # v1 no longer valid
            "state": "de_he",
            "tile": {"z": 15, "x": 0, "y": 0},
            "generated_at": "2026-05-15T14:23:11Z",
            "source_dataset_version": "x",
            "buildings": [],
        })


def test_building_with_attributes_validates():
    b = Building(
        source_id="x",
        polygons=[Polygon(vertices=[
            Vertex(lat=0, lon=0, alt=0),
            Vertex(lat=1, lon=0, alt=0),
            Vertex(lat=1, lon=1, alt=0),
            Vertex(lat=0, lon=0, alt=0),
        ])],
        attributes=BuildingAttributes(
            building_class="residential",
            measured_height_m=18.4,
            storeys_above_ground=5,
            year_of_construction=1985,
            raw={"currentUse": "residential"},
        ),
    )
    assert b.attributes.building_class == "residential"
    assert b.attributes.measured_height_m == 18.4


def test_building_without_attributes_fails():
    with pytest.raises(pydantic.ValidationError):
        Building(
            source_id="x",
            polygons=[Polygon(vertices=[
                Vertex(lat=0, lon=0, alt=0),
                Vertex(lat=1, lon=0, alt=0),
                Vertex(lat=1, lon=1, alt=0),
                Vertex(lat=0, lon=0, alt=0),
            ])],
        )  # missing attributes


def test_invalid_building_class_fails():
    with pytest.raises(pydantic.ValidationError):
        BuildingAttributes(
            building_class="not_a_class",
            measured_height_m=None,
            storeys_above_ground=None,
            year_of_construction=None,
            raw={},
        )


def test_tile_v2_schema_version():
    t = Tile(
        schema_version=2,
        state="de_he",
        tile=TileCoord(z=15, x=0, y=0),
        generated_at="2026-05-07T00:00:00Z",
        source_dataset_version="hessen-2026-Q1",
        buildings=[],
    )
    assert t.schema_version == 2


def test_tile_v1_no_longer_validates():
    with pytest.raises(pydantic.ValidationError):
        Tile(
            schema_version=1,  # v1 not supported in this v2 schema module
            state="de_he",
            tile=TileCoord(z=15, x=0, y=0),
            generated_at="2026-05-07T00:00:00Z",
            source_dataset_version="x",
            buildings=[],
        )
