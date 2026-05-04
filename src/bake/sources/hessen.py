"""Hessen INSPIRE bu-core3d 4.0 WFS fetcher.

Endpoint and request shape mirror the iOS `INSPIREBuCore3DAdapter` in
`TrackRider/Services/World3D/Fetching/LoD2/INSPIREBuCore3DAdapter.swift`.
The Hessen WFS lives at `inspire-hessen.de/ows/services/...` — verified
working as of 2026-05-04.
"""
from __future__ import annotations

from typing import Iterator
from urllib.parse import urlencode

import requests

from bake.sources._bucore3d import parse_bucore3d_gml, ParsedBuilding

HE_ENDPOINT = (
    "https://inspire-hessen.de/ows/services/"
    "org.2.ef07833e-78a6-4c2c-a895-e31de788aac3_wfs"
)

USER_AGENT = "mapbiker-tile-bake (+https://github.com/boerne-lab/mapbiker)"
TIMEOUT_SECONDS = 60


def build_query_url(*, min_lat: float, min_lon: float,
                    max_lat: float, max_lon: float) -> str:
    """Build the WFS GetFeature URL for one bbox query.

    EPSG:4326 axis order is (lat, lon) — the bbox value is lat-first.
    The 3D coordinate system EPSG:7423 (also lat-first) is used for
    response geometry, so building polygons come back as
    (lat, lon, alt) triples.
    """
    params = [
        ("SERVICE", "WFS"),
        ("VERSION", "2.0.0"),
        ("REQUEST", "GetFeature"),
        ("typeNames", "bu-core3d:Building"),
        ("srsName", "http://www.opengis.net/def/crs/EPSG/0/7423"),
        ("bbox", f"{min_lat},{min_lon},{max_lat},{max_lon},"
                 f"urn:ogc:def:crs:EPSG::4326"),
        ("count", "10000"),
    ]
    return f"{HE_ENDPOINT}?{urlencode(params)}"


def fetch_buildings(*, min_lat: float, min_lon: float,
                    max_lat: float, max_lon: float
                    ) -> Iterator[ParsedBuilding]:
    """Fetch one bbox's worth of buildings from Hessen INSPIRE WFS.

    Streams the GML response through the bu-core3d parser, yielding
    one ParsedBuilding at a time. Caller is responsible for binning
    them into tiles (see `bake.retile`).

    Raises requests.HTTPError on non-2xx response.
    """
    url = build_query_url(
        min_lat=min_lat, min_lon=min_lon,
        max_lat=max_lat, max_lon=max_lon,
    )
    with requests.get(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "application/gml+xml",
        },
        timeout=TIMEOUT_SECONDS,
        stream=True,
    ) as resp:
        resp.raise_for_status()
        # `stream=True` + `resp.raw.decode_content=True` lets the GML
        # parser consume the response incrementally — important for
        # state-wide bboxes that return tens of MB.
        resp.raw.decode_content = True
        yield from parse_bucore3d_gml(resp.raw)
