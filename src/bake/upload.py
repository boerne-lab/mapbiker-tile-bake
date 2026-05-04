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

import os
from pathlib import Path

import boto3
from dotenv import load_dotenv

# Load .env at import time so callers don't need to remember.
# load_dotenv() is idempotent and a no-op if .env doesn't exist.
load_dotenv()


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
