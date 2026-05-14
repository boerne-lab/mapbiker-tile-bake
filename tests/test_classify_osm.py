import pytest
from bake.normalize.classify_osm import (
    classify_building, classify_landuse, classify_road,
    classify_surface, classify_railway, classify_tree_species,
    classify_sidewalks,
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


# classify_sidewalks: explicit `sidewalk=*` tag wins over highway-default;
# per-side `sidewalk:left=yes` / `sidewalk:right=yes` overrides individual flags.
@pytest.mark.parametrize("tags,highway,expected", [
    # Explicit sidewalk=* tag
    ({"sidewalk": "both"}, "residential", (True, True)),
    ({"sidewalk": "left"}, "residential", (True, False)),
    ({"sidewalk": "right"}, "residential", (False, True)),
    ({"sidewalk": "no"}, "residential", (False, False)),
    ({"sidewalk": "none"}, "residential", (False, False)),
    ({"sidewalk": "separate"}, "residential", (False, False)),
    # No sidewalk tag → fall back to highway default
    ({}, "residential", (True, True)),     # EU urban default
    ({}, "tertiary", (True, True)),
    ({}, "motorway", (False, False)),
    ({}, "footway", (False, False)),       # footway itself is the path
    ({}, "track", (False, False)),
    # Per-side override
    ({"sidewalk:left": "yes"}, "motorway", (True, False)),
    ({"sidewalk:right": "yes"}, "motorway", (False, True)),
    ({"sidewalk:left": "yes", "sidewalk:right": "yes"}, "track",
     (True, True)),
    # Per-side override combined with sidewalk=*: per-side wins
    ({"sidewalk": "no", "sidewalk:left": "yes"}, "residential",
     (True, False)),
    # Unknown highway falls back to (False, False)
    ({}, "nonsense_class", (False, False)),
])
def test_classify_sidewalks(tags, highway, expected):
    assert classify_sidewalks(tags=tags, highway=highway) == expected
