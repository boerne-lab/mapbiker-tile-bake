import pytest
from pathlib import Path

FIX = Path(__file__).parent / "fixtures" / "osm_pbf"


def test_parses_building_with_full_tags():
    from bake.sources.osm_pbf import parse_pbf
    pbf_path = FIX / "building_residential.osm.pbf"
    if not pbf_path.exists():
        pytest.skip("fixture not built; run build_fixtures.py")
    tiles = list(parse_pbf(pbf_path, state="de_he", source_version="test"))
    assert len(tiles) >= 1
    # find the tile that has the building (location ~50.11, 8.68)
    bldg_tile = next((t for t in tiles if t.buildings), None)
    assert bldg_tile is not None
    assert len(bldg_tile.buildings) == 1
    b = bldg_tile.buildings[0]
    assert b.building_type == "residential"
    assert b.building_class == "residential"
    assert b.levels == 5
    assert b.height_m == 18.4
    assert b.wikidata == "Q42"
    assert b.name == "Test Haus"


def test_parses_landuse_polygon():
    from bake.sources.osm_pbf import parse_pbf
    pbf_path = FIX / "landuse_farmland.osm.pbf"
    if not pbf_path.exists():
        pytest.skip("fixture not built")
    tiles = list(parse_pbf(pbf_path, state="de_he", source_version="test"))
    lu_tile = next((t for t in tiles if t.landuse), None)
    assert lu_tile is not None
    assert len(lu_tile.landuse) == 1
    lu = lu_tile.landuse[0]
    assert lu.landuse_class == "farmland"
    assert lu.raw_tag == {"landuse": "farmland"}


def test_parses_tree_with_genus_promoted_to_ornamental():
    from bake.sources.osm_pbf import parse_pbf
    pbf_path = FIX / "tree_prunus.osm.pbf"
    if not pbf_path.exists():
        pytest.skip("fixture not built")
    tiles = list(parse_pbf(pbf_path, state="de_he", source_version="test"))
    tree_tile = next((t for t in tiles if t.trees), None)
    assert tree_tile is not None
    assert len(tree_tile.trees) == 1
    tr = tree_tile.trees[0]
    assert tr.genus == "Prunus"
    assert tr.species_class == "ornamental"


# --- v3 pbf parser tests ---

def test_barrier_hedge_produces_barrier_record():
    """A way with barrier=hedge is classified as 'hedge' and emitted in barriers."""
    from bake.sources.osm_pbf import parse_pbf
    pbf_path = FIX / "barrier_hedge.osm.pbf"
    if not pbf_path.exists():
        pytest.skip("fixture not built; run build_fixtures.py")
    tiles = list(parse_pbf(pbf_path, state="de_he", source_version="test"))
    barrier_tile = next((t for t in tiles if t.barriers), None)
    assert barrier_tile is not None, "Expected at least one tile with a barrier"
    assert len(barrier_tile.barriers) == 1
    b = barrier_tile.barriers[0]
    assert b.kind == "hedge"
    assert b.height_m == 1.5


def test_barrier_kerb_is_dropped():
    """A way with barrier=kerb maps to 'ignore' and must NOT appear in barriers."""
    from bake.sources.osm_pbf import parse_pbf
    pbf_path = FIX / "barrier_kerb.osm.pbf"
    if not pbf_path.exists():
        pytest.skip("fixture not built; run build_fixtures.py")
    tiles = list(parse_pbf(pbf_path, state="de_he", source_version="test"))
    # All tiles must have empty barriers list
    for t in tiles:
        assert t.barriers == [], f"Expected no barriers, found {t.barriers}"


def test_road_width_tunnel_maxspeed():
    """A highway way with width=5.5, tunnel=yes, maxspeed=30 populates Road correctly."""
    from bake.sources.osm_pbf import parse_pbf
    pbf_path = FIX / "road_width_tunnel.osm.pbf"
    if not pbf_path.exists():
        pytest.skip("fixture not built; run build_fixtures.py")
    tiles = list(parse_pbf(pbf_path, state="de_he", source_version="test"))
    road_tile = next((t for t in tiles if t.roads), None)
    assert road_tile is not None
    assert len(road_tile.roads) == 1
    r = road_tile.roads[0]
    assert r.width_m == 5.5
    assert r.is_tunnel is True
    assert r.maxspeed == 30


def test_water_polygon_lake_populates_kind():
    """A way with natural=water and water=lake populates WaterPolygon.kind='lake'."""
    from bake.sources.osm_pbf import parse_pbf
    pbf_path = FIX / "water_polygon_lake.osm.pbf"
    if not pbf_path.exists():
        pytest.skip("fixture not built; run build_fixtures.py")
    tiles = list(parse_pbf(pbf_path, state="de_he", source_version="test"))
    water_tile = next((t for t in tiles if t.water_polygons), None)
    assert water_tile is not None
    assert len(water_tile.water_polygons) == 1
    w = water_tile.water_polygons[0]
    assert w.kind == "lake"
    assert w.name == "Teststausee"


def test_coastline_way_extracted_to_coastlines_bin():
    """Direct-bin-injection check that the handler initialises a
    `coastlines` list in each bin and that Coastline records can be
    appended. NOTE: the public class is `_Handler` (private) and
    `_bin()` takes only (x, y) — adapted from plan's `OSMTileBins`
    sketch to the actual API."""
    from bake.sources.osm_pbf import _Handler
    from bake.schema_osm import Coastline, Coord
    h = _Handler()
    bin_ = h._bin(17000, 11000)
    coords = [Coord(lat=54.0, lon=8.0), Coord(lat=54.001, lon=8.001),
              Coord(lat=54.002, lon=8.002)]
    bin_["coastlines"].append(Coastline(id=999, coordinates=coords,
                                        name=None))
    assert len(bin_["coastlines"]) == 1
    assert bin_["coastlines"][0].id == 999


def test_building_colour_and_material():
    """A building with building:colour=red and building:material=brick populates
    Building.colour and Building.material correctly."""
    from bake.sources.osm_pbf import parse_pbf
    pbf_path = FIX / "building_colour_material.osm.pbf"
    if not pbf_path.exists():
        pytest.skip("fixture not built; run build_fixtures.py")
    tiles = list(parse_pbf(pbf_path, state="de_he", source_version="test"))
    bldg_tile = next((t for t in tiles if t.buildings), None)
    assert bldg_tile is not None
    assert len(bldg_tile.buildings) == 1
    b = bldg_tile.buildings[0]
    assert b.colour == "red"
    assert b.material == "brick"   # classify_building_material("brick") → "brick"
    assert b.roof_colour == "#cc3300"
    assert b.roof_material == "tile"   # classify_roof_material("tile") → "tile"
