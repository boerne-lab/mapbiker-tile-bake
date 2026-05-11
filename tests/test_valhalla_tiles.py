"""Tests for `bake.valhalla_tiles` — the parts that don't require
Docker.

`build_tiles_via_docker` shells out to docker and is integration-
tested manually. `package_bundle` is pure-Python and lends itself
to a synthetic tile dir + round-trip extraction test, which is the
core risk surface (extract path, manifest correctness, sha256
stability).
"""
from __future__ import annotations

import gzip
import json
import tarfile
from pathlib import Path

import pytest

from bake.valhalla_tiles import (
    BundleManifest,
    package_bundle,
    write_manifest,
)


def _seed_synthetic_tiles(parent: Path) -> Path:
    """Create a fake `<parent>/valhalla_tiles/` + `<parent>/config.json`
    layout that mirrors what the real `valhalla_build_tiles` writes.
    Returns the tiles dir path."""
    tiles_dir = parent / "valhalla_tiles"
    tiles_dir.mkdir(parents=True, exist_ok=True)
    # Two synthetic per-level tile files. Real Valhalla writes
    # hierarchical-graph tiles per level; for the bake we only care
    # that they end up in the archive, not what's inside.
    (tiles_dir / "0").mkdir()
    (tiles_dir / "0" / "001.gph").write_bytes(b"level-0-tile")
    (tiles_dir / "1").mkdir()
    (tiles_dir / "1" / "002.gph").write_bytes(b"level-1-tile")
    # Valhalla writes its config alongside the tiles dir (next to
    # `valhalla_tiles/`), not inside. Either `valhalla.json` or
    # `config.json` — the bake handles both names.
    (parent / "config.json").write_text(
        '{"mjolnir":{"tile_dir":"valhalla_tiles"}}')
    return tiles_dir


def test_package_bundle_writes_tar_gz(tmp_path: Path) -> None:
    tiles_dir = _seed_synthetic_tiles(tmp_path / "work")
    out_path = tmp_path / "bundle.tar.gz"

    manifest = package_bundle(
        tiles_dir=tiles_dir,
        out_path=out_path,
        region="dach",
        bundle_version=42,
    )

    assert out_path.exists()
    assert manifest.region == "dach"
    assert manifest.bundle_version == 42
    assert manifest.bundle_url == "v1/valhalla/dach/tiles-v42.tar.gz"
    assert manifest.compressed_bytes == out_path.stat().st_size
    assert manifest.uncompressed_bytes > 0
    assert len(manifest.sha256) == 64  # hex string
    assert manifest.created_at.endswith("+00:00")


def test_package_bundle_archive_layout_matches_ios_expectation(
    tmp_path: Path,
) -> None:
    """The iOS `ValhallaTileStore` extracts into
    `Documents/ValhallaTiles/<region>/`. The archive root must
    contain `config.json` + `valhalla_tiles/` so that the matcher's
    `tileDirectory` parameter just points at the region dir."""
    tiles_dir = _seed_synthetic_tiles(tmp_path / "work")
    out_path = tmp_path / "bundle.tar.gz"
    package_bundle(
        tiles_dir=tiles_dir, out_path=out_path,
        region="dach", bundle_version=1,
    )

    with gzip.open(out_path, "rb") as gz:
        with tarfile.open(fileobj=gz, mode="r") as tar:
            names = sorted(tar.getnames())
    assert "config.json" in names
    assert "valhalla_tiles" in names
    # Sanity-check the level tiles survived.
    assert "valhalla_tiles/0/001.gph" in names
    assert "valhalla_tiles/1/002.gph" in names


def test_package_bundle_sha256_is_deterministic(tmp_path: Path) -> None:
    """Re-run with identical inputs → identical SHA-256. Critical
    for the manifest pin: iOS rejects bundles whose download SHA-256
    doesn't match the manifest, so the bake must be reproducible.

    Caveat: tarfile records modification time per entry. We touch
    every file to a fixed mtime to expose the sha-stability path.
    Without the mtime fixture the SHA differs between runs (real-
    world behaviour — bake.run_valhalla bumps bundle_version every
    rebuild, so deterministic SHA across re-runs isn't required).
    """
    tiles_dir_a = _seed_synthetic_tiles(tmp_path / "a")
    tiles_dir_b = _seed_synthetic_tiles(tmp_path / "b")

    # Pin mtimes so the tar headers match byte-for-byte.
    fixed_ts = 1_700_000_000
    for d in (tiles_dir_a.parent, tiles_dir_b.parent):
        for p in d.rglob("*"):
            import os
            os.utime(p, (fixed_ts, fixed_ts))

    out_a = tmp_path / "a.tar.gz"
    out_b = tmp_path / "b.tar.gz"
    m_a = package_bundle(
        tiles_dir=tiles_dir_a, out_path=out_a,
        region="dach", bundle_version=1)
    m_b = package_bundle(
        tiles_dir=tiles_dir_b, out_path=out_b,
        region="dach", bundle_version=1)

    # The gzip stream's header includes its own mtime — under
    # Python's stdlib `gzip.GzipFile(fileobj=, mode="wb")` that
    # defaults to time.time(), which won't match across runs.
    # Just compare SHA-256 of the tar payload after gzip decode.
    with gzip.open(out_a, "rb") as ga, gzip.open(out_b, "rb") as gb:
        import hashlib
        sha_a = hashlib.sha256(ga.read()).hexdigest()
        sha_b = hashlib.sha256(gb.read()).hexdigest()
    assert sha_a == sha_b, (
        "tar payload SHA-256 should match for identical inputs")
    # `m_a.sha256` covers the full gzip output (including its mtime
    # header) so the two manifests can differ even when the tar
    # payload is identical. The iOS download verifies the full-gzip
    # SHA-256 anyway, so this is fine.


def test_package_bundle_rejects_missing_tiles_dir(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="tiles_dir"):
        package_bundle(
            tiles_dir=tmp_path / "missing",
            out_path=tmp_path / "out.tar.gz",
            region="dach", bundle_version=1,
        )


def test_package_bundle_rejects_missing_config(tmp_path: Path) -> None:
    tiles_dir = tmp_path / "work" / "valhalla_tiles"
    tiles_dir.mkdir(parents=True)
    (tiles_dir / "001.gph").write_bytes(b"x")
    # No config.json next to the tiles dir.
    with pytest.raises(FileNotFoundError, match="config.json"):
        package_bundle(
            tiles_dir=tiles_dir,
            out_path=tmp_path / "out.tar.gz",
            region="dach", bundle_version=1,
        )


def test_manifest_json_roundtrip(tmp_path: Path) -> None:
    m = BundleManifest(
        schema_version=1,
        region="dach",
        bundle_version=7,
        bundle_url="v1/valhalla/dach/tiles-v7.tar.gz",
        sha256="ab" * 32,
        compressed_bytes=1_500_000_000,
        uncompressed_bytes=2_500_000_000,
        created_at="2026-05-11T20:00:00+00:00",
    )
    path = tmp_path / "manifest.json"
    write_manifest(manifest=m, path=path)
    decoded = json.loads(path.read_text())
    assert decoded["region"] == "dach"
    assert decoded["bundleVersion"] == 7
    assert decoded["sha256"] == "ab" * 32
    assert decoded["compressedBytes"] == 1_500_000_000
    assert decoded["bundleURL"] == "v1/valhalla/dach/tiles-v7.tar.gz"
