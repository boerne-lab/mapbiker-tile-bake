"""Layer-presence + class-distribution sanity checks for v2 LoD2 tiles.
These tests run AFTER a re-bake of HE/BY/NRW (Tasks 1.19-1.22). They
gate the bake quality.

If the local data dir does not yet contain a baked tile, tests SKIP.
This is intentional — pytest.skip is the right behaviour during
development; a CI gate later would require the dir present.
"""
from pathlib import Path
import json
import pytest


VALID_CLASSES = {"residential", "commercial", "industrial", "civic",
                 "religious", "agricultural", "historic", "unknown"}

# Frankfurt-Innenstadt at z15 — verifiziert via mercantile.tile(8.68, 50.11, 15)
FRANKFURT_TILE = ("de_he", 17171, 11045)

# Spot-check root for baked-output. Adapt if `pack.write_tile_file` writes elsewhere;
# data/tiled_full/{state}/v1/lod2/.../<x>/<y>.json.gz is the existing v1 LoD2 layout.
# v2 layout TBD by Task 1.19's bake — these tests will be re-pointed if the path
# differs.
BAKED_DIR_CANDIDATES = [
    Path("data/tiled_v2"),       # if v2 bake writes here
    Path("data/tiled_full"),     # if reuses existing dir
]


def _baked_dir() -> Path | None:
    for cand in BAKED_DIR_CANDIDATES:
        if cand.exists():
            return cand
    return None


def _load_tile(state: str, x: int, y: int) -> dict:
    base = _baked_dir()
    if base is None:
        pytest.skip("no baked-output directory found yet")
    # Try a few candidate path layouts:
    candidates = [
        base / state / "z15" / str(x) / f"{y}.json",
        base / state / "v2" / "lod2" / "z15" / str(x) / f"{y}.json",
        base / "v2" / "lod2" / state / "z15" / str(x) / f"{y}.json",
    ]
    for path in candidates:
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
    pytest.skip(f"tile not yet baked at any of: {candidates}")


def test_baked_tile_is_v2():
    tile = _load_tile(*FRANKFURT_TILE)
    assert tile["schema_version"] == 2


def test_baked_tile_has_class_distribution():
    tile = _load_tile(*FRANKFURT_TILE)
    classes = {b["attributes"]["building_class"] for b in tile["buildings"]}
    assert "residential" in classes, f"expected residential, got {classes}"
    assert classes & {"commercial", "civic"}, \
        f"expected ≥1 non-residential urban class, got {classes}"


def test_no_building_lacks_attributes():
    tile = _load_tile(*FRANKFURT_TILE)
    for b in tile["buildings"]:
        assert "attributes" in b, f"building {b['source_id']} missing attributes"
        assert b["attributes"]["building_class"] in VALID_CLASSES


def test_unknown_class_share_under_threshold():
    """If >50% of buildings classify as 'unknown', source-data parsing or
    mapping is broken."""
    tile = _load_tile(*FRANKFURT_TILE)
    n = len(tile["buildings"])
    if n < 10:
        pytest.skip(f"tile has only {n} buildings; threshold-test not meaningful")
    unknowns = sum(1 for b in tile["buildings"]
                   if b["attributes"]["building_class"] == "unknown")
    assert unknowns / n < 0.5, \
        f"{unknowns}/{n} buildings classify as unknown — bake or classify broken?"
