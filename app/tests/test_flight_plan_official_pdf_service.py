from io import BytesIO
from pathlib import Path
from uuid import uuid4

import boto3
import pytest
from moto import mock_aws
from pypdf import PdfReader

from app.core.config import Settings
from app.models.aircraft import WakeTurbulenceCat
from app.models.flight_plan import FlightPlan, FlightPlanStatus, FlightRules, FlightType
from app.pdf.eana_flight_plan_pdf_generator import EanaFlightPlanPdfGenerator
from app.pdf.map_flight_plan_to_pdf_data import map_flight_plan_to_pdf_data
from app.services.flight_plan_official_pdf_service import FlightPlanOfficialPdfService
from app.services.flight_plan_signature_service import FlightPlanSignatureService
from app.tests.png_fixtures import TINY_PNG
from app.services.object_storage_service import ObjectStorageService

ROOT = Path(__file__).resolve().parents[2]
TEMPLATE_PATH = ROOT / "docs" / "eana_flight_plan_template.pdf"


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
        flight_rules=FlightRules.V,
        flight_type=FlightType.G,
        departure_aerodrome_icao="SABE",
        departure_time_utc="1430",
        destination_aerodrome_icao="SAEZ",
        alternate1_aerodrome_icao="SADP",
        alternate2_aerodrome_icao="SADF",
        aircraft_identification_snapshot="LV-ABC",
        aircraft_type_designator_snapshot="C172",
        wake_turbulence_category_snapshot=WakeTurbulenceCat.L,
        equipment_com_nav_snapshot="SDFGR",
        equipment_surveillance_snapshot="B1",
        cruising_speed="N0120",
        cruising_level="A045",
        route="DCT GUALE DCT",
        total_eet="0100",
        endurance="0230",
        persons_on_board=2,
        emergency_radio_uhf_snapshot=True,
        emergency_radio_vhf_snapshot=False,
        survival_equipment_present_snapshot=True,
        survival_polar_snapshot=True,
        life_jackets_present_snapshot=True,
        dinghies_present_snapshot=False,
        color_and_markings_snapshot="WHITE BLUE",
        pilot_in_command="Amelia Earhart",
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

    pdf_bytes = official_pdf_service._storage.get_object_bytes(key=object_key)
    assert len(pdf_bytes) > 0
    assert len(PdfReader(TEMPLATE_PATH).pages) == 1
    assert len(PdfReader(BytesIO(pdf_bytes)).pages) == 1


def test_map_and_generate_produces_expected_strike_marks(official_pdf_service: FlightPlanOfficialPdfService):
    plan = _plan_with_signature_key("unused")
    plan.emergency_radio_vhf_snapshot = False
    plan.dinghies_present_snapshot = False

    data = map_flight_plan_to_pdf_data(plan, signature_png_bytes=TINY_PNG)

    assert data.mark_fields["emergency_radio_vhf"] is True
    assert data.mark_fields["dinghies_present"] is True
    assert data.text_fields["dinghies_number"] == ""
    assert "flight_date" not in data.text_fields
