"""DGM10 per-z15-tile DEM bake.

Reads BKG DGM10 GeoTIFFs (per-Bundesland, EPSG:25832 UTM32N, 10 m grid)
and writes one compact binary **per z15 tile** that the iOS
`R2HostedDGM10TileAdapter` reads on tile-mount.

# Why per-z15-tile (not per-Bundesland like DGM200)

DGM10's 10 m grid spacing is 20× denser than DGM200's. A whole-Hessen
DGM10 binary would be ~400 MB — far too big for the streaming-on-mount
flow we use for OSM and LoD2 tiles. Splitting by z15 (the existing
tile resolution for buildings + OSM) keeps each binary at ~10–20 KB
and gives us free disk-cache reuse on the iOS side (the per-tile
`RawSourceCache` infrastructure is already shared with LoD2 + OSM).

# Binary format

Same `DGM2 v1` header + Int16 body as DGM200 — see `bake.dgm`. The iOS
reader (`DGMBinaryReader`) is grid-agnostic; it reads `rows`, `cols`,
`bbox`, `scale`, `offset` from the header and bilinear-samples. No
schema change on the receiving side.

# Output sizing per tile

A z15 tile is ~786 m (lon) × ~600 m (lat) at Hessen latitudes. With
`DEFAULT_OUTPUT_DEG_DGM10 = 0.0001°` (≈ 11 m at lat 50°):
- lon cells ≈ 110, lat cells ≈ 90
- ~10 000 cells × 2 bytes = ~20 KB per tile uncompressed
- gzip on R2 cuts to ~10 KB

For Hessen's ~30 000 z15 tiles → ~300 MB total R2 storage. Per
streaming fetch: ~10 KB on the wire, sub-100 ms latency from R2 cache.

# One-tile-buffer

Each baked tile covers `tile_bbox + 1 cell of buffer in all four
directions` so the iOS bilinear sampler can read at the tile edge
without going out-of-bounds. The header `bbox` records the buffered
extent, so the iOS reader's edge-check on `(lat, lon) ∈ bbox` works
without special-casing.
"""
from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

import mercantile

from bake.dgm import (
    DEFAULT_OFFSET,
    DEFAULT_SCALE,
    DGMBinary,
    STATE_BBOXES,
    crop_and_reproject_geotiff,
    pack_float_grid,
    write_binary,
)

# 0.0001° ≈ 11.1 m lat / 7.1 m lon at lat 50°. Slight over-sampling
# vs. DGM10's native 10 m grid keeps interpolation bounded under
# reprojection from UTM32N without bloating the per-tile binary.
DEFAULT_OUTPUT_DEG_DGM10 = 0.0001

# One output-grid cell of buffer on each side of the tile bbox, so
# bilinear sampling at the tile edge stays inside the binary's
# recorded bbox. Without this the iOS reader returns `nil` for
# coordinates that land exactly on the tile boundary — visible as
# missing height at z15 tile seams.
DEFAULT_BUFFER_DEG = DEFAULT_OUTPUT_DEG_DGM10

ZOOM = 15


@dataclass(frozen=True)
class TileCoord:
    """A z15 web-mercator tile coordinate."""
    z: int
    x: int
    y: int

    @property
    def cache_key(self) -> str:
        """Mirrors iOS `TileID.cacheKey` — used as the local filename
        stem and as the {x}/{y} segment in the R2 remote key."""
        return f"z{self.z}_{self.x}_{self.y}"

    def bounds(self) -> tuple[float, float, float, float]:
        """Return WGS84 bbox `(min_lat, min_lon, max_lat, max_lon)`."""
        b = mercantile.bounds(self.x, self.y, self.z)
        return (b.south, b.west, b.north, b.east)


def iter_z15_tiles_for_state(state: str) -> Iterator[TileCoord]:
    """Yield every z15 tile whose bbox overlaps the state's bbox.

    Uses `mercantile.tiles(west, south, east, north, zooms)`, which
    handles the y-axis inversion of TMS vs. XYZ internally. Result
    order is row-major (y outer, x inner) but no consumer depends on
    that — the per-tile bake is order-independent.
    """
    if state not in STATE_BBOXES:
        raise KeyError(
            f"unknown state '{state}'; known: {sorted(STATE_BBOXES)}")
    min_lat, min_lon, max_lat, max_lon = STATE_BBOXES[state]
    for t in mercantile.tiles(min_lon, min_lat, max_lon, max_lat, zooms=[ZOOM]):
        yield TileCoord(z=t.z, x=t.x, y=t.y)


def bake_tile(
    *,
    src_geotiff: Path,
    tile: TileCoord,
    out_path: Path,
    output_deg: float = DEFAULT_OUTPUT_DEG_DGM10,
    buffer_deg: float = DEFAULT_BUFFER_DEG,
    scale: float = DEFAULT_SCALE,
    offset: float = DEFAULT_OFFSET,
) -> DGMBinary:
    """Bake one z15 tile from `src_geotiff` to `out_path`.

    The source GeoTIFF should cover at least the tile's bbox + buffer.
    Cells outside the source raster's coverage become `nodata_i16` in
    the output — the iOS reader returns `nil` for those samples.

    Returns the in-memory `DGMBinary` for smoke-testing /
    round-trip verification.

    `output_deg` controls the per-cell ground spacing. Default
    `0.0001°` ≈ 11 m lat / 7 m lon at HE latitude — close to DGM10's
    native 10 m resolution.

    `buffer_deg` extends the bbox by this amount in each direction so
    bilinear sampling at the tile edge stays in-bounds. Default = one
    output cell.
    """
    tile_min_lat, tile_min_lon, tile_max_lat, tile_max_lon = tile.bounds()
    buffered = (
        tile_min_lat - buffer_deg,
        tile_min_lon - buffer_deg,
        tile_max_lat + buffer_deg,
        tile_max_lon + buffer_deg,
    )
    elev, snapped_bbox = crop_and_reproject_geotiff(
        src_geotiff=src_geotiff,
        bbox=buffered,
        output_deg=output_deg,
    )
    s_min_lat, s_min_lon, s_max_lat, s_max_lon = snapped_bbox

    binary = pack_float_grid(
        elev_m=elev,
        min_lat=s_min_lat, max_lat=s_max_lat,
        min_lon=s_min_lon, max_lon=s_max_lon,
        scale=scale, offset=offset,
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    write_binary(out_path, binary)
    return binary


def local_path_for_tile(
    *, out_root: Path, state: str, tile: TileCoord) -> Path:
    """Standard local layout: `{out_root}/{state}/z{z}/{x}/{y}.bin`.

    Matches the R2 remote key layout (without the `v1/dgm10/` prefix)
    so a local-vs-R2 diff is a straight path comparison.
    """
    return (
        out_root
        / state
        / f"z{tile.z}"
        / str(tile.x)
        / f"{tile.y}.bin"
    )
