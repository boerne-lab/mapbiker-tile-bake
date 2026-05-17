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


def test_road_wikidata_optional_and_defaults_none():
    """Road gains optional `wikidata` for landmark-special bridge
    matching. Default None when not set; preserves the Q-ID string
    verbatim when set (no validation — iOS catalog is the source of
    truth for what Q-IDs map to which procedural variants).
    """
    from bake.schema_osm import Road, Coord
    r_no_qid = Road(
        id=1,
        coordinates=[Coord(lat=0, lon=0), Coord(lat=0, lon=1)],
        highway="residential",
        road_class="local_road",
        surface_class="paved",
        sidewalk_left=False, sidewalk_right=False,
    )
    assert r_no_qid.wikidata is None

    r_alte_bruecke = Road(
        id=2,
        coordinates=[Coord(lat=50.108, lon=8.681), Coord(lat=50.109, lon=8.682)],
        highway="residential",
        road_class="local_road",
        surface_class="cobble",
        is_bridge=True,
        sidewalk_left=True, sidewalk_right=True,
        wikidata="Q1378478",
    )
    assert r_alte_bruecke.wikidata == "Q1378478"


def test_bus_stop_with_shelter_flag():
    """BusStop captures `highway=bus_stop` node + the `shelter=yes`
    flag that the iOS-side mesh builder uses to decide whether to add
    the Wartehäuschen + glass roof on top of the bare H-Schild pole."""
    from bake.schema_osm import BusStop, Coord
    with_shelter = BusStop(
        id=1,
        coordinate=Coord(lat=50.110, lon=8.682),
        name="Konstablerwache",
        ref="36",
        has_shelter=True,
    )
    assert with_shelter.has_shelter is True
    assert with_shelter.ref == "36"

    bare_pole = BusStop(
        id=2,
        coordinate=Coord(lat=50.110, lon=8.681),
    )
    assert bare_pole.has_shelter is False
    assert bare_pole.name is None


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


def test_osm_tile_accepts_coastline_records():
    from bake.schema_osm import OSMTile, TileCoord, Coastline, Coord
    tile = OSMTile(
        schema_version=3,
        state="de_sh",
        tile=TileCoord(z=15, x=17000, y=11000),
        generated_at="2026-05-16T00:00:00Z",
        source_dataset_version="test",
        buildings=[], roads=[], waterways=[], water_polygons=[],
        railways=[], traffic_signals=[], trees=[], forests=[],
        bridges=[], landuse=[], barriers=[], traffic_islands=[],
        coastlines=[
            Coastline(
                id=42,
                coordinates=[
                    Coord(lat=54.0, lon=8.0),
                    Coord(lat=54.001, lon=8.001),
                ],
                name="Test Küste",
            )
        ],
    )
    assert len(tile.coastlines) == 1
    assert tile.coastlines[0].id == 42
    assert tile.coastlines[0].name == "Test Küste"


def test_osm_tile_coastlines_default_empty():
    from bake.schema_osm import OSMTile, TileCoord
    tile = OSMTile(
        schema_version=3,
        state="de_he",
        tile=TileCoord(z=15, x=17174, y=11097),
        generated_at="2026-05-16T00:00:00Z",
        source_dataset_version="test",
        buildings=[], roads=[], waterways=[], water_polygons=[],
        railways=[], traffic_signals=[], trees=[], forests=[],
        bridges=[], landuse=[], barriers=[], traffic_islands=[],
    )
    assert tile.coastlines == []


def test_osm_tile_accepts_railway_platforms_and_platform_roofs():
    """Bahnsteig + Bahnsteig-Überdachung records validate inside OSMTile."""
    from bake.schema_osm import (
        OSMTile, TileCoord, RailwayPlatform, PlatformRoof, Coord,
    )
    tile = OSMTile(
        schema_version=3,
        state="de_he",
        tile=TileCoord(z=15, x=17174, y=11097),
        generated_at="2026-05-16T00:00:00Z",
        source_dataset_version="test",
        buildings=[], roads=[], waterways=[], water_polygons=[],
        railways=[], traffic_signals=[], trees=[], forests=[],
        bridges=[], landuse=[], barriers=[], traffic_islands=[],
        coastlines=[],
        railway_platforms=[
            RailwayPlatform(
                id=101,
                coordinates=[
                    Coord(lat=50.110, lon=8.682),
                    Coord(lat=50.110, lon=8.683),
                    Coord(lat=50.1101, lon=8.683),
                    Coord(lat=50.1101, lon=8.682),
                    Coord(lat=50.110, lon=8.682),
                ],
                name="Hofheim",
                ref="Gleis 1",
            ),
        ],
        platform_roofs=[
            PlatformRoof(
                id=202,
                coordinates=[
                    Coord(lat=50.110, lon=8.682),
                    Coord(lat=50.110, lon=8.683),
                    Coord(lat=50.1101, lon=8.683),
                    Coord(lat=50.1101, lon=8.682),
                    Coord(lat=50.110, lon=8.682),
                ],
                height_m=3.5,
                roof_material="glass",
                layer=1,
            ),
        ],
    )
    assert len(tile.railway_platforms) == 1
    assert tile.railway_platforms[0].ref == "Gleis 1"
    assert len(tile.platform_roofs) == 1
    assert tile.platform_roofs[0].roof_material == "glass"
    assert tile.platform_roofs[0].layer == 1


def test_osm_tile_railway_platforms_and_roofs_default_empty():
    """Pre-Item-5 tiles validate with the new fields defaulting to []."""
    from bake.schema_osm import OSMTile, TileCoord
    tile = OSMTile(
        schema_version=3,
        state="de_he",
        tile=TileCoord(z=15, x=17174, y=11097),
        generated_at="2026-05-16T00:00:00Z",
        source_dataset_version="test",
        buildings=[], roads=[], waterways=[], water_polygons=[],
        railways=[], traffic_signals=[], trees=[], forests=[],
        bridges=[], landuse=[], barriers=[], traffic_islands=[],
    )
    assert tile.railway_platforms == []
    assert tile.platform_roofs == []


def test_platform_roof_defaults_for_optional_fields():
    """PlatformRoof with no height_m / material / layer falls back cleanly."""
    from bake.schema_osm import PlatformRoof, Coord
    p = PlatformRoof(
        id=1,
        coordinates=[
            Coord(lat=0.0, lon=0.0),
            Coord(lat=0.0, lon=0.001),
            Coord(lat=0.001, lon=0.001),
            Coord(lat=0.0, lon=0.0),
        ],
    )
    assert p.height_m is None
    assert p.roof_material is None
    assert p.layer == 0
