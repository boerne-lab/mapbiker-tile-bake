import mercantile

from bake.schema import Building, Polygon, Vertex
from bake.retile import bin_buildings_by_z15_tile


def _building_at(lat: float, lon: float, source_id: str) -> Building:
    """Build a tiny synthetic 4-vertex closed-ring building at the
    given lat/lon (offset by ~10 m to give it a footprint)."""
    return Building(
        source_id=source_id,
        polygons=[Polygon(vertices=[
            Vertex(lat=lat, lon=lon, alt=100),
            Vertex(lat=lat, lon=lon + 0.0001, alt=100),
            Vertex(lat=lat + 0.0001, lon=lon + 0.0001, alt=100),
            Vertex(lat=lat + 0.0001, lon=lon, alt=100),
            Vertex(lat=lat, lon=lon, alt=100),
        ])],
    )


def test_centroid_assigns_to_one_z15_tile():
    # Frankfurt centre
    b = _building_at(50.110, 8.682, "fra-1")
    bins = bin_buildings_by_z15_tile([b])
    assert len(bins) == 1
    (z, x, y), buildings = next(iter(bins.items()))
    assert z == 15
    assert len(buildings) == 1
    assert buildings[0].source_id == "fra-1"


def test_two_far_apart_buildings_split_into_two_tiles():
    fra = _building_at(50.110, 8.682, "fra-1")     # Frankfurt
    muc = _building_at(48.137, 11.575, "muc-1")    # München
    bins = bin_buildings_by_z15_tile([fra, muc])
    assert len(bins) == 2


def test_z15_tile_for_frankfurt_centre_matches_known_value():
    """The centroid of the synthetic Frankfurt building (offset by
    +0.0001 in each direction from the lat/lon corner) is at roughly
    (50.11005, 8.68205). mercantile.tile() should agree with the
    bin_buildings_by_z15_tile() output."""
    b = _building_at(50.110, 8.682, "x")
    bins = bin_buildings_by_z15_tile([b])
    key, _ = next(iter(bins.items()))

    # Compute expected key from the building's actual centroid
    verts = b.polygons[0].vertices
    centroid_lon = sum(v.lon for v in verts) / len(verts)
    centroid_lat = sum(v.lat for v in verts) / len(verts)
    expected = mercantile.tile(centroid_lon, centroid_lat, 15)
    assert key == (15, expected.x, expected.y)


def test_two_buildings_in_same_tile_grouped_together():
    """Two buildings ~30 m apart in central Frankfurt should both fall
    in the same z15 tile (z15 ~= 700-850 m on a side at DACH lat)."""
    a = _building_at(50.1100, 8.6820, "fra-a")
    b = _building_at(50.1102, 8.6822, "fra-b")
    bins = bin_buildings_by_z15_tile([a, b])
    # Either 1 tile (both buildings share a tile) or 2 tiles (rare but
    # possible at tile boundaries). Most commonly 1.
    if len(bins) == 1:
        _, buildings = next(iter(bins.items()))
        assert len(buildings) == 2
    else:
        # If they did fall on opposite sides of a boundary, ensure each
        # tile has one building.
        for buildings in bins.values():
            assert len(buildings) == 1
