"""Tests for `bake.dgm` binary format + bilinear sampler.

The sampler is the reference oracle for the iOS side — any change to
the encoding here MUST be reflected in `BKGDGM200StateRaster.swift`.
The bilinear test cases double as fixtures the iOS unit tests pin to.
"""
from __future__ import annotations

import struct
from pathlib import Path

import numpy as np
import pytest

from bake.dgm import (
    DEFAULT_NODATA_I16,
    DGMBinary,
    FORMAT_VERSION,
    HEADER_SIZE,
    MAGIC,
    pack_float_grid,
    read_binary,
    write_binary,
)


# -----------------------------------------------------------------------------
# Header roundtrip
# -----------------------------------------------------------------------------

def _make_minimal_dgm(rows: int = 2, cols: int = 2) -> DGMBinary:
    return DGMBinary(
        min_lat=49.0, max_lat=51.0,
        min_lon=7.0, max_lon=10.0,
        scale=0.1, offset=0.0,
        nodata_i16=DEFAULT_NODATA_I16,
        values_i16=np.zeros((rows, cols), dtype=np.int16),
    )


def test_write_then_read_preserves_header(tmp_path: Path) -> None:
    src = DGMBinary(
        min_lat=49.39, max_lat=51.66,
        min_lon=7.77, max_lon=10.24,
        scale=0.1, offset=0.0,
        nodata_i16=DEFAULT_NODATA_I16,
        values_i16=np.array([[100, 200], [300, 400]], dtype=np.int16),
    )
    path = tmp_path / "he.bin"
    write_binary(path, src)
    out = read_binary(path)

    assert out.min_lat == pytest.approx(src.min_lat)
    assert out.max_lat == pytest.approx(src.max_lat)
    assert out.min_lon == pytest.approx(src.min_lon)
    assert out.max_lon == pytest.approx(src.max_lon)
    assert out.scale == pytest.approx(src.scale)
    assert out.offset == pytest.approx(src.offset)
    assert out.nodata_i16 == src.nodata_i16
    assert out.rows == 2
    assert out.cols == 2
    np.testing.assert_array_equal(out.values_i16, src.values_i16)


def test_header_size_is_64_bytes(tmp_path: Path) -> None:
    path = tmp_path / "x.bin"
    write_binary(path, _make_minimal_dgm())
    raw = path.read_bytes()
    # 4 cells * 2 bytes = 8 byte body
    assert len(raw) == HEADER_SIZE + 8


def test_magic_bytes_are_DGM2(tmp_path: Path) -> None:
    path = tmp_path / "x.bin"
    write_binary(path, _make_minimal_dgm())
    assert path.read_bytes()[:4] == b"DGM2"
    assert MAGIC == b"DGM2"


def test_version_field_is_recorded(tmp_path: Path) -> None:
    path = tmp_path / "x.bin"
    write_binary(path, _make_minimal_dgm())
    raw = path.read_bytes()
    version = struct.unpack("<I", raw[4:8])[0]
    assert version == FORMAT_VERSION == 1


def test_read_rejects_bad_magic(tmp_path: Path) -> None:
    path = tmp_path / "bad.bin"
    write_binary(path, _make_minimal_dgm())
    # Corrupt the magic
    raw = bytearray(path.read_bytes())
    raw[0:4] = b"XXXX"
    path.write_bytes(bytes(raw))
    with pytest.raises(ValueError, match="magic"):
        read_binary(path)


def test_read_rejects_truncated_body(tmp_path: Path) -> None:
    path = tmp_path / "short.bin"
    write_binary(path, _make_minimal_dgm())
    raw = path.read_bytes()
    # Drop the last 4 body bytes
    path.write_bytes(raw[:-4])
    with pytest.raises(ValueError, match="body length"):
        read_binary(path)


def test_read_rejects_unknown_version(tmp_path: Path) -> None:
    path = tmp_path / "v99.bin"
    write_binary(path, _make_minimal_dgm())
    raw = bytearray(path.read_bytes())
    # Set version field to 99
    raw[4:8] = struct.pack("<I", 99)
    path.write_bytes(bytes(raw))
    with pytest.raises(ValueError, match="version"):
        read_binary(path)


def test_body_is_little_endian_int16(tmp_path: Path) -> None:
    """iOS reads with mmap + Int16 little-endian; this test pins the
    wire byte order so a host-machine endian flip can never silently
    corrupt the upload."""
    src = DGMBinary(
        min_lat=0.0, max_lat=1.0, min_lon=0.0, max_lon=1.0,
        scale=1.0, offset=0.0, nodata_i16=DEFAULT_NODATA_I16,
        values_i16=np.array([[0x0102, 0x0304]], dtype=np.int16),
    )
    path = tmp_path / "endian.bin"
    write_binary(path, src)
    body = path.read_bytes()[HEADER_SIZE:]
    # 0x0102 little-endian = 0x02 0x01
    assert body[0:2] == b"\x02\x01"
    assert body[2:4] == b"\x04\x03"


# -----------------------------------------------------------------------------
# Bilinear sampler — these doubles as iOS pin-tests
# -----------------------------------------------------------------------------

@pytest.fixture
def simple_2x2_grid() -> DGMBinary:
    """2×2 grid covering lat=[0,1], lon=[0,1]. Row 0 (north) = [10, 20];
    Row 1 (south) = [30, 40]. Values are in raw int16 with scale=1.0
    so the bilinear math is easy to verify by hand.
    """
    return DGMBinary(
        min_lat=0.0, max_lat=1.0,
        min_lon=0.0, max_lon=1.0,
        scale=1.0, offset=0.0,
        nodata_i16=DEFAULT_NODATA_I16,
        values_i16=np.array([[10, 20], [30, 40]], dtype=np.int16),
    )


def test_bilinear_corner_NW(simple_2x2_grid: DGMBinary) -> None:
    # NW corner = max_lat, min_lon = row 0, col 0 = 10
    assert simple_2x2_grid.sample_bilinear(1.0, 0.0) == pytest.approx(10.0)


def test_bilinear_corner_NE(simple_2x2_grid: DGMBinary) -> None:
    assert simple_2x2_grid.sample_bilinear(1.0, 1.0) == pytest.approx(20.0)


def test_bilinear_corner_SW(simple_2x2_grid: DGMBinary) -> None:
    assert simple_2x2_grid.sample_bilinear(0.0, 0.0) == pytest.approx(30.0)


def test_bilinear_corner_SE(simple_2x2_grid: DGMBinary) -> None:
    assert simple_2x2_grid.sample_bilinear(0.0, 1.0) == pytest.approx(40.0)


def test_bilinear_center_is_mean_of_four(simple_2x2_grid: DGMBinary) -> None:
    # Center: 0.5 weight on each corner
    assert simple_2x2_grid.sample_bilinear(0.5, 0.5) == pytest.approx(
        (10 + 20 + 30 + 40) / 4)


def test_bilinear_midpoint_top_edge(simple_2x2_grid: DGMBinary) -> None:
    # Half-way between NW (10) and NE (20) = 15
    assert simple_2x2_grid.sample_bilinear(1.0, 0.5) == pytest.approx(15.0)


def test_bilinear_returns_none_outside_bbox(simple_2x2_grid: DGMBinary) -> None:
    assert simple_2x2_grid.sample_bilinear(2.0, 0.5) is None
    assert simple_2x2_grid.sample_bilinear(-0.5, 0.5) is None
    assert simple_2x2_grid.sample_bilinear(0.5, 2.0) is None
    assert simple_2x2_grid.sample_bilinear(0.5, -0.5) is None


def test_bilinear_returns_none_when_neighbour_is_nodata() -> None:
    """Strict mode — even one nodata neighbour invalidates the bilinear
    result. Prevents the iOS horizon mesh from quietly extrapolating
    over coastline / coverage holes."""
    grid = DGMBinary(
        min_lat=0.0, max_lat=1.0, min_lon=0.0, max_lon=1.0,
        scale=1.0, offset=0.0,
        nodata_i16=DEFAULT_NODATA_I16,
        values_i16=np.array([[10, DEFAULT_NODATA_I16],
                             [30, 40]], dtype=np.int16),
    )
    assert grid.sample_bilinear(0.5, 0.5) is None


def test_bilinear_respects_scale_and_offset() -> None:
    grid = DGMBinary(
        min_lat=0.0, max_lat=1.0, min_lon=0.0, max_lon=1.0,
        scale=0.1, offset=100.0,
        nodata_i16=DEFAULT_NODATA_I16,
        values_i16=np.array([[10, 20], [30, 40]], dtype=np.int16),
    )
    # NW corner: 10 * 0.1 + 100 = 101.0
    assert grid.sample_bilinear(1.0, 0.0) == pytest.approx(101.0)
    # SE corner: 40 * 0.1 + 100 = 104.0
    assert grid.sample_bilinear(0.0, 1.0) == pytest.approx(104.0)


# -----------------------------------------------------------------------------
# pack_float_grid (Float metres → Int16)
# -----------------------------------------------------------------------------

def test_pack_float_grid_encodes_decimetres_at_scale_0_1() -> None:
    # Frankfurt elevation field: typical values 100-200m
    elev = np.array([[107.3, 112.8], [105.1, 110.0]], dtype=np.float32)
    b = pack_float_grid(
        elev_m=elev,
        min_lat=49.0, max_lat=51.0,
        min_lon=7.0, max_lon=10.0,
        scale=0.1, offset=0.0,
    )
    # 107.3m → 1073 dm
    assert b.values_i16[0, 0] == 1073
    assert b.values_i16[0, 1] == 1128
    assert b.values_i16[1, 0] == 1051
    assert b.values_i16[1, 1] == 1100


def test_pack_float_grid_encodes_nan_as_nodata() -> None:
    elev = np.array([[100.0, np.nan], [105.0, 110.0]], dtype=np.float32)
    b = pack_float_grid(
        elev_m=elev,
        min_lat=0.0, max_lat=1.0, min_lon=0.0, max_lon=1.0,
    )
    assert b.values_i16[0, 1] == DEFAULT_NODATA_I16
    # Sanity: non-NaN cells survive untouched
    assert b.values_i16[0, 0] == 1000


def test_pack_float_grid_raises_on_overflow() -> None:
    # Scale 0.001 (millimetres) → int16 max ≈ 32m. Frankfurt 107m
    # would overflow → must raise rather than silently wrapping.
    elev = np.array([[107.0]], dtype=np.float32)
    with pytest.raises(OverflowError, match="int16"):
        pack_float_grid(
            elev_m=elev,
            min_lat=0.0, max_lat=1.0, min_lon=0.0, max_lon=1.0,
            scale=0.001, offset=0.0,
        )


def test_pack_then_sample_roundtrip_within_precision(tmp_path: Path) -> None:
    """Pack a known float grid, write, read back, bilinear-sample at the
    centre, and verify the result is within `scale` (= 0.1 m = 10 cm)
    of the analytic answer."""
    elev = np.array([[100.0, 200.0], [300.0, 400.0]], dtype=np.float32)
    src = pack_float_grid(
        elev_m=elev,
        min_lat=0.0, max_lat=1.0, min_lon=0.0, max_lon=1.0,
        scale=0.1, offset=0.0,
    )
    path = tmp_path / "rt.bin"
    write_binary(path, src)
    out = read_binary(path)

    # Centre bilinear = (100 + 200 + 300 + 400) / 4 = 250
    sampled = out.sample_bilinear(0.5, 0.5)
    assert sampled is not None
    assert abs(sampled - 250.0) < 0.1  # within one scale-unit (10 cm)


# -----------------------------------------------------------------------------
# GeoTIFF crop + reproject pipeline (rasterio)
# -----------------------------------------------------------------------------
#
# Synthetic GeoTIFF in EPSG:4326 keeps the test free of CRS-warping
# concerns — rasterio's `reproject()` machinery is well-tested upstream.
# These tests verify the bake.dgm-level orchestration: bbox snapping,
# row/col layout, NaN propagation, exception on unknown state.

def _make_synthetic_geotiff_4326(
    *,
    path: Path,
    bbox: tuple[float, float, float, float],
    resolution_deg: float,
    fill_value: float = 150.0,
) -> None:
    """Write a tiny EPSG:4326 GeoTIFF filled with `fill_value`. bbox is
    (min_lat, min_lon, max_lat, max_lon)."""
    import rasterio
    from rasterio.transform import from_origin

    min_lat, min_lon, max_lat, max_lon = bbox
    cols = int(round((max_lon - min_lon) / resolution_deg))
    rows = int(round((max_lat - min_lat) / resolution_deg))
    transform = from_origin(min_lon, max_lat, resolution_deg, resolution_deg)
    data = np.full((rows, cols), fill_value, dtype=np.float32)

    with rasterio.open(
        path, "w",
        driver="GTiff",
        height=rows, width=cols, count=1,
        dtype=data.dtype,
        crs="EPSG:4326",
        transform=transform,
        nodata=-9999.0,
    ) as dst:
        dst.write(data, 1)


def test_bake_state_full_flow(tmp_path: Path) -> None:
    from bake.dgm import bake_state, read_binary

    # Synthetic source GeoTIFF covers all of Hessen at 0.01 degree
    # resolution, constant 150 m elevation.
    src_tif = tmp_path / "src.tif"
    _make_synthetic_geotiff_4326(
        path=src_tif,
        bbox=(49.0, 7.0, 52.0, 11.0),
        resolution_deg=0.01,
        fill_value=150.0,
    )
    out_bin = tmp_path / "de_he.bin"
    binary = bake_state(
        src_geotiff=src_tif,
        state="de_he",
        out_path=out_bin,
        output_deg=0.01,
    )
    assert binary.rows > 200  # 2.27 deg / 0.01 deg ≈ 227 rows
    assert binary.cols > 200

    # Round-trip via disk
    out = read_binary(out_bin)
    assert out.rows == binary.rows
    assert out.cols == binary.cols

    # Centre sample inside Hessen should hit ~150 m (constant fill).
    sampled = out.sample_bilinear(50.5, 9.0)
    assert sampled is not None
    assert abs(sampled - 150.0) < 0.1


def test_bake_state_rejects_unknown_state(tmp_path: Path) -> None:
    from bake.dgm import bake_state

    src_tif = tmp_path / "src.tif"
    _make_synthetic_geotiff_4326(
        path=src_tif,
        bbox=(49.0, 7.0, 50.0, 8.0),
        resolution_deg=0.01,
    )
    with pytest.raises(KeyError, match="unknown state"):
        bake_state(
            src_geotiff=src_tif,
            state="de_xx",
            out_path=tmp_path / "out.bin",
        )


def test_bake_state_uses_state_bbox_from_table(tmp_path: Path) -> None:
    """The output binary's bbox must come from `STATE_BBOXES['de_he']`
    (with snapping for the cell-quantum), NOT from the source raster.
    This ensures the same state code always produces the same bbox
    regardless of source-GeoTIFF coverage."""
    from bake.dgm import STATE_BBOXES, bake_state, read_binary

    src_tif = tmp_path / "src.tif"
    # Source covers way more than Hessen
    _make_synthetic_geotiff_4326(
        path=src_tif,
        bbox=(45.0, 5.0, 55.0, 15.0),
        resolution_deg=0.02,
        fill_value=100.0,
    )
    out_bin = tmp_path / "de_he.bin"
    bake_state(
        src_geotiff=src_tif,
        state="de_he",
        out_path=out_bin,
        output_deg=0.02,
    )
    out = read_binary(out_bin)
    he_min_lat, he_min_lon, _, _ = STATE_BBOXES["de_he"]
    assert out.min_lat == pytest.approx(he_min_lat, abs=0.02)
    assert out.min_lon == pytest.approx(he_min_lon, abs=0.02)


def test_bake_state_propagates_nodata_outside_source(tmp_path: Path) -> None:
    """When the source GeoTIFF doesn't cover the full state bbox, the
    uncovered cells must be `nodata_i16` (= no extrapolation)."""
    from bake.dgm import (
        DEFAULT_NODATA_I16, bake_state, read_binary,
    )

    src_tif = tmp_path / "src.tif"
    # Source covers only the southern third of Hessen
    _make_synthetic_geotiff_4326(
        path=src_tif,
        bbox=(49.39, 7.77, 49.85, 10.24),
        resolution_deg=0.01,
    )
    out_bin = tmp_path / "de_he.bin"
    bake_state(
        src_geotiff=src_tif,
        state="de_he",
        out_path=out_bin,
        output_deg=0.01,
    )
    out = read_binary(out_bin)
    # Northern row of the output bbox should be nodata
    assert out.values_i16[0, out.cols // 2] == DEFAULT_NODATA_I16
    # Southern row should have real data
    assert out.values_i16[-1, out.cols // 2] != DEFAULT_NODATA_I16
