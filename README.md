# mapbiker-tile-bake

Pipeline that bakes LoD2 building tiles for the [mapbiker](https://github.com/boerne-lab/mapbiker)
iOS app. Pulls source data from German Bundesland LoD2 services,
normalises to a common per-tile JSON schema, and uploads to a
Cloudflare R2 bucket. Schema contract: see [`docs/tile-format-v1.md`](docs/tile-format-v1.md).

## State coverage

| State | Source | Endpoint | Status |
|---|---|---|---|
| Hessen (HE) | INSPIRE bu-core3d 4.0 WFS | `inspire-hessen.de/...` | M1 active |
| Bayern (BY) | Bayernwolke CityGML 2.0 | `download1.bayernwolke.de/a/lod2/citygml/{ekm}_{nkm}.gml` | M1 active |
| NRW | OGC API + bulk download | `opengeodata.nrw.de/produkte/geobasis/3dg/lod2_gml/` | deferred to M1.5 |

Each state has its own fetcher in `src/bake/sources/`. The CityGML 2.0 parser
(`_citygml2.py`) is shared between Bayern and the future NRW bulk-download path.
The bu-core3d parser (`_bucore3d.py`) is shared by Hessen and any future
INSPIRE WFS state.

## Setup

```bash
python -m venv .venv
.venv\Scripts\activate    # Windows; on macOS/Linux: source .venv/bin/activate
pip install -e ".[dev]"
pytest -v
```

A `.env` file at the repo root (gitignored) provides R2 credentials:

```
R2_ACCESS_KEY_ID=<your access key>
R2_SECRET_ACCESS_KEY=<your secret>
R2_ENDPOINT=https://<account-id>.r2.cloudflarestorage.com
R2_BUCKET=mapbiker-tiles
R2_PUBLIC_URL=https://pub-<hash>.r2.dev
```

`bake.upload` loads these via `python-dotenv` at module import time.

## Run-book

### Re-bake one state (yearly maintenance)

```bash
.venv\Scripts\activate
python -m bake.run all --state he --source-version hessen-YYYY-QN
python -m bake.run all --state by --source-version bayern-YYYY-QN
```

`--source-version` is an opaque dataset-version string written into every
emitted tile's `source_dataset_version` field. Useful for forensics —
when the iOS app sees buildings that look out of date, this string in
the tile JSON tells you exactly which bake produced it.

`--no-upload` runs the full pipeline locally without hitting R2.
Useful for dry-runs or for inspecting the local `data/tiled/` output
before publishing.

### Wall-time estimates

| State | Wall time | Bottleneck |
|---|---|---|
| Hessen | ~30-90 min | INSPIRE WFS server-side latency, recursive bbox-chunking around dense urban areas |
| Bayern | **~8-15 hours** | Bulk download (~200 GB raw CityGML) + parsing 156 MB urban tiles |

Disk-space requirements:

- Hessen: ~5-10 GB peak
- Bayern: **~200-400 GB peak** local disk for `data/raw/` + `data/tiled/`

`data/` is gitignored. Safe to delete between bakes (`rmdir /s /q data` on Windows).

### Per-state pipeline overview

The five bake stages run sequentially per state:

1. **Fetch** — state-specific `bake.sources.{state}.fetch_buildings()`
   - Hessen: bbox-queries the WFS in adaptive chunks (recursively halves on 10000-cap)
   - Bayern: enumerates UTM32N 2 km × 2 km tile coverage, downloads each `.gml` file once
2. **Parse** — state-specific GML parser yields `ParsedBuilding` records
3. **Normalize** — `bake.normalize.to_schema_building` converts to wire-format `Building`
4. **Retile** — `bake.retile.bin_buildings_by_z15_tile` bins by web-mercator z15 centroid
5. **Pack + upload** — `bake.pack.write_tile_file` writes gzipped JSON, `bake.upload.upload_tile` ships to R2 with `Content-Encoding: gzip`

Output URLs:

```
https://pub-<hash>.r2.dev/v1/lod2/{state}/{z}/{x}/{y}.json.gz

de_he/15/17171/11094.json.gz   # Hessen tile
de_by/15/17572/11308.json.gz   # Bayern tile
```

### Verify a tile is reachable

```bash
curl -s "https://pub-<hash>.r2.dev/v1/lod2/de_he/15/17171/11094.json.gz" \
  --compressed \
  | python -m json.tool \
  | head
```

The `--compressed` flag tells curl to send `Accept-Encoding: gzip` — Cloudflare
auto-decompresses; the JSON arrives plain. (iOS `URLSession` does the same
transparently — see `R2HostedLoD2Adapter.swift` in the mapbiker repo.)

### Local data directory cleanup

```bash
rmdir /s /q data   # Windows
rm -rf data        # macOS/Linux
```

`data/raw/`, `data/normalized/`, `data/tiled/`, `data/tiled_full/` —
all gitignored, all expendable between bakes.

## Cloudflare setup (one-time)

The R2 bucket `mapbiker-tiles` was configured 2026-05-04:

- **Bucket**: `mapbiker-tiles`, location automatic
- **Public access**: r2.dev subdomain enabled
  (`https://pub-fdb4dff2c852412692b686e8cef0e28d.r2.dev`)
- **API token**: Object Read & Write scoped to this bucket only

If the bucket needs to be re-created (lost-account, migration, etc.),
re-do these steps via the Cloudflare dashboard. The bake pipeline
re-uploads idempotently, so a fresh bucket is back in service in
~30 min for HE + ~8-15 h for BY of pipeline run.

The r2.dev subdomain is intended for development; pre-launch we
will swap to a custom domain (`tiles.<our-domain>`). That requires
the domain's DNS to be on Cloudflare. Code change is one-line in
the iOS `R2HostedLoD2Adapter.Config.{state}R2(baseURL:)` factories.

## License

Code: proprietary.

The data this pipeline produces is licensed by the upstream publishers:

- **Hessen**: dl-de/zero-2.0 (no attribution legally required; courteously included)
- **Bayern**: CC BY 4.0, attribution required: "© Bayerische Vermessungsverwaltung – CC BY 4.0"
- **NRW** (future): dl-de/zero-2.0

Attribution strings live in the iOS `R2HostedLoD2Adapter.Config` factories
(`bayernR2`, `nrwR2`, `hessenR2`) and are surfaced via the app's Attribution view.

## OSM Bake Pipeline (added 2026-05)

Parallel to LoD2, OSM data is also baked to R2 for HE/BY/NRW. Wire-format
**v2** carries normalized class-systems (building / landuse / road / surface /
railway / species), pedestrian-sidewalk presence flags per road (`sidewalk_left`,
`sidewalk_right`), plus raw OSM tags as escape-hatch.

v2 bumped from v1 on 2026-05-13 to add the required sidewalk flags
(European urban roads almost always have at least one sidewalk; classifier
uses explicit `sidewalk=*` tags + per-highway-class defaults). v1 tiles
remain on `/v1/osm/` on R2 for roll-back; new bakes write to `/v2/osm/`.

Source of truth for class mappings: `data/classify_osm_tables.json`.
This file is also synced into `mapbiker/TrackRider/Resources/` so iOS can
classify Live-Overpass tiles consistently.

CLI:
    python -m bake.run_osm --state he --source-version geofabrik-2026-05

## Modules

| File | Responsibility |
|---|---|
| `src/bake/schema.py` | Pydantic mirror of tile-format-v1 |
| `src/bake/sources/_bucore3d.py` | INSPIRE bu-core3d 4.0 GML parser |
| `src/bake/sources/_citygml2.py` | CityGML 2.0 parser (UTM32N → WGS84) |
| `src/bake/sources/hessen.py` | Hessen INSPIRE WFS fetcher |
| `src/bake/sources/bayern.py` | Bayernwolke per-2km tile fetcher |
| `src/bake/normalize.py` | `ParsedBuilding` → schema `Building` |
| `src/bake/retile.py` | Web-mercator z15 binning |
| `src/bake/chunking.py` | Adaptive bbox chunking for capped APIs |
| `src/bake/pack.py` | Per-tile gzipped-JSON writer |
| `src/bake/upload.py` | boto3 R2 upload (S3-compatible API) |
| `src/bake/run.py` | CLI entrypoint, per-state dispatch |
