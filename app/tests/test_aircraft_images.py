import boto3
import pytest
from fastapi import HTTPException
from moto import mock_aws

from app.core.config import Settings
from app.models.aircraft import Aircraft
from app.models.user import Role
from app.services.aircraft_image_service import AircraftImageService
from app.services.object_storage_service import ObjectStorageService


def _storage_settings() -> Settings:
    return Settings(
        S3_ENDPOINT_URL="http://localhost:9000",
        S3_ACCESS_KEY_ID="test-access-key",
        S3_SECRET_ACCESS_KEY="test-secret-key",
        S3_BUCKET_NAME="jetpass",
        S3_REGION="us-east-1",
    )


@pytest.fixture
def image_service() -> AircraftImageService:
    with mock_aws():
        settings = _storage_settings()
        s3_client = boto3.client("s3", region_name=settings.S3_REGION)
        s3_client.create_bucket(Bucket=settings.S3_BUCKET_NAME)
        storage = ObjectStorageService(app_settings=settings, s3_client=s3_client)
        yield AircraftImageService(storage=storage)


def test_presign_for_create_returns_upload_data(image_service: AircraftImageService):
    from uuid import uuid4

    from app.models.user import User

    user = User(
        id=uuid4(),
        email="pilot@example.com",
        password_hash="hashed",
        first_name="Amelia",
        last_name="Earhart",
        phone=None,
        role=Role.PILOT,
        is_active=True,
    )

    result = image_service.presign_for_create(current_user=user, content_type="image/jpeg")

    assert result["upload_url"]
    assert result["image_key"].startswith(f"aircraft/pending/{user.id}/")
    assert result["expires_in"] == 3600


def test_validate_image_key_for_create_requires_uploaded_object(image_service: AircraftImageService):
    from uuid import uuid4

    from app.models.user import User

    user = User(
        id=uuid4(),
        email="pilot@example.com",
        password_hash="hashed",
        first_name="Amelia",
        last_name="Earhart",
        phone=None,
        role=Role.PILOT,
        is_active=True,
    )
    image_key = image_service.pending_image_key(user_id=user.id, content_type="image/png")

    with pytest.raises(HTTPException) as exc_info:
        image_service.validate_image_key_for_create(current_user=user, image_key=image_key)

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail == "Aircraft image was not uploaded"


def test_finalize_pending_image_moves_object_to_aircraft_prefix(image_service: AircraftImageService):
    from uuid import uuid4

    pending_key = image_service.pending_image_key(user_id=uuid4(), content_type="image/jpeg")
    image_service._storage.put_object(key=pending_key, body=b"img", content_type="image/jpeg")

    aircraft_id = uuid4()
    final_key = image_service.finalize_pending_image(pending_key=pending_key, aircraft_id=aircraft_id)

    assert final_key == f"aircraft/{aircraft_id}/{pending_key.rsplit('/', 1)[-1]}"
    assert image_service._storage.object_exists(key=final_key) is True
    assert image_service._storage.object_exists(key=pending_key) is False


def test_resolve_public_image_url_returns_presigned_url(image_service: AircraftImageService):
    image_key = "aircraft/test/sample.jpg"
    image_service._storage.put_object(key=image_key, body=b"img", content_type="image/jpeg")

    image_url = image_service.resolve_public_image_url(stored_value=image_key)

    assert image_url
    assert image_key in image_url


def test_resolve_public_image_url_keeps_legacy_http_value(image_service: AircraftImageService):
    legacy_url = "https://example.com/legacy.jpg"

    image_url = image_service.resolve_public_image_url(stored_value=legacy_url)

    assert image_url == legacy_url


def test_validate_image_key_for_update_checks_aircraft_prefix(image_service: AircraftImageService):
    from uuid import uuid4

    from app.models.aircraft import WakeTurbulenceCat

    aircraft_id = uuid4()
    image_key = image_service.aircraft_image_key(aircraft_id=aircraft_id, content_type="image/webp")
    aircraft = Aircraft(
        id=aircraft_id,
        owner_user_id=uuid4(),
        alias="Test",
        identification="LV-ABC",
        icao_type_designator="C172",
        wake_turbulence_category=WakeTurbulenceCat.L,
        equipment_com_nav="S",
        equipment_surveillance="C",
        color_and_markings="White",
        is_active=True,
    )

    with pytest.raises(HTTPException) as exc_info:
        image_service.validate_image_key_for_update(aircraft=aircraft, image_key=image_key)

    assert exc_info.value.status_code == 400

    image_service._storage.put_object(key=image_key, body=b"img", content_type="image/webp")
    validated = image_service.validate_image_key_for_update(aircraft=aircraft, image_key=image_key)

    assert validated == image_key
