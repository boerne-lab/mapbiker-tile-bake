"""Tests for `bake.srtm30` — AWS Terrain Tiles → DGM2 v1 per-tile bake.

Tests run offline: synthetic Terrarium PNGs are written into a tmp
cache directory, then `bake_tile_from_srtm` reads from cache (no HTTP)
and bakes. The real Terrarium endpoint is exercised once in
`test_smoke_real_aws_one_tile` — marked manual via env-var so CI / dev
runs don't depend on network.
"""
from __future__ import annotations

import io
import os
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from bake.dgm import read_binary
from bake.dgm10 import TileCoord
from bake.srtm30 import (
    DEFAULT_DOWNSAMPLE_FACTOR,
    _block_mean_downsample,
    bake_tile_from_srtm,
    fetch_terrarium_tile,
)


# -----------------------------------------------------------------------------
# Test fixture: synthetic Terrarium PNG with a known elevation pattern
# -----------------------------------------------------------------------------

def _encode_terrarium(elev_m: np.ndarray) -> bytes:
    """Encode a (256, 256) elevation array into a Terrarium-formatted
    PNG. Inverse of `srtm30.fetch_terrarium_tile`'s decode.
    """
    assert elev_m.shape == (256, 256)
    raw = (elev_m + 32768.0)  # shift to [0, 65535] for ±32768 range
    # Terrarium: height = R*256 + G + B/256 - 32768
    # → raw = R*256 + G + B/256
    # Extract integer + fractional parts.
    R = np.floor(raw / 256).astype(np.int32)
    G_part = raw - R * 256
    G = np.floor(G_part).astype(np.int32)
    B = np.floor((G_part - G) * 256).astype(np.int32)
    R = np.clip(R, 0, 255)
    G = np.clip(G, 0, 255)
    B = np.clip(B, 0, 255)
    rgb = np.stack([R, G, B], axis=2).astype(np.uint8)
    img = Image.fromarray(rgb, mode="RGB")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _seed_cache(*, cache_root: Path, tile: TileCoord, elev_m: np.ndarray) -> None:
    """Write a synthetic Terrarium PNG to where the fetcher's cache
    expects it. Lets the bake run offline."""
    p = cache_root / f"z{tile.z}" / str(tile.x) / f"{tile.y}.png"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(_encode_terrarium(elev_m))


# -----------------------------------------------------------------------------
# fetch_terrarium_tile (cache hit)
# -----------------------------------------------------------------------------

def test_fetch_decodes_uniform_elevation(tmp_path: Path) -> None:
    tile = TileCoord(z=15, x=17167, y=11095)
    flat = np.full((256, 256), 150.0, dtype=np.float32)
    _seed_cache(cache_root=tmp_path, tile=tile, elev_m=flat)

    result = fetch_terrarium_tile(tile=tile, cache_root=tmp_path)
    # Terrarium has ~1 cm precision (B/256 step). Loose tolerance.
    assert np.allclose(result.elev_m, 150.0, atol=0.01)
    assert result.elev_m.shape == (256, 256)


def test_fetch_decodes_gradient(tmp_path: Path) -> None:
    """A linear south-to-north elevation ramp. Pixel (0, 0) is NORTH —
    encode high, pixel (255, 0) SOUTH — encode low."""
    tile = TileCoord(z=15, x=17167, y=11095)
    rows = np.linspace(200.0, 100.0, 256, dtype=np.float32)
    grad = np.broadcast_to(rows[:, None], (256, 256)).copy()
    _seed_cache(cache_root=tmp_path, tile=tile, elev_m=grad)

    result = fetch_terrarium_tile(tile=tile, cache_root=tmp_path)
    # Pixel (0, 0) = north = 200 m, pixel (255, 0) = south = 100 m.
    assert result.elev_m[0, 0] == pytest.approx(200.0, abs=0.05)
    assert result.elev_m[255, 0] == pytest.approx(100.0, abs=0.05)


# -----------------------------------------------------------------------------
# _block_mean_downsample
# -----------------------------------------------------------------------------

def test_block_mean_uniform_input_preserves_value() -> None:
    arr = np.full((256, 256), 42.0, dtype=np.float32)
    out = _block_mean_downsample(arr, 4)
    assert out.shape == (64, 64)
    assert np.all(out == 42.0)


def test_block_mean_averages_distinct_quadrants() -> None:
    """2×2 input where each cell holds a distinct value. Downsample
    factor 2 → 1×1, value = mean of the four."""
    arr = np.array([[10.0, 20.0], [30.0, 40.0]], dtype=np.float32)
    out = _block_mean_downsample(arr, 2)
    assert out.shape == (1, 1)
    assert out[0, 0] == pytest.approx(25.0)


def test_block_mean_rejects_indivisible_factor() -> None:
    arr = np.zeros((100, 100), dtype=np.float32)
    with pytest.raises(ValueError, match="not evenly divisible"):
        _block_mean_downsample(arr, 7)


# -----------------------------------------------------------------------------
# bake_tile_from_srtm (end-to-end via cache)
# -----------------------------------------------------------------------------

def test_bake_writes_dgm2_v1_binary(tmp_path: Path) -> None:
    tile = TileCoord(z=15, x=17167, y=11095)
    elev = np.full((256, 256), 100.0, dtype=np.float32)
    cache_root = tmp_path / "cache"
    _seed_cache(cache_root=cache_root, tile=tile, elev_m=elev)

    out_path = tmp_path / "out.bin"
    binary = bake_tile_from_srtm(
        tile=tile, out_path=out_path, cache_root=cache_root)

    assert out_path.exists()
    assert out_path.read_bytes()[:4] == b"DGM2"

    # Default downsample factor 4 → 64×64.
    assert binary.rows == 256 // DEFAULT_DOWNSAMPLE_FACTOR
    assert binary.cols == 256 // DEFAULT_DOWNSAMPLE_FACTOR


def test_bake_roundtrip_preserves_constant_elevation(tmp_path: Path) -> None:
    tile = TileCoord(z=15, x=17167, y=11095)
    elev = np.full((256, 256), 250.0, dtype=np.float32)
    cache_root = tmp_path / "cache"
    _seed_cache(cache_root=cache_root, tile=tile, elev_m=elev)

    out_path = tmp_path / "out.bin"
    bake_tile_from_srtm(
        tile=tile, out_path=out_path, cache_root=cache_root)
    out_again = read_binary(out_path)

    min_lat, min_lon, max_lat, max_lon = tile.bounds()
    center_lat = (min_lat + max_lat) / 2
    center_lon = (min_lon + max_lon) / 2
    sampled = out_again.sample_bilinear(center_lat, center_lon)
    assert sampled is not None
    # scale=0.1 Int16 quantisation → ±0.05 m; allow 0.5 m headroom
    # for terrarium 1 cm precision noise.
    assert abs(sampled - 250.0) < 0.5


def test_bake_bbox_matches_tile_bounds(tmp_path: Path) -> None:
    """The output binary's bbox must equal the tile's web-mercator
    bounds exactly. iOS bilinear-clamp depends on this."""
    tile = TileCoord(z=15, x=17167, y=11095)
    elev = np.zeros((256, 256), dtype=np.float32)
    cache_root = tmp_path / "cache"
    _seed_cache(cache_root=cache_root, tile=tile, elev_m=elev)

    binary = bake_tile_from_srtm(
        tile=tile, out_path=tmp_path / "x.bin", cache_root=cache_root)
    expected_min_lat, expected_min_lon, expected_max_lat, expected_max_lon = tile.bounds()
    assert binary.min_lat == pytest.approx(expected_min_lat)
    assert binary.max_lat == pytest.approx(expected_max_lat)
    assert binary.min_lon == pytest.approx(expected_min_lon)
    assert binary.max_lon == pytest.approx(expected_max_lon)


def test_bake_full_resolution_keeps_256_grid(tmp_path: Path) -> None:
    """downsample_factor=1 keeps the native Terrarium 256×256 grid."""
    tile = TileCoord(z=15, x=17167, y=11095)
    elev = np.zeros((256, 256), dtype=np.float32)
    cache_root = tmp_path / "cache"
    _seed_cache(cache_root=cache_root, tile=tile, elev_m=elev)

    binary = bake_tile_from_srtm(
        tile=tile, out_path=tmp_path / "x.bin",
        cache_root=cache_root, downsample_factor=1)
    assert binary.rows == 256
    assert binary.cols == 256


# -----------------------------------------------------------------------------
# Real AWS smoke-test — opt-in via env-var
# -----------------------------------------------------------------------------

@pytest.mark.skipif(
    os.environ.get("BAKE_TEST_NETWORK") != "1",
    reason="set BAKE_TEST_NETWORK=1 to exercise the real AWS endpoint")
def test_smoke_real_aws_one_tile(tmp_path: Path) -> None:
    """Fetch one real Terrarium tile from AWS, bake it, sample at the
    tile centroid. Sanity-pins that the public S3 URL + decode
    formula still work end-to-end. Sample elevation should be a
    plausible Frankfurt-Westend value."""
    tile = TileCoord(z=15, x=17167, y=11095)
    binary = bake_tile_from_srtm(
        tile=tile,
        out_path=tmp_path / "smoke.bin",
        cache_root=tmp_path / "cache",
    )
    min_lat, min_lon, max_lat, max_lon = tile.bounds()
    y = binary.sample_bilinear(
        (min_lat + max_lat) / 2, (min_lon + max_lon) / 2)
    assert y is not None
    # Frankfurt-Westend sits at ~95–110 m NHN.
    assert 80.0 < y < 150.0, f"unexpected elevation {y} m"
