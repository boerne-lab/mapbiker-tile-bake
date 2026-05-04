"""CityGML 2.0 GML stream parser.

Used by:
- Bayern Bayernwolke (per-2km UTM32N CityGML files)
- NRW bulk download (per-1km UTM32N CityGML files)

Both publish the same CityGML 2.0 schema with `bldg:Building` features
in EPSG:25832 (ETRS89 / UTM Zone 32N). One parser, two states.

Differs from bu-core3d 4.0 (`_bucore3d.py`) in:
- gml namespace URI (no /3.2 suffix)
- Building element is `bldg:Building` not `bu-core3d:Building`
- Coordinates are UTM32N (easting,northing,alt) — transformed to
  WGS84 lat/lon/alt here at parse time
- Geometry wrappers vary: `bldg:lod2Solid` (synthetic test fixtures)
  OR `bldg:boundedBy → bldg:GroundSurface/RoofSurface/WallSurface`
  (real Bayern data). The parser walks ALL LinearRings within each
  Building so the wrapper choice is invisible.

Stream-parses with lxml.iterparse so a 156 MB München tile stays
within bounded memory. Each Building's sub-tree is freed after we
yield the ParsedBuilding for it.
"""
from __future__ import annotations

from typing import IO, Iterator

from lxml import etree
from pyproj import Transformer

from bake.sources._bucore3d import ParsedBuilding, Polygon

# CityGML 2.0 namespaces. Note `gml` URI has NO version suffix —
# bu-core3d 4.0 uses /3.2; CityGML 2.0 does not.
NS = {
    "gml": "http://www.opengis.net/gml",
    "bldg": "http://www.opengis.net/citygml/building/2.0",
    "core": "http://www.opengis.net/citygml/2.0",
}

# UTM Zone 32N → WGS84. Cached at module load — pyproj transformers
# are expensive to construct (each load_to_crs call rebuilds an
# internal proj string).
_TRANSFORMER = Transformer.from_crs(
    "EPSG:25832", "EPSG:4326", always_xy=True,
)


def _parse_pos_list_utm(text: str) -> Polygon:
    """Parse a CityGML 2.0 <gml:posList> body. Coordinates are
    UTM32N (easting, northing, altitude) triples — transform to
    WGS84 (lat, lon, alt) triples for the wire-format output.

    Raises ValueError if the count of whitespace-separated floats is
    not a multiple of 3.
    """
    parts = text.split()
    if len(parts) % 3 != 0:
        raise ValueError(
            f"posList length {len(parts)} not divisible by 3 — "
            f"expected (easting, northing, alt) triples"
        )
    out: Polygon = []
    for i in range(0, len(parts), 3):
        easting = float(parts[i])
        northing = float(parts[i + 1])
        alt = float(parts[i + 2])
        # always_xy=True → transform returns (lon, lat) in that order
        lon, lat = _TRANSFORMER.transform(easting, northing)
        out.append((lat, lon, alt))
    return out


def parse_citygml2_gml(stream: IO[bytes]) -> Iterator[ParsedBuilding]:
    """Stream-parse a CityGML 2.0 file. Yields one ParsedBuilding per
    `bldg:Building` element with WGS84-transformed polygons. Frees
    parsed sub-trees as each Building closes."""
    tag_building = f"{{{NS['bldg']}}}Building"
    tag_linear_ring = f"{{{NS['gml']}}}LinearRing"
    tag_pos_list = f"{{{NS['gml']}}}posList"

    context = etree.iterparse(stream, events=("end",), tag=tag_building)
    for _, elem in context:
        gml_id = elem.get(f"{{{NS['gml']}}}id") or ""

        polygons: list[Polygon] = []
        # Walk every LinearRing inside this Building, regardless of
        # whether it's nested under lod2Solid (synthetic fixture) or
        # boundedBy/GroundSurface (real Bayern data). The two wrappers
        # both nest LinearRings the same way underneath.
        for ring in elem.iter(tag_linear_ring):
            pos = ring.find(tag_pos_list)
            if pos is not None and pos.text:
                try:
                    polygons.append(_parse_pos_list_utm(pos.text))
                except ValueError:
                    # Skip malformed posList. Real CityGML files
                    # occasionally have these — keep the bake going
                    # rather than failing on one bad geometry.
                    continue

        if polygons:
            yield ParsedBuilding(source_id=gml_id, polygons=polygons)

        # Free the parsed Building sub-tree.
        elem.clear()
        # Drop preceding siblings to keep memory flat across the stream.
        while elem.getprevious() is not None:
            del elem.getparent()[0]
