"""SRTM30 per-z15-tile DEM bake via AWS Terrain Tiles (Terrarium-encoded PNG).

# Why SRTM30 and not DGM10/DGM1

BKG doesn't sell DGM10. DGM1 from BKG costs > 8 000 €. The German
Bundesländer publish DGM1 free as Open-Data but the portals are
INTERSHOP-based (browser sessions, shopping-cart pattern) and don't
allow headless bulk download. SRTM30 is the universal fallback:
- 1 arc-second (~30 m) native grid in DACH latitudes (~24 m × 30 m)
- Public AWS S3 bucket `elevation-tiles-prod`, no auth, no rate
  limits, served via the Terrarium PNG-encoding
- z15-aligned: AWS serves slippy-map tiles, so a z15 Terrarium tile
  covers the same lat/lon footprint as our z15 output tile
- ~30 m source data resolution is 6× finer than DGM200's 200 m grid
  — captures dams, embankments, ridges that DGM200 averages out

When a Bundesland's open-data DGM1 lands on disk (user does the
manual download), a separate `dgm1_xyz.py` adapter can override
specific tiles. Until then, SRTM30 is the universal source.

# Source bucket

`https://s3.amazonaws.com/elevation-tiles-prod/terrarium/{z}/{x}/{y}.png`

Terrarium encoding (decoded per-pixel):
    elev_m = R * 256 + G + B / 256 - 32768

256 × 256 px per tile. At z15 this maps to ~3 m per pixel oversampling
of the ~30 m source. We downsample on bake to keep the binary lean.

# Output

Same DGM2 v1 format as `dgm.py` / `dgm10.py`. The iOS reader is grid-
agnostic — it picks up `rows × cols` from the header. R2 path mirrors
DGM10: `v1/dgm10/{state}/z15/{x}/{y}.bin` (same shelf — the iOS
adapter doesn't need to know whether the y-values came from DGM1 or
SRTM, only that they conform to the binary format).

# Local PNG cache

Raw Terrarium PNGs go into `data/raw/srtm30_terrarium/{z}/{x}/{y}.png`.
Re-bake reads from cache, no second HTTP round-trip. AWS S3 doesn't
rate-limit anonymous reads but we still avoid hitting it twice for
the same tile.
"""
from __future__ import annotations

import io
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import numpy as np
import requests
from PIL import Image

from bake.dgm import (
    DEFAULT_OFFSET,
    DEFAULT_SCALE,
    DGMBinary,
    pack_float_grid,
    write_binary,
)
from bake.dgm10 import TileCoord

# AWS S3 public, US-East-1. EU mirror exists at
# `elevation-tiles-prod-eu.s3.eu-central-1.amazonaws.com` but the bake
# runs from Windows in a typical home connection — the latency
# difference is dwarfed by per-tile bandwidth, and the US bucket has
# longer track record / wider CDN coverage.
TERRARIUM_BASE_URL = "https://s3.amazonaws.com/elevation-tiles-prod/terrarium"

# Terrarium pixel grid is 256 × 256. Block-mean downsample 256 → 64
# gives a 64 × 64 binary grid (~12 m effective spacing at HE
# latitude), 8 KB raw / ~4 KB gzipped per tile. Set to 1 to keep the
# full 256 × 256 grid (~131 KB raw / ~60 KB gzipped per tile).
DEFAULT_DOWNSAMPLE_FACTOR = 4


@dataclass(frozen=True)
class FetchResult:
    """Raw Terrarium tile result. `elev_m` is row-major (256, 256)
    float32 with row 0 = NORTH edge of the tile (matches AWS pixel
    convention and DGM2 v1 binary convention)."""
    tile: TileCoord
    elev_m: np.ndarray  # shape (256, 256), float32


def _cache_path(*, cache_root: Path, tile: TileCoord) -> Path:
    return (
        cache_root
        / f"z{tile.z}"
        / str(tile.x)
        / f"{tile.y}.png"
    )


def fetch_terrarium_tile(
    *,
    tile: TileCoord,
    session: Optional[requests.Session] = None,
    cache_root: Optional[Path] = None,
    timeout_s: float = 30.0,
) -> FetchResult:
    """Fetch + decode one Terrarium tile.

    - Reads from the local PNG cache when `cache_root` points to a
      directory containing `z{z}/{x}/{y}.png`. Cache miss → HTTP fetch
      + write to cache.
    - When `session` is `None`, a one-shot `requests.get` is used.
      Pass a `requests.Session` for connection-pooling across a batch.
    """
    cache_file = _cache_path(cache_root=cache_root, tile=tile) if cache_root else None
    png_bytes: bytes
    if cache_file is not None and cache_file.exists():
        png_bytes = cache_file.read_bytes()
    else:
        url = f"{TERRARIUM_BASE_URL}/{tile.z}/{tile.x}/{tile.y}.png"
        getter = session.get if session is not None else requests.get
        resp = getter(url, timeout=timeout_s)
        resp.raise_for_status()
        png_bytes = resp.content
        if cache_file is not None:
            cache_file.parent.mkdir(parents=True, exist_ok=True)
            cache_file.write_bytes(png_bytes)

    img = Image.open(io.BytesIO(png_bytes))
    # Force RGB — Terrarium tiles are typically RGBA but the alpha
    # channel is always 255; some are RGB. Coerce to a known shape.
    img = img.convert("RGB")
    arr = np.asarray(img, dtype=np.int32)  # (256, 256, 3) — uint8 cast to int32
    if arr.shape != (256, 256, 3):
        raise ValueError(
            f"unexpected Terrarium tile shape {arr.shape} "
            f"(expected (256, 256, 3))")

    R = arr[:, :, 0]
    G = arr[:, :, 1]
    B = arr[:, :, 2]
    elev = R * 256 + G + B / 256.0 - 32768.0
    return FetchResult(tile=tile, elev_m=elev.astype(np.float32))


def _block_mean_downsample(
    arr: np.ndarray, factor: int) -> np.ndarray:
    """Block-average downsample by integer `factor`. Input `(h, w)`,
    output `(h // factor, w // factor)`. Requires `h % factor == 0`
    and same for `w` — AWS Terrarium tiles are 256 × 256 so factors
    1, 2, 4, 8, 16, 32, 64, 128, 256 all work."""
    h, w = arr.shape
    if h % factor != 0 or w % factor != 0:
        raise ValueError(
            f"shape {arr.shape} not evenly divisible by {factor}")
    nh, nw = h // factor, w // factor
    return arr.reshape(nh, factor, nw, factor).mean(axis=(1, 3)).astype(arr.dtype)


def bake_tile_from_srtm(
    *,
    tile: TileCoord,
    out_path: Path,
    session: Optional[requests.Session] = None,
    cache_root: Optional[Path] = None,
    downsample_factor: int = DEFAULT_DOWNSAMPLE_FACTOR,
    scale: float = DEFAULT_SCALE,
    offset: float = DEFAULT_OFFSET,
) -> DGMBinary:
    """End-to-end: fetch Terrarium PNG, decode, optional downsample,
    pack to DGM2 v1, write to `out_path`. Returns the in-memory
    `DGMBinary`.

    The tile's bbox is computed from `TileCoord.bounds()` (web-mercator
    via mercantile). Terrarium pixels and tile bounds are aligned by
    construction — no reprojection needed.

    Row 0 of the resulting binary is the NORTH edge (matches Terrarium
    pixel (0, 0) and DGM2 v1 header convention).
    """
    fetched = fetch_terrarium_tile(
        tile=tile, session=session, cache_root=cache_root)
    elev = fetched.elev_m
    if downsample_factor > 1:
        elev = _block_mean_downsample(elev, downsample_factor)

    min_lat, min_lon, max_lat, max_lon = tile.bounds()
    binary = pack_float_grid(
        elev_m=elev,
        min_lat=min_lat, max_lat=max_lat,
        min_lon=min_lon, max_lon=max_lon,
        scale=scale, offset=offset,
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    write_binary(out_path, binary)
    return binary
