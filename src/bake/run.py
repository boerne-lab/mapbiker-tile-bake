"""CLI entrypoint for the tile-bake pipeline.

Phase 3 supports only Hessen end-to-end. NRW (Task 20) and Bayern
(Task 24) tasks register additional source modules in the dispatch
chain in `_bake_state()` below.

Usage:

    python -m bake.run all --state he --source-version hessen-2026-Q1

Optional:
    --out DIR           output directory (default: data/tiled)
    --no-upload         skip the R2 upload step
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import mercantile

from bake.chunking import chunked_fetch
from bake.intermediate import IntermediateStore
from bake.normalize import to_schema_building
from bake.pack import write_tile_file
from bake.sources import hessen
from bake.upload import upload_tile

# State bbox: (min_lat, min_lon, max_lat, max_lon).
# Approximate; intersected with state-boundary at fetch time if
# upstream supports it (INSPIRE WFS does via bbox+CRS).
HESSEN_BBOX = (49.39, 7.77, 51.66, 10.24)
BAYERN_BBOX = (47.27, 8.97, 50.56, 13.84)

STATE_BBOXES = {
    "he": HESSEN_BBOX,
    "by": BAYERN_BBOX,
    # "nw": NRW_BBOX,    # added by Task 20
}

R2_BUCKET = "mapbiker-tiles"


def _bake_state(state: str, out_dir: Path,
                source_version: str, do_upload: bool) -> int:
    """Two-phase bake. Phase 1 streams parsed buildings into per-tile
    NDJSON files on disk. Phase 2 reads each NDJSON and produces the
    final gzipped JSON tile. Memory peak is bounded by a single
    Building (Phase 1) or a single tile's worth of buildings (Phase 2)
    — never the entire state."""
    state_code = f"de_{state}"
    bbox = STATE_BBOXES[state]

    # Per-bake intermediate store sits next to the final output.
    intermediate = IntermediateStore(
        root_dir=out_dir.parent / "intermediate",
        state=state_code,
    )
    intermediate.clear_all()
    print(f"[{state}] intermediate store at "
          f"{intermediate.state_root}", file=sys.stderr, flush=True)

    # ----- Phase 1: stream-bin -----
    if state == "he":
        parsed_iter = chunked_fetch(
            hessen.fetch_buildings,
            lat_min=bbox[0], lon_min=bbox[1],
            lat_max=bbox[2], lon_max=bbox[3],
            initial_chunk_deg=0.05,
            min_chunk_deg=0.005,
            cap=10000,
            verbose=True,
        )
    elif state == "by":
        from bake.sources import bayern
        parsed_iter = bayern.fetch_buildings(
            min_lat=bbox[0], min_lon=bbox[1],
            max_lat=bbox[2], max_lon=bbox[3],
        )
    else:
        raise ValueError(f"state not yet implemented: {state}")

    n_parsed = 0
    n_binned = 0
    for parsed in parsed_iter:
        b = to_schema_building(parsed)
        if b is None:
            continue
        n_parsed += 1
        # Inline centroid + tile lookup. We avoid the
        # bin_buildings_by_z15_tile([list]) shape because that requires
        # the whole list in memory, defeating the refactor's purpose.
        verts = b.polygons[0].vertices
        n_v = len(verts)
        lon = sum(v.lon for v in verts) / n_v
        lat = sum(v.lat for v in verts) / n_v
        t = mercantile.tile(lon, lat, 15)
        intermediate.append_building(
            z=15, x=t.x, y=t.y, building=b,
        )
        n_binned += 1
        if n_binned % 10_000 == 0:
            print(f"[{state}] phase 1: {n_binned} buildings binned",
                  file=sys.stderr, flush=True)

    print(f"[{state}] phase 1 done: {n_parsed} parsed, "
          f"{n_binned} binned to disk", file=sys.stderr, flush=True)

    # ----- Phase 2: finalize per tile -----
    n_tiles = 0
    for (z, x, y) in intermediate.iter_tile_keys():
        tile_buildings = intermediate.read_tile(z=z, x=x, y=y)
        p = write_tile_file(
            out_dir=out_dir, state=state_code,
            z=z, x=x, y=y,
            buildings=tile_buildings,
            source_dataset_version=source_version,
        )
        if do_upload:
            rel = p.relative_to(out_dir).as_posix()
            upload_tile(
                local_path=p, bucket=R2_BUCKET, remote_key=rel,
            )
        # Free intermediate disk space progressively as each tile
        # is finalised — keeps peak disk usage tighter.
        intermediate.clear_tile(z=z, x=x, y=y)
        n_tiles += 1
        if n_tiles % 50 == 0:
            verb = "uploaded" if do_upload else "wrote"
            print(f"[{state}] phase 2: {verb} {n_tiles} tiles",
                  file=sys.stderr, flush=True)

    print(f"[{state}] phase 2 done: {n_tiles} tiles total",
          file=sys.stderr, flush=True)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="bake.run")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_all = sub.add_parser(
        "all",
        help="fetch + parse + normalize + retile + pack + upload",
    )
    p_all.add_argument("--state", required=True,
                       choices=list(STATE_BBOXES.keys()))
    p_all.add_argument("--out", default="data/tiled",
                       help="output directory (default: data/tiled)")
    p_all.add_argument("--source-version", required=True,
                       help="opaque dataset-version string "
                            "(e.g. hessen-2026-Q1)")
    p_all.add_argument("--no-upload", action="store_true",
                       help="skip the R2 upload step")

    args = parser.parse_args(argv)

    if args.cmd == "all":
        return _bake_state(
            state=args.state,
            out_dir=Path(args.out),
            source_version=args.source_version,
            do_upload=not args.no_upload,
        )
    return 1


if __name__ == "__main__":
    sys.exit(main())
