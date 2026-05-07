"""LoD2 building_class mapping.

INSPIRE bu-core3d 4.0 currentUse + buildingNature → unified class.
CityGML 1.0/2.0 bldg:function (ALKIS code) → unified class.
"""
from __future__ import annotations


INSPIRE_USE_TO_CLASS = {
    "residential":     "residential",
    "industrial":      "industrial",
    "commercial":      "commercial",
    "agriculture":     "agricultural",
    "agricultural":    "agricultural",
    "religious":       "religious",
    "education":       "civic",
    "health":          "civic",
    "publicService":   "civic",
    "transport":       "unknown",
    "unknown":         "unknown",
}

INSPIRE_NATURE_TO_CLASS = {
    "residential":     "residential",
    "industrial":      "industrial",
    "commercial":      "commercial",
    "religious":       "religious",
    "agricultural":    "agricultural",
    "bruecke":         "unknown",
    "garage":          "unknown",
}

ALKIS_FUNCTION_TO_CLASS = {
    "31001": "residential",
    "31002": "commercial",
    "31003": "commercial",
    "31004": "agricultural",
    "31005": "commercial",
    "31006": "industrial",
    "31007": "religious",
    "31008": "civic",
    "31009": "unknown",
    "31010": "industrial",
}


def classify_inspire(raw: dict) -> str:
    """currentUse wins over buildingNature; falls back to 'unknown'."""
    use = raw.get("currentUse")
    if use and use in INSPIRE_USE_TO_CLASS:
        return INSPIRE_USE_TO_CLASS[use]
    nature = raw.get("buildingNature")
    if nature and nature in INSPIRE_NATURE_TO_CLASS:
        return INSPIRE_NATURE_TO_CLASS[nature]
    return "unknown"


def classify_citygml(raw: dict) -> str:
    """5-digit prefix of bldg:function → class. Fallback 'unknown'."""
    func = raw.get("function")
    if not func:
        return "unknown"
    prefix = func.split("_")[0][:5]
    return ALKIS_FUNCTION_TO_CLASS.get(prefix, "unknown")
