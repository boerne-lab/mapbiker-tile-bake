"""INSPIRE bu-core3d 4.0 GML stream parser.

Yields one ParsedBuilding per <bu-core3d:Building> element. v2-extends:
also extracts buildingNature, currentUse, heightAboveGround into
raw_attrs + height_m, for downstream classify_inspire."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import IO, Iterator, Optional

from lxml import etree

NS = {
    "gml": "http://www.opengis.net/gml/3.2",
    "bu-core3d": "http://inspire.ec.europa.eu/schemas/bu-core3d/4.0",
    "bu-base": "http://inspire.ec.europa.eu/schemas/bu-base/4.0",
    "xlink": "http://www.w3.org/1999/xlink",
}

Polygon = list[tuple[float, float, float]]


@dataclass
class ParsedBuilding:
    """Source-side intermediate. Converted to the wire-format `Building`
    by `bake.normalize.to_schema_building` (Task 9)."""
    source_id: str
    polygons: list[Polygon]
    raw_attrs: dict[str, str] = field(default_factory=dict)
    height_m: Optional[float] = None
    storeys: Optional[int] = None       # not in INSPIRE; CityGML-pendant
    year_built: Optional[int] = None    # not in INSPIRE


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


def _extract_codelist_leaf(href: Optional[str]) -> Optional[str]:
    """Extract leaf from xlink:href like '.../CurrentUseValue/residential' → 'residential'."""
    if not href:
        return None
    return href.rstrip("/").rsplit("/", 1)[-1] or None


def _extract_attrs(elem) -> tuple[dict[str, str], Optional[float]]:
    """Walk the Building's bu-base subtree, extract currentUse,
    buildingNature, heightAboveGround.value."""
    raw: dict[str, str] = {}
    height: Optional[float] = None
    href_attr = f"{{{NS['xlink']}}}href"

    # currentUse: search for nested <bu-base:currentUse> with xlink:href.
    # Note INSPIRE uses both <bu-base:currentUse> as parent wrapper AND
    # as the inner element with xlink:href. We want the inner one's href.
    for cu in elem.iter(f"{{{NS['bu-base']}}}currentUse"):
        href = cu.get(href_attr)
        leaf = _extract_codelist_leaf(href)
        if leaf:
            raw["currentUse"] = leaf
            break

    # buildingNature
    for bn in elem.iter(f"{{{NS['bu-base']}}}buildingNature"):
        href = bn.get(href_attr)
        leaf = _extract_codelist_leaf(href)
        if leaf:
            raw["buildingNature"] = leaf
            break

    # heightAboveGround.value
    for v in elem.iter(f"{{{NS['bu-base']}}}value"):
        parent = v.getparent()
        gp = parent.getparent() if parent is not None else None
        if gp is not None and gp.tag == f"{{{NS['bu-base']}}}heightAboveGround":
            try:
                height = float(v.text or "0")
            except (TypeError, ValueError):
                pass
            break

    return raw, height


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

        raw_attrs, height = _extract_attrs(elem)

        if polygons:
            yield ParsedBuilding(
                source_id=gml_id,
                polygons=polygons,
                raw_attrs=raw_attrs,
                height_m=height,
                storeys=None,
                year_built=None,
            )

        # Free the parsed Building sub-tree.
        elem.clear()
        # Drop preceding siblings to keep memory flat across the stream.
        while elem.getprevious() is not None:
            del elem.getparent()[0]
