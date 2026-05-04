"""Adaptive bbox chunking for WFS sources with response caps.

Hessen INSPIRE WFS caps responses at 10000 buildings (the `count`
parameter is also capped at 10000 by the server's `CountDefault`).
A state-wide bbox saturates this cap and silently truncates.

This module wraps any state-specific `fetch_buildings(*, min_lat, ...)`
function and recursively chunks the bbox: if a chunk's response hits
the cap, it's split into 4 quadrants and re-fetched; otherwise the
chunk's buildings are yielded directly.

Most rural chunks (<10 buildings) make a single quick query.
Dense urban chunks (Frankfurt-Centre, downtown Wiesbaden) recurse
1-3 levels.
"""
from __future__ import annotations

import sys
from typing import Callable, Iterator

from bake.sources._bucore3d import ParsedBuilding

FetchFn = Callable[..., Iterator[ParsedBuilding]]


def chunked_fetch(
    fetch_fn: FetchFn,
    *,
    lat_min: float,
    lon_min: float,
    lat_max: float,
    lon_max: float,
    initial_chunk_deg: float = 0.05,
    min_chunk_deg: float = 0.005,
    cap: int = 10000,
    verbose: bool = False,
) -> Iterator[ParsedBuilding]:
    """Yield all buildings in [lat_min, lon_min, lat_max, lon_max] from
    `fetch_fn`, chunking the bbox into `initial_chunk_deg`-sized cells
    and recursively halving any cell whose response hits `cap`.

    `initial_chunk_deg`: starting cell size (degrees lat/lon).
    0.05° ≈ 5 km at DACH latitudes — a reasonable starting point.

    `min_chunk_deg`: hard floor for recursive halving. 0.005° ≈ 500 m.
    If a chunk this small still hits the cap, we yield what we got
    (truncated) and warn — better than infinite recursion.

    `cap`: the buildings-per-response cap of the upstream WFS. INSPIRE
    bu-core3d 4.0 endpoints hit 10000.

    `verbose`: when true, prints a progress line per leaf chunk to
    stderr — useful for state-scale bakes that take 30+ minutes.
    """
    yield from _chunk_recursive(
        fetch_fn,
        lat_min=lat_min, lon_min=lon_min,
        lat_max=lat_max, lon_max=lon_max,
        chunk_deg=initial_chunk_deg,
        min_chunk_deg=min_chunk_deg,
        cap=cap,
        verbose=verbose,
        depth=0,
    )


def _chunk_recursive(
    fetch_fn: FetchFn, *,
    lat_min: float, lon_min: float,
    lat_max: float, lon_max: float,
    chunk_deg: float, min_chunk_deg: float,
    cap: int, verbose: bool, depth: int,
) -> Iterator[ParsedBuilding]:
    """Tile [bbox] into chunk_deg-sized cells. Each cell is fetched;
    cap-hit cells recurse with chunk_deg / 2."""
    cy = lat_min
    while cy < lat_max:
        cy_next = min(cy + chunk_deg, lat_max)
        cx = lon_min
        while cx < lon_max:
            cx_next = min(cx + chunk_deg, lon_max)

            cell_buildings = list(fetch_fn(
                min_lat=cy, min_lon=cx,
                max_lat=cy_next, max_lon=cx_next,
            ))

            if len(cell_buildings) >= cap and chunk_deg > min_chunk_deg:
                # Cap hit; recurse with halved chunk_deg.
                if verbose:
                    print(
                        f"  [chunk] depth={depth} cell "
                        f"({cy:.4f},{cx:.4f})-({cy_next:.4f},{cx_next:.4f}) "
                        f"hit cap ({len(cell_buildings)}); splitting",
                        file=sys.stderr, flush=True,
                    )
                yield from _chunk_recursive(
                    fetch_fn,
                    lat_min=cy, lon_min=cx,
                    lat_max=cy_next, lon_max=cx_next,
                    chunk_deg=chunk_deg / 2,
                    min_chunk_deg=min_chunk_deg,
                    cap=cap, verbose=verbose, depth=depth + 1,
                )
            else:
                if len(cell_buildings) >= cap:
                    print(
                        f"  [chunk] WARN cell "
                        f"({cy:.4f},{cx:.4f})-({cy_next:.4f},{cx_next:.4f}) "
                        f"hit cap at min chunk size {min_chunk_deg} "
                        f"({len(cell_buildings)} buildings); "
                        f"data may be truncated",
                        file=sys.stderr, flush=True,
                    )
                if verbose:
                    print(
                        f"  [chunk] depth={depth} cell "
                        f"({cy:.4f},{cx:.4f}) → "
                        f"{len(cell_buildings)} buildings",
                        file=sys.stderr, flush=True,
                    )
                yield from cell_buildings

            cx = cx_next
        cy = cy_next
