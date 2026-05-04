"""Bin schema Buildings into web-mercator z15 tile buckets.

Centroid-assignment: each building lives in exactly one tile (the one
containing the centroid of its first polygon's vertices). Buildings
whose footprint crosses a tile boundary are NOT replicated in v1 —
a deliberate spec choice. If iPad smoke tests show conspicuous
boundary gaps later, switch to all-overlapping-tiles replication.

z15 chosen to match the iOS `TileFetcher`'s fixed corridor zoom level
(see TileID.swift line 6-7 in the mapbiker repo).
"""
from __future__ import annotations

from collections import defaultdict

import mercantile

from bake.schema import Building

ZOOM = 15

# Bin key: (z, x, y) — mirrors the local file path layout
# v1/lod2/{state}/{z}/{x}/{y}.json.gz
TileKey = tuple[int, int, int]


def _centroid_lonlat(building: Building) -> tuple[float, float]:
    """Mean of the first polygon's vertices, returned as (lon, lat).

    Sufficient for binning — we don't need a planimetric centroid,
    just a stable point inside the building's footprint.
    """
    verts = building.polygons[0].vertices
    n = len(verts)
    return (
        sum(v.lon for v in verts) / n,
        sum(v.lat for v in verts) / n,
    )


def bin_buildings_by_z15_tile(
    buildings: list[Building],
) -> dict[TileKey, list[Building]]:
    """Group `buildings` by the z15 tile containing each one's centroid.

    Returns a dict keyed by `(15, x, y)`. Buildings that share a tile
    appear together in the value list. Empty input returns an empty dict.
    """
    bins: dict[TileKey, list[Building]] = defaultdict(list)
    for b in buildings:
        lon, lat = _centroid_lonlat(b)
        tile = mercantile.tile(lon, lat, ZOOM)
        bins[(ZOOM, tile.x, tile.y)].append(b)
    return dict(bins)
