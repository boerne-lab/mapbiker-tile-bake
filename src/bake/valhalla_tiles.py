"""Valhalla tile-bundle bake for the offline map-matcher.

Builds a routing-tile bundle from OSM PBF extracts using
`valhalla_build_tiles` via Docker, packages the output, and uploads
to R2 so iOS clients can download via `ValhallaTileStore`.

# Why Docker

`valhalla_build_tiles` is a C++ binary. Compiling it from source
requires a full Valhalla build (~20 min on a beefy machine, plus
boost / protobuf / lz4 / et al.). Docker side-steps the whole
toolchain — the upstream `ghcr.io/valhalla/valhalla:run-latest`
image ships a known-good binary.

# Inputs

OSM PBF extracts from Geofabrik (free, no auth, redistributable
under ODbL). For DACH the relevant downloads are:

- https://download.geofabrik.de/europe/germany-latest.osm.pbf (~4 GB)
- https://download.geofabrik.de/europe/austria-latest.osm.pbf (~700 MB)
- https://download.geofabrik.de/europe/switzerland-latest.osm.pbf (~600 MB)

# Outputs (per region)

Local: `data/raw/valhalla/<region>/tiles/` (the raw tile output —
`config.json` + per-level `<id>.gph` files). Each tile build is a
fresh wipe of this directory; resuming a partial build isn't
useful because Valhalla writes most of its output near the end of
the build.

Bundle: `data/tiled/v1/valhalla/<region>/tiles-v<N>.tar.gz` —
single gzipped tar of the tiles dir. Sized ~1.5 GB for DACH-
cycling. SHA-256 computed during pack so the iOS client can
verify after download.

Manifest: `data/tiled/v1/valhalla/<region>/manifest.json` — small
JSON describing the latest bundle's URL + SHA-256 + version. iOS
fetches the manifest first to decide whether the local install is
current.

R2 layout:
    v1/valhalla/<region>/manifest.json
    v1/valhalla/<region>/tiles-v<N>.tar.gz

# Cycling profile

Plenty of OSM ways are tagged `bicycle=no` or `highway=motorway`
that the bicycle cost model already rejects at routing time, but
keeping them in the tile graph wastes ~30 % space. Future
optimisation: pre-filter the PBF with osmium tags-filter before
the Valhalla build to drop unreachable-by-bike ways. Out of scope
for v1 — the un-pruned ~2.5 GB bundle is acceptable.
"""
from __future__ import annotations

import gzip
import hashlib
import json
import shutil
import subprocess
import tarfile
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

# DACH OSM PBF source URLs (Geofabrik, ODbL). The container reads
# these via its `tile_urls` env var. Mirrors are stable enough that
# pinning a checksum here is overkill — the manifest covers
# downstream verification.
GEOFABRIK_PBF_URLS: dict[str, tuple[str, ...]] = {
    "dach": (
        "https://download.geofabrik.de/europe/germany-latest.osm.pbf",
        "https://download.geofabrik.de/europe/austria-latest.osm.pbf",
        "https://download.geofabrik.de/europe/switzerland-latest.osm.pbf",
    ),
}

# Default Valhalla container. `run-latest` is the curated stable
# tag with prebuilt binaries; the `latest` tag is the upstream HEAD
# which sometimes ships breaking config changes mid-week.
DEFAULT_VALHALLA_IMAGE = "ghcr.io/valhalla/valhalla:run-latest"


@dataclass(frozen=True)
class BundleManifest:
    """Describes one packaged tile bundle. Serialised as JSON for
    the iOS client to fetch via `ValhallaTileStore`."""
    schema_version: int
    region: str
    bundle_version: int
    bundle_url: str          # R2-relative path or full HTTPS URL
    sha256: str
    compressed_bytes: int
    uncompressed_bytes: int
    created_at: str          # ISO-8601 UTC

    def to_json(self) -> str:
        return json.dumps({
            "schemaVersion": self.schema_version,
            "region": self.region,
            "bundleVersion": self.bundle_version,
            "bundleURL": self.bundle_url,
            "sha256": self.sha256,
            "compressedBytes": self.compressed_bytes,
            "uncompressedBytes": self.uncompressed_bytes,
            "createdAt": self.created_at,
        }, indent=2)


def download_pbf(*, url: str, dest_path: Path) -> Path:
    """Download a single OSM PBF from `url` to `dest_path`.
    Idempotent: skips when the destination file already exists with
    non-zero size (re-runs are cheap, no checksum check — we trust
    Geofabrik). Streamed download so we don't load multi-GB PBFs
    into memory."""
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    if dest_path.exists() and dest_path.stat().st_size > 0:
        print(f"[valhalla_tiles] cached PBF {dest_path.name}")
        return dest_path
    print(f"[valhalla_tiles] downloading {url} -> {dest_path}")
    tmp = dest_path.with_suffix(dest_path.suffix + ".part")
    with urllib.request.urlopen(url) as resp:
        with open(tmp, "wb") as f:
            shutil.copyfileobj(resp, f, length=1024 * 1024)
    tmp.replace(dest_path)
    return dest_path


def generate_valhalla_config(
    *,
    work_dir: Path,
    tile_dir: Path,
    config_path: Path | None = None,
) -> Path:
    """Generate a valhalla.json config by invoking the `valhalla_build_config`
    CLI. Returns the path of the written config.

    `valhalla_build_config` ships with the Debian/Homebrew valhalla
    packages (and is also inside the container). Output is a JSON
    structure with sensible defaults for routing — we override only
    `mjolnir.tile_dir` to point at our per-region tiles directory.
    """
    config_path = config_path or (work_dir / "valhalla.json")
    work_dir.mkdir(parents=True, exist_ok=True)
    proc = subprocess.run(
        [
            "valhalla_build_config",
            "--mjolnir-tile-dir", str(tile_dir),
            "--mjolnir-timezone", str(tile_dir / "timezones.sqlite"),
            "--mjolnir-admin", str(tile_dir / "admins.sqlite"),
        ],
        capture_output=True, text=True, check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError(
            f"valhalla_build_config failed ({proc.returncode}): " +
            proc.stderr[:400])
    config_path.write_text(proc.stdout)
    return config_path


def build_tiles_native(
    *,
    pbf_urls: Iterable[str],
    work_dir: Path,
    config_path: Path | None = None,
) -> Path:
    """Build Valhalla tiles using the native `valhalla_build_tiles`
    binary (from Homebrew on macOS, or `valhalla-bin` apt package on
    Linux / WSL2). No Docker needed.

    Layout in `work_dir` after success:
      - `<region>-pbfs/` containing the downloaded `.osm.pbf` files
      - `valhalla_tiles/` containing per-level `.gph` files
      - `valhalla.json` Valhalla routing config
    """
    work_dir.mkdir(parents=True, exist_ok=True)
    pbf_dir = work_dir / "pbfs"
    pbf_dir.mkdir(exist_ok=True)
    tiles_dir = work_dir / "valhalla_tiles"
    tiles_dir.mkdir(exist_ok=True)

    pbf_paths: list[Path] = []
    for url in pbf_urls:
        filename = url.rsplit("/", 1)[-1]
        path = download_pbf(url=url, dest_path=pbf_dir / filename)
        pbf_paths.append(path)

    resolved_config = generate_valhalla_config(
        work_dir=work_dir,
        tile_dir=tiles_dir,
        config_path=config_path,
    )

    print(f"[valhalla_tiles] valhalla_build_tiles begin "
          f"(work_dir={work_dir}, {len(pbf_paths)} PBFs)")
    # `valhalla_build_tiles -c <config> <pbf1> <pbf2> ...` is the
    # full build pipeline (initial-graph → hierarchy → transitions →
    # restrictions → admins). Single-pass; no resume support.
    args = ["valhalla_build_tiles", "-c", str(resolved_config)]
    args.extend(str(p) for p in pbf_paths)
    proc = subprocess.run(args, check=False)
    if proc.returncode != 0:
        raise RuntimeError(
            f"valhalla_build_tiles exited with code {proc.returncode}")

    if not any(tiles_dir.iterdir()):
        raise RuntimeError(
            f"valhalla_build_tiles produced no output in {tiles_dir}")
    # Move the config to the canonical name `config.json` expected
    # by the iOS-side packager + matcher.
    canonical = work_dir / "config.json"
    if resolved_config != canonical:
        shutil.copyfile(resolved_config, canonical)
    return tiles_dir


def build_tiles_via_docker(
    *,
    pbf_urls: Iterable[str],
    work_dir: Path,
    image: str = DEFAULT_VALHALLA_IMAGE,
    cores: int = 4,
    extra_run_args: list[str] | None = None,
) -> Path:
    """Run `valhalla_build_tiles` inside a Docker container.

    `work_dir` is the host-side directory mounted into the
    container at `/custom_files`. The container downloads the
    PBF URLs into this dir on first run, generates a config, then
    runs the build. On success the directory contains:

      - `config.json` (final Valhalla routing config)
      - `valhalla_tiles/` (the per-level `.gph` files)
      - The original `.osm.pbf` downloads (kept for re-runs)

    Returns the path to the tiles directory.

    Requires Docker (Desktop or daemon) installed and reachable on
    PATH. Build wall-time for DACH cycling: 30–60 min on an M-series
    Mac, several hours on a low-power Windows box.
    """
    work_dir.mkdir(parents=True, exist_ok=True)
    tile_urls = ",".join(pbf_urls)
    args: list[str] = [
        "docker", "run",
        "--rm",
        "-e", f"tile_urls={tile_urls}",
        "-e", f"build_tar=False",
        "-e", f"force_rebuild=False",
        "-e", f"force_rebuild_elevation=False",
        "-e", f"use_tiles_ignore_pbf=False",
        "-e", f"server_threads={cores}",
        "-v", f"{work_dir.resolve()}:/custom_files",
        image,
    ]
    if extra_run_args:
        args.extend(extra_run_args)

    print(f"[valhalla_tiles] docker run begin "
          f"(work_dir={work_dir}, image={image})")
    proc = subprocess.run(args, check=False)
    if proc.returncode != 0:
        raise RuntimeError(
            f"valhalla docker exited with code {proc.returncode}")

    tiles_dir = work_dir / "valhalla_tiles"
    if not tiles_dir.is_dir():
        raise RuntimeError(
            f"expected tile output at {tiles_dir}, not found")
    config = work_dir / "valhalla.json"
    if not config.exists():
        config = work_dir / "config.json"
        if not config.exists():
            raise RuntimeError(
                f"expected Valhalla config in {work_dir}, found none")
    return tiles_dir


def package_bundle(
    *,
    tiles_dir: Path,
    out_path: Path,
    region: str,
    bundle_version: int,
) -> BundleManifest:
    """Tar+gzip the tiles directory, compute SHA-256, return a
    `BundleManifest`. Idempotent: re-runs overwrite `out_path`.

    The archive layout follows the iOS `ValhallaTileStore` expected
    layout: extracting into `Documents/ValhallaTiles/<region>/`
    yields the same structure the matcher's `tileDirectory`
    parameter expects. Concretely, we tar with the tiles dir at the
    root of the archive (NOT inside an extra layer).
    """
    if not tiles_dir.is_dir():
        raise FileNotFoundError(f"tiles_dir not a directory: {tiles_dir}")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    # Include the parent dir's config.json alongside the tiles when
    # we tar. iOS expects `config.json` at the root of the extracted
    # bundle. Find the config from the parent (Valhalla writes it
    # next to `valhalla_tiles/`).
    config_src = tiles_dir.parent / "valhalla.json"
    if not config_src.exists():
        config_src = tiles_dir.parent / "config.json"
        if not config_src.exists():
            raise FileNotFoundError(
                f"config.json/valhalla.json not next to {tiles_dir}")

    sha = hashlib.sha256()
    uncompressed_bytes = 0
    # Stream the tar through gzip and sha256 in one pass.
    with open(out_path, "wb") as raw_out:
        sha_writer = _Sha256Writer(raw_out, sha)
        with gzip.GzipFile(
                fileobj=sha_writer, mode="wb", compresslevel=6) as gz:
            with tarfile.open(fileobj=gz, mode="w") as tar:
                tar.add(config_src, arcname="config.json")
                tar.add(tiles_dir, arcname="valhalla_tiles")
    # File is closed + flushed at this point; stat() reads the
    # final on-disk size.
    compressed_bytes = out_path.stat().st_size
    # Walk the tile dir to record uncompressed size (informational).
    for p in tiles_dir.rglob("*"):
        if p.is_file():
            uncompressed_bytes += p.stat().st_size
    uncompressed_bytes += config_src.stat().st_size

    return BundleManifest(
        schema_version=1,
        region=region,
        bundle_version=bundle_version,
        bundle_url=f"v1/valhalla/{region}/tiles-v{bundle_version}.tar.gz",
        sha256=sha.hexdigest(),
        compressed_bytes=compressed_bytes,
        uncompressed_bytes=uncompressed_bytes,
        created_at=datetime.now(timezone.utc)
            .replace(microsecond=0)
            .isoformat(),
    )


class _Sha256Writer:
    """File-like wrapper that mirrors writes into a sha256
    accumulator. Used by `package_bundle` to compute the checksum
    of the gzip output without a second pass over the file."""
    def __init__(self, inner, sha):
        self._inner = inner
        self._sha = sha

    def write(self, b: bytes) -> int:
        self._sha.update(b)
        return self._inner.write(b)

    def flush(self) -> None:
        self._inner.flush()


def write_manifest(*, manifest: BundleManifest, path: Path) -> None:
    """Write the manifest JSON next to the bundle archive. iOS
    fetches the manifest at app launch, compares its
    `bundleVersion` against the local install, and decides whether
    to trigger a re-download."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(manifest.to_json())
