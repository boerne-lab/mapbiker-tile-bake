"""Convert source-side ParsedBuilding to wire-format Building. v2 path:
calls classify.classify_inspire / classify_citygml to assign
building_class, then packs measuredHeight/storeys/year/raw into
BuildingAttributes."""
from __future__ import annotations
from typing import Optional, Literal

from bake.sources._bucore3d import ParsedBuilding
from bake.schema import Building, Polygon, Vertex, BuildingAttributes
from bake.normalize.classify import classify_inspire, classify_citygml

# Re-export classify functions
__all__ = [
    "to_schema_building", "classify_inspire", "classify_citygml",
    "canonical_roof_type",
]


# ALKIS Bauwerksart "Dachform" codes (Objektartenkatalog 6.0, OK_Bayern
# 2.0.2 §15.5). Maps the 4-digit codes Bayern + NRW CityGML emit to the
# canonical iOS-side enum.
_ALKIS_ROOF_CODES: dict[str, str] = {
    "1000": "flat",        # Flachdach
    "2100": "monopitch",   # Pultdach
    "2200": "monopitch",   # Versetztes Pultdach (counted as monopitch)
    "3100": "gable",       # Satteldach
    "3200": "hip",         # Walmdach
    "3300": "halfHip",     # Krüppelwalmdach
    "3400": "pyramid",     # Zeltdach
    "3500": "mansard",     # Mansardendach
    "3600": "sawtooth",    # Sheddach
    "3700": "mansardHip",  # Mansard-Walmdach
    "3800": "dome",        # Bogendach / Tonnendach
    "3900": "steeple",     # Turmdach
    "4000": "arched",      # Bogen / Gewölbe
    "9999": "other",       # Sonstiges
}

# INSPIRE bu-base 4.0 `RoofTypeValue` codelist leaves → canonical.
# Spellings come from the official codelist registry; "hipAndGable"
# is the INSPIRE term for what ALKIS calls "Krüppelwalm".
_INSPIRE_ROOF_LEAVES: dict[str, str] = {
    "flat":               "flat",
    "monopitch":          "monopitch",
    "gable":              "gable",
    "hip":                "hip",
    "hipAndGable":        "halfHip",
    "mansard":            "mansard",
    "pyramid":            "pyramid",
    "dome":               "dome",
    "conic":              "steeple",
    "sawTooth":           "sawtooth",
    "otherSpecified":     "other",
    "otherUnspecified":   "other",
}


def canonical_roof_type(raw: Optional[str]) -> Optional[str]:
    """Map an ALKIS numeric code OR an INSPIRE codelist leaf to the
    canonical iOS-side roof string. Returns None for empty input or
    unknown codes — the iOS shader treats nil as "infer from geometry".
    """
    if not raw:
        return None
    if raw in _ALKIS_ROOF_CODES:
        return _ALKIS_ROOF_CODES[raw]
    if raw in _INSPIRE_ROOF_LEAVES:
        return _INSPIRE_ROOF_LEAVES[raw]
    return None


def to_schema_building(
    parsed: ParsedBuilding,
    source: Literal["inspire", "citygml"] = "inspire",
) -> Optional[Building]:
    """Convert source-side ParsedBuilding to wire-format Building (v2).
    Returns None if input has no polygons."""
    if not parsed.polygons:
        return None
    cls = (classify_inspire(parsed.raw_attrs)
           if source == "inspire"
           else classify_citygml(parsed.raw_attrs))
    return Building(
        source_id=parsed.source_id,
        polygons=[
            Polygon(vertices=[
                Vertex(lat=lat, lon=lon, alt=alt)
                for (lat, lon, alt) in poly
            ])
            for poly in parsed.polygons
        ],
        attributes=BuildingAttributes(
            building_class=cls,
            measured_height_m=parsed.height_m,
            storeys_above_ground=parsed.storeys,
            year_of_construction=parsed.year_built,
            roof_type=canonical_roof_type(parsed.raw_attrs.get("roofType")),
            raw=parsed.raw_attrs,
        ),
    )
