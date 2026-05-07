import gzip
import json
import tempfile
from pathlib import Path

from bake.schema import Building, BuildingAttributes, Polygon, Vertex
from bake.pack import write_tile_file


def _sample_building() -> Building:
    return Building(
        source_id="he_x",
        polygons=[Polygon(vertices=[
            Vertex(lat=50.110, lon=8.682, alt=110),
            Vertex(lat=50.111, lon=8.682, alt=110),
            Vertex(lat=50.111, lon=8.683, alt=110),
            Vertex(lat=50.110, lon=8.683, alt=110),
            Vertex(lat=50.110, lon=8.682, alt=110),
        ])],
        attributes=BuildingAttributes(building_class="unknown", raw={}),
    )


def test_writes_gzipped_json_with_correct_schema_version():
    with tempfile.TemporaryDirectory() as tmp:
        out_dir = Path(tmp)
        path = write_tile_file(
            out_dir=out_dir,
            state="de_he",
            z=15, x=17086, y=10958,
            buildings=[_sample_building()],
            source_dataset_version="hessen-2026-Q1",
        )
        assert path.exists()
        assert path.suffix == ".gz"
        # Inflate and decode
        with gzip.open(path, "rb") as f:
            decoded = json.loads(f.read())
        assert decoded["schema_version"] == 2
        assert decoded["state"] == "de_he"
        assert decoded["tile"] == {"z": 15, "x": 17086, "y": 10958}
        assert len(decoded["buildings"]) == 1
        assert decoded["buildings"][0]["source_id"] == "he_x"


def test_path_layout_matches_url_scheme():
    """Local file layout mirrors the R2 URL prefix exactly so
    upload.py can map a local path 1:1 to a remote key."""
    with tempfile.TemporaryDirectory() as tmp:
        out_dir = Path(tmp)
        path = write_tile_file(
            out_dir=out_dir,
            state="de_he",
            z=15, x=17086, y=10958,
            buildings=[],
            source_dataset_version="x",
        )
        rel = path.relative_to(out_dir).as_posix()
        assert rel == "v1/lod2/de_he/15/17086/10958.json.gz"


def test_includes_generated_at_iso_timestamp():
    with tempfile.TemporaryDirectory() as tmp:
        out_dir = Path(tmp)
        path = write_tile_file(
            out_dir=out_dir,
            state="de_by",
            z=15, x=17572, y=11308,
            buildings=[_sample_building()],
            source_dataset_version="bayern-test",
        )
        with gzip.open(path, "rb") as f:
            decoded = json.loads(f.read())
        # ISO 8601 timestamps include "T" between date and time
        assert "T" in decoded["generated_at"]
        # Should be UTC-ish; pydantic's datetime serialiser emits
        # offset like "+00:00" or "Z" — accept either.
        gen = decoded["generated_at"]
        assert gen.endswith("Z") or "+00:00" in gen or gen[-6] in "+-"
