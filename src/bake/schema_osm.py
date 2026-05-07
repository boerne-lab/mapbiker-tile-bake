"""OSM Wire-format-v1 schema. Parallel to LoD2 schema.py — separate
version space, separate URL pfade (/v1/osm/{state}/...). Class-Felder
REQUIRED, raw OSM tags preserved as escape-hatch for sub-classification
without re-bake."""
from typing import Literal, Optional
from pydantic import BaseModel, Field


class Coord(BaseModel):
    lat: float
    lon: float


class TileCoord(BaseModel):
    z: int = Field(ge=0, le=22)
    x: int = Field(ge=0)
    y: int = Field(ge=0)


class Building(BaseModel):
    id: int
    coordinates: list[Coord] = Field(min_length=3)
    levels: Optional[int] = None
    height_m: Optional[float] = None
    roof_shape: Optional[str] = None
    roof_height_m: Optional[float] = None
    roof_levels: Optional[int] = None
    building_type: Optional[str] = None
    building_class: str
    wikidata: Optional[str] = None
    historic: Optional[str] = None
    name: Optional[str] = None


class Road(BaseModel):
    id: int
    coordinates: list[Coord] = Field(min_length=2)
    highway: str
    road_class: str
    surface: Optional[str] = None
    surface_class: str
    name: Optional[str] = None
    lanes: Optional[int] = None
    is_bridge: bool = False
    layer: int = 0
    cycleway: Optional[str] = None


class Railway(BaseModel):
    id: int
    coordinates: list[Coord] = Field(min_length=2)
    kind: str
    railway_class: str
    name: Optional[str] = None
    is_bridge: bool = False
    is_tunnel: bool = False


class Tree(BaseModel):
    id: int
    coordinate: Coord
    leaf_type: Optional[str] = None
    genus: Optional[str] = None
    species_class: str
    crown_diameter_m: Optional[float] = None
    height_m: Optional[float] = None


class Forest(BaseModel):
    id: int
    coordinates: list[Coord] = Field(min_length=3)
    leaf_type: Optional[str] = None
    species_class: str
    leaf_cycle: Optional[str] = None


class LandUse(BaseModel):
    id: int
    coordinates: list[Coord] = Field(min_length=3)
    landuse_class: str
    raw_tag: dict[str, str] = Field(default_factory=dict)


class Waterway(BaseModel):
    id: int
    coordinates: list[Coord] = Field(min_length=2)
    kind: str
    name: Optional[str] = None
    width_m: Optional[float] = None


class WaterPolygon(BaseModel):
    id: int
    coordinates: list[Coord] = Field(min_length=3)
    name: Optional[str] = None


class TrafficSignal(BaseModel):
    id: int
    coordinate: Coord
    kind: str


class Bridge(BaseModel):
    id: int
    name: Optional[str] = None
    structure: Optional[str] = None


class OSMTile(BaseModel):
    schema_version: Literal[1]
    state: Literal["de_by", "de_nw", "de_he", "de_be", "de_bb",
                   "de_bw", "de_hh", "de_hb", "de_mv", "de_ni",
                   "de_rp", "de_sh", "de_sl", "de_sn", "de_st", "de_th"]
    tile: TileCoord
    generated_at: str
    source_dataset_version: str
    buildings: list[Building]
    roads: list[Road]
    waterways: list[Waterway]
    water_polygons: list[WaterPolygon]
    railways: list[Railway]
    traffic_signals: list[TrafficSignal]
    trees: list[Tree]
    forests: list[Forest]
    bridges: list[Bridge]
    landuse: list[LandUse]
