"""End-to-end pipeline test with synthetic PBF — no network, no R2 upload."""
import json
import subprocess
import tempfile
from pathlib import Path

import pytest


@pytest.mark.slow
def test_full_pipeline_synthetic_hessen_corner():
    fixture = Path(__file__).parent / "fixtures" / "osm_pbf" / "building_residential.osm.pbf"
    if not fixture.exists():
        pytest.skip("fixture not present; run build_fixtures.py first")

    with tempfile.TemporaryDirectory() as tmp:
        result = subprocess.run([
            "python", "-m", "bake.run_osm",
            "--state", "he",
            "--pbf", str(fixture),
            "--source-version", "test",
            "--out", tmp,
            "--no-upload", "--no-filter",
        ], check=True, capture_output=True, text=True)

        # Verify at least one tile was produced
        tiles = list(Path(tmp).rglob("*.json"))
        assert len(tiles) >= 1, f"no tiles produced; stdout={result.stdout}"

        tile_data = json.loads(tiles[0].read_text(encoding="utf-8"))
        assert tile_data["schema_version"] == 1
        assert len(tile_data["buildings"]) >= 1
        assert tile_data["buildings"][0]["building_class"] == "residential"
        assert tile_data["buildings"][0]["building_type"] == "residential"
        assert tile_data["buildings"][0]["wikidata"] == "Q42"


@pytest.mark.slow
def test_full_pipeline_landuse_fixture():
    fixture = Path(__file__).parent / "fixtures" / "osm_pbf" / "landuse_farmland.osm.pbf"
    if not fixture.exists():
        pytest.skip("fixture not present")

    with tempfile.TemporaryDirectory() as tmp:
        subprocess.run([
            "python", "-m", "bake.run_osm",
            "--state", "he",
            "--pbf", str(fixture),
            "--source-version", "test",
            "--out", tmp,
            "--no-upload", "--no-filter",
        ], check=True, capture_output=True, text=True)

        tiles = list(Path(tmp).rglob("*.json"))
        assert len(tiles) >= 1
        tile_data = json.loads(tiles[0].read_text(encoding="utf-8"))
        assert len(tile_data["landuse"]) >= 1
        assert tile_data["landuse"][0]["landuse_class"] == "farmland"
        assert tile_data["landuse"][0]["raw_tag"] == {"landuse": "farmland"}
