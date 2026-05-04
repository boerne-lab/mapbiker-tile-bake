# mapbiker-tile-bake

Pipeline that bakes LoD2 building tiles for the [mapbiker](https://github.com/boerne-lab/mapbiker)
iOS app. Pulls source data from German Bundesland LoD2 services
(Bayern Bayernwolke CityGML, NRW WFS, Hessen INSPIRE bu-core3d 4.0 WFS),
normalises to a common per-tile JSON schema, and uploads to a
Cloudflare R2 bucket served at `https://tiles.mapbiker.app`.

Schema contract: see [`docs/tile-format-v1.md`](docs/tile-format-v1.md).

## Setup

```bash
python -m venv .venv
.venv\Scripts\activate    # Windows; on macOS/Linux: source .venv/bin/activate
pip install -e ".[dev]"
pytest -v
```

## Run

```bash
# Single state
python -m bake.run all --state hessen

# All M1 states
python -m bake.run all --states by,nrw,he
```

See `docs/run-book.md` (TBD after Phase 2) for stage-level details.

## License

Proprietary. The data this pipeline produces is licensed separately
(dl-de/by-2.0 for NRW, CC BY 4.0 for Bayern, dl-de/zero-2.0 for Hessen).
