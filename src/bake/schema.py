"""Canonical wire-format schema. v2 adds BuildingAttributes (class,
height, storeys, year, raw) — see classify.py + classify_osm.py for
class-resolution. v1 stays available conceptually via /v1/lod2/ URLs
(no schema validation for it here); this module is the v2 single
source of truth.
"""
from typing import Literal, Optional
from pydantic import BaseModel, Field


class Vertex(BaseModel):
    lat: float
    lon: float
    alt: float


class Polygon(BaseModel):
    vertices: list[Vertex] = Field(min_length=4)


class BuildingAttributes(BaseModel):
    building_class: Literal["residential", "commercial", "industrial",
                            "civic", "religious", "agricultural",
                            "historic", "unknown"]
    measured_height_m: Optional[float] = None
    storeys_above_ground: Optional[int] = None
    year_of_construction: Optional[int] = None
    raw: dict[str, str] = Field(default_factory=dict)


class Building(BaseModel):
    source_id: str
    polygons: list[Polygon] = Field(min_length=1)
    attributes: BuildingAttributes


class TileCoord(BaseModel):
    z: int = Field(ge=0, le=22)
    x: int = Field(ge=0)
    y: int = Field(ge=0)


class Tile(BaseModel):
    schema_version: Literal[2]
    state: Literal["de_by", "de_nw", "de_he"]
    tile: TileCoord
    generated_at: str
    source_dataset_version: str
    buildings: list[Building]
