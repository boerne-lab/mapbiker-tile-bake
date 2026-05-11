"""CityGML GML stream parser — handles BOTH 1.0 and 2.0.

Used by:
- Bayern Bayernwolke (per-2km UTM32N CityGML 1.0 files — verified
  2026-05-05 by sampling the 690_5334.gml München tile, which
  declares `xmlns="http://www.opengis.net/citygml/1.0"` and
  `xmlns:bldg="http://www.opengis.net/citygml/building/1.0"`)
- NRW bulk download (per-1km UTM32N CityGML files — version TBD,
  parser handles both)
- Synthetic test fixtures `by-sample.gml` / `nrw-sample.gml`
  (CityGML 2.0)

Both versions publish in EPSG:25832 (ETRS89 / UTM Zone 32N) with
`bldg:Building` features. The geometry wrappers (`lod2Solid` vs
`boundedBy/GroundSurface`) and the namespace URI are the only
differences this parser cares about — coordinate format and
LinearRing/posList nesting are identical.

The first Bayern bake on 2026-05-05 silently produced 0 buildings
because the parser was hard-coded to CityGML 2.0 namespace
(`citygml/building/2.0`) while the real Bayernwolke data uses 1.0.
This module now matches Building elements in either namespace.

Stream-parses with lxml.iterparse so a 156 MB München tile stays
within bounded memory. Each Building's sub-tree is freed after we
yield the ParsedBuilding for it.
"""
from __future__ import annotations

from typing import IO, Iterator

from lxml import etree
from pyproj import Transformer

from bake.sources._bucore3d import ParsedBuilding, Polygon

# CityGML 1.0 namespaces (used by Bayernwolke and likely NRW bulk).
# `gml` URI has no version suffix in CityGML 1.0, 2.0, AND 3.0; only
# bu-core3d 4.0 differs (uses /3.2). So gml is shared across both
# CityGML versions our parser handles.
NS_CITYGML_1 = {
    "gml": "http://www.opengis.net/gml",
    "bldg": "http://www.opengis.net/citygml/building/1.0",
    "core": "http://www.opengis.net/citygml/1.0",
}

# CityGML 2.0 namespaces (used by the synthetic test fixtures and
# possibly by other states' future bulk downloads).
NS_CITYGML_2 = {
    "gml": "http://www.opengis.net/gml",
    "bldg": "http://www.opengis.net/citygml/building/2.0",
    "core": "http://www.opengis.net/citygml/2.0",
}

# Union of Building tags from both versions, fed to lxml.iterparse so
# files of either version produce hits.
_BUILDING_TAGS = (
    f"{{{NS_CITYGML_1['bldg']}}}Building",
    f"{{{NS_CITYGML_2['bldg']}}}Building",
)
# `gml` namespace is identical across CityGML versions — single value
# for LinearRing/posList traversal.
_TAG_LINEAR_RING = f"{{{NS_CITYGML_1['gml']}}}LinearRing"
_TAG_POS_LIST = f"{{{NS_CITYGML_1['gml']}}}posList"
_GML_ID_ATTR = f"{{{NS_CITYGML_1['gml']}}}id"

# UTM Zone 32N → WGS84. Cached at module load — pyproj transformers
# are expensive to construct (each load_to_crs call rebuilds an
# internal proj string).
_TRANSFORMER = Transformer.from_crs(
    "EPSG:25832", "EPSG:4326", always_xy=True,
)


def _extract_first_text(elem, tags: list[str]):
    """Find first descendant matching any of the given (namespace-qualified) tags;
    return text content or None."""
    for tag in tags:
        for child in elem.iter(tag):
            if child.text:
                return child.text.strip()
    return None


def _parse_pos_list_utm(text: str) -> Polygon:
    """Parse a CityGML <gml:posList> body. Coordinates are UTM32N
    (easting, northing, altitude) triples — transform to WGS84
    (lat, lon, alt) triples for the wire-format output.

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
    """Stream-parse a CityGML file (version 1.0 OR 2.0). Yields one
    ParsedBuilding per `bldg:Building` element with WGS84-transformed
    polygons. Frees parsed sub-trees as each Building closes.

    Function name kept as `parse_citygml2_gml` for backward
    compatibility with existing imports — the "2" historically meant
    "CityGML 2.0", but the parser now handles both 1.0 and 2.0.
    """
    # iterparse(tag=...) accepts a single tag or a tuple/list of tags.
    # By passing both Building tags, files of either CityGML version
    # produce hits without needing to inspect the document namespace
    # first.
    context = etree.iterparse(stream, events=("end",), tag=_BUILDING_TAGS)
    for _, elem in context:
        gml_id = elem.get(_GML_ID_ATTR) or ""

        polygons: list[Polygon] = []
        # Walk every LinearRing inside this Building, regardless of
        # whether it's nested under lod2Solid, boundedBy/WallSurface,
        # boundedBy/GroundSurface, or boundedBy/RoofSurface. The
        # `gml` namespace is the same in CityGML 1.0 and 2.0, so a
        # single LinearRing tag matches both versions.
        for ring in elem.iter(_TAG_LINEAR_RING):
            pos = ring.find(_TAG_POS_LIST)
            if pos is not None and pos.text:
                try:
                    polygons.append(_parse_pos_list_utm(pos.text))
                except ValueError:
                    # Skip malformed posList. Real CityGML files
                    # occasionally have these — keep the bake going
                    # rather than failing on one bad geometry.
                    continue

        tag_function = [f"{{{NS_CITYGML_1['bldg']}}}function",
                        f"{{{NS_CITYGML_2['bldg']}}}function"]
        tag_storeys  = [f"{{{NS_CITYGML_1['bldg']}}}storeysAboveGround",
                        f"{{{NS_CITYGML_2['bldg']}}}storeysAboveGround"]
        tag_height   = [f"{{{NS_CITYGML_1['bldg']}}}measuredHeight",
                        f"{{{NS_CITYGML_2['bldg']}}}measuredHeight"]
        tag_year     = [f"{{{NS_CITYGML_1['bldg']}}}yearOfConstruction",
                        f"{{{NS_CITYGML_2['bldg']}}}yearOfConstruction"]
        tag_roof     = [f"{{{NS_CITYGML_1['bldg']}}}roofType",
                        f"{{{NS_CITYGML_2['bldg']}}}roofType"]

        raw_attrs: dict[str, str] = {}
        if function := _extract_first_text(elem, tag_function):
            raw_attrs["function"] = function
        # roofType: numeric ALKIS code (1000=flat, 3100=gable, etc.).
        # Normalised to a canonical RoofType string by `bake.normalize`.
        if roof_raw := _extract_first_text(elem, tag_roof):
            raw_attrs["roofType"] = roof_raw

        storeys = None
        if storeys_str := _extract_first_text(elem, tag_storeys):
            try: storeys = int(storeys_str)
            except ValueError: pass

        height_m = None
        if height_str := _extract_first_text(elem, tag_height):
            try: height_m = float(height_str)
            except ValueError: pass

        year_built = None
        if year_str := _extract_first_text(elem, tag_year):
            try: year_built = int(year_str)
            except ValueError: pass

        if polygons:
            yield ParsedBuilding(
                source_id=gml_id,
                polygons=polygons,
                raw_attrs=raw_attrs,
                height_m=height_m,
                storeys=storeys,
                year_built=year_built,
            )

        # Free the parsed Building sub-tree.
        elem.clear()
        # Drop preceding siblings to keep memory flat across the stream.
        while elem.getprevious() is not None:
            del elem.getparent()[0]
