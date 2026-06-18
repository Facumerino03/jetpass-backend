import boto3
import pytest
from httpx import ASGITransport, AsyncClient
from moto import mock_aws
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import Settings
from app.core.database import Base, get_db
from app.main import app
from app.models import aircraft as _aircraft_model
from app.models import auth_session as _auth_session_model
from app.models import controlled_aerodrome as _controlled_aerodrome_model
from app.models import flight_plan as _flight_plan_model
from app.models import flight_plan_approval as _approval_model
from app.models import flight_plan_status_history as _history_model
from app.models import profiles as _profiles_model
from app.models import user as _user_model
from app.repositories.controlled_aerodrome_repository import ControlledAerodromeRepository
from app.routes.flight_plans import get_flight_plan_signature_service
from app.services.flight_plan_service import FlightPlanService
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
async def client_with_storage():
    with mock_aws():
        settings = _storage_settings()
        s3_client = boto3.client("s3", region_name=settings.S3_REGION)
        s3_client.create_bucket(Bucket=settings.S3_BUCKET_NAME)
        storage = ObjectStorageService(app_settings=settings, s3_client=s3_client)
        signature_service = FlightPlanSignatureService(storage=storage)
        FlightPlanService._signature_service = signature_service

        engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        session_factory = async_sessionmaker(engine, expire_on_commit=False)
        async with session_factory() as session:
            await ControlledAerodromeRepository.upsert_many(
                session,
                items=[
                    {"icao_code": "SABE", "name": "Aeroparque", "is_active": True},
                    {"icao_code": "SAEZ", "name": "Ezeiza", "is_active": True},
                    {"icao_code": "SADP", "name": "El Palomar", "is_active": True},
                    {"icao_code": "SADF", "name": "San Fernando", "is_active": True},
                ],
            )
            await session.commit()

        async def override_get_db():
            async with session_factory() as session:
                yield session

        app.dependency_overrides[get_db] = override_get_db
        app.dependency_overrides[get_flight_plan_signature_service] = lambda: signature_service

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as test_client:
            yield test_client, storage

        FlightPlanService._signature_service = None
        app.dependency_overrides.clear()
        await engine.dispose()


async def register_pilot(client: AsyncClient, email: str = "pilot@example.com") -> str:
    response = await client.post(
        "/auth/register/pilot",
        json={
            "email": email,
            "password": "safe-password-123",
            "first_name": "Amelia",
            "last_name": "Earhart",
            "phone": None,
        },
    )
    assert response.status_code == 201
    return response.json()["access_token"]


def step_one_payload() -> dict:
    return {
        "departure_aerodrome_icao": "sabe",
        "departure_time_utc": "1430",
        "flight_date": "2026-05-18",
        "destination_aerodrome_icao": "saez",
        "alternate1_aerodrome_icao": "sadp",
        "alternate2_aerodrome_icao": "sadf",
    }


async def create_aircraft(client: AsyncClient, headers: dict) -> str:
    response = await client.post(
        "/pilot/aircraft",
        json={
            "alias": "Trainer",
            "identification": "lv-abc",
            "icao_type_designator": "c172",
            "wake_turbulence_category": "L",
            "equipment_com_nav": "SDFGR",
            "equipment_surveillance": "B1",
            "color_and_markings": "White with blue stripes",
        },
        headers=headers,
    )
    assert response.status_code == 201
    return response.json()["id"]


@pytest.mark.asyncio
async def test_pilot_can_presign_upload_signature_and_submit_flight_plan(client_with_storage):
    client, storage = client_with_storage
    token = await register_pilot(client)
    headers = {"Authorization": f"Bearer {token}"}

    create_response = await client.post("/flight-plans", json=step_one_payload(), headers=headers)
    assert create_response.status_code == 201
    flight_plan_id = create_response.json()["id"]
    aircraft_id = await create_aircraft(client, headers)

    await client.patch(
        f"/flight-plans/{flight_plan_id}",
        json={
            "flight_rules": "V",
            "flight_type": "G",
            "aircraft_id": aircraft_id,
            "cruising_speed": "N0120",
            "cruising_level": "A045",
            "route": "DCT GUALE DCT",
            "total_eet": "0100",
            "endurance": "0230",
            "persons_on_board": 2,
        },
        headers=headers,
    )

    presign_response = await client.post(
        f"/flight-plans/{flight_plan_id}/signature/presign",
        json={"content_type": "image/png"},
        headers=headers,
    )
    assert presign_response.status_code == 200
    presign_data = presign_response.json()
    signature_key = presign_data["signature_key"]
    storage.put_object(key=signature_key, body=b"signature-png", content_type="image/png")

    patch_signature_response = await client.patch(
        f"/flight-plans/{flight_plan_id}",
        json={"signature_key": signature_key},
        headers=headers,
    )
    assert patch_signature_response.status_code == 200
    assert patch_signature_response.json()["signature_url"]

    submit_response = await client.post(f"/flight-plans/{flight_plan_id}/submit", headers=headers)
    assert submit_response.status_code == 200
    assert submit_response.json()["status"] == "pending_approval"


@pytest.mark.asyncio
async def test_submit_without_signature_returns_422(client_with_storage):
    client, _storage = client_with_storage
    token = await register_pilot(client)
    headers = {"Authorization": f"Bearer {token}"}

    create_response = await client.post("/flight-plans", json=step_one_payload(), headers=headers)
    flight_plan_id = create_response.json()["id"]
    aircraft_id = await create_aircraft(client, headers)

    await client.patch(
        f"/flight-plans/{flight_plan_id}",
        json={
            "flight_rules": "V",
            "flight_type": "G",
            "aircraft_id": aircraft_id,
            "cruising_speed": "N0120",
            "cruising_level": "A045",
            "route": "DCT GUALE DCT",
            "total_eet": "0100",
            "endurance": "0230",
            "persons_on_board": 2,
        },
        headers=headers,
    )

    submit_response = await client.post(f"/flight-plans/{flight_plan_id}/submit", headers=headers)
    assert submit_response.status_code == 422
    assert "signature_url" in submit_response.json()["detail"]
