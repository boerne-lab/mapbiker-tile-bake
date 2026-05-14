import pytest
from pydantic import ValidationError


def test_osm_tile_validates_minimal():
    from bake.schema_osm import OSMTile, TileCoord
    t = OSMTile(
        schema_version=2, state="de_he",
        tile=TileCoord(z=15, x=0, y=0),
        generated_at="2026-05-07T00:00:00Z",
        source_dataset_version="geofabrik-2026-05",
        buildings=[], roads=[], waterways=[], water_polygons=[],
        railways=[], traffic_signals=[], trees=[], forests=[],
        bridges=[], landuse=[],
    )
    assert t.schema_version == 2
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
        sidewalk_left=False, sidewalk_right=False,
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
            schema_version=2, state="at_w",  # AT not in v2 schema literal
            tile=TileCoord(z=15, x=0, y=0),
            generated_at="2026-05-07T00:00:00Z",
            source_dataset_version="x",
            buildings=[], roads=[], waterways=[], water_polygons=[],
            railways=[], traffic_signals=[], trees=[], forests=[],
            bridges=[], landuse=[],
        )


def test_osm_tile_validates_at_v2():
    """Schema bumped to v2 for required sidewalk_left/right on Road."""
    from bake.schema_osm import OSMTile, TileCoord
    t = OSMTile(
        schema_version=2, state="de_he",
        tile=TileCoord(z=15, x=0, y=0),
        generated_at="2026-05-07T00:00:00Z",
        source_dataset_version="geofabrik-2026-05",
        buildings=[], roads=[], waterways=[], water_polygons=[],
        railways=[], traffic_signals=[], trees=[], forests=[],
        bridges=[], landuse=[],
    )
    assert t.schema_version == 2


def test_osm_tile_rejects_v1_schema_version():
    """v1 readers cannot parse v2 tiles, and vice versa — they live
    under different URL prefixes (/v1/osm/ vs /v2/osm/)."""
    from bake.schema_osm import OSMTile, TileCoord
    with pytest.raises(ValidationError):
        OSMTile(
            schema_version=1, state="de_he",
            tile=TileCoord(z=15, x=0, y=0),
            generated_at="2026-05-07T00:00:00Z",
            source_dataset_version="geofabrik-2026-05",
            buildings=[], roads=[], waterways=[], water_polygons=[],
            railways=[], traffic_signals=[], trees=[], forests=[],
            bridges=[], landuse=[],
        )


def test_road_requires_sidewalk_flags():
    """Sidewalk flags are REQUIRED — pre-bake assigns them explicitly
    via classify_sidewalks."""
    from bake.schema_osm import Road, Coord
    with pytest.raises(ValidationError):
        Road(id=1, coordinates=[Coord(lat=0, lon=0), Coord(lat=0, lon=0.001)],
             highway="primary", road_class="main_road",
             surface=None, surface_class="unknown",
             name=None, lanes=None, is_bridge=False, layer=0,
             cycleway=None,
             # sidewalk_left + sidewalk_right missing!
             )


def test_road_accepts_sidewalk_flags():
    from bake.schema_osm import Road, Coord
    r = Road(id=2, coordinates=[Coord(lat=0, lon=0), Coord(lat=0, lon=0.001)],
             highway="residential", road_class="local_road",
             surface=None, surface_class="unknown",
             name=None, lanes=None, is_bridge=False, layer=0,
             cycleway=None,
             sidewalk_left=True, sidewalk_right=False)
    assert r.sidewalk_left is True
    assert r.sidewalk_right is False
