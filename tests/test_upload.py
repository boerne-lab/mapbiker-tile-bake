import os
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

# Set required env vars BEFORE importing upload — bake.upload reads
# from os.environ at module-import-time-via-load_dotenv. These dummy
# values let the import succeed in test environments without a real
# .env file.
os.environ.setdefault('R2_ACCESS_KEY_ID', 'test-key')
os.environ.setdefault('R2_SECRET_ACCESS_KEY', 'test-secret')
os.environ.setdefault('R2_ENDPOINT', 'https://test.example.com')
os.environ.setdefault('R2_BUCKET', 'test-bucket')

from bake.upload import upload_tile  # noqa: E402


def test_upload_invokes_put_object_with_correct_args():
    with tempfile.NamedTemporaryFile(suffix='.json.gz', delete=False) as f:
        f.write(b'compressed-content')
        local_path = Path(f.name)

    with patch('bake.upload._get_s3_client') as mock_factory:
        mock_client = MagicMock()
        mock_factory.return_value = mock_client
        upload_tile(
            local_path=local_path,
            bucket='mapbiker-tiles',
            remote_key='v1/lod2/de_he/15/17086/10958.json.gz',
        )

    mock_client.put_object.assert_called_once()
    call_kwargs = mock_client.put_object.call_args.kwargs
    assert call_kwargs['Bucket'] == 'mapbiker-tiles'
    assert call_kwargs['Key'] == 'v1/lod2/de_he/15/17086/10958.json.gz'
    assert call_kwargs['Body'] == b'compressed-content'
    assert call_kwargs['ContentType'] == 'application/json'
    assert call_kwargs['ContentEncoding'] == 'gzip'

    local_path.unlink()


def test_upload_without_content_encoding():
    with tempfile.NamedTemporaryFile(suffix='.txt', delete=False) as f:
        f.write(b'plain text')
        local_path = Path(f.name)

    with patch('bake.upload._get_s3_client') as mock_factory:
        mock_client = MagicMock()
        mock_factory.return_value = mock_client
        upload_tile(
            local_path=local_path,
            bucket='mapbiker-tiles',
            remote_key='health.txt',
            content_type='text/plain',
            content_encoding=None,
        )

    call_kwargs = mock_client.put_object.call_args.kwargs
    assert call_kwargs['ContentType'] == 'text/plain'
    assert 'ContentEncoding' not in call_kwargs

    local_path.unlink()


def test_remote_path_for_lod2_v2():
    from bake.upload import _remote_path_for
    p = _remote_path_for(state="de_he", z=15, x=100, y=200, source_type="lod2")
    assert p == "v2/lod2/de_he/z15/100/200.json"


def test_remote_path_for_osm_v1():
    from bake.upload import _remote_path_for
    p = _remote_path_for(state="de_he", z=15, x=100, y=200, source_type="osm")
    assert p == "v1/osm/de_he/z15/100/200.json"


def test_remote_path_for_unknown_source_type_raises():
    from bake.upload import _remote_path_for
    import pytest
    with pytest.raises(ValueError):
        _remote_path_for(state="de_he", z=15, x=100, y=200, source_type="invalid")
