"""osmium tags-filter pre-pass — drops irrelevant tags from PBF.
Reduces PBF size ~50-60% before pyosmium-streaming."""
from __future__ import annotations

KEEP_KEYS: frozenset[str] = frozenset({
    # Buildings
    "building", "building:levels", "building:height", "height",
    "roof:shape", "roof:height", "roof:levels",
    # Roads
    "highway", "surface", "lanes", "bridge", "layer", "cycleway",
    # Land use
    "landuse", "natural", "water", "waterway", "width",
    # Rail
    "railway", "tunnel",
    # Trees / forests
    "leaf_type", "leaf_cycle", "genus", "diameter_crown",
    # D3 / landmarks
    "wikidata", "historic", "tourism", "religion", "denomination",
    # v3 additions: road detail
    "maxspeed",
    # v3 additions: building detail
    "building:colour", "roof:colour", "building:material", "roof:material",
    # v3 additions: barrier layer
    "barrier",
    # v3 additions: tree taxon
    "taxon",
    # Bus stops (highway=bus_stop nodes use `shelter` to decide whether
    # the iOS-side Wartehäuschen + glass roof should be rendered).
    "shelter",
    # Common
    "name", "ref",
})


def build_filter_command(input_path: str, output_path: str) -> list[str]:
    """Construct osmium tags-filter shell command."""
    keys = ",".join(sorted(KEEP_KEYS))
    return [
        "osmium", "tags-filter",
        input_path,
        f"a/{keys}",   # all object types
        "-o", output_path,
        "--overwrite",
    ]
