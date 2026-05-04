"""Convert source-side `ParsedBuilding` (lat/lon/alt triples) to the
wire-format `Building` (pydantic model with structured polygons).

Drops buildings with no polygons. The transformation is a pure
passthrough for sources that already deliver WGS84 (INSPIRE bu-core3d
4.0). Bayern's UTM-projected coordinates are transformed at parse-time
inside `bake.sources.bayern`, not here — keeping the normalize layer
trivial means it has no source-specific branches.
"""
from __future__ import annotations

from typing import Optional

from bake.sources._bucore3d import ParsedBuilding
from bake.schema import Building, Polygon, Vertex


def to_schema_building(parsed: ParsedBuilding) -> Optional[Building]:
    """Return a wire-format Building, or None if the parsed building
    has no polygons (defensive — upstream parsers already drop empties,
    but normalize is a good belt-and-braces gate before tile binning)."""
    if not parsed.polygons:
        return None
    return Building(
        source_id=parsed.source_id,
        polygons=[
            Polygon(vertices=[
                Vertex(lat=lat, lon=lon, alt=alt)
                for (lat, lon, alt) in poly
            ])
            for poly in parsed.polygons
        ],
    )
