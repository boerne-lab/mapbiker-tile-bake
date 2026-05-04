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

from bake.chunking import chunked_fetch
from bake.normalize import to_schema_building
from bake.pack import write_tile_file
from bake.retile import bin_buildings_by_z15_tile
from bake.sources import hessen
from bake.upload import upload_tile

# State bbox: (min_lat, min_lon, max_lat, max_lon).
# Approximate; intersected with state-boundary at fetch time if
# upstream supports it (INSPIRE WFS does via bbox+CRS).
HESSEN_BBOX = (49.39, 7.77, 51.66, 10.24)

STATE_BBOXES = {
    "he": HESSEN_BBOX,
    # "nw": NRW_BBOX,    # added by Task 20
    # "by": BAYERN_BBOX, # added by Task 24
}

R2_BUCKET = "mapbiker-tiles"


def _bake_state(state: str, out_dir: Path,
                source_version: str, do_upload: bool) -> int:
    """Fetch + parse + normalize + retile + pack + (optionally) upload
    one Bundesland's worth of tiles."""
    state_code = f"de_{state}"
    bbox = STATE_BBOXES[state]

    if state == "he":
        parsed_iter = chunked_fetch(
            hessen.fetch_buildings,
            lat_min=bbox[0], lon_min=bbox[1],
            lat_max=bbox[2], lon_max=bbox[3],
            initial_chunk_deg=0.05,  # ~5 km
            min_chunk_deg=0.005,     # ~500 m
            cap=10000,
            verbose=True,
        )
    else:
        raise ValueError(f"state not yet implemented: {state}")

    # Materialise the iterator as we normalise — keeps memory usage
    # bounded by total building count, not response body size.
    buildings = []
    for parsed in parsed_iter:
        b = to_schema_building(parsed)
        if b is not None:
            buildings.append(b)
    print(f"[{state}] parsed {len(buildings)} buildings",
          file=sys.stderr, flush=True)

    bins = bin_buildings_by_z15_tile(buildings)
    print(f"[{state}] binned into {len(bins)} z15 tiles",
          file=sys.stderr, flush=True)

    paths = []
    for (z, x, y), tile_buildings in bins.items():
        p = write_tile_file(
            out_dir=out_dir, state=state_code,
            z=z, x=x, y=y,
            buildings=tile_buildings,
            source_dataset_version=source_version,
        )
        paths.append(p)
    print(f"[{state}] wrote {len(paths)} tile files",
          file=sys.stderr, flush=True)

    if do_upload:
        for i, p in enumerate(paths, 1):
            rel = p.relative_to(out_dir).as_posix()
            upload_tile(local_path=p, bucket=R2_BUCKET, remote_key=rel)
            if i % 50 == 0 or i == len(paths):
                print(f"[{state}] uploaded {i}/{len(paths)}",
                      file=sys.stderr, flush=True)
        print(f"[{state}] uploaded {len(paths)} tiles to R2",
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
