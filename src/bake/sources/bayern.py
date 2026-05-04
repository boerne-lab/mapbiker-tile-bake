"""Bayern Bayernwolke LoD2 fetcher.

Bayernwolke distributes LoD2 as 2 km × 2 km UTM32N CityGML tiles:
    https://download1.bayernwolke.de/a/lod2/citygml/{KKKK}_{NNNN}.gml

where KKKK is the easting in km and NNNN is the northing in km
(both multiples of 2 since tiles are 2 km × 2 km).

Unlike Hessen INSPIRE (bbox-queryable, capped at 10000 buildings),
Bayern's data is per-tile static download. No bbox-chunking needed —
each tile is already a bounded file. Per-tile sizes range from 1 KB
(empty / water-only stubs) to 156 MB (dense urban — München central).

HTTP 404 from a tile URL means "no coverage" (state-edge gaps, water,
or unmapped areas). The fetcher logs and continues.

License: CC BY 4.0. Attribution required: "© Bayerische Vermessungsverwaltung – CC BY 4.0".
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path
from typing import Iterator

import requests
from pyproj import Transformer

from bake.sources._bucore3d import ParsedBuilding
from bake.sources._citygml2 import parse_citygml2_gml

ENDPOINT_BASE = "https://download1.bayernwolke.de/a/lod2/citygml/"

USER_AGENT = "mapbiker-tile-bake (+https://github.com/boerne-lab/mapbiker)"
# Generous timeout for 156 MB downloads on slow connections.
TIMEOUT_SECONDS = 600

# WGS84 → UTM32N for the bbox-corner-projection step in coverage_tiles.
_INVERSE_TRANSFORMER = Transformer.from_crs(
    "EPSG:4326", "EPSG:25832", always_xy=True,
)


def tile_url(*, easting_km: int, northing_km: int) -> str:
    """Build the Bayernwolke download URL for one 2 km UTM32N tile."""
    return f"{ENDPOINT_BASE}{easting_km}_{northing_km}.gml"


def coverage_tiles(*, min_lat: float, min_lon: float,
                   max_lat: float, max_lon: float
                   ) -> list[tuple[int, int]]:
    """Returns a list of `(eastingKm, northingKm)` tuples for the 2 km
    UTM32N tiles whose AABB intersects the WGS84 bbox.

    Mirrors `BayernAdapter.swift` `coverageTiles(for:)`. All four corner
    projections are taken because the WGS84-to-UTM transform skews
    sub-degree bboxes; using only two corners would miss tiles near
    the AABB diagonal.
    """
    corners = [
        _INVERSE_TRANSFORMER.transform(min_lon, min_lat),
        _INVERSE_TRANSFORMER.transform(max_lon, min_lat),
        _INVERSE_TRANSFORMER.transform(max_lon, max_lat),
        _INVERSE_TRANSFORMER.transform(min_lon, max_lat),
    ]
    eastings = [c[0] for c in corners]
    northings = [c[1] for c in corners]

    e_min, e_max = min(eastings), max(eastings)
    n_min, n_max = min(northings), max(northings)

    # SW-corner km values that are multiples of 2.
    e_start = int(e_min // 2000) * 2
    e_end = -(-int(e_max) // 2000) * 2 - 2  # ceil-div trick
    n_start = int(n_min // 2000) * 2
    n_end = -(-int(n_max) // 2000) * 2 - 2

    tiles: list[tuple[int, int]] = []
    e = e_start
    while e <= e_end:
        n = n_start
        while n <= n_end:
            tiles.append((e, n))
            n += 2
        e += 2
    return tiles


def stream_tile_to_file(*, easting_km: int, northing_km: int,
                        dest_path: Path) -> int | None:
    """Download one Bayernwolke tile and write it to `dest_path`.
    Returns the byte count on success, `None` if the tile is missing
    (HTTP 404 = not in coverage).

    Streams chunks (8 MiB) directly to disk so memory peak is bounded
    regardless of tile size. The largest München tile is 156 MB;
    `requests.get(...).content` would buffer the entire response and
    then memcpy it during the join, briefly using ~2× the tile size in
    RAM. Mid-bake, that's enough to hit MemoryError on a 16 GB machine.

    Raises `requests.HTTPError` on non-200/404 responses.
    """
    url = tile_url(easting_km=easting_km, northing_km=northing_km)
    with requests.get(
        url,
        headers={"User-Agent": USER_AGENT},
        timeout=TIMEOUT_SECONDS,
        stream=True,
    ) as response:
        if response.status_code == 404:
            return None
        response.raise_for_status()
        total = 0
        with dest_path.open("wb") as f:
            for chunk in response.iter_content(chunk_size=8 * 1024 * 1024):
                if chunk:
                    f.write(chunk)
                    total += len(chunk)
        return total


def fetch_buildings(*, min_lat: float, min_lon: float,
                    max_lat: float, max_lon: float
                    ) -> Iterator[ParsedBuilding]:
    """Iterate buildings for every 2 km UTM32N tile intersecting the
    WGS84 bbox. Each tile is streamed to a reusable temp file on disk,
    then stream-parsed via lxml.iterparse — peak memory is bounded by
    the chunk size + lxml's incremental buffer regardless of tile size.

    Caller (typically `bake.run._bake_state`) is responsible for
    binning buildings into z15 tiles.
    """
    tiles = coverage_tiles(
        min_lat=min_lat, min_lon=min_lon,
        max_lat=max_lat, max_lon=max_lon,
    )
    print(f"[bayern] {len(tiles)} UTM32N tiles to fetch",
          file=sys.stderr, flush=True)

    # One reusable temp file per state-bake — overwritten per tile.
    # Avoids creating + destroying 35k temp files (would thrash the
    # filesystem on Windows).
    tmp_dir = Path(tempfile.gettempdir())
    tmp_path = tmp_dir / f"mapbiker-bake-bayern-{os.getpid()}.gml"

    try:
        for i, (ekm, nkm) in enumerate(tiles, 1):
            try:
                size = stream_tile_to_file(
                    easting_km=ekm, northing_km=nkm,
                    dest_path=tmp_path,
                )
            except requests.HTTPError as e:
                print(
                    f"[bayern]   tile {ekm}_{nkm} HTTP error "
                    f"{e.response.status_code if e.response else '?'}"
                    f" — skipping",
                    file=sys.stderr, flush=True,
                )
                continue

            if size is None:
                # 404 — tile not in Bayernwolke coverage. Common at
                # state edges (Czech border, Austria, BW).
                continue

            size_kb = size // 1024
            print(
                f"[bayern]   {i}/{len(tiles)} tile {ekm}_{nkm} "
                f"({size_kb} KB) — parsing",
                file=sys.stderr, flush=True,
            )
            with tmp_path.open("rb") as f:
                yield from parse_citygml2_gml(f)
    finally:
        # Clean up the temp file when the iterator is exhausted or
        # the caller bails (StopIteration / GeneratorExit).
        if tmp_path.exists():
            try:
                tmp_path.unlink()
            except OSError:
                pass
