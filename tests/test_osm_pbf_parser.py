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
