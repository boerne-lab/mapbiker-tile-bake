"""Build tiny PBF fixtures via pyosmium SimpleWriter. Run once; commit outputs."""
from pathlib import Path
import osmium
import osmium.osm.mutable

OUT = Path(__file__).parent


def write_pbf(name: str, nodes: list, ways: list = None):
    pbf_file = OUT / f"{name}.osm.pbf"
    writer = osmium.SimpleWriter(str(pbf_file), overwrite=True)
    for node in nodes:
        writer.add_node(node)
    if ways:
        for way in ways:
            writer.add_way(way)
    writer.close()
    print(f"Wrote {pbf_file}")


def mk_node(node_id: int, lat: float, lon: float, tags: dict = None):
    return osmium.osm.mutable.Node(
        id=node_id,
        location=(lon, lat),  # osmium Location is (lon, lat)
        tags=tags or {},
    )


def mk_way(way_id: int, node_refs: list, tags: dict = None):
    return osmium.osm.mutable.Way(
        id=way_id,
        nodes=node_refs,
        tags=tags or {},
    )


# Fixture 1: building polygon with full tags
write_pbf(
    "building_residential",
    nodes=[
        mk_node(1, 50.110, 8.680),
        mk_node(2, 50.111, 8.680),
        mk_node(3, 50.111, 8.681),
        mk_node(4, 50.110, 8.681),
    ],
    ways=[
        mk_way(100, [1, 2, 3, 4, 1], tags={
            "building": "residential",
            "building:levels": "5",
            "height": "18.4",
            "wikidata": "Q42",
            "name": "Test Haus",
        }),
    ],
)

# Fixture 2: landuse polygon
write_pbf(
    "landuse_farmland",
    nodes=[
        mk_node(1, 50.0, 8.0),
        mk_node(2, 50.001, 8.0),
        mk_node(3, 50.001, 8.001),
        mk_node(4, 50.0, 8.001),
    ],
    ways=[
        mk_way(100, [1, 2, 3, 4, 1], tags={"landuse": "farmland"}),
    ],
)

# Fixture 3: tree node with genus
write_pbf(
    "tree_prunus",
    nodes=[
        mk_node(1, 50.0, 8.0, tags={"natural": "tree", "genus": "Prunus"}),
    ],
)
