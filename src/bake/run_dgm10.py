"""CLI entrypoint for the DGM10 per-z15-tile DEM bake.

Reads a BKG DGM10 GeoTIFF for one Bundesland (EPSG:25832 UTM32N,
10 m raster, DL-DE BY 2.0) and emits one binary per z15 tile within
the state's bbox, optionally uploading all of them to R2.

# One-time source acquisition

The BKG DGM10 GeoTIFFs are free under DL-DE BY 2.0 but require manual
download (the BKG download page sets session cookies that headless
fetchers don't have). Per-Bundesland files keep the source manageable:

1. Visit https://gdz.bkg.bund.de/index.php/default/digitales-gelandemodell-gitterweite-10-m-dgm10.html
   (or https://daten.gdz.bkg.bund.de/produkte/dgm/dgm10/ if cataloged).
2. Download the Bundesland file (e.g. `dgm10_he.tif` for Hessen,
   ~500 MB – 1 GB compressed). EPSG:25832 / UTM32N.
3. Save to `data/raw/dgm10/{state}.tif` (gitignored).

# Usage

    python -m bake.run_dgm10 --state he --source-tif data/raw/dgm10/he.tif

Optional:
    --out-dir DIR     output root (default: data/tiled/v1/dgm10)
    --no-upload       skip R2 upload (local files only)
    --output-deg X    output grid spacing in degrees (default: 0.0001 ≈ 10 m)
    --resume          skip tiles whose local output already exists
    --limit N         stop after N tiles (smoke-test)

# Wall time

~30 000 z15 tiles for Hessen × ~0.3 s per tile (crop + reproject +
pack + R2 PUT) ≈ 2.5 h end-to-end. Use `--limit 10` for a smoke test
first to validate a few tiles round-trip from R2 before kicking off
the full state.
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

from bake.dgm10 import (
    DEFAULT_OUTPUT_DEG_DGM10,
    bake_tile,
    iter_z15_tiles_for_state,
    local_path_for_tile,
)
from bake.upload import upload_dgm10_tile

R2_BUCKET = "mapbiker-tiles"

STATE_ALIASES = {
    "he": "de_he",
    "by": "de_by",
}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="bake.run_dgm10",
        description="Bake per-z15-tile DGM10 binaries for the mapbiker iOS app.",
    )
    parser.add_argument(
        "--state", required=True, choices=sorted(STATE_ALIASES),
        help="Bundesland code (e.g. he, by).",
    )
    parser.add_argument(
        "--source-tif", required=True, type=Path,
        help="Path to the BKG DGM10 GeoTIFF for this state.",
    )
    parser.add_argument(
        "--out-dir", type=Path, default=None,
        help="Output root directory. Defaults to data/tiled/v1/dgm10.",
    )
    parser.add_argument(
        "--output-deg", type=float, default=DEFAULT_OUTPUT_DEG_DGM10,
        help=f"Output grid spacing in degrees (default: {DEFAULT_OUTPUT_DEG_DGM10}).",
    )
    parser.add_argument(
        "--no-upload", action="store_true",
        help="Skip R2 upload — local files only.",
    )
    parser.add_argument(
        "--resume", action="store_true",
        help="Skip tiles whose local output binary already exists.",
    )
    parser.add_argument(
        "--limit", type=int, default=None,
        help="Stop after N tiles (smoke-test).",
    )
    args = parser.parse_args(argv)

    state_full = STATE_ALIASES[args.state]

    if not args.source_tif.exists():
        print(f"error: source GeoTIFF not found: {args.source_tif}",
              file=sys.stderr)
        print(
            "  Download from "
            "https://gdz.bkg.bund.de/index.php/default/"
            "digitales-gelandemodell-gitterweite-10-m-dgm10.html",
            file=sys.stderr)
        return 2

    out_root = args.out_dir or Path("data") / "tiled" / "v1" / "dgm10"

    print(f"[run_dgm10] state={state_full} src={args.source_tif}")
    print(f"[run_dgm10] output_deg={args.output_deg} out_root={out_root}")
    print(f"[run_dgm10] resume={args.resume} upload={not args.no_upload}")
    if args.limit is not None:
        print(f"[run_dgm10] limit={args.limit} (smoke-test mode)")

    tiles = list(iter_z15_tiles_for_state(state_full))
    print(f"[run_dgm10] {len(tiles)} z15 tiles in {state_full} bbox.")
    if args.limit is not None:
        tiles = tiles[: args.limit]

    skipped = 0
    failed = 0
    started = time.monotonic()
    for i, tile in enumerate(tiles):
        out_path = local_path_for_tile(
            out_root=out_root, state=state_full, tile=tile)
        if args.resume and out_path.exists():
            skipped += 1
            continue
        try:
            binary = bake_tile(
                src_geotiff=args.source_tif,
                tile=tile,
                out_path=out_path,
                output_deg=args.output_deg,
            )
        except Exception as exc:  # noqa: BLE001 — log + continue, do not abort the run
            print(f"[run_dgm10] FAIL tile={tile.cache_key}: {exc}",
                  file=sys.stderr)
            failed += 1
            continue

        if not args.no_upload:
            try:
                upload_dgm10_tile(
                    local_path=out_path, bucket=R2_BUCKET,
                    state=state_full, z=tile.z, x=tile.x, y=tile.y,
                )
            except Exception as exc:  # noqa: BLE001
                print(
                    f"[run_dgm10] UPLOAD FAIL tile={tile.cache_key}: {exc}",
                    file=sys.stderr,
                )
                failed += 1
                continue

        if (i + 1) % 100 == 0 or i == 0 or i == len(tiles) - 1:
            elapsed = time.monotonic() - started
            done = i + 1 - skipped
            rate = done / elapsed if elapsed > 0 else 0.0
            eta = (len(tiles) - i - 1) / rate if rate > 0 else float("inf")
            print(
                f"[run_dgm10] {i + 1}/{len(tiles)} "
                f"tile={tile.cache_key} "
                f"({binary.rows}x{binary.cols}) "
                f"{rate:.2f} tiles/s eta={eta / 60:.1f} min "
                f"(skipped={skipped}, failed={failed})"
            )

    elapsed = time.monotonic() - started
    print(
        f"[run_dgm10] complete: "
        f"{len(tiles) - skipped - failed} baked, "
        f"{skipped} skipped, {failed} failed, "
        f"elapsed={elapsed / 60:.1f} min"
    )
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
