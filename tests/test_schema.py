import pytest
import pydantic
from bake.schema import Tile, Building, Polygon, Vertex


def test_round_trip_minimal_tile():
    tile = Tile(
        schema_version=1,
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
            "schema_version": 2,
            "state": "de_he",
            "tile": {"z": 15, "x": 0, "y": 0},
            "generated_at": "2026-05-15T14:23:11Z",
            "source_dataset_version": "x",
            "buildings": [],
        })
