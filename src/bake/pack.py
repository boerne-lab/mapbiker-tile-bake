"""Write per-tile JSON files compressed with gzip.

On-disk layout mirrors the R2 URL prefix exactly:
`{out_dir}/v1/lod2/{state}/{z}/{x}/{y}.json.gz`

so `bake.upload.upload_tile()` can map a local path 1:1 to a remote
key by stripping the `out_dir` prefix.
"""
from __future__ import annotations

import gzip
from datetime import datetime, timezone
from pathlib import Path

from bake.schema import Tile, TileCoord, Building


def write_tile_file(*, out_dir: Path, state: str,
                    z: int, x: int, y: int,
                    buildings: list[Building],
                    source_dataset_version: str) -> Path:
    """Serialise one tile to `{out_dir}/v1/lod2/{state}/{z}/{x}/{y}.json.gz`
    and return the resulting path. Creates parent directories as needed.
    Overwrites silently if the file already exists.
    """
    payload = Tile(
        schema_version=2,
        state=state,
        tile=TileCoord(z=z, x=x, y=y),
        generated_at=datetime.now(timezone.utc).isoformat(),
        source_dataset_version=source_dataset_version,
        buildings=buildings,
    )

    path = (out_dir / "v1" / "lod2" / state / str(z)
            / str(x) / f"{y}.json.gz")
    path.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(path, "wb", compresslevel=9) as f:
        f.write(payload.model_dump_json().encode("utf-8"))
    return path
