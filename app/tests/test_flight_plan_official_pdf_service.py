from uuid import uuid4

import boto3
import pytest
from moto import mock_aws

from app.core.config import Settings
from app.models.flight_plan import FlightPlan, FlightPlanStatus
from app.pdf.eana_flight_plan_pdf_generator import EanaFlightPlanPdfGenerator
from app.services.flight_plan_official_pdf_service import FlightPlanOfficialPdfService
from app.services.flight_plan_signature_service import FlightPlanSignatureService
from app.tests.png_fixtures import TINY_PNG
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
def official_pdf_service() -> FlightPlanOfficialPdfService:
    with mock_aws():
        settings = _storage_settings()
        s3_client = boto3.client("s3", region_name=settings.S3_REGION)
        s3_client.create_bucket(Bucket=settings.S3_BUCKET_NAME)
        storage = ObjectStorageService(app_settings=settings, s3_client=s3_client)
        signature_service = FlightPlanSignatureService(storage=storage)
        try:
            pdf_generator = EanaFlightPlanPdfGenerator()
        except Exception:
            pytest.skip("EANA template PDF not found")
        yield FlightPlanOfficialPdfService(
            storage=storage,
            signature_service=signature_service,
            pdf_generator=pdf_generator,
        )


def _plan_with_signature_key(signature_key: str) -> FlightPlan:
    return FlightPlan(
        id=uuid4(),
        pilot_user_id=uuid4(),
        status=FlightPlanStatus.DRAFT,
        aircraft_number=1,
        departure_aerodrome_icao="SABE",
        destination_aerodrome_icao="SAEZ",
        alternate1_aerodrome_icao="SADP",
        alternate2_aerodrome_icao="SADF",
        aircraft_identification_snapshot="LV-ABC",
        signature_url=signature_key,
    )


def test_generate_and_store_uploads_official_pdf(official_pdf_service: FlightPlanOfficialPdfService):
    plan = _plan_with_signature_key(f"flight-plans/{uuid4()}/signature.png")
    signature_key = f"flight-plans/{plan.id}/signature.png"
    plan.signature_url = signature_key
    official_pdf_service._storage.put_object(
        key=signature_key,
        body=TINY_PNG,
        content_type="image/png",
    )

    object_key = official_pdf_service.generate_and_store(plan)

    assert object_key == f"flight-plans/{plan.id}/official-eana.pdf"
    assert official_pdf_service._storage.object_exists(key=object_key) is True

    pdf_url = official_pdf_service.resolve_public_official_pdf_url(stored_value=object_key)
    assert pdf_url
