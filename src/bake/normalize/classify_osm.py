"""OSM tag → unified class mappings, loaded at module init from
data/classify_osm_tables.json (single source of truth, also synced to
iOS Resources)."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

# data/classify_osm_tables.json sits at the repo root, sibling to src/.
# This file lives at src/bake/normalize/classify_osm.py — go up 3 levels.
_TABLES_PATH = (
    Path(__file__).parent.parent.parent.parent / "data" / "classify_osm_tables.json"
)
_TABLES: dict = {}


def _load_tables() -> dict:
    global _TABLES
    if not _TABLES:
        _TABLES = json.loads(_TABLES_PATH.read_text(encoding="utf-8"))
    return _TABLES


def classify_building(building_type: Optional[str]) -> str:
    if not building_type:
        return "unknown"
    return _load_tables()["OSM_BUILDING_TO_CLASS"].get(building_type, "unknown")


def classify_landuse(*, landuse: Optional[str] = None,
                     natural: Optional[str] = None) -> str:
    table = _load_tables()["OSM_LANDUSE_TO_CLASS"]
    if landuse:
        result = table.get(f"landuse:{landuse}")
        if result:
            return result
    if natural:
        result = table.get(f"natural:{natural}")
        if result:
            return result
    return "unknown"


def classify_road(highway: str) -> str:
    return _load_tables()["OSM_HIGHWAY_TO_CLASS"].get(highway, "unknown")


def classify_surface(surface: Optional[str]) -> str:
    if not surface:
        return "unknown"
    return _load_tables()["OSM_SURFACE_TO_CLASS"].get(surface, "unknown")


def classify_railway(kind: str) -> str:
    return _load_tables()["OSM_RAILWAY_TO_CLASS"].get(kind, "unknown")


def classify_tree_species(*, leaf_type: Optional[str] = None,
                          genus: Optional[str] = None) -> str:
    tables = _load_tables()
    # Genus boost: ornamental wins over leaf_type
    if genus:
        ornamentals = {g.lower() for g in tables["OSM_GENUS_TO_ORNAMENTAL"]}
        if genus.lower() in ornamentals:
            return "ornamental"
    if leaf_type:
        return tables["OSM_LEAF_TYPE_TO_CLASS"].get(leaf_type, "unknown")
    return "unknown"
