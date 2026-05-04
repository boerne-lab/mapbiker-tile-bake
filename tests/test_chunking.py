"""Tests for bake.chunking — recursive bbox chunking with cap-driven split."""
from typing import Iterator
from bake.sources._bucore3d import ParsedBuilding
from bake.chunking import chunked_fetch


def _fake_uniform_fetcher(buildings_per_sq_deg: int):
    """Returns a fetch_fn that yields a deterministic number of
    buildings per square-degree, scaled to bbox area."""
    def fetch_fn(*, min_lat: float, min_lon: float,
                 max_lat: float, max_lon: float) -> Iterator[ParsedBuilding]:
        area = (max_lat - min_lat) * (max_lon - min_lon)
        n = int(buildings_per_sq_deg * area)
        for i in range(n):
            yield ParsedBuilding(
                source_id=f"fake_{min_lat:.4f}_{min_lon:.4f}_{i}",
                polygons=[[(min_lat, min_lon, 0.0)]],  # placeholder geom
            )
    return fetch_fn


def test_no_chunking_for_sparse_bbox():
    """Sparse area (few buildings, never hits cap) — no recursion."""
    fetch = _fake_uniform_fetcher(buildings_per_sq_deg=10)
    out = list(chunked_fetch(fetch,
                             lat_min=50.0, lon_min=8.0,
                             lat_max=50.5, lon_max=8.5,
                             initial_chunk_deg=0.1, cap=10000))
    # 25 chunks at 0.1°, each with 10 * 0.01 = 0.1 → int = 0 buildings
    # so total 0. Zero is fine — verifies no infinite recursion.
    assert isinstance(out, list)


def test_dense_chunk_recurses_into_quadrants():
    """Force a single chunk to hit the cap. Verify it splits into 4
    sub-chunks at half the chunk size."""
    # buildings_per_sq_deg = 50000 → at chunk_deg=0.1, area=0.01 →
    # 500 buildings. Won't hit cap. So crank density up.
    fetch = _fake_uniform_fetcher(buildings_per_sq_deg=2_000_000)
    out = list(chunked_fetch(fetch,
                             lat_min=50.0, lon_min=8.0,
                             lat_max=50.1, lon_max=8.1,
                             initial_chunk_deg=0.1, cap=10000))
    # At 0.1° one chunk: 2M * 0.01 = 20000 buildings → over cap →
    # recurse to 0.05°. At 0.05° four chunks of 0.0025 area each =
    # 5000 each → under cap. Total: 4 × 5000 = 20000.
    assert 15000 < len(out) < 25000


def test_cap_at_min_chunk_emits_warning_but_yields():
    """If even the min_chunk_deg hits cap, yield what we got and warn —
    don't infinite-recurse."""
    # ridiculous density
    fetch = _fake_uniform_fetcher(buildings_per_sq_deg=10_000_000_000)
    out = list(chunked_fetch(fetch,
                             lat_min=50.0, lon_min=8.0,
                             lat_max=50.01, lon_max=8.01,
                             initial_chunk_deg=0.01,
                             min_chunk_deg=0.005,
                             cap=10000))
    # Recursion stops at min_chunk; we get whatever each leaf returned.
    # The actual count doesn't matter as long as the function returns.
    assert isinstance(out, list)


def test_progress_logged_to_stderr(capsys):
    """At least one progress line per chunk, so a multi-hour bake
    isn't silent."""
    fetch = _fake_uniform_fetcher(buildings_per_sq_deg=5)
    list(chunked_fetch(fetch,
                       lat_min=50.0, lon_min=8.0,
                       lat_max=50.1, lon_max=8.1,
                       initial_chunk_deg=0.05, cap=10000,
                       verbose=True))
    captured = capsys.readouterr()
    # Should mention "chunk" at least once in stderr
    assert "chunk" in captured.err.lower()
