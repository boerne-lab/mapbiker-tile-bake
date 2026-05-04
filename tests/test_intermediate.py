import tempfile
from pathlib import Path

from bake.intermediate import IntermediateStore
from bake.schema import Building, Polygon, Vertex


def _sample_building(source_id: str, lat: float = 50.1) -> Building:
    return Building(
        source_id=source_id,
        polygons=[Polygon(vertices=[
            Vertex(lat=lat, lon=8.7, alt=100),
            Vertex(lat=lat, lon=8.71, alt=100),
            Vertex(lat=lat + 0.001, lon=8.71, alt=100),
            Vertex(lat=lat + 0.001, lon=8.7, alt=100),
            Vertex(lat=lat, lon=8.7, alt=100),
        ])],
    )


def test_append_and_read_round_trip():
    with tempfile.TemporaryDirectory() as tmp:
        store = IntermediateStore(Path(tmp), state="de_he")
        b1 = _sample_building("b1")
        b2 = _sample_building("b2")
        store.append_building(z=15, x=17171, y=11094, building=b1)
        store.append_building(z=15, x=17171, y=11094, building=b2)
        out = store.read_tile(z=15, x=17171, y=11094)
        assert len(out) == 2
        assert {b.source_id for b in out} == {"b1", "b2"}


def test_iter_tile_keys_finds_appended_tiles():
    with tempfile.TemporaryDirectory() as tmp:
        store = IntermediateStore(Path(tmp), state="de_by")
        store.append_building(z=15, x=17572, y=11308,
                              building=_sample_building("muc"))
        store.append_building(z=15, x=17171, y=11094,
                              building=_sample_building("fra"))
        keys = sorted(store.iter_tile_keys())
        assert (15, 17171, 11094) in keys
        assert (15, 17572, 11308) in keys


def test_clear_tile_removes_file():
    with tempfile.TemporaryDirectory() as tmp:
        store = IntermediateStore(Path(tmp), state="de_he")
        store.append_building(z=15, x=1, y=2,
                              building=_sample_building("b1"))
        assert store.read_tile(z=15, x=1, y=2) != []
        store.clear_tile(z=15, x=1, y=2)
        assert store.read_tile(z=15, x=1, y=2) == []


def test_clear_all_wipes_state_root():
    with tempfile.TemporaryDirectory() as tmp:
        store = IntermediateStore(Path(tmp), state="de_he")
        for x in range(5):
            store.append_building(z=15, x=x, y=2,
                                  building=_sample_building(f"b{x}"))
        store.clear_all()
        assert list(store.iter_tile_keys()) == []


def test_separate_states_dont_interfere():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        store_he = IntermediateStore(root, state="de_he")
        store_by = IntermediateStore(root, state="de_by")
        store_he.append_building(z=15, x=1, y=1,
                                 building=_sample_building("he"))
        store_by.append_building(z=15, x=1, y=1,
                                 building=_sample_building("by"))
        # Same (z,x,y) coords but different states — no interference.
        he_out = store_he.read_tile(z=15, x=1, y=1)
        by_out = store_by.read_tile(z=15, x=1, y=1)
        assert len(he_out) == 1 and he_out[0].source_id == "he"
        assert len(by_out) == 1 and by_out[0].source_id == "by"
