import boto3
import pytest
from moto import mock_aws

from app.core.config import Settings
from app.services.object_storage_service import ObjectStorageService


def _storage_settings() -> Settings:
    return Settings(
        S3_ENDPOINT_URL="http://localhost:9000",
        S3_ACCESS_KEY_ID="test-access-key",
        S3_SECRET_ACCESS_KEY="test-secret-key",
        S3_BUCKET_NAME="jetpass",
        S3_REGION="us-east-1",
    )


@mock_aws
def test_put_object_and_object_exists():
    settings = _storage_settings()
    s3_client = boto3.client("s3", region_name=settings.S3_REGION)
    s3_client.create_bucket(Bucket=settings.S3_BUCKET_NAME)

    service = ObjectStorageService(app_settings=settings, s3_client=s3_client)

    key = service.put_object(key="test/hello.txt", body=b"hello", content_type="text/plain")

    assert key == "test/hello.txt"
    assert service.object_exists(key="test/hello.txt") is True
    assert service.object_exists(key="missing.txt") is False


@mock_aws
def test_delete_object_removes_object():
    settings = _storage_settings()
    s3_client = boto3.client("s3", region_name=settings.S3_REGION)
    s3_client.create_bucket(Bucket=settings.S3_BUCKET_NAME)

    service = ObjectStorageService(app_settings=settings, s3_client=s3_client)
    service.put_object(key="test/delete-me.txt", body=b"bye", content_type="text/plain")

    assert service.object_exists(key="test/delete-me.txt") is True

    service.delete_object(key="test/delete-me.txt")

    assert service.object_exists(key="test/delete-me.txt") is False


@mock_aws
def test_generate_presigned_urls():
    settings = _storage_settings()
    s3_client = boto3.client("s3", region_name=settings.S3_REGION)
    s3_client.create_bucket(Bucket=settings.S3_BUCKET_NAME)

    service = ObjectStorageService(app_settings=settings, s3_client=s3_client)

    put_url = service.generate_presigned_put_url(
        key="test/upload.txt",
        content_type="text/plain",
    )
    get_url = service.generate_presigned_get_url(key="test/upload.txt")

    assert put_url
    assert get_url
    assert "test/upload.txt" in put_url
    assert "test/upload.txt" in get_url


@mock_aws
def test_presigned_urls_use_public_endpoint_when_configured():
    settings = Settings(
        S3_ENDPOINT_URL="http://localhost:9000",
        S3_PUBLIC_ENDPOINT_URL="http://10.0.2.2:9000",
        S3_ACCESS_KEY_ID="test-access-key",
        S3_SECRET_ACCESS_KEY="test-secret-key",
        S3_BUCKET_NAME="jetpass",
        S3_REGION="us-east-1",
    )
    s3_client = boto3.client("s3", region_name=settings.S3_REGION)
    s3_client.create_bucket(Bucket=settings.S3_BUCKET_NAME)

    service = ObjectStorageService(app_settings=settings, s3_client=s3_client)

    put_url = service.generate_presigned_put_url(
        key="test/mobile-upload.jpg",
        content_type="image/jpeg",
    )
    get_url = service.generate_presigned_get_url(key="test/mobile-upload.jpg")

    assert "10.0.2.2:9000" in put_url
    assert "10.0.2.2:9000" in get_url
    assert "localhost" not in put_url
    assert "localhost" not in get_url


def test_is_configured_false_when_credentials_missing():
    settings = Settings(
        S3_ENDPOINT_URL="http://localhost:9000",
        S3_ACCESS_KEY_ID=None,
        S3_SECRET_ACCESS_KEY=None,
    )
    service = ObjectStorageService(app_settings=settings)

    assert service.is_configured() is False


@mock_aws
def test_move_object_renames_object():
    settings = _storage_settings()
    s3_client = boto3.client("s3", region_name=settings.S3_REGION)
    s3_client.create_bucket(Bucket=settings.S3_BUCKET_NAME)

    service = ObjectStorageService(app_settings=settings, s3_client=s3_client)
    service.put_object(key="source/file.txt", body=b"moved", content_type="text/plain")

    final_key = service.move_object(source_key="source/file.txt", dest_key="dest/file.txt")

    assert final_key == "dest/file.txt"
    assert service.object_exists(key="dest/file.txt") is True
    assert service.object_exists(key="source/file.txt") is False


def test_put_object_raises_when_not_configured():
    settings = Settings(
        S3_ENDPOINT_URL=None,
        S3_ACCESS_KEY_ID=None,
        S3_SECRET_ACCESS_KEY=None,
    )
    service = ObjectStorageService(app_settings=settings)

    with pytest.raises(RuntimeError, match="Object storage is not configured"):
        service.put_object(key="test.txt", body=b"x", content_type="text/plain")
