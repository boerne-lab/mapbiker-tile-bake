"""Canonical wire-format schema for tile-format-v1.

Mirrors the iOS Codable types defined in R2HostedLoD2Adapter.swift —
keep both in lock-step when the schema evolves (v2, etc.).
"""
from typing import Literal
from pydantic import BaseModel, Field


class Vertex(BaseModel):
    lat: float
    lon: float
    alt: float


class Polygon(BaseModel):
    vertices: list[Vertex] = Field(min_length=4)
    # min_length=4 because a closed ring on a 3-point footprint has
    # 4 vertices (first == last).


class Building(BaseModel):
    source_id: str
    polygons: list[Polygon] = Field(min_length=1)


class TileCoord(BaseModel):
    z: int = Field(ge=0, le=22)
    x: int = Field(ge=0)
    y: int = Field(ge=0)


class Tile(BaseModel):
    schema_version: Literal[1]
    state: Literal["de_by", "de_nw", "de_he"]
    tile: TileCoord
    generated_at: str
    source_dataset_version: str
    buildings: list[Building]
