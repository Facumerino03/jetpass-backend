import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.database import Base, get_db
from app.main import app
from app.models import aircraft as _aircraft_model
from app.models import auth_session as _auth_session_model
from app.models import aerodrome as _aerodrome_model
from app.models import flight_plan as _flight_plan_model
from app.models import flight_plan_approval as _approval_model
from app.models import flight_plan_status_history as _history_model
from app.models import profiles as _profiles_model
from app.models import user as _user_model
from app.tests.aerodrome_fixtures import seed_aerodrome, seed_flight_plan_aerodromes
from app.services.flight_plan_field18_service import FlightPlanField18Service


@pytest.fixture
async def client():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        await seed_flight_plan_aerodromes(session)
        await seed_aerodrome(
            session,
            local_identifier="MZA",
            icao_code=None,
            name="Mendoza El Plumerillo",
            latitude=-32.8317,
            longitude=-68.7928,
            is_controlled=False,
        )
        await session.commit()

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
        json={"email": email, "password": "safe-password-123", "first_name": "Amelia", "last_name": "Earhart", "phone": None},
    )
    assert response.status_code == 201
    return response.json()["access_token"]


def auth_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def step_one_payload() -> dict:
    return {
        "departure_aerodrome_icao": "sabe",
        "departure_time_utc": "1430",
        "flight_date": "2026-05-18",
        "destination_aerodrome_icao": "saez",
        "alternate1_aerodrome_icao": "sadp",
        "alternate2_aerodrome_icao": "sadf",
    }


@pytest.mark.asyncio
async def test_pilot_can_create_list_get_and_patch_draft_flight_plan(client):
    token = await register_pilot(client)
    headers = auth_headers(token)

    create_response = await client.post("/flight-plans", json=step_one_payload(), headers=headers)
    assert create_response.status_code == 201
    created = create_response.json()
    assert created["status"] == "draft"
    assert created["departure_aerodrome_icao"] == "SABE"
    assert created["aircraft_number"] == 1
    assert created["pilot_in_command"] == "Amelia Earhart"
    flight_plan_id = created["id"]

    list_response = await client.get("/flight-plans", headers=headers)
    assert list_response.status_code == 200
    assert [item["id"] for item in list_response.json()] == [flight_plan_id]

    get_response = await client.get(f"/flight-plans/{flight_plan_id}", headers=headers)
    assert get_response.status_code == 200
    assert get_response.json()["id"] == flight_plan_id

    patch_response = await client.patch(
        f"/flight-plans/{flight_plan_id}",
        json={"flight_rules": "V", "flight_type": "G"},
        headers=headers,
    )
    assert patch_response.status_code == 200
    assert patch_response.json()["flight_rules"] == "V"


@pytest.mark.asyncio
async def test_flight_plan_routes_require_authentication(client):
    response = await client.post("/flight-plans", json=step_one_payload())
    assert response.status_code == 401


class FakeField18IntelligenceClient:
    async def run(self, payload):
        departure = payload["fpl_field18"]["fpl_fields"]["departure_aerodrome"]
        if departure == "MZA":
            return {
                "intent": "fpl_field18",
                "fpl_field18": {
                    "computed_field18": "DEP/MZA3250S06848W",
                    "suggestions": [],
                    "fpl_updates": [
                        {
                            "field": "departure_aerodrome",
                            "from_value": "MZA",
                            "to_value": "ZZZZ",
                            "reason": "Non-controlled aerodrome must use ZZZZ in item 13",
                        }
                    ],
                    "alerts": [],
                    "messages": [],
                },
            }
        return {
            "intent": "fpl_field18",
            "fpl_field18": {
                "computed_field18": "",
                "suggestions": [],
                "fpl_updates": [],
                "alerts": [],
                "messages": [],
            },
        }


@pytest.mark.asyncio
async def test_field18_preview_and_apply_routes(client, monkeypatch):
    monkeypatch.setattr(
        FlightPlanField18Service,
        "_client",
        lambda self: FakeField18IntelligenceClient(),
    )
    token = await register_pilot(client)
    headers = auth_headers(token)

    create_response = await client.post(
        "/flight-plans",
        json={
            **step_one_payload(),
            "departure_aerodrome_icao": "mza",
        },
        headers=headers,
    )
    assert create_response.status_code == 201
    flight_plan_id = create_response.json()["id"]
    assert create_response.json()["departure_aerodrome_icao"] == "MZA"

    preview_response = await client.post(
        f"/flight-plans/{flight_plan_id}/field18/preview",
        headers=headers,
    )
    assert preview_response.status_code == 200
    preview_body = preview_response.json()
    assert preview_body["intent"] == "fpl_field18"
    assert preview_body["field18"]["computed_field18"] == "DEP/MZA3250S06848W"
    assert preview_body["field18"]["fpl_updates"][0]["to_value"] == "ZZZZ"

    get_before_apply = await client.get(f"/flight-plans/{flight_plan_id}", headers=headers)
    assert get_before_apply.json()["departure_aerodrome_icao"] == "MZA"
    assert get_before_apply.json()["other_information"] is None

    apply_response = await client.post(
        f"/flight-plans/{flight_plan_id}/field18/apply",
        headers=headers,
    )
    assert apply_response.status_code == 200
    apply_body = apply_response.json()
    assert apply_body["plan"]["departure_aerodrome_icao"] == "ZZZZ"
    assert apply_body["plan"]["other_information"] == "DEP/MZA3250S06848W"
    assert apply_body["field18"]["computed_field18"] == "DEP/MZA3250S06848W"
