"""Disk-buffered intermediate store for the bake pipeline.

Phase 1 of `_bake_state` streams parsed-and-normalized buildings into
per-z15-tile NDJSON files under `data/intermediate/{state}/{z}/{x}/{y}.ndjson`.
Phase 2 enumerates those files, builds the final wire-format Tile,
gzips, uploads, and deletes each file.

Why disk-buffered: a state-scale bake (e.g. Bayern with ~10 million
buildings) does not fit in RAM as an in-memory accumulator. Disk is
cheap, RAM is not. State-scale intermediate is ~1.5 GB on disk for
Bayern, well within working-tree budget; RAM peak is bounded by one
Building at a time during Phase 1 and one tile's buildings during
Phase 2 (max few thousand, ~MB scale).

The append-mode JSON-lines format means a single building can be added
in O(1) without reading the whole file. Phase 2 reads each file once
to build the final Tile.

OSM-Pipeline (run_osm.py) does in-memory binning via osm_pbf._Handler
— this module is LoD2-specific.
"""
from __future__ import annotations

import shutil
from pathlib import Path
from typing import Iterator

from bake.schema import Building


class IntermediateStore:
    """Append-only NDJSON store keyed by (state, z, x, y)."""

    def __init__(self, root_dir: Path, state: str) -> None:
        """`root_dir` is the parent dir for all states' intermediates.
        `state` is the state code (e.g. `de_he`, `de_by`)."""
        self.state = state
        self.state_root = root_dir / state
        self.state_root.mkdir(parents=True, exist_ok=True)

    def _path(self, z: int, x: int, y: int) -> Path:
        return self.state_root / str(z) / str(x) / f"{y}.ndjson"

    def append_building(self, *, z: int, x: int, y: int,
                        building: Building) -> None:
        """Append the building's JSON to the (z, x, y) tile's NDJSON file.
        Creates parent directories on first write."""
        p = self._path(z, x, y)
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open("a", encoding="utf-8") as f:
            f.write(building.model_dump_json())
            f.write("\n")

    def iter_tile_keys(self) -> Iterator[tuple[int, int, int]]:
        """Yield every (z, x, y) tuple that has at least one building
        appended. Order is filesystem-dependent."""
        for path in self.state_root.rglob("*.ndjson"):
            # path is {state_root}/{z}/{x}/{y}.ndjson
            try:
                y = int(path.stem)
                x = int(path.parent.name)
                z = int(path.parent.parent.name)
            except ValueError:
                continue
            yield (z, x, y)

    def read_tile(self, *, z: int, x: int, y: int) -> list[Building]:
        """Read all buildings from the (z, x, y) tile's NDJSON.
        Returns an empty list if the tile has no buildings."""
        p = self._path(z, x, y)
        if not p.exists():
            return []
        out: list[Building] = []
        with p.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                out.append(Building.model_validate_json(line))
        return out

    def clear_tile(self, *, z: int, x: int, y: int) -> None:
        """Delete the (z, x, y) tile's NDJSON if present."""
        p = self._path(z, x, y)
        if p.exists():
            try:
                p.unlink()
            except OSError:
                pass

    def clear_all(self) -> None:
        """Wipe all intermediate data for this state."""
        if self.state_root.exists():
            shutil.rmtree(self.state_root)
        self.state_root.mkdir(parents=True, exist_ok=True)
