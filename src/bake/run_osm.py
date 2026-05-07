"""CLI for OSM-Bake. Usage:
    python -m bake.run_osm --state he --source-version geofabrik-2026-05
"""
from __future__ import annotations

import argparse
import datetime
import subprocess
import sys
from pathlib import Path

from bake.sources.osm_pbf import parse_pbf
from bake.tags_filter import build_filter_command

R2_BUCKET = "mapbiker-tiles"


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Bake OSM data to per-tile JSON for R2 hosting (wire-format-v1).")
    parser.add_argument("--state", required=True, choices=["he", "by", "nw"],
                        help="DE state to bake")
    parser.add_argument("--pbf",
                        help="Path to Geofabrik PBF (default: data/{state}-latest.osm.pbf)")
    parser.add_argument("--source-version",
                        default=datetime.date.today().isoformat(),
                        help="Tracked in each tile as source_dataset_version")
    parser.add_argument("--out", default="data/tiled_osm",
                        help="Output directory")
    parser.add_argument("--no-upload", action="store_true",
                        help="Skip the R2 upload step")
    parser.add_argument("--no-filter", action="store_true",
                        help="Skip osmium tags-filter pre-pass (for already-filtered PBFs)")
    args = parser.parse_args()

    state_full = f"de_{args.state}"
    pbf_in = Path(args.pbf or f"data/{args.state}-latest.osm.pbf")
    if not pbf_in.exists():
        print(f"ERROR: PBF not found at {pbf_in}", file=sys.stderr)
        sys.exit(1)

    # Step 1: tags-filter pre-pass (osmium CLI)
    if not args.no_filter:
        filtered = pbf_in.with_suffix(".filtered.osm.pbf")
        cmd = build_filter_command(str(pbf_in), str(filtered))
        print(f">>> {' '.join(cmd)}")
        try:
            subprocess.check_call(cmd)
            pbf_in = filtered
        except FileNotFoundError:
            print("WARN: osmium CLI not found on PATH; skipping tags-filter "
                  "pre-pass (use --no-filter to silence this warning)",
                  file=sys.stderr)
        except subprocess.CalledProcessError as e:
            print(f"ERROR: osmium tags-filter failed: {e}", file=sys.stderr)
            sys.exit(1)

    # Step 2: parse + emit tiles
    out_dir = Path(args.out) / state_full
    out_dir.mkdir(parents=True, exist_ok=True)

    tile_count = 0
    for tile in parse_pbf(pbf_in, state=state_full,
                          source_version=args.source_version):
        tile_path = out_dir / f"z{tile.tile.z}/{tile.tile.x}/{tile.tile.y}.json"
        tile_path.parent.mkdir(parents=True, exist_ok=True)
        tile_path.write_text(tile.model_dump_json(), encoding="utf-8")
        tile_count += 1

    print(f"Wrote {tile_count} tiles to {out_dir}")

    # Step 3: upload (unless --no-upload)
    # upload_tile signature: upload_tile(*, local_path, bucket, remote_key,
    #                                    content_type, content_encoding)
    # OSM tiles are plain JSON (not gzip), so pass content_encoding=None.
    if not args.no_upload:
        from bake.upload import upload_tile  # imported here to avoid early failures
        for tile_path in out_dir.rglob("*.json"):
            rel = tile_path.relative_to(Path(args.out))
            remote_key = f"v1/osm/{rel.as_posix()}"
            upload_tile(
                local_path=tile_path,
                bucket=R2_BUCKET,
                remote_key=remote_key,
                content_encoding=None,
            )
        print(f"Uploaded {tile_count} tiles to R2")


if __name__ == "__main__":
    main()
