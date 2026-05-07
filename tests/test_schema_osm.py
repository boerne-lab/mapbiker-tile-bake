import pytest
from pydantic import ValidationError


def test_osm_tile_validates_minimal():
    from bake.schema_osm import OSMTile, TileCoord
    t = OSMTile(
        schema_version=1, state="de_he",
        tile=TileCoord(z=15, x=0, y=0),
        generated_at="2026-05-07T00:00:00Z",
        source_dataset_version="geofabrik-2026-05",
        buildings=[], roads=[], waterways=[], water_polygons=[],
        railways=[], traffic_signals=[], trees=[], forests=[],
        bridges=[], landuse=[],
    )
    assert t.schema_version == 1
    assert t.state == "de_he"


def test_building_class_required():
    from bake.schema_osm import Building, Coord
    with pytest.raises(ValidationError):
        Building(
            id=1,
            coordinates=[Coord(lat=0, lon=0), Coord(lat=0, lon=0.001), Coord(lat=0.001, lon=0)],
            # building_class missing!
            building_type=None, levels=None, height_m=None,
            roof_shape=None, roof_height_m=None, roof_levels=None,
            wikidata=None, historic=None, name=None,
        )


def test_landuse_with_class_and_raw_tag():
    from bake.schema_osm import LandUse, Coord
    lu = LandUse(
        id=1,
        coordinates=[Coord(lat=0, lon=0), Coord(lat=0, lon=1), Coord(lat=1, lon=1)],
        landuse_class="farmland",
        raw_tag={"landuse": "farmland"},
    )
    assert lu.landuse_class == "farmland"
    assert lu.raw_tag == {"landuse": "farmland"}


def test_road_class_and_surface_class_required():
    from bake.schema_osm import Road, Coord
    r = Road(
        id=1,
        coordinates=[Coord(lat=0, lon=0), Coord(lat=0, lon=1)],
        highway="primary",
        road_class="main_road",
        surface=None,
        surface_class="unknown",
        name=None, lanes=None, is_bridge=False, layer=0, cycleway=None,
    )
    assert r.road_class == "main_road"
    assert r.surface_class == "unknown"


def test_tree_with_species_class():
    from bake.schema_osm import Tree, Coord
    t = Tree(
        id=1, coordinate=Coord(lat=0, lon=0),
        leaf_type="needleleaved", genus=None,
        species_class="needleleaved",
        crown_diameter_m=None, height_m=None,
    )
    assert t.species_class == "needleleaved"


def test_railway_with_class():
    from bake.schema_osm import Railway, Coord
    r = Railway(
        id=1,
        coordinates=[Coord(lat=0, lon=0), Coord(lat=0, lon=1)],
        kind="rail",
        railway_class="mainline",
        name=None, is_bridge=False, is_tunnel=False,
    )
    assert r.railway_class == "mainline"


def test_state_must_be_german():
    from bake.schema_osm import OSMTile, TileCoord
    with pytest.raises(ValidationError):
        OSMTile(
            schema_version=1, state="at_w",  # AT not in v1 schema literal
            tile=TileCoord(z=15, x=0, y=0),
            generated_at="2026-05-07T00:00:00Z",
            source_dataset_version="x",
            buildings=[], roads=[], waterways=[], water_polygons=[],
            railways=[], traffic_signals=[], trees=[], forests=[],
            bridges=[], landuse=[],
        )
