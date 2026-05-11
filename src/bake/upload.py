"""Upload baked tiles to a Cloudflare R2 bucket via the S3-compatible API.

R2 is fully S3-compatible — boto3 with `endpoint_url` set to the R2
endpoint behaves exactly like AWS S3.

Credentials are loaded from environment variables, populated either
directly (CI) or from a gitignored `.env` file at the repo root (local
development). The four required env vars are:

- R2_ACCESS_KEY_ID
- R2_SECRET_ACCESS_KEY
- R2_ENDPOINT (e.g. https://<account-id>.r2.cloudflarestorage.com)
- R2_BUCKET (target bucket name; consumers may override per-call)
"""
from __future__ import annotations

import gzip
import os
from pathlib import Path

import boto3
from dotenv import load_dotenv

# Load .env at import time so callers don't need to remember.
# load_dotenv() is idempotent and a no-op if .env doesn't exist.
load_dotenv()


def _remote_path_for(*, state: str, z: int, x: int, y: int,
                     source_type: str = "lod2") -> str:
    """Build R2 remote key for a tile.

    LoD2 uses /v2/lod2/{state}/z{z}/{x}/{y}.json (bumped from v1 in 2026-05).
    OSM uses /v1/osm/{state}/z{z}/{x}/{y}.json (new in 2026-05).
    """
    if source_type == "lod2":
        return f"v2/lod2/{state}/z{z}/{x}/{y}.json"
    elif source_type == "osm":
        return f"v1/osm/{state}/z{z}/{x}/{y}.json"
    raise ValueError(f"unknown source_type: {source_type}")


def _remote_path_for_dgm(*, state: str) -> str:
    """Build R2 remote key for a per-Bundesland DGM200 binary.

    DGM200 uses /v1/dgm/{state}.bin (one file per state, not tiled).
    The bake produces an uncompressed DGM2 binary; upload sets
    `Content-Encoding: gzip` so the file is gzipped on the wire.
    """
    return f"v1/dgm/{state}.bin"


def _remote_path_for_dgm10(*, state: str, z: int, x: int, y: int) -> str:
    """Build R2 remote key for a per-z15-tile DGM10 binary.

    DGM10 uses /v1/dgm10/{state}/z{z}/{x}/{y}.bin — per-tile, mirrors
    the LoD2 and OSM tile layouts so the iOS adapter can share its
    RawSourceCache infrastructure.
    """
    return f"v1/dgm10/{state}/z{z}/{x}/{y}.bin"


def _get_s3_client():
    """Build a boto3 S3 client pointing at R2.

    Factored out for testability — tests patch this to inject a mock.
    """
    return boto3.client(
        's3',
        endpoint_url=os.environ['R2_ENDPOINT'],
        aws_access_key_id=os.environ['R2_ACCESS_KEY_ID'],
        aws_secret_access_key=os.environ['R2_SECRET_ACCESS_KEY'],
        region_name='auto',
    )


def upload_tile(*, local_path: Path, bucket: str, remote_key: str,
                content_type: str = 'application/json',
                content_encoding: str | None = 'gzip') -> None:
    """Upload `local_path` to `bucket/remote_key` on R2.

    Defaults are tuned for the LoD2 tile use case:
    - `content_type='application/json'` — the inflated body is JSON
    - `content_encoding='gzip'` — the file on disk is gzip-compressed,
      so URLSession (and curl --compressed) can transparently inflate
      on the receiving end

    Pass `content_encoding=None` for uncompressed assets (e.g. health
    probes, README files).
    """
    s3 = _get_s3_client()
    extra_args: dict[str, str] = {'ContentType': content_type}
    if content_encoding is not None:
        extra_args['ContentEncoding'] = content_encoding

    with local_path.open('rb') as f:
        s3.put_object(
            Bucket=bucket,
            Key=remote_key,
            Body=f.read(),
            **extra_args,
        )


def upload_dgm_binary(*, local_path: Path, bucket: str, state: str) -> None:
    """Upload a DGM2 v1 state binary to `bucket` at `v1/dgm/{state}.bin`.

    The local file is uncompressed; this function gzips it in-memory
    before uploading and sets `Content-Encoding: gzip` so URLSession /
    curl auto-inflates on the receiving side. DGM200 elevation data
    compresses ~50-70% via gzip (smooth field), so wire size is
    typically ~1-2 MB for Hessen / Bayern even though the raw binary
    is ~2-4 MB.
    """
    s3 = _get_s3_client()
    raw = local_path.read_bytes()
    compressed = gzip.compress(raw, compresslevel=9)
    s3.put_object(
        Bucket=bucket,
        Key=_remote_path_for_dgm(state=state),
        Body=compressed,
        ContentType='application/octet-stream',
        ContentEncoding='gzip',
    )


def upload_dgm10_tile(
    *, local_path: Path, bucket: str,
    state: str, z: int, x: int, y: int,
) -> None:
    """Upload a per-z15-tile DGM10 binary to
    `bucket/v1/dgm10/{state}/z{z}/{x}/{y}.bin`.

    Same gzip-in-memory + `Content-Encoding: gzip` pattern as the
    state-wide DGM200 upload. A per-tile DGM10 binary is ~20 KB
    uncompressed → ~10 KB on the wire.
    """
    s3 = _get_s3_client()
    raw = local_path.read_bytes()
    compressed = gzip.compress(raw, compresslevel=9)
    s3.put_object(
        Bucket=bucket,
        Key=_remote_path_for_dgm10(state=state, z=z, x=x, y=y),
        Body=compressed,
        ContentType='application/octet-stream',
        ContentEncoding='gzip',
    )


def upload_valhalla_bundle(
    *, local_path: Path, bucket: str, region: str, bundle_version: int,
) -> None:
    """Upload a packaged Valhalla tile bundle to
    `bucket/v1/valhalla/{region}/tiles-v{N}.tar.gz`.

    The file is ALREADY gzipped (the bake's `package_bundle`
    writes a .tar.gz). We upload it as-is with `Content-Type:
    application/gzip` and no `Content-Encoding` — clients like
    URLSession (and curl --output) should write the response body
    untouched to disk so the on-disk file matches the SHA-256 the
    manifest pinned.

    For a typical DACH-cycling bundle (~1.5 GB compressed) this
    takes 5–10 min over a home connection. boto3 chunks the upload
    via its multipart-upload threshold automatically.
    """
    s3 = _get_s3_client()
    key = f"v1/valhalla/{region}/tiles-v{bundle_version}.tar.gz"
    s3.upload_file(
        Filename=str(local_path),
        Bucket=bucket,
        Key=key,
        ExtraArgs={
            "ContentType": "application/gzip",
        },
    )


def upload_valhalla_manifest(
    *, local_path: Path, bucket: str, region: str,
) -> None:
    """Upload the manifest JSON to
    `bucket/v1/valhalla/{region}/manifest.json`.

    iOS reads this small file (~300 B) at app launch to decide
    whether to fetch a new bundle. JSON, gzipped on the wire for
    cleanliness with the rest of our static-asset shelf — even
    though the saving is meaningless at this size.
    """
    s3 = _get_s3_client()
    key = f"v1/valhalla/{region}/manifest.json"
    raw = local_path.read_bytes()
    compressed = gzip.compress(raw, compresslevel=9)
    s3.put_object(
        Bucket=bucket,
        Key=key,
        Body=compressed,
        ContentType="application/json",
        ContentEncoding="gzip",
    )
