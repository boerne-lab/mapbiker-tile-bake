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
__all__ = ["to_schema_building", "classify_inspire", "classify_citygml"]


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
            raw=parsed.raw_attrs,
        ),
    )
