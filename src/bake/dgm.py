"""DGM200 horizon-DEM bake.

Reads BKG DGM200 GeoTIFFs (1 GeoTIFF for all of Germany, EPSG:25832 UTM32N,
200 m grid spacing) and writes one compact per-Bundesland binary that the
iOS `BKGDGM200StateRaster` reads via memory-mapped I/O.

# Why per-Bundesland (not per z15-tile)

DGM200 is a smooth continuous field, ~3 MB per state at 200 m resolution
after Int16-packing. Splitting by z15 would mean ~600 bytes per tile and
50+ fan-out fetches for one horizon mesh — pure header/round-trip
overhead with no upside. One state file fetches once over the
app lifetime and lives in disk + memory cache indefinitely (DEM
doesn't change).

# Binary layout (DGM2 v1)

Total header = 64 bytes (8 bytes of zero-padding at the end for
future-proofing). All multi-byte fields little-endian. Row 0 = max_lat
(north-first convention; matches GDAL's pixel-space).

```
offset  size  type     field
------  ----  -------  ----------------------------------------
 0       4    char[4]  magic = b"DGM2"
 4       4    uint32   version = 1
 8       8    float64  min_lat   (south edge of grid)
16       8    float64  max_lat   (north edge of grid)
24       8    float64  min_lon   (west edge of grid)
32       8    float64  max_lon   (east edge of grid)
40       4    uint32   rows      (= height; row 0 is north)
44       4    uint32   cols      (= width;  col 0 is west)
48       4    float32  scale     (elev_m = value_i16 * scale + offset)
52       4    float32  offset
56       4    int32    nodata_i16 (sentinel for missing samples)
60       4    -        reserved (zero)
------  ----
 64                    (header end; body begins here)

Body: rows * cols * int16 little-endian. Row-major (C order).
elevation_m = grid[r][c] * scale + offset   (if grid[r][c] != nodata_i16)
elevation_m = None / undefined              (if grid[r][c] == nodata_i16)
```

# Recommended pack params for DGM200

- `scale = 0.1` (decimetres) → ±3276 m range, 10 cm precision. DGM200's
  native vertical accuracy is ~1-2 m, so 10 cm is loss-free for our use.
- `offset = 0.0`
- `nodata_i16 = -32768` (Int16 min sentinel; never collides with real
  data because Germany's lowest point is ~-3 m NHN).
"""
from __future__ import annotations

import struct
from dataclasses import dataclass
from pathlib import Path

import numpy as np

# State -> WGS84 bbox (min_lat, min_lon, max_lat, max_lon). Mirrors
# `bake.run.STATE_BBOXES` to keep the bbox source-of-truth co-located
# with the LoD2 pipeline. Importing from `bake.run` here would create
# a cycle (run.py imports normalize → schema → ...); duplicating two
# tuples is cheaper than refactoring.
STATE_BBOXES: dict[str, tuple[float, float, float, float]] = {
    "de_he": (49.39, 7.77, 51.66, 10.24),   # Hessen
    "de_by": (47.27, 8.97, 50.56, 13.84),   # Bayern
}


MAGIC = b"DGM2"
FORMAT_VERSION = 1
HEADER_SIZE = 64
DEFAULT_NODATA_I16 = -32768
DEFAULT_SCALE = 0.1
DEFAULT_OFFSET = 0.0


@dataclass(frozen=True)
class DGMBinary:
    """In-memory representation of a baked DGM binary.

    `values_i16` is a (rows, cols) Int16 numpy array, row 0 at max_lat.
    `nodata_i16` cells contain no data; readers should treat them as
    missing (`None` in iOS).
    """
    min_lat: float
    max_lat: float
    min_lon: float
    max_lon: float
    scale: float
    offset: float
    nodata_i16: int
    values_i16: np.ndarray  # shape (rows, cols), dtype int16

    @property
    def rows(self) -> int:
        return int(self.values_i16.shape[0])

    @property
    def cols(self) -> int:
        return int(self.values_i16.shape[1])

    def sample_bilinear(self, lat: float, lon: float) -> float | None:
        """Bilinear-sample at WGS84 lat/lon.

        Returns `None` when the point is outside the grid bbox OR when
        any of the four neighbours is `nodata_i16` (strict — bilinear
        over a partial neighbourhood is meaningless for elevation).

        Implemented in Python primarily as the round-trip test oracle
        for the iOS bilinear sampler. The hot path in iOS reads the
        same binary directly without touching Python.
        """
        if not (self.min_lat <= lat <= self.max_lat):
            return None
        if not (self.min_lon <= lon <= self.max_lon):
            return None

        # Map lat/lon → fractional row/col. Row 0 = max_lat, so
        # row-axis is inverted relative to lat.
        u = (self.max_lat - lat) / (self.max_lat - self.min_lat)
        v = (lon - self.min_lon) / (self.max_lon - self.min_lon)
        r_f = u * (self.rows - 1)
        c_f = v * (self.cols - 1)

        r0 = int(np.floor(r_f))
        r1 = min(r0 + 1, self.rows - 1)
        c0 = int(np.floor(c_f))
        c1 = min(c0 + 1, self.cols - 1)
        dr = r_f - r0
        dc = c_f - c0

        q00 = int(self.values_i16[r0, c0])
        q01 = int(self.values_i16[r0, c1])
        q10 = int(self.values_i16[r1, c0])
        q11 = int(self.values_i16[r1, c1])

        nd = self.nodata_i16
        if nd in (q00, q01, q10, q11):
            return None

        # Bilinear in Int16 space, then scale once.
        top = q00 * (1 - dc) + q01 * dc
        bot = q10 * (1 - dc) + q11 * dc
        v_i16 = top * (1 - dr) + bot * dr
        return v_i16 * self.scale + self.offset


def write_binary(path: Path, b: DGMBinary) -> None:
    """Serialise `b` to `path` in DGM2 v1 format. Caller is responsible
    for `path.parent.mkdir(parents=True, exist_ok=True)` if needed.

    No gzipping here — the `bake.upload` step sets `Content-Encoding:
    gzip` on the R2 upload, and the local copy stays uncompressed for
    easy inspection / round-trip testing.
    """
    if b.values_i16.dtype != np.int16:
        raise ValueError(
            f"values_i16 must be int16, got {b.values_i16.dtype}")
    if b.values_i16.ndim != 2:
        raise ValueError(
            f"values_i16 must be 2-D, got shape {b.values_i16.shape}")

    header = struct.pack(
        "<4sI4d2I2fi4x",
        MAGIC,
        FORMAT_VERSION,
        b.min_lat, b.max_lat, b.min_lon, b.max_lon,
        b.rows, b.cols,
        b.scale, b.offset,
        b.nodata_i16,
    )
    assert len(header) == HEADER_SIZE, f"header size {len(header)} != {HEADER_SIZE}"

    # Force little-endian on write regardless of host byte order so
    # iOS (ARM, little-endian anyway) reads the same bytes.
    body = b.values_i16.astype("<i2", copy=False).tobytes()
    path.write_bytes(header + body)


def read_binary(path: Path) -> DGMBinary:
    """Round-trip reader for `write_binary` output. Used by tests and
    by any local-inspection tooling — iOS reads the same bytes
    directly with mmap.

    Raises `ValueError` if the magic/version don't match or the body
    length disagrees with `rows * cols * 2`.
    """
    raw = path.read_bytes()
    if len(raw) < HEADER_SIZE:
        raise ValueError(f"file too short ({len(raw)} bytes) — header is {HEADER_SIZE}")
    (
        magic, version,
        min_lat, max_lat, min_lon, max_lon,
        rows, cols,
        scale, offset,
        nodata_i16,
    ) = struct.unpack("<4sI4d2I2fi4x", raw[:HEADER_SIZE])
    if magic != MAGIC:
        raise ValueError(f"magic mismatch: got {magic!r}, expected {MAGIC!r}")
    if version != FORMAT_VERSION:
        raise ValueError(
            f"unsupported DGM binary version {version}; reader is v{FORMAT_VERSION}")

    expected_body = rows * cols * 2
    body = raw[HEADER_SIZE:]
    if len(body) != expected_body:
        raise ValueError(
            f"body length {len(body)} != rows*cols*2 = {expected_body}")

    grid = np.frombuffer(body, dtype="<i2").reshape((rows, cols)).copy()
    return DGMBinary(
        min_lat=min_lat, max_lat=max_lat,
        min_lon=min_lon, max_lon=max_lon,
        scale=scale, offset=offset,
        nodata_i16=nodata_i16,
        values_i16=grid,
    )


def pack_float_grid(
    *,
    elev_m: np.ndarray,
    min_lat: float, max_lat: float,
    min_lon: float, max_lon: float,
    scale: float = DEFAULT_SCALE,
    offset: float = DEFAULT_OFFSET,
    nodata_i16: int = DEFAULT_NODATA_I16,
    nan_sentinel: bool = True,
) -> DGMBinary:
    """Convert a Float32/Float64 (rows, cols) elevation grid (in metres)
    to a `DGMBinary` ready for `write_binary`.

    `elev_m` cells equal to `NaN` are encoded as `nodata_i16`. Out-of-range
    real values raise `OverflowError` so silent wrap-around can't happen.

    Row 0 must be the **north** edge (= max_lat) — matches GDAL's
    pixel-space convention. The header bbox is recorded as-is; the
    reader uses it as the bilinear interpolation domain.
    """
    if elev_m.ndim != 2:
        raise ValueError(f"elev_m must be 2-D, got shape {elev_m.shape}")
    if scale <= 0:
        raise ValueError(f"scale must be positive, got {scale}")

    encoded = np.empty_like(elev_m, dtype=np.int16)
    is_nan = np.isnan(elev_m) if nan_sentinel else np.zeros_like(elev_m, dtype=bool)

    # Skip the NaN cells when scaling so we don't trip the overflow
    # check on them.
    real = ~is_nan
    if real.any():
        scaled = (elev_m[real] - offset) / scale
        # Bound check: would integer-cast clip silently?
        if (scaled.min() < -32767) or (scaled.max() > 32767):
            raise OverflowError(
                f"scaled values outside int16 range "
                f"[{scaled.min()}, {scaled.max()}] — "
                f"adjust scale={scale} / offset={offset}")
        # Use -32767 as the lowest legal value so -32768 stays reserved
        # for nodata even when a real value rounds there.
        encoded[real] = np.clip(np.round(scaled), -32767, 32767).astype(np.int16)
    encoded[is_nan] = nodata_i16

    return DGMBinary(
        min_lat=min_lat, max_lat=max_lat,
        min_lon=min_lon, max_lon=max_lon,
        scale=scale, offset=offset,
        nodata_i16=nodata_i16,
        values_i16=encoded,
    )


# ---------------------------------------------------------------------------
# GeoTIFF ingestion (rasterio)
# ---------------------------------------------------------------------------
#
# `rasterio` is a heavy dependency (drags in GDAL). Imported lazily so
# the binary-format module (used by tests + iOS verification scripts)
# stays import-cheap. Only the bake CLI touches the rasterio path.


# Default WGS84 output resolution. At latitude 50°, 0.002° ≈ 222 m
# (lat) × 143 m (lon) — slight over-sampling vs. the native UTM32N
# 200 m raster, which keeps interpolation bounded under reprojection
# without bloating the binary.
DEFAULT_OUTPUT_DEG = 0.002


def crop_and_reproject_geotiff(
    *,
    src_geotiff: Path,
    bbox: tuple[float, float, float, float],
    output_deg: float = DEFAULT_OUTPUT_DEG,
) -> tuple[np.ndarray, tuple[float, float, float, float]]:
    """Crop `src_geotiff` to the lat/lon `bbox` and reproject to EPSG:4326.

    `bbox` is `(min_lat, min_lon, max_lat, max_lon)`. The output grid is
    regular in degrees (square cells of side `output_deg`). Row 0 is
    the **north** edge of the output bbox so the result drops directly
    into `pack_float_grid` / `write_binary`.

    Returns `(elev_m, snapped_bbox)`:
    - `elev_m`: 2-D `np.float32` array of metres. Cells outside the
      source raster's coverage are `np.nan`.
    - `snapped_bbox`: the actual bbox covered, which may be slightly
      smaller than the requested `bbox` because we round to an
      integer number of `output_deg` cells.

    Imports rasterio lazily — `from bake.dgm import ...` for the
    binary format stays GDAL-free.
    """
    import rasterio
    from rasterio.transform import from_origin
    from rasterio.warp import Resampling, reproject

    min_lat, min_lon, max_lat, max_lon = bbox

    # Snap bbox to a whole number of output cells so every row/col is
    # an exact `output_deg` step. Round outward so the requested bbox
    # is fully contained.
    cols = int(np.ceil((max_lon - min_lon) / output_deg))
    rows = int(np.ceil((max_lat - min_lat) / output_deg))
    snapped_max_lon = min_lon + cols * output_deg
    snapped_max_lat = min_lat + rows * output_deg

    # `from_origin(west, north, xres, yres)` — yres is positive even
    # though row index grows southward, because rasterio bakes the
    # sign into its internal pixel→world math.
    dst_transform = from_origin(
        min_lon, snapped_max_lat, output_deg, output_deg)
    dst = np.full((rows, cols), np.nan, dtype=np.float32)

    with rasterio.open(src_geotiff) as src:
        # `src.nodata` may be None (BKG GeoTIFF typically encodes
        # ocean / no-data as a finite sentinel like -9999). The
        # reproject() call handles whatever sentinel the source
        # declares; afterwards we map it to NaN for downstream
        # NaN→nodata_i16 encoding.
        reproject(
            source=rasterio.band(src, 1),
            destination=dst,
            src_transform=src.transform,
            src_crs=src.crs,
            dst_transform=dst_transform,
            dst_crs="EPSG:4326",
            resampling=Resampling.bilinear,
            dst_nodata=np.nan,
        )

    return dst, (min_lat, min_lon, snapped_max_lat, snapped_max_lon)


def bake_state(
    *,
    src_geotiff: Path,
    state: str,
    out_path: Path,
    output_deg: float = DEFAULT_OUTPUT_DEG,
    scale: float = DEFAULT_SCALE,
    offset: float = DEFAULT_OFFSET,
) -> DGMBinary:
    """End-to-end: read GeoTIFF, crop to `state`'s bbox, pack as DGM2 v1
    binary, write to `out_path`.

    Returns the in-memory `DGMBinary` for inspection / smoke-testing
    against the iOS reader.

    Raises `KeyError` if `state` isn't in `STATE_BBOXES` — explicit
    failure mode rather than silently baking the wrong region.
    """
    if state not in STATE_BBOXES:
        raise KeyError(
            f"unknown state '{state}'; known: {sorted(STATE_BBOXES)}")
    bbox = STATE_BBOXES[state]
    elev, snapped_bbox = crop_and_reproject_geotiff(
        src_geotiff=src_geotiff, bbox=bbox, output_deg=output_deg)
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
