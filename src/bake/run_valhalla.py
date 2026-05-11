"""CLI entrypoint for the Valhalla routing-tile bake.

Runs the full pipeline for a region: Docker-driven tile build via
`valhalla_build_tiles` + package as `.tar.gz` + manifest + optional
R2 upload. iOS consumes the manifest via `ValhallaTileStore`.

# Usage

End-to-end for DACH cycling tiles, bundle version 1:

    python -m bake.run_valhalla --region dach --bundle-version 1

This will:
  1. mkdir data/raw/valhalla/dach/
  2. docker run ghcr.io/valhalla/valhalla:run-latest with the three
     Geofabrik PBF URLs → downloads + builds tiles into the mounted dir
  3. tar+gzip the result into data/tiled/v1/valhalla/dach/tiles-v1.tar.gz
  4. write data/tiled/v1/valhalla/dach/manifest.json
  5. upload both to R2 at v1/valhalla/dach/

Flags:
  --no-build       skip the docker build step (assume tiles already
                   present at data/raw/valhalla/<region>/)
  --no-package     skip the tar+gzip step (assume bundle exists)
  --no-upload      skip the R2 upload (local files only)
  --docker-image   override the Valhalla container tag
  --cores N        worker threads inside the container (default 4)

# Wall time

DACH cycling end-to-end: 30–60 min on an M-series Mac with fast
disk + 10+ GB free RAM; 3+ hours on a typical Windows laptop. The
docker step is the long pole; package + upload combined take
~5–15 min depending on uplink.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from bake.upload import upload_valhalla_bundle, upload_valhalla_manifest
from bake.valhalla_tiles import (
    DEFAULT_VALHALLA_IMAGE,
    GEOFABRIK_PBF_URLS,
    BundleManifest,
    build_tiles_via_docker,
    package_bundle,
    write_manifest,
)

R2_BUCKET = "mapbiker-tiles"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="bake.run_valhalla",
        description="Bake Valhalla routing-tile bundles for the mapbiker iOS app.",
    )
    parser.add_argument(
        "--region", required=True, choices=sorted(GEOFABRIK_PBF_URLS),
        help="Region key (currently only 'dach').",
    )
    parser.add_argument(
        "--bundle-version", type=int, required=True,
        help="Integer bundle version, embedded in the on-R2 filename "
             "and used by iOS to detect updates. Bump for every fresh "
             "bake.",
    )
    parser.add_argument(
        "--work-dir", type=Path, default=None,
        help="Host dir mounted as /custom_files in the container. "
             "Defaults to data/raw/valhalla/<region>.",
    )
    parser.add_argument(
        "--out-dir", type=Path, default=None,
        help="Output dir for the .tar.gz + manifest.json. "
             "Defaults to data/tiled/v1/valhalla/<region>.",
    )
    parser.add_argument(
        "--docker-image", default=DEFAULT_VALHALLA_IMAGE,
        help=f"Valhalla container tag (default {DEFAULT_VALHALLA_IMAGE}).",
    )
    parser.add_argument(
        "--cores", type=int, default=4,
        help="Server threads inside the container.",
    )
    parser.add_argument(
        "--no-build", action="store_true",
        help="Skip the docker build step; assume tiles already in "
             "the work-dir.",
    )
    parser.add_argument(
        "--no-package", action="store_true",
        help="Skip tar+gzip; assume bundle already exists in out-dir.",
    )
    parser.add_argument(
        "--no-upload", action="store_true",
        help="Skip R2 upload — local files only.",
    )
    args = parser.parse_args(argv)

    region = args.region
    work_dir = args.work_dir or Path("data") / "raw" / "valhalla" / region
    out_dir = args.out_dir or Path("data") / "tiled" / "v1" / "valhalla" / region
    bundle_path = out_dir / f"tiles-v{args.bundle_version}.tar.gz"
    manifest_path = out_dir / "manifest.json"

    print(f"[run_valhalla] region={region} bundle_version={args.bundle_version}")
    print(f"[run_valhalla] work_dir={work_dir} out_dir={out_dir}")

    if not args.no_build:
        print(f"[run_valhalla] STEP 1/3 docker build (this is the long pole)")
        build_tiles_via_docker(
            pbf_urls=GEOFABRIK_PBF_URLS[region],
            work_dir=work_dir,
            image=args.docker_image,
            cores=args.cores,
        )
    else:
        print(f"[run_valhalla] STEP 1/3 SKIPPED (--no-build)")

    if not args.no_package:
        print(f"[run_valhalla] STEP 2/3 tar+gzip + sha256")
        tiles_dir = work_dir / "valhalla_tiles"
        manifest = package_bundle(
            tiles_dir=tiles_dir,
            out_path=bundle_path,
            region=region,
            bundle_version=args.bundle_version,
        )
        write_manifest(manifest=manifest, path=manifest_path)
        print(f"[run_valhalla] bundle={bundle_path} "
              f"compressed={manifest.compressed_bytes / 1e9:.2f} GB "
              f"sha256={manifest.sha256[:16]}…")
    else:
        print(f"[run_valhalla] STEP 2/3 SKIPPED (--no-package)")

    if not args.no_upload:
        print(f"[run_valhalla] STEP 3/3 upload bundle + manifest to R2")
        upload_valhalla_bundle(
            local_path=bundle_path, bucket=R2_BUCKET,
            region=region, bundle_version=args.bundle_version,
        )
        upload_valhalla_manifest(
            local_path=manifest_path, bucket=R2_BUCKET, region=region,
        )
        print(f"[run_valhalla] uploads complete: "
              f"v1/valhalla/{region}/tiles-v{args.bundle_version}.tar.gz + "
              f"manifest.json")
    else:
        print(f"[run_valhalla] STEP 3/3 SKIPPED (--no-upload)")

    print(f"[run_valhalla] done.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
