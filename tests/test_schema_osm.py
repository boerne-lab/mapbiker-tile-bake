import pytest
from pydantic import ValidationError


def _minimal_tile(**kwargs):
    """Helper: build a minimal OSMTile v3 with overrideable fields."""
    from bake.schema_osm import OSMTile, TileCoord
    defaults = dict(
        schema_version=3, state="de_he",
        tile=TileCoord(z=15, x=0, y=0),
        generated_at="2026-05-07T00:00:00Z",
        source_dataset_version="geofabrik-2026-05",
        buildings=[], roads=[], waterways=[], water_polygons=[],
        railways=[], traffic_signals=[], trees=[], forests=[],
        bridges=[], landuse=[], barriers=[],
    )
    defaults.update(kwargs)
    return OSMTile(**defaults)


def test_osm_tile_validates_minimal():
    t = _minimal_tile()
    assert t.schema_version == 3
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
            schema_version=3, state="at_w",  # AT not in v3 schema literal
            tile=TileCoord(z=15, x=0, y=0),
            generated_at="2026-05-07T00:00:00Z",
            source_dataset_version="x",
            buildings=[], roads=[], waterways=[], water_polygons=[],
            railways=[], traffic_signals=[], trees=[], forests=[],
            bridges=[], landuse=[], barriers=[],
        )


def test_osm_tile_validates_at_v3():
    """Schema bumped to v3 for Road width/tunnel/maxspeed, Building colour/material,
    WaterPolygon kind, Tree taxon, and new Barrier layer."""
    t = _minimal_tile()
    assert t.schema_version == 3
    assert t.barriers == []


def test_osm_tile_rejects_v2_schema_version():
    """v2 readers cannot parse v3 tiles, and vice versa — they live
    under different URL prefixes (/v2/osm/ vs /v3/osm/)."""
    from bake.schema_osm import OSMTile, TileCoord
    with pytest.raises(ValidationError):
        OSMTile(
            schema_version=2, state="de_he",
            tile=TileCoord(z=15, x=0, y=0),
            generated_at="2026-05-07T00:00:00Z",
            source_dataset_version="geofabrik-2026-05",
            buildings=[], roads=[], waterways=[], water_polygons=[],
            railways=[], traffic_signals=[], trees=[], forests=[],
            bridges=[], landuse=[], barriers=[],
        )


def test_osm_tile_rejects_v1_schema_version():
    """v1 tiles are incompatible with v3 schema."""
    from bake.schema_osm import OSMTile, TileCoord
    with pytest.raises(ValidationError):
        OSMTile(
            schema_version=1, state="de_he",
            tile=TileCoord(z=15, x=0, y=0),
            generated_at="2026-05-07T00:00:00Z",
            source_dataset_version="geofabrik-2026-05",
            buildings=[], roads=[], waterways=[], water_polygons=[],
            railways=[], traffic_signals=[], trees=[], forests=[],
            bridges=[], landuse=[], barriers=[],
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


def test_road_optional_width_tunnel_maxspeed():
    """Road accepts the v3 optional fields and they round-trip correctly."""
    from bake.schema_osm import Road, Coord
    r = Road(
        id=99,
        coordinates=[Coord(lat=50.0, lon=8.0), Coord(lat=50.001, lon=8.001)],
        highway="primary", road_class="main_road",
        surface="asphalt", surface_class="paved",
        name="Hauptstraße", lanes=2,
        is_bridge=False, layer=0, cycleway=None,
        sidewalk_left=True, sidewalk_right=True,
        width_m=7.5, is_tunnel=True, maxspeed=50,
    )
    assert r.width_m == 7.5
    assert r.is_tunnel is True
    assert r.maxspeed == 50


def test_road_optional_fields_default_to_none_false():
    """New v3 Road fields default cleanly (no required-field errors)."""
    from bake.schema_osm import Road, Coord
    r = Road(
        id=1,
        coordinates=[Coord(lat=0, lon=0), Coord(lat=0, lon=1)],
        highway="residential", road_class="local_road",
        surface=None, surface_class="unknown",
        name=None, lanes=None, is_bridge=False, layer=0, cycleway=None,
        sidewalk_left=False, sidewalk_right=False,
    )
    assert r.width_m is None
    assert r.is_tunnel is False
    assert r.maxspeed is None


def test_building_optional_colour_material():
    """Building accepts the v3 optional colour and material fields."""
    from bake.schema_osm import Building, Coord
    b = Building(
        id=42,
        coordinates=[Coord(lat=0, lon=0), Coord(lat=0, lon=0.001), Coord(lat=0.001, lon=0)],
        building_class="residential",
        colour="white",
        roof_colour="#cc3300",
        material="brick",
        roof_material="tile",
    )
    assert b.colour == "white"
    assert b.roof_colour == "#cc3300"
    assert b.material == "brick"
    assert b.roof_material == "tile"


def test_building_optional_colour_material_defaults_to_none():
    """Existing Building fixtures still work — new fields default to None."""
    from bake.schema_osm import Building, Coord
    b = Building(
        id=1,
        coordinates=[Coord(lat=0, lon=0), Coord(lat=0, lon=0.001), Coord(lat=0.001, lon=0)],
        building_class="unknown",
    )
    assert b.colour is None
    assert b.material is None


def test_barrier_validates():
    """Barrier model accepts kind and optional height_m."""
    from bake.schema_osm import Barrier, Coord
    b = Barrier(
        id=1001,
        coordinates=[Coord(lat=50.0, lon=8.0), Coord(lat=50.001, lon=8.0)],
        kind="hedge",
        height_m=1.5,
        name=None,
    )
    assert b.kind == "hedge"
    assert b.height_m == 1.5


def test_barrier_requires_two_coords():
    """Barrier inherits the min_length=2 constraint from Field."""
    from bake.schema_osm import Barrier, Coord
    with pytest.raises(ValidationError):
        Barrier(
            id=1, coordinates=[Coord(lat=0, lon=0)],  # only 1 coord — invalid
            kind="fence",
        )
