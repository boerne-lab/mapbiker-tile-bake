"""Layer-presence + class-diversity sanity checks for OSM v1 baked tiles.
Run AFTER an OSM-bake of HE/BY/NRW (Tasks 1.20-1.22). Skip when not yet baked."""
from pathlib import Path
import json
import pytest


def _load_osm_tile(state: str, x: int, y: int) -> dict:
    candidates = [
        Path(f"data/tiled_osm/{state}/z15/{x}/{y}.json"),
        Path(f"data/tiled_osm/v1/osm/{state}/z15/{x}/{y}.json"),
    ]
    for path in candidates:
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
    pytest.skip(f"OSM tile not yet baked at any of: {candidates}")


FRANKFURT_TILE = ("de_he", 17171, 11045)
HESSEN_RURAL_TILE = ("de_he", 17150, 11030)


def test_urban_tile_has_all_expected_layers():
    tile = _load_osm_tile(*FRANKFURT_TILE)
    assert tile["schema_version"] == 1
    assert len(tile["buildings"]) > 0, "no buildings in urban tile"
    assert len(tile["roads"]) > 0, "no roads in urban tile"
    assert len(tile["landuse"]) > 0, "no landuse polygons in urban tile"


def test_urban_tile_has_class_diversity():
    tile = _load_osm_tile(*FRANKFURT_TILE)
    road_classes = {r["road_class"] for r in tile["roads"]}
    assert len(road_classes) >= 2, \
        f"expected ≥2 road classes in urban tile, got {road_classes}"

    building_classes = {b["building_class"] for b in tile["buildings"]}
    assert (building_classes & {"residential", "commercial"}), \
        f"expected residential or commercial buildings, got {building_classes}"


def test_rural_tile_has_agricultural_landuse():
    tile = _load_osm_tile(*HESSEN_RURAL_TILE)
    landuse_classes = {l["landuse_class"] for l in tile["landuse"]}
    assert landuse_classes & {"farmland", "meadow", "forest"}, \
        f"expected agricultural landuse, got {landuse_classes}"
