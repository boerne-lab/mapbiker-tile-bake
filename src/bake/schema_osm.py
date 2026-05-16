"""OSM Wire-format-v3 schema. Parallel to LoD2 schema.py — separate
version space, separate URL pfade (/v3/osm/{state}/...). Class-Felder REQUIRED.

v2 vs v1 (2026-05-13):
- Road gains REQUIRED `sidewalk_left: bool` + `sidewalk_right: bool` flags,
  computed bake-side from `sidewalk=*` OSM tag + per-side overrides +
  highway-class default (see `classify_sidewalks`). v1 tiles remain on
  /v1/osm/ on R2 for roll-back; v2 tiles ship under /v2/osm/.

v3 vs v2 (2026-05-14):
- Road gains optional `width_m`, `is_tunnel`, `maxspeed` fields.
- Building gains optional `colour`, `roof_colour`, `material`, `roof_material`.
- WaterPolygon gains optional `kind` (lake/pond/canal/reservoir/basin/river).
- Tree gains optional `taxon` (Wikidata QID for genus/species precision).
- NEW: Barrier model (hedges, fences, walls) + OSMTile.barriers list.
  v2 tiles remain on /v2/osm/ for roll-back; v3 tiles ship under /v3/osm/.
"""
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
    # v3 additions
    colour: Optional[str] = None        # raw OSM building:colour value (e.g. "white", "#a0522d")
    roof_colour: Optional[str] = None   # raw OSM roof:colour value
    material: Optional[str] = None      # mapped via OSM_BUILDING_MATERIAL_TO_CLASS
    roof_material: Optional[str] = None  # mapped via OSM_ROOF_MATERIAL_TO_CLASS


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
    # Sidewalk flags — computed bake-side from `sidewalk=*` OSM tag
    # plus per-side overrides plus highway-class default fallback
    # (see `classify_sidewalks` in bake.normalize.classify_osm).
    # REQUIRED so iOS always has a defined value; pre-bake assigns
    # explicitly. European urban streets almost always have at
    # least one sidewalk; without these flags the rendered world
    # reads as "industrial backroad" everywhere.
    sidewalk_left: bool
    sidewalk_right: bool
    # v3 additions
    width_m: Optional[float] = None   # OSM width=* in metres
    is_tunnel: bool = False            # OSM tunnel=yes (mirrors is_bridge)
    maxspeed: Optional[int] = None    # OSM maxspeed=* in km/h (integers only; "DE:urban" etc. → None)


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
    # v3 addition
    taxon: Optional[str] = None   # Wikidata QID for genus/species precision


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
    # v3 addition
    kind: Optional[str] = None   # subtype: lake/pond/canal/reservoir/basin/river


class Barrier(BaseModel):
    """Linear barrier ways — hedges, fences, walls.

    Visual layer for cycling-world stylization. `kind` is one of:
    `hedge`, `fence`, `wall`, `ignore`. Entries classified as `ignore`
    (e.g. kerbs that are part of road geometry) are dropped at bake time.
    """
    id: int
    coordinates: list[Coord] = Field(min_length=2)
    kind: str   # mapped via OSM_BARRIER_TO_CLASS, REQUIRED
    height_m: Optional[float] = None   # if `height=*` is set; useful for walls
    name: Optional[str] = None


class TrafficSignal(BaseModel):
    id: int
    coordinate: Coord
    kind: str


class Bridge(BaseModel):
    id: int
    name: Optional[str] = None
    structure: Optional[str] = None


class TrafficIsland(BaseModel):
    """Verkehrsinsel — a small raised polygon at a road intersection or
    between traffic lanes, separating flows and offering pedestrians
    refuge. Tagged in OSM as either:
        - `area:highway=traffic_island` (newer Carto convention)
        - `highway=traffic_island` on a closed way (older)
        - `traffic_calming=island` (sometimes on a closed way for
          actual polygons; for nodes we do not extract — needs a
          separate `traffic_calming` node layer)
    iOS rendering: small flat polygon ~5 cm above terrain, concrete-
    grey color, optionally with a slight kerb-edge bevel.
    """
    id: int
    coordinates: list[Coord] = Field(min_length=3)
    name: Optional[str] = None


class OSMTile(BaseModel):
    schema_version: Literal[3]
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
    barriers: list[Barrier]
    # v3 backward-compatible addition (May 2026): traffic islands.
    # Default empty so pre-v3.1 tiles still validate. Schema_version
    # stays at 3 — iOS clients that don't know the field ignore it.
    traffic_islands: list[TrafficIsland] = Field(default_factory=list)
