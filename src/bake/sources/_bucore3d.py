"""INSPIRE bu-core3d 4.0 GML stream parser.

Yields one ParsedBuilding per <bu-core3d:Building> element in a WFS
GetFeature response. Reads the <gml:posList> bodies under the
<bu-core3d:geometryMultiSurface><gml:MultiSurface> tree as flat float
arrays in (lat, lon, alt) triples — bu-core3d 4.0 uses EPSG:7423,
which is lat-first.

Used by Hessen (Task 8) and probably NRW (Task 20+) once the live
endpoint serves bu-core3d 4.0.

Stream-parses with lxml.iterparse so a multi-megabyte response stays
within bounded memory. Each Building's sub-tree is freed after we yield
the ParsedBuilding for it.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import IO, Iterator

from lxml import etree

# Namespaces used by INSPIRE bu-core3d 4.0 WFS GetFeature responses.
# Note `gml` is /3.2 — the CityGML 2.0 fixtures elsewhere in the repo
# use plain http://www.opengis.net/gml without a version suffix.
NS = {
    "gml": "http://www.opengis.net/gml/3.2",
    "bu-core3d": "http://inspire.ec.europa.eu/schemas/bu-core3d/4.0",
}

# One closed ring as (lat, lon, alt) triples (first == last).
Polygon = list[tuple[float, float, float]]


@dataclass
class ParsedBuilding:
    """Source-side intermediate. Converted to the wire-format `Building`
    by `bake.normalize.to_schema_building` (Task 9)."""
    source_id: str
    polygons: list[Polygon]


def _parse_pos_list(text: str) -> Polygon:
    """Parse a <gml:posList> body into [(lat, lon, alt), ...].

    Raises ValueError if the count of whitespace-separated floats is
    not a multiple of 3.
    """
    parts = text.split()
    if len(parts) % 3 != 0:
        raise ValueError(
            f"posList length {len(parts)} not divisible by 3 — "
            f"expected (lat, lon, alt) triples"
        )
    out: Polygon = []
    for i in range(0, len(parts), 3):
        out.append((
            float(parts[i]),       # lat
            float(parts[i + 1]),   # lon
            float(parts[i + 2]),   # alt
        ))
    return out


def parse_bucore3d_gml(stream: IO[bytes]) -> Iterator[ParsedBuilding]:
    """Stream-parse a bu-core3d WFS response. Yields one ParsedBuilding
    at a time, freeing the parsed sub-tree as each <Building> closes.
    Suitable for state-wide WFS responses (tens of MB)."""
    tag_building = f"{{{NS['bu-core3d']}}}Building"
    tag_linear_ring = f"{{{NS['gml']}}}LinearRing"
    tag_pos_list = f"{{{NS['gml']}}}posList"

    context = etree.iterparse(stream, events=("end",), tag=tag_building)
    for _, elem in context:
        gml_id = elem.get(f"{{{NS['gml']}}}id") or ""

        polygons: list[Polygon] = []
        # Only collect posList inside LinearRing — the fixture also has
        # gml:LineString elements (terrain/facade curves) whose posList
        # entries are not closed polygon rings and must be skipped.
        for ring in elem.iter(tag_linear_ring):
            pos = ring.find(tag_pos_list)
            if pos is not None and pos.text:
                polygons.append(_parse_pos_list(pos.text))

        if polygons:
            yield ParsedBuilding(source_id=gml_id, polygons=polygons)

        # Free the parsed Building sub-tree.
        elem.clear()
        # Drop preceding siblings to keep memory flat across the stream.
        while elem.getprevious() is not None:
            del elem.getparent()[0]
