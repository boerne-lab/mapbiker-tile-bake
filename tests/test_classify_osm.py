import pytest
from bake.normalize.classify_osm import (
    classify_building, classify_landuse, classify_road,
    classify_surface, classify_railway, classify_tree_species,
)


@pytest.mark.parametrize("building_type,expected", [
    ("residential", "residential"),
    ("apartments", "residential"),
    ("cathedral", "religious"),
    ("church", "religious"),
    ("commercial", "commercial"),
    ("office", "commercial"),
    ("industrial", "industrial"),
    ("school", "civic"),
    ("hospital", "civic"),
    ("barn", "agricultural"),
    ("castle", "historic"),
    ("yes", "unknown"),
    ("nonsense", "unknown"),
    (None, "unknown"),
])
def test_classify_building(building_type, expected):
    assert classify_building(building_type) == expected


@pytest.mark.parametrize("landuse,natural,expected", [
    ("farmland", None, "farmland"),
    ("meadow", None, "meadow"),
    ("forest", None, "forest"),
    (None, "wood", "forest"),
    ("vineyard", None, "vineyard"),
    ("residential", None, "residential"),
    ("retail", None, "commercial"),
    (None, "water", "water"),
    (None, "scrub", "meadow"),
    ("playground", None, "unknown"),
    (None, None, "unknown"),
])
def test_classify_landuse(landuse, natural, expected):
    assert classify_landuse(landuse=landuse, natural=natural) == expected


@pytest.mark.parametrize("highway,expected", [
    ("motorway", "highway"),
    ("trunk", "highway"),
    ("motorway_link", "highway"),
    ("primary", "main_road"),
    ("secondary", "main_road"),
    ("tertiary", "main_road"),
    ("residential", "local_road"),
    ("unclassified", "local_road"),
    ("service", "service_road"),
    ("cycleway", "cycleway"),
    ("path", "footway"),
    ("footway", "footway"),
    ("track", "track"),
    ("nonsense", "unknown"),
])
def test_classify_road(highway, expected):
    assert classify_road(highway) == expected


@pytest.mark.parametrize("surface,expected", [
    ("asphalt", "paved"),
    ("concrete", "paved"),
    ("paving_stones", "paved"),
    ("cobblestone", "cobble"),
    ("sett", "cobble"),
    ("gravel", "gravel"),
    ("dirt", "gravel"),
    ("grass", "gravel"),
    (None, "unknown"),
    ("nonsense", "unknown"),
])
def test_classify_surface(surface, expected):
    assert classify_surface(surface) == expected


@pytest.mark.parametrize("kind,expected", [
    ("rail", "mainline"),
    ("tram", "tram"),
    ("light_rail", "light_rail"),
    ("subway", "light_rail"),
    ("narrow_gauge", "narrow_gauge"),
    ("monorail", "light_rail"),
    ("industrial", "industrial"),
    ("nonsense", "unknown"),
])
def test_classify_railway(kind, expected):
    assert classify_railway(kind) == expected


@pytest.mark.parametrize("leaf_type,genus,expected", [
    ("needleleaved", None, "needleleaved"),
    ("broadleaved", None, "broadleaved"),
    ("mixed", None, "mixed"),
    (None, None, "unknown"),
    (None, "Prunus", "ornamental"),
    (None, "prunus", "ornamental"),
    ("broadleaved", "Magnolia", "ornamental"),
    (None, "Quercus", "unknown"),
])
def test_classify_tree_species(leaf_type, genus, expected):
    assert classify_tree_species(leaf_type=leaf_type, genus=genus) == expected
