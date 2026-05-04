# Tile Format v1

Canonical wire format for `mapbiker-tile-bake` output. Consumed by the
iOS `R2HostedLoD2Adapter` in the `mapbiker` repo.

## URL

`https://tiles.mapbiker.app/v1/lod2/{state_code}/{z}/{x}/{y}.json.gz`

- `state_code` ∈ `de_by`, `de_nw`, `de_he`
- `{z}/{x}/{y}` is web-mercator tile addressing (z = 15 in M1)
- HTTP `404` for keys with no buildings (state boundary, water, gap)

## Body

UTF-8 JSON, compressed with gzip, served with `Content-Encoding: gzip`.

```json
{
  "schema_version": 1,
  "state": "de_by",
  "tile": {"z": 15, "x": 17572, "y": 11308},
  "generated_at": "2026-05-15T14:23:11Z",
  "source_dataset_version": "bayernwolke-2025-Q4",
  "buildings": [
    {
      "source_id": "by_DEBY_LOD2_4906xxxxx",
      "polygons": [
        {
          "vertices": [
            {"lat": 48.1372, "lon": 11.5755, "alt": 519.2},
            {"lat": 48.1372, "lon": 11.5757, "alt": 519.2},
            {"lat": 48.1374, "lon": 11.5757, "alt": 532.4},
            {"lat": 48.1374, "lon": 11.5755, "alt": 532.4},
            {"lat": 48.1372, "lon": 11.5755, "alt": 519.2}
          ]
        }
      ]
    }
  ]
}
```

## Field semantics

- `schema_version`: always `1` for this format. v2 is a parallel-hosted format if introduced later.
- `state`: lowercased state code, redundant with the URL but useful for log forensics.
- `tile`: redundant with URL; useful for diff-debugging local files.
- `generated_at`: ISO 8601 UTC timestamp of bake. Debug metadata; client ignores.
- `source_dataset_version`: opaque string identifying the upstream snapshot. Debug metadata.
- `buildings[].source_id`: upstream `gml:id`. Stable across re-fetches.
- `buildings[].polygons[].vertices`: closed ring (first vertex == last). Each polygon is one building surface (wall, roof slope, ground). No semantic label.
- `vertices[].lat` / `lon`: WGS84 decimal degrees.
- `vertices[].alt`: NHN-relative metres above the German vertical datum.

## Empty bodies

A `200 OK` response with `"buildings": []` is valid and means "this tile is covered by the bake but contains no buildings." Equivalent to a `404`.

## Versioning

URLs include `/v1/` so a future `/v2/` can be hosted in parallel without breaking deployed iOS clients.
