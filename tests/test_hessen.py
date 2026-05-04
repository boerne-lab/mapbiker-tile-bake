from urllib.parse import urlparse, parse_qs
from bake.sources.hessen import build_query_url, HE_ENDPOINT


def test_build_query_url_has_required_params():
    url = build_query_url(min_lat=50.10, min_lon=8.66,
                          max_lat=50.12, max_lon=8.69)
    p = urlparse(url)
    q = parse_qs(p.query)
    assert q["SERVICE"] == ["WFS"]
    assert q["VERSION"] == ["2.0.0"]
    assert q["REQUEST"] == ["GetFeature"]
    assert q["typeNames"] == ["bu-core3d:Building"]
    assert q["count"] == ["10000"]
    assert q["srsName"] == ["http://www.opengis.net/def/crs/EPSG/0/7423"]


def test_build_query_url_bbox_is_lat_first():
    """EPSG:4326 axis order is (latitude, longitude). The bbox value
    must be lat,lon,lat,lon — verified empirically against the live
    Hessen WFS that lon-first returns empty results."""
    url = build_query_url(min_lat=50.10, min_lon=8.66,
                          max_lat=50.12, max_lon=8.69)
    p = urlparse(url)
    q = parse_qs(p.query)
    bbox_value = q["bbox"][0]
    # Expect "50.1,8.66,50.12,8.69,urn:ogc:def:crs:EPSG::4326"
    # (parse_qs decodes %2C back to comma)
    assert bbox_value == "50.1,8.66,50.12,8.69,urn:ogc:def:crs:EPSG::4326"


def test_endpoint_constant_is_hessen_inspire():
    assert HE_ENDPOINT.startswith("https://")
    assert "inspire-hessen.de" in HE_ENDPOINT
