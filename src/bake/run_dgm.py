"""CLI entrypoint for the DGM200 horizon-DEM bake.

Reads the BKG DGM200 GeoTIFF (whole-Germany source, EPSG:25832 UTM32N,
200 m raster, DL-DE BY 2.0) and emits one per-Bundesland binary,
optionally uploading to R2.

# One-time source acquisition

The BKG DGM200 GeoTIFF is free under DL-DE BY 2.0 but requires manual
download (the BKG download page sets a session cookie that headless
fetchers don't have). Steps:

1. Visit https://daten.bkg.bund.de/produkte/dgm/dgm200/aktuell/
2. Download `dgm200.tif` (whole Germany, ~30 MB, EPSG:25832).
3. Save to `data/raw/dgm200/dgm200.tif` (gitignored).

# Usage

    python -m bake.run_dgm --state he --source-tif data/raw/dgm200/dgm200.tif

Optional:
    --out FILE        output path (default: data/tiled/v1/dgm/{state}.bin)
    --no-upload       skip R2 upload (local file only)
    --output-deg X    output grid spacing in degrees (default: 0.002 = ~220 m)

The output binary follows the `bake.dgm` DGM2 v1 format — see that
module's header for the on-the-wire layout.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from bake.dgm import DEFAULT_OUTPUT_DEG, bake_state
from bake.upload import upload_dgm_binary

R2_BUCKET = "mapbiker-tiles"

# Map short CLI state code → full state identifier used in remote keys.
STATE_ALIASES = {
    "he": "de_he",
    "by": "de_by",
}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="bake.run_dgm",
        description="Bake DGM200 horizon-DEM binaries for the mapbiker iOS app.",
    )
    parser.add_argument(
        "--state", required=True, choices=sorted(STATE_ALIASES),
        help="Bundesland code (e.g. he, by).",
    )
    parser.add_argument(
        "--source-tif", required=True, type=Path,
        help="Path to the BKG DGM200 GeoTIFF (whole-Germany source).",
    )
    parser.add_argument(
        "--out", type=Path, default=None,
        help="Output binary path. Defaults to data/tiled/v1/dgm/{state}.bin.",
    )
    parser.add_argument(
        "--output-deg", type=float, default=DEFAULT_OUTPUT_DEG,
        help=f"Output grid spacing in degrees (default: {DEFAULT_OUTPUT_DEG}).",
    )
    parser.add_argument(
        "--no-upload", action="store_true",
        help="Skip R2 upload — local file only.",
    )
    args = parser.parse_args(argv)

    state_full = STATE_ALIASES[args.state]

    if not args.source_tif.exists():
        print(f"error: source GeoTIFF not found: {args.source_tif}",
              file=sys.stderr)
        print(
            "  Download from "
            "https://daten.bkg.bund.de/produkte/dgm/dgm200/aktuell/",
            file=sys.stderr)
        return 2

    out_path = args.out or (
        Path("data") / "tiled" / "v1" / "dgm" / f"{state_full}.bin")

    print(f"[run_dgm] state={state_full} src={args.source_tif}")
    print(f"[run_dgm] output_deg={args.output_deg}")
    print(f"[run_dgm] out={out_path}")

    binary = bake_state(
        src_geotiff=args.source_tif,
        state=state_full,
        out_path=out_path,
        output_deg=args.output_deg,
    )
    size_bytes = out_path.stat().st_size
    print(
        f"[run_dgm] wrote {binary.rows} x {binary.cols} cells "
        f"({size_bytes / 1024:.1f} KB) "
        f"bbox=({binary.min_lat:.4f}, {binary.min_lon:.4f}, "
        f"{binary.max_lat:.4f}, {binary.max_lon:.4f})")

    if args.no_upload:
        print("[run_dgm] --no-upload set, skipping R2.")
        return 0

    print(f"[run_dgm] uploading to s3://{R2_BUCKET}/v1/dgm/{state_full}.bin")
    upload_dgm_binary(
        local_path=out_path,
        bucket=R2_BUCKET,
        state=state_full,
    )
    print("[run_dgm] upload complete.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
