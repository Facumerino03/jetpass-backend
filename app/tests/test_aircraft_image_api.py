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
from app.models import user as _user_model
from app.routes.aircraft import get_aircraft_service
from app.services.aircraft_image_service import AircraftImageService
from app.services.aircraft_service import AircraftService
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
        image_service = AircraftImageService(storage=storage)
        aircraft_service = AircraftService(image_service=image_service)

        engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        session_factory = async_sessionmaker(engine, expire_on_commit=False)

        async def override_get_db():
            async with session_factory() as session:
                yield session

        app.dependency_overrides[get_db] = override_get_db
        app.dependency_overrides[get_aircraft_service] = lambda: aircraft_service

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as test_client:
            yield test_client, storage

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


def aircraft_payload() -> dict:
    return {
        "alias": "Trainer",
        "identification": "lv-abc",
        "icao_type_designator": "c172",
        "wake_turbulence_category": "L",
        "equipment_com_nav": "SDFGR",
        "equipment_surveillance": "B1",
        "pbn_capabilities": None,
        "emergency_radio_uhf": True,
        "emergency_radio_vhf": True,
        "emergency_radio_elt": False,
        "survival_equipment_present": True,
        "survival_polar": False,
        "survival_desert": False,
        "survival_maritime": False,
        "survival_jungle": True,
        "life_jackets_present": True,
        "life_jackets_lights": True,
        "life_jackets_fluorescein": False,
        "life_jackets_uhf": False,
        "life_jackets_vhf": False,
        "dinghies_present": False,
        "dinghies_cover_present": False,
        "color_and_markings": "White with blue stripes",
    }


@pytest.mark.asyncio
async def test_pilot_can_create_aircraft_with_uploaded_image(client_with_storage):
    client, storage = client_with_storage
    access_token = await register_pilot(client)
    headers = {"Authorization": f"Bearer {access_token}"}

    presign_response = await client.post(
        "/pilot/aircraft/image/presign",
        json={"content_type": "image/jpeg"},
        headers=headers,
    )
    assert presign_response.status_code == 200
    presign_data = presign_response.json()
    image_key = presign_data["image_key"]

    storage.put_object(key=image_key, body=b"aircraft-image", content_type="image/jpeg")

    payload = aircraft_payload()
    payload["image_key"] = image_key
    create_response = await client.post(
        "/pilot/aircraft",
        json=payload,
        headers=headers,
    )

    assert create_response.status_code == 201
    created = create_response.json()
    assert created["image_url"]
    assert f"aircraft/{created['id']}/" in created["image_url"] or image_key.rsplit("/", 1)[-1] in created["image_url"]

    stored_key = f"aircraft/{created['id']}/{image_key.rsplit('/', 1)[-1]}"
    assert storage.object_exists(key=stored_key) is True
