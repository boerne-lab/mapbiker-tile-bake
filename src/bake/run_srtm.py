"""CLI entrypoint for the SRTM30 per-z15-tile DEM bake.

Universal fallback DEM source for the procedural-3D-world pipeline.
Uses AWS Terrain Tiles (Terrarium-encoded PNG) — public S3, no auth.

# Usage

Smoke-test one tile around Frankfurt-Westend (origin of the iPad
test route):

    python -m bake.run_srtm --tile z15:17167:11095 --no-upload

Bake all z15 tiles in a state bbox:

    python -m bake.run_srtm --state he

Bake a smaller region by lat/lon bbox (e.g. Frankfurt ~10×10 km):

    python -m bake.run_srtm \\
        --bbox 50.07,8.55,50.16,8.72 \\
        --state-prefix de_he

Optional flags:
    --no-upload          local-only (skip R2 PUT)
    --downsample-factor  256 → 256/F (default: 4 → 64-grid, ~12 m
                         effective spacing at HE latitude)
    --resume             skip tiles whose local output exists
    --limit N            stop after N tiles
    --cache-root DIR     where Terrarium PNGs are cached (default:
                         data/raw/srtm30_terrarium)

# State-prefix semantics

The R2 path is `v1/dgm10/{state}/z15/{x}/{y}.bin` (shares the dgm10
shelf — the iOS adapter is grid-agnostic). `--state` resolves to the
full bbox via STATE_ALIASES. `--bbox + --state-prefix` lets you bake a
sub-region under an arbitrary state-label (e.g. only the Frankfurt
corridor for a quick smoke test before committing to the full HE bake).
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import mercantile
import requests

from bake.dgm10 import (
    TileCoord,
    iter_z15_tiles_for_state,
    local_path_for_tile,
)
from bake.srtm30 import DEFAULT_DOWNSAMPLE_FACTOR, bake_tile_from_srtm
from bake.upload import upload_dgm10_tile

R2_BUCKET = "mapbiker-tiles"

STATE_ALIASES = {
    "he": "de_he",
    "by": "de_by",
}


def _parse_tile_arg(s: str) -> TileCoord:
    """Parse `z:x:y` (e.g. `z15:17167:11095`)."""
    parts = s.replace("z", "", 1).split(":")
    if len(parts) != 3:
        raise ValueError(f"--tile must be z:x:y, got {s!r}")
    z, x, y = (int(p) for p in parts)
    return TileCoord(z=z, x=x, y=y)


def _parse_bbox_arg(s: str) -> tuple[float, float, float, float]:
    """Parse `min_lat,min_lon,max_lat,max_lon`."""
    parts = s.split(",")
    if len(parts) != 4:
        raise ValueError(
            f"--bbox must be min_lat,min_lon,max_lat,max_lon, got {s!r}")
    return tuple(float(p) for p in parts)  # type: ignore[return-value]


def _iter_tiles_in_bbox(
    bbox: tuple[float, float, float, float],
) -> list[TileCoord]:
    """Enumerate z15 tiles whose bbox overlaps `bbox`. Uses mercantile."""
    min_lat, min_lon, max_lat, max_lon = bbox
    return [
        TileCoord(z=t.z, x=t.x, y=t.y)
        for t in mercantile.tiles(min_lon, min_lat, max_lon, max_lat, zooms=[15])
    ]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="bake.run_srtm",
        description="Bake per-z15-tile SRTM30 binaries via AWS Terrain Tiles.",
    )
    g = parser.add_mutually_exclusive_group(required=True)
    g.add_argument(
        "--state", choices=sorted(STATE_ALIASES),
        help="Bundesland code (e.g. he, by). Bakes every z15 tile "
             "in the state's bbox.",
    )
    g.add_argument(
        "--bbox", type=_parse_bbox_arg,
        help="Lat/lon bbox: min_lat,min_lon,max_lat,max_lon. Bakes "
             "every z15 tile that overlaps. Use with --state-prefix.",
    )
    g.add_argument(
        "--tile", type=_parse_tile_arg,
        help="Single tile (z:x:y) for smoke-testing. Use with "
             "--state-prefix.",
    )

    parser.add_argument(
        "--state-prefix", default="de_he",
        help="State label used in the R2 path "
             "(v1/dgm10/{state-prefix}/z15/{x}/{y}.bin). "
             "Defaults to de_he for the --bbox / --tile paths. "
             "Ignored when --state is set (resolved via STATE_ALIASES).",
    )
    parser.add_argument(
        "--out-dir", type=Path, default=None,
        help="Output root directory. Defaults to data/tiled/v1/dgm10.",
    )
    parser.add_argument(
        "--cache-root", type=Path,
        default=Path("data") / "raw" / "srtm30_terrarium",
        help="Where Terrarium PNGs are cached locally.",
    )
    parser.add_argument(
        "--downsample-factor", type=int, default=DEFAULT_DOWNSAMPLE_FACTOR,
        help=f"Block-mean downsample factor (default: {DEFAULT_DOWNSAMPLE_FACTOR}). "
             "Must divide 256 evenly. 1 keeps the full 256×256 grid; "
             "4 → 64×64 (~12 m grid, ~4 KB gzipped per tile).",
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

    if args.state is not None:
        state_full = STATE_ALIASES[args.state]
        tiles = list(iter_z15_tiles_for_state(state_full))
    elif args.bbox is not None:
        state_full = args.state_prefix
        tiles = _iter_tiles_in_bbox(args.bbox)
    else:
        state_full = args.state_prefix
        tiles = [args.tile]

    out_root = args.out_dir or Path("data") / "tiled" / "v1" / "dgm10"

    print(f"[run_srtm] state-prefix={state_full} out_root={out_root}")
    print(f"[run_srtm] cache_root={args.cache_root}")
    print(f"[run_srtm] downsample_factor={args.downsample_factor} "
          f"resume={args.resume} upload={not args.no_upload}")
    print(f"[run_srtm] {len(tiles)} tiles to process.")
    if args.limit is not None:
        tiles = tiles[: args.limit]
        print(f"[run_srtm] limit={args.limit} applied.")

    session = requests.Session()
    session.headers["User-Agent"] = "mapbiker-tile-bake/0.1 (+srtm30)"

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
            binary = bake_tile_from_srtm(
                tile=tile,
                out_path=out_path,
                session=session,
                cache_root=args.cache_root,
                downsample_factor=args.downsample_factor,
            )
        except Exception as exc:  # noqa: BLE001
            print(f"[run_srtm] FAIL tile={tile.cache_key}: {exc}",
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
                    f"[run_srtm] UPLOAD FAIL tile={tile.cache_key}: {exc}",
                    file=sys.stderr,
                )
                failed += 1
                continue

        if (i + 1) % 25 == 0 or i == 0 or i == len(tiles) - 1:
            elapsed = time.monotonic() - started
            done = i + 1 - skipped
            rate = done / elapsed if elapsed > 0 else 0.0
            eta = (len(tiles) - i - 1) / rate if rate > 0 else float("inf")
            print(
                f"[run_srtm] {i + 1}/{len(tiles)} "
                f"tile={tile.cache_key} ({binary.rows}x{binary.cols}) "
                f"{rate:.1f} tiles/s eta={eta:.0f}s "
                f"(skipped={skipped}, failed={failed})"
            )

    elapsed = time.monotonic() - started
    print(
        f"[run_srtm] complete: "
        f"{len(tiles) - skipped - failed} baked, "
        f"{skipped} skipped, {failed} failed, "
        f"elapsed={elapsed:.1f}s"
    )
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
