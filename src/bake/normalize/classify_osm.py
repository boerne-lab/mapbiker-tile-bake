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


def classify_water_subkind(*, water_tag: Optional[str] = None) -> Optional[str]:
    """OSM water=* subtype → canonical kind. Returns None for unmapped values."""
    if not water_tag:
        return None
    return _load_tables()["OSM_WATER_SUBKIND_TO_CLASS"].get(water_tag)


def classify_barrier_kind(*, barrier_tag: Optional[str]) -> Optional[str]:
    """OSM barrier=* → canonical kind. Returns None for unmapped or `ignore`-classified values."""
    if not barrier_tag:
        return None
    result = _load_tables()["OSM_BARRIER_TO_CLASS"].get(barrier_tag)
    if result == "ignore":
        return None
    return result


def classify_building_material(*, material_tag: Optional[str] = None) -> Optional[str]:
    if not material_tag:
        return None
    return _load_tables()["OSM_BUILDING_MATERIAL_TO_CLASS"].get(material_tag)


def classify_roof_material(*, material_tag: Optional[str] = None) -> Optional[str]:
    if not material_tag:
        return None
    return _load_tables()["OSM_ROOF_MATERIAL_TO_CLASS"].get(material_tag)


def classify_sidewalks(*, tags: dict, highway: str) -> tuple[bool, bool]:
    """Return `(sidewalk_left, sidewalk_right)` for a highway way.

    Resolution order:
      1. Per-side tags `sidewalk:left=yes` / `sidewalk:right=yes`
         override individual flags (highest priority).
      2. Explicit `sidewalk=both|left|right|no|none|separate`.
      3. Fallback: `OSM_SIDEWALK_DEFAULT_BY_HIGHWAY[highway]`.
      4. Highway not in default table → `(False, False)`.

    `separate` returns `(False, False)` because the sidewalk exists as
    its own `highway=footway` way and is rendered there — emitting an
    attached strip too would double-render.
    """
    tables = _load_tables()

    # Base from explicit sidewalk=* or highway default
    if tags.get("sidewalk") in tables["OSM_SIDEWALK_TAG"]:
        base = tables["OSM_SIDEWALK_TAG"][tags["sidewalk"]]
    else:
        base = tables["OSM_SIDEWALK_DEFAULT_BY_HIGHWAY"].get(
            highway, {"left": False, "right": False})
    left = base["left"]
    right = base["right"]

    # Per-side override (highest priority — wins over sidewalk=no etc.)
    if tags.get("sidewalk:left") == "yes":
        left = True
    if tags.get("sidewalk:right") == "yes":
        right = True
    if tags.get("sidewalk:left") in ("no", "none"):
        left = False
    if tags.get("sidewalk:right") in ("no", "none"):
        right = False

    return (left, right)
