"""Fallback-Verhalten: missing/unmapped tags must yield 'unknown', never crash."""
import pytest


def test_building_no_specific_type_classifies_unknown():
    """OSM `building=yes` → unknown class, not residential."""
    from bake.normalize.classify_osm import classify_building
    assert classify_building("yes") == "unknown"


def test_road_no_surface_yields_unknown_surface_class():
    """`paved` is NOT default — fehlende Info ist `unknown`."""
    from bake.normalize.classify_osm import classify_surface
    assert classify_surface(None) == "unknown"
    assert classify_surface(None) != "paved"


def test_landuse_unknown_kind_falls_back():
    """`landuse=playground` ist nicht in unserer Tabelle → unknown."""
    from bake.normalize.classify_osm import classify_landuse
    assert classify_landuse(landuse="playground") == "unknown"


def test_tree_no_leaf_type_yields_unknown():
    from bake.normalize.classify_osm import classify_tree_species
    assert classify_tree_species() == "unknown"


def test_unmapped_railway_kind_yields_unknown():
    from bake.normalize.classify_osm import classify_railway
    assert classify_railway("nonsense") == "unknown"


def test_classify_building_none_input_handled():
    from bake.normalize.classify_osm import classify_building
    assert classify_building(None) == "unknown"


def test_landuse_only_natural_tag_works():
    """natural=scrub maps to meadow, even without landuse= tag."""
    from bake.normalize.classify_osm import classify_landuse
    assert classify_landuse(natural="scrub") == "meadow"
