"""Tests for `bake.dgm10` per-z15-tile DGM10 bake.

Mirrors `tests/test_dgm.py` but per-tile. The on-the-wire binary format
is `DGM2 v1` (same as DGM200), so the wire-format tests in
`test_dgm.py` already cover that side; here we focus on per-tile
specifics: tile enumeration, bbox + buffer, output paths, R2 keys.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
import rasterio
from rasterio.transform import from_bounds

from bake.dgm import read_binary
from bake.dgm10 import (
    DEFAULT_BUFFER_DEG,
    DEFAULT_OUTPUT_DEG_DGM10,
    ZOOM,
    TileCoord,
    bake_tile,
    iter_z15_tiles_for_state,
    local_path_for_tile,
)
from bake.upload import _remote_path_for_dgm10


# -----------------------------------------------------------------------------
# TileCoord
# -----------------------------------------------------------------------------

def test_tile_cache_key_matches_ios_format() -> None:
    """iOS `TileID.cacheKey` = `"z{z}_{x}_{y}"` — the Python side must
    produce the same string so cache-key joins (curl URL, R2 list) work
    without translation."""
    assert TileCoord(z=15, x=17167, y=11095).cache_key == "z15_17167_11095"


def test_tile_bounds_is_valid_bbox() -> None:
    """A z15 tile near Frankfurt — bounds returned as
    (min_lat, min_lon, max_lat, max_lon) and min < max on both axes,
    and bracket a known Frankfurt-Westend coord (50.124, 8.605)."""
    t = TileCoord(z=15, x=17167, y=11095)
    min_lat, min_lon, max_lat, max_lon = t.bounds()
    assert min_lat < max_lat
    assert min_lon < max_lon
    # Frankfurt-Westend (matches the iPad-test origin (50.124, 8.605))
    # — the actual tile bbox should bracket those coords.
    assert min_lat < 50.124 < max_lat
    assert min_lon < 8.605 < max_lon


# -----------------------------------------------------------------------------
# iter_z15_tiles_for_state
# -----------------------------------------------------------------------------

def test_iter_z15_tiles_for_state_yields_tiles() -> None:
    tiles = list(iter_z15_tiles_for_state("de_he"))
    # Hessen is ~21000 km² ≈ 30 000 z15 tiles. Anything dramatically
    # smaller means the bbox or zoom is wrong; dramatically bigger
    # means we'd accidentally cover the whole country.
    assert len(tiles) > 10_000
    assert len(tiles) < 100_000


def test_iter_z15_tiles_for_state_returns_z15() -> None:
    tile = next(iter(iter_z15_tiles_for_state("de_he")))
    assert tile.z == ZOOM == 15


def test_iter_z15_tiles_for_state_tiles_overlap_state_bbox() -> None:
    """Every yielded tile must have at least one corner inside the
    state bbox — sanity check against an off-by-1 in the mercantile
    call."""
    from bake.dgm import STATE_BBOXES
    s_min_lat, s_min_lon, s_max_lat, s_max_lon = STATE_BBOXES["de_he"]
    tiles = list(iter_z15_tiles_for_state("de_he"))
    # Sample first / last / middle to keep the test fast.
    samples = [tiles[0], tiles[len(tiles) // 2], tiles[-1]]
    for t in samples:
        min_lat, min_lon, max_lat, max_lon = t.bounds()
        assert max_lat >= s_min_lat and min_lat <= s_max_lat, (
            f"tile {t.cache_key} lat-range {min_lat}..{max_lat} "
            f"misses state lat-range {s_min_lat}..{s_max_lat}")
        assert max_lon >= s_min_lon and min_lon <= s_max_lon, (
            f"tile {t.cache_key} lon-range {min_lon}..{max_lon} "
            f"misses state lon-range {s_min_lon}..{s_max_lon}")


def test_iter_z15_tiles_for_state_rejects_unknown_state() -> None:
    with pytest.raises(KeyError, match="unknown state"):
        next(iter(iter_z15_tiles_for_state("de_xx")))


# -----------------------------------------------------------------------------
# local_path_for_tile
# -----------------------------------------------------------------------------

def test_local_path_layout() -> None:
    p = local_path_for_tile(
        out_root=Path("/tmp/out"),
        state="de_he",
        tile=TileCoord(z=15, x=17167, y=11095),
    )
    assert p == Path("/tmp/out/de_he/z15/17167/11095.bin")


# -----------------------------------------------------------------------------
# R2 remote path
# -----------------------------------------------------------------------------

def test_remote_path_for_dgm10() -> None:
    """The iOS adapter constructs this key client-side; keeping it in
    one shape avoids client/server drift."""
    key = _remote_path_for_dgm10(state="de_he", z=15, x=17167, y=11095)
    assert key == "v1/dgm10/de_he/z15/17167/11095.bin"


# -----------------------------------------------------------------------------
# bake_tile — end-to-end with a synthetic GeoTIFF
# -----------------------------------------------------------------------------

def _make_synthetic_geotiff(
    path: Path,
    *,
    bbox: tuple[float, float, float, float],
    elev_func,
    width: int = 256,
    height: int = 256,
) -> None:
    """Write a tiny EPSG:4326 GeoTIFF whose pixel values come from
    `elev_func(lat, lon)`. Used by the bake-roundtrip tests so we don't
    need the 500 MB BKG GeoTIFF on the test path.

    `bbox` is `(min_lat, min_lon, max_lat, max_lon)`.
    """
    min_lat, min_lon, max_lat, max_lon = bbox
    transform = from_bounds(
        west=min_lon, south=min_lat, east=max_lon, north=max_lat,
        width=width, height=height,
    )
    data = np.zeros((height, width), dtype=np.float32)
    # Row 0 = north (max_lat). Pixel center for row r =
    # max_lat - (r + 0.5) * (max_lat - min_lat) / height.
    for r in range(height):
        lat = max_lat - (r + 0.5) * (max_lat - min_lat) / height
        for c in range(width):
            lon = min_lon + (c + 0.5) * (max_lon - min_lon) / width
            data[r, c] = elev_func(lat, lon)
    with rasterio.open(
        path, "w",
        driver="GTiff",
        height=height, width=width,
        count=1, dtype="float32",
        crs="EPSG:4326",
        transform=transform,
    ) as dst:
        dst.write(data, 1)


def test_bake_tile_roundtrips_via_synthetic_geotiff(tmp_path: Path) -> None:
    """A linear ramp `elev = 100 + 1000*(lat - 50.0)` baked into a
    synthetic source TIFF, baked again through `bake_tile`, then read
    back. The mid-tile sample should match the ramp within Int16
    quantisation (scale=0.1 → ±5 cm)."""
    tile = TileCoord(z=15, x=17167, y=11095)
    min_lat, min_lon, max_lat, max_lon = tile.bounds()

    # Source GeoTIFF covers a slightly larger area than the tile so the
    # buffered bake bbox stays in-bounds.
    src_min_lat = min_lat - 0.01
    src_max_lat = max_lat + 0.01
    src_min_lon = min_lon - 0.01
    src_max_lon = max_lon + 0.01
    src_path = tmp_path / "src.tif"
    _make_synthetic_geotiff(
        src_path,
        bbox=(src_min_lat, src_min_lon, src_max_lat, src_max_lon),
        elev_func=lambda lat, lon: 100.0 + 1000.0 * (lat - 50.0),
    )

    out_path = tmp_path / "out.bin"
    binary = bake_tile(
        src_geotiff=src_path,
        tile=tile,
        out_path=out_path,
    )

    # Header bbox extends ≥ tile bbox (because of the buffer).
    assert binary.min_lat <= min_lat
    assert binary.max_lat >= max_lat
    assert binary.min_lon <= min_lon
    assert binary.max_lon >= max_lon

    # Round-trip: read back, sample at the tile centroid.
    out_again = read_binary(out_path)
    center_lat = (min_lat + max_lat) / 2
    center_lon = (min_lon + max_lon) / 2
    sampled = out_again.sample_bilinear(center_lat, center_lon)
    expected = 100.0 + 1000.0 * (center_lat - 50.0)
    # scale=0.1 → ±0.05 m quantisation, plus minor bilinear-reproject
    # noise from the source raster. Allow 0.5 m headroom.
    assert sampled is not None
    assert abs(sampled - expected) < 0.5, (
        f"sampled={sampled} expected={expected} diff={sampled - expected}")


def test_bake_tile_grid_spacing_close_to_target(tmp_path: Path) -> None:
    """Output grid spacing should be close to `output_deg`. Note:
    `crop_and_reproject_geotiff` produces a PIXEL grid of size
    `cols × rows` covering `cols * output_deg × rows * output_deg`,
    while the DGM2 v1 reader treats grid samples as VERTICES at the
    bbox corners — so the step between adjacent vertices is
    `cols * output_deg / (cols - 1)`, slightly larger than
    `output_deg`. For DGM10 with ~70 cells per tile, the error is
    ~1.5%. Pin to a 5% tolerance to allow that without masking real
    regressions (e.g. wrong axis, 2× step)."""
    tile = TileCoord(z=15, x=17167, y=11095)
    min_lat, min_lon, max_lat, max_lon = tile.bounds()
    src_path = tmp_path / "flat.tif"
    _make_synthetic_geotiff(
        src_path,
        bbox=(min_lat - 0.02, min_lon - 0.02,
              max_lat + 0.02, max_lon + 0.02),
        elev_func=lambda lat, lon: 100.0,  # uniform — easy to verify
    )
    out_path = tmp_path / "spacing.bin"
    binary = bake_tile(
        src_geotiff=src_path,
        tile=tile,
        out_path=out_path,
        output_deg=DEFAULT_OUTPUT_DEG_DGM10,
    )
    lat_step = (binary.max_lat - binary.min_lat) / (binary.rows - 1)
    lon_step = (binary.max_lon - binary.min_lon) / (binary.cols - 1)
    # Step is ≥ output_deg by construction (vertex/pixel convention),
    # and at most ~5% larger for tile-sized grids.
    assert DEFAULT_OUTPUT_DEG_DGM10 <= lat_step < DEFAULT_OUTPUT_DEG_DGM10 * 1.05
    assert DEFAULT_OUTPUT_DEG_DGM10 <= lon_step < DEFAULT_OUTPUT_DEG_DGM10 * 1.05


def test_bake_tile_buffer_extends_bbox(tmp_path: Path) -> None:
    """The buffered bake bbox must extend the tile bbox by at least
    `buffer_deg` on each side so iOS bilinear at the tile edge is
    in-bounds."""
    tile = TileCoord(z=15, x=17167, y=11095)
    min_lat, min_lon, max_lat, max_lon = tile.bounds()
    src_path = tmp_path / "src.tif"
    _make_synthetic_geotiff(
        src_path,
        bbox=(min_lat - 0.02, min_lon - 0.02,
              max_lat + 0.02, max_lon + 0.02),
        elev_func=lambda lat, lon: 50.0,
    )
    out_path = tmp_path / "buf.bin"
    binary = bake_tile(
        src_geotiff=src_path,
        tile=tile,
        out_path=out_path,
    )
    # Lower bounds reach AT LEAST buffer_deg below tile, upper bounds
    # AT LEAST buffer_deg above (the snap may round outward further).
    assert binary.min_lat <= min_lat - DEFAULT_BUFFER_DEG + 1e-9
    assert binary.min_lon <= min_lon - DEFAULT_BUFFER_DEG + 1e-9
    assert binary.max_lat >= max_lat + DEFAULT_BUFFER_DEG - 1e-9
    assert binary.max_lon >= max_lon + DEFAULT_BUFFER_DEG - 1e-9


def test_bake_tile_writes_file(tmp_path: Path) -> None:
    """Sanity: bake_tile actually creates the output file and it's a
    valid DGM2 v1 binary (magic + version)."""
    tile = TileCoord(z=15, x=17167, y=11095)
    min_lat, min_lon, max_lat, max_lon = tile.bounds()
    src_path = tmp_path / "f.tif"
    _make_synthetic_geotiff(
        src_path,
        bbox=(min_lat - 0.02, min_lon - 0.02,
              max_lat + 0.02, max_lon + 0.02),
        elev_func=lambda lat, lon: 200.0,
    )
    out_path = tmp_path / "nested" / "out.bin"
    assert not out_path.exists()
    bake_tile(src_geotiff=src_path, tile=tile, out_path=out_path)
    assert out_path.exists()
    assert out_path.read_bytes()[:4] == b"DGM2"
