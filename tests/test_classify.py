import pytest
from bake.normalize.classify import classify_inspire, classify_citygml


@pytest.mark.parametrize("raw,expected", [
    ({"currentUse": "residential"}, "residential"),
    ({"currentUse": "industrial"}, "industrial"),
    ({"currentUse": "religious"}, "religious"),
    ({"currentUse": "transport"}, "unknown"),  # bridges
    ({"buildingNature": "residential"}, "residential"),  # falls back to nature
    ({"currentUse": "residential", "buildingNature": "industrial"},
     "residential"),  # currentUse wins over buildingNature
    ({}, "unknown"),
    ({"currentUse": "totally_unknown"}, "unknown"),
])
def test_classify_inspire(raw, expected):
    assert classify_inspire(raw) == expected


@pytest.mark.parametrize("raw,expected", [
    ({"function": "31001_2010"}, "residential"),
    ({"function": "31001"}, "residential"),
    ({"function": "31007_X"}, "religious"),
    ({"function": "31006_2010"}, "industrial"),
    ({"function": "31008"}, "civic"),
    ({"function": "99999"}, "unknown"),
    ({}, "unknown"),
])
def test_classify_citygml(raw, expected):
    assert classify_citygml(raw) == expected


def test_classify_citygml_takes_first_5_digits():
    assert classify_citygml({"function": "31001_2010_someextra"}) == "residential"
