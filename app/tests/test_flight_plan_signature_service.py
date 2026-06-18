from uuid import uuid4

import pytest
from fastapi import HTTPException
from moto import mock_aws
import boto3

from app.core.config import Settings
from app.models.flight_plan import FlightPlan, FlightPlanStatus
from app.services.flight_plan_signature_service import FlightPlanSignatureService
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
def signature_service() -> FlightPlanSignatureService:
    with mock_aws():
        settings = _storage_settings()
        s3_client = boto3.client("s3", region_name=settings.S3_REGION)
        s3_client.create_bucket(Bucket=settings.S3_BUCKET_NAME)
        storage = ObjectStorageService(app_settings=settings, s3_client=s3_client)
        yield FlightPlanSignatureService(storage=storage)


def _flight_plan(*, flight_plan_id=None) -> FlightPlan:
    plan_id = flight_plan_id or uuid4()
    return FlightPlan(
        id=plan_id,
        pilot_user_id=uuid4(),
        status=FlightPlanStatus.DRAFT,
        aircraft_number=1,
        departure_aerodrome_icao="SABE",
        destination_aerodrome_icao="SAEZ",
        alternate1_aerodrome_icao="SADP",
        alternate2_aerodrome_icao="SADF",
    )


def test_presign_for_plan_returns_signature_key(signature_service: FlightPlanSignatureService):
    plan = _flight_plan()

    result = signature_service.presign_for_plan(plan=plan, content_type="image/png")

    assert result["upload_url"]
    assert result["signature_key"].startswith(f"flight-plans/{plan.id}/")
    assert result["signature_key"].endswith(".png")
    assert result["expires_in"] == 3600


def test_validate_signature_key_rejects_missing_upload(signature_service: FlightPlanSignatureService):
    plan = _flight_plan()
    signature_key = signature_service.signature_key(flight_plan_id=plan.id)

    with pytest.raises(HTTPException) as exc_info:
        signature_service.validate_signature_key_for_plan(plan=plan, signature_key=signature_key)

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail == "Flight plan signature was not uploaded"


def test_validate_signature_key_rejects_other_plan(signature_service: FlightPlanSignatureService):
    plan = _flight_plan()
    other_plan = _flight_plan()
    signature_key = signature_service.signature_key(flight_plan_id=other_plan.id)
    signature_service._storage.put_object(key=signature_key, body=b"sig", content_type="image/png")

    with pytest.raises(HTTPException) as exc_info:
        signature_service.validate_signature_key_for_plan(plan=plan, signature_key=signature_key)

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail == "Invalid flight plan signature key"


def test_resolve_public_signature_url_returns_presigned_url(signature_service: FlightPlanSignatureService):
    signature_key = "flight-plans/test/sample.png"
    signature_service._storage.put_object(key=signature_key, body=b"sig", content_type="image/png")

    signature_url = signature_service.resolve_public_signature_url(stored_value=signature_key)

    assert signature_url
    assert signature_key in signature_url


def test_resolve_public_signature_url_keeps_legacy_http_value(signature_service: FlightPlanSignatureService):
    legacy_url = "https://example.com/signature.png"

    signature_url = signature_service.resolve_public_signature_url(stored_value=legacy_url)

    assert signature_url == legacy_url
