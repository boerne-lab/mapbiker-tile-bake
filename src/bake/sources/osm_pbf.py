"""pyosmium streaming handler that emits OSMTile per z15 tile bbox."""
from __future__ import annotations

import datetime
from pathlib import Path
from typing import Iterator

import mercantile
import osmium

from bake.schema_osm import (
    OSMTile, TileCoord, Coord,
    Building, Road, Railway, Tree, Forest, LandUse,
    Waterway, WaterPolygon, TrafficSignal, Bridge,
)
from bake.normalize.classify_osm import (
    classify_building, classify_landuse, classify_road,
    classify_surface, classify_railway, classify_tree_species,
    classify_sidewalks,
)


Z = 15


def _tile_for_coord(lat: float, lon: float) -> tuple[int, int]:
    t = mercantile.tile(lon, lat, Z)
    return (t.x, t.y)


def _coord_centroid(coords: list[Coord]) -> tuple[float, float]:
    if not coords:
        return (0.0, 0.0)
    return (
        sum(c.lat for c in coords) / len(coords),
        sum(c.lon for c in coords) / len(coords),
    )


def _parse_float(val: str | None) -> float | None:
    if val is None:
        return None
    try:
        return float(val)
    except (ValueError, TypeError):
        return None


def _parse_int(val: str | None) -> int | None:
    if val is None:
        return None
    try:
        return int(val)
    except (ValueError, TypeError):
        return None


class _Handler(osmium.SimpleHandler):
    def __init__(self):
        super().__init__()
        self.bins: dict[tuple[int, int], dict[str, list]] = {}

    def _bin(self, x: int, y: int) -> dict[str, list]:
        key = (x, y)
        if key not in self.bins:
            self.bins[key] = {
                "buildings": [], "roads": [], "waterways": [],
                "water_polygons": [], "railways": [],
                "traffic_signals": [], "trees": [], "forests": [],
                "bridges": [], "landuse": [],
            }
        return self.bins[key]

    def node(self, n):
        if not n.location.valid():
            return
        tags = dict(n.tags)
        lat, lon = n.location.lat, n.location.lon
        x, y = _tile_for_coord(lat, lon)
        bin_ = self._bin(x, y)

        if tags.get("highway") in {"traffic_signals", "stop", "give_way"}:
            bin_["traffic_signals"].append(TrafficSignal(
                id=n.id,
                coordinate=Coord(lat=lat, lon=lon),
                kind=tags["highway"],
            ))
        elif tags.get("natural") == "tree":
            bin_["trees"].append(Tree(
                id=n.id,
                coordinate=Coord(lat=lat, lon=lon),
                leaf_type=tags.get("leaf_type"),
                genus=tags.get("genus"),
                species_class=classify_tree_species(
                    leaf_type=tags.get("leaf_type"),
                    genus=tags.get("genus"),
                ),
                crown_diameter_m=_parse_float(tags.get("diameter_crown")),
                height_m=_parse_float(tags.get("height")),
            ))

    def way(self, w):
        try:
            coords = [
                Coord(lat=node.lat, lon=node.lon)
                for node in w.nodes
                if node.location.valid()
            ]
        except Exception:
            return
        if len(coords) < 2:
            return

        tags = dict(w.tags)
        cy, cx = _coord_centroid(coords)
        x, y = _tile_for_coord(cy, cx)
        bin_ = self._bin(x, y)

        is_closed = (
            len(coords) >= 4
            and coords[0].lat == coords[-1].lat
            and coords[0].lon == coords[-1].lon
        )

        if "building" in tags and is_closed:
            self._add_building(bin_, w.id, coords, tags)
        elif "highway" in tags and tags["highway"] not in {
            "traffic_signals", "stop", "give_way"
        }:
            self._add_road(bin_, w.id, coords, tags)
        elif "railway" in tags:
            self._add_railway(bin_, w.id, coords, tags)
        elif tags.get("waterway"):
            bin_["waterways"].append(Waterway(
                id=w.id,
                coordinates=coords,
                kind=tags["waterway"],
                name=tags.get("name"),
                width_m=_parse_float(tags.get("width")),
            ))
        elif (tags.get("natural") == "water" or "water" in tags) and is_closed:
            bin_["water_polygons"].append(WaterPolygon(
                id=w.id,
                coordinates=coords,
                name=tags.get("name"),
            ))
        elif (tags.get("landuse") == "forest" or tags.get("natural") == "wood") and is_closed:
            bin_["forests"].append(Forest(
                id=w.id,
                coordinates=coords,
                leaf_type=tags.get("leaf_type"),
                species_class=classify_tree_species(
                    leaf_type=tags.get("leaf_type"),
                    genus=tags.get("genus"),
                ),
                leaf_cycle=tags.get("leaf_cycle"),
            ))
        elif is_closed and ("landuse" in tags or "natural" in tags):
            cls = classify_landuse(
                landuse=tags.get("landuse"),
                natural=tags.get("natural"),
            )
            raw_tag: dict[str, str] = {}
            if "landuse" in tags:
                raw_tag["landuse"] = tags["landuse"]
            if "natural" in tags:
                raw_tag["natural"] = tags["natural"]
            bin_["landuse"].append(LandUse(
                id=w.id,
                coordinates=coords,
                landuse_class=cls,
                raw_tag=raw_tag,
            ))

        if tags.get("bridge") == "yes":
            bin_["bridges"].append(Bridge(
                id=w.id,
                name=tags.get("name"),
                structure=tags.get("bridge:structure"),
            ))

    def _add_building(self, bin_: dict, wid: int, coords: list[Coord], tags: dict):
        h = _parse_float(tags.get("height")) or _parse_float(tags.get("building:height"))
        bin_["buildings"].append(Building(
            id=wid,
            coordinates=coords,
            levels=_parse_int(tags.get("building:levels")),
            height_m=h,
            roof_shape=tags.get("roof:shape"),
            roof_height_m=_parse_float(tags.get("roof:height")),
            roof_levels=_parse_int(tags.get("roof:levels")),
            building_type=tags.get("building"),
            building_class=classify_building(tags.get("building")),
            wikidata=tags.get("wikidata"),
            historic=tags.get("historic"),
            name=tags.get("name"),
        ))

    def _add_road(self, bin_: dict, wid: int, coords: list[Coord], tags: dict):
        try:
            layer = int(tags.get("layer", "0"))
        except (ValueError, TypeError):
            layer = 0
        sidewalk_left, sidewalk_right = classify_sidewalks(
            tags=tags, highway=tags["highway"]
        )
        bin_["roads"].append(Road(
            id=wid,
            coordinates=coords,
            highway=tags["highway"],
            road_class=classify_road(tags["highway"]),
            surface=tags.get("surface"),
            surface_class=classify_surface(tags.get("surface")),
            name=tags.get("name"),
            lanes=_parse_int(tags.get("lanes")),
            is_bridge=(tags.get("bridge") == "yes"),
            layer=layer,
            cycleway=tags.get("cycleway"),
            sidewalk_left=sidewalk_left,
            sidewalk_right=sidewalk_right,
        ))

    def _add_railway(self, bin_: dict, wid: int, coords: list[Coord], tags: dict):
        bin_["railways"].append(Railway(
            id=wid,
            coordinates=coords,
            kind=tags["railway"],
            railway_class=classify_railway(tags["railway"]),
            name=tags.get("name"),
            is_bridge=(tags.get("bridge") == "yes"),
            is_tunnel=(tags.get("tunnel") == "yes"),
        ))


def parse_pbf(
    path: Path | str,
    *,
    state: str,
    source_version: str,
) -> Iterator[OSMTile]:
    """Stream-parse a PBF, emit one OSMTile per non-empty z15-bin."""
    h = _Handler()
    h.apply_file(str(path), locations=True, idx="flex_mem")

    now = datetime.datetime.utcnow().isoformat() + "Z"
    for (x, y), bin_ in h.bins.items():
        if not any(bin_.values()):
            continue
        yield OSMTile(
            schema_version=2,
            state=state,
            tile=TileCoord(z=Z, x=x, y=y),
            generated_at=now,
            source_dataset_version=source_version,
            **bin_,
        )
