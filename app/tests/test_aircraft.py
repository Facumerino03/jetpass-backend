import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.database import Base, get_db
from app.main import app
from app.models import aircraft as _aircraft_model
from app.models import auth_session as _auth_session_model
from app.models import user as _user_model
from app.services.aircraft_service import AircraftService


@pytest.fixture
async def client():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async def override_get_db():
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as test_client:
        yield test_client
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
async def test_pilot_can_create_list_get_patch_and_soft_delete_aircraft(client):
    access_token = await register_pilot(client)
    headers = {"Authorization": f"Bearer {access_token}"}

    create_response = await client.post(
        "/pilot/aircraft",
        json=aircraft_payload(),
        headers=headers,
    )

    assert create_response.status_code == 201
    created = create_response.json()
    assert created["identification"] == "LV-ABC"
    assert created["is_valid"] is None
    aircraft_id = created["id"]

    list_response = await client.get("/pilot/aircraft", headers=headers)
    assert list_response.status_code == 200
    listed = list_response.json()
    assert len(listed) == 1
    assert listed[0]["id"] == aircraft_id

    get_response = await client.get(f"/pilot/aircraft/{aircraft_id}", headers=headers)
    assert get_response.status_code == 200
    assert get_response.json()["id"] == aircraft_id

    patch_response = await client.patch(
        f"/pilot/aircraft/{aircraft_id}",
        json={"alias": "Updated trainer", "color_and_markings": "Red and white"},
        headers=headers,
    )
    assert patch_response.status_code == 200
    patched = patch_response.json()
    assert patched["alias"] == "Updated trainer"
    assert patched["color_and_markings"] == "Red and white"

    delete_response = await client.delete(f"/pilot/aircraft/{aircraft_id}", headers=headers)
    assert delete_response.status_code == 200
    assert delete_response.json() == {"deleted": True}

    list_after_delete_response = await client.get("/pilot/aircraft", headers=headers)
    assert list_after_delete_response.status_code == 200
    assert list_after_delete_response.json() == []

    get_after_delete_response = await client.get(
        f"/pilot/aircraft/{aircraft_id}",
        headers=headers,
    )
    assert get_after_delete_response.status_code == 404


@pytest.mark.asyncio
async def test_aircraft_routes_require_authentication(client):
    response = await client.get("/pilot/aircraft")

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_pilot_cannot_get_aircraft_owned_by_another_pilot(client):
    owner_token = await register_pilot(client, email="owner@example.com")
    other_token = await register_pilot(client, email="other@example.com")
    owner_headers = {"Authorization": f"Bearer {owner_token}"}
    other_headers = {"Authorization": f"Bearer {other_token}"}
    payload = aircraft_payload()
    payload["alias"] = "Club Cessna"

    create_response = await client.post(
        "/pilot/aircraft",
        json=payload,
        headers=owner_headers,
    )
    assert create_response.status_code == 201
    aircraft_id = create_response.json()["id"]

    response = await client.get(
        f"/pilot/aircraft/{aircraft_id}",
        headers=other_headers,
    )
    assert response.status_code == 404

    patch_response = await client.patch(
        f"/pilot/aircraft/{aircraft_id}",
        json={"alias": "Hijacked Cessna"},
        headers=other_headers,
    )
    assert patch_response.status_code == 404

    delete_response = await client.delete(
        f"/pilot/aircraft/{aircraft_id}",
        headers=other_headers,
    )
    assert delete_response.status_code == 404

    owner_get_response = await client.get(
        f"/pilot/aircraft/{aircraft_id}",
        headers=owner_headers,
    )
    assert owner_get_response.status_code == 200
    owner_aircraft = owner_get_response.json()
    assert owner_aircraft["alias"] == "Club Cessna"
    assert owner_aircraft["is_active"] is True


class FakeTypeIntelligenceClient:
    async def verify_aircraft_type(self, designator: str):
        if designator.upper() == "ZZZZINVALID":
            return {
                "designator": designator.upper(),
                "is_valid": False,
                "entry": None,
                "messages": [],
            }
        return {
            "designator": designator.upper(),
            "is_valid": True,
            "entry": {"designator": designator.upper()},
            "messages": [],
        }


@pytest.mark.asyncio
async def test_verify_type_endpoint_updates_aircraft(client, monkeypatch):
    monkeypatch.setattr(
        AircraftService,
        "_get_intelligence_client",
        lambda self: FakeTypeIntelligenceClient(),
    )
    access_token = await register_pilot(client)
    headers = {"Authorization": f"Bearer {access_token}"}

    create_response = await client.post(
        "/pilot/aircraft",
        json=aircraft_payload(),
        headers=headers,
    )
    assert create_response.status_code == 201
    aircraft_id = create_response.json()["id"]

    verify_response = await client.post(
        f"/pilot/aircraft/{aircraft_id}/verify-type",
        headers=headers,
    )
    assert verify_response.status_code == 200
    body = verify_response.json()
    assert body["is_valid"] is True
    assert body["verified_at"] is not None
