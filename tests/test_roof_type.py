"""Tests for roof_type extraction + canonical normalisation across
the INSPIRE bu-core3d and CityGML 1.0/2.0 source parsers.

The canonical strings here are the iOS-side enum values
`LoD2RawBuilding.RoofType.allCases.rawValue`. Any drift between
this file and the iOS enum is a wire-format break — pinning the
strings in tests makes it loud."""
from pathlib import Path

import pytest

from bake.normalize import canonical_roof_type, to_schema_building
from bake.sources._bucore3d import ParsedBuilding
from bake.sources._citygml2 import parse_citygml2_gml


BY_FIXTURE = Path(__file__).parent / "fixtures" / "by-sample.gml"


# -----------------------------------------------------------------------------
# canonical_roof_type
# -----------------------------------------------------------------------------

@pytest.mark.parametrize("code, canonical", [
    ("1000", "flat"),
    ("2100", "monopitch"),
    ("3100", "gable"),
    ("3200", "hip"),
    ("3300", "halfHip"),
    ("3400", "pyramid"),
    ("3500", "mansard"),
    ("3600", "sawtooth"),
    ("3700", "mansardHip"),
    ("3800", "dome"),
    ("3900", "steeple"),
])
def test_alkis_numeric_codes_canonicalise(code: str, canonical: str) -> None:
    assert canonical_roof_type(code) == canonical


@pytest.mark.parametrize("leaf, canonical", [
    ("flat", "flat"),
    ("gable", "gable"),
    ("hip", "hip"),
    ("hipAndGable", "halfHip"),
    ("mansard", "mansard"),
    ("pyramid", "pyramid"),
    ("dome", "dome"),
    ("conic", "steeple"),
    ("otherSpecified", "other"),
])
def test_inspire_codelist_leaves_canonicalise(leaf: str, canonical: str) -> None:
    assert canonical_roof_type(leaf) == canonical


def test_unknown_value_returns_none() -> None:
    assert canonical_roof_type("9876") is None
    assert canonical_roof_type("not-a-roof") is None


def test_empty_or_none_returns_none() -> None:
    assert canonical_roof_type(None) is None
    assert canonical_roof_type("") is None


# -----------------------------------------------------------------------------
# Parser → schema integration
# -----------------------------------------------------------------------------

def test_bayern_fixture_extracts_roof_type_into_raw_attrs() -> None:
    """The Bayern test fixture has <bldg:roofType>3300</bldg:roofType>.
    Parser must surface that into raw_attrs so normalise can canonicalise."""
    with BY_FIXTURE.open("rb") as f:
        buildings = list(parse_citygml2_gml(f))
    assert any(b.raw_attrs.get("roofType") == "3300" for b in buildings)


def test_schema_building_carries_canonical_roof_type() -> None:
    """End-to-end: raw_attrs roofType "3300" → BuildingAttributes.roof_type "halfHip"."""
    parsed = ParsedBuilding(
        source_id="x",
        polygons=[[(50.0, 8.0, 100.0), (50.0, 8.001, 100.0),
                   (50.001, 8.001, 100.0), (50.0, 8.0, 100.0)]],
        raw_attrs={"function": "1010", "roofType": "3300"},
        height_m=12.0,
    )
    b = to_schema_building(parsed, source="citygml")
    assert b is not None
    assert b.attributes.roof_type == "halfHip"
    # raw still has the original value for downstream tooling
    assert b.attributes.raw["roofType"] == "3300"


def test_schema_building_roof_type_nil_when_source_lacks_it() -> None:
    """Hessen INSPIRE doesn't emit roofType in the current fixture — the
    schema field must end up None, not ""."""
    parsed = ParsedBuilding(
        source_id="he-1",
        polygons=[[(50.0, 8.0, 100.0), (50.0, 8.001, 100.0),
                   (50.001, 8.001, 100.0), (50.0, 8.0, 100.0)]],
        raw_attrs={"currentUse": "residential"},
    )
    b = to_schema_building(parsed, source="inspire")
    assert b is not None
    assert b.attributes.roof_type is None
