import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.database import Base, get_db
from app.core.security import create_access_token
from app.main import app
from app.models import aerodrome as _aerodrome_model
from app.models import user as _user_model
from app.models.user import Role
from app.repositories.aerodrome_repository import AerodromeRepository
from app.repositories.user_repository import UserRepository
from app.services.aerodrome_catalog_sync_service import AerodromeCatalogSyncService
from app.tests.aerodrome_fixtures import seed_aerodrome, seed_flight_plan_aerodromes


@pytest.fixture
async def db_session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        yield session
    await engine.dispose()


@pytest.fixture
async def client_with_session_factory():
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
        yield test_client, session_factory
    app.dependency_overrides.clear()
    await engine.dispose()


async def create_user_and_token(session_factory, *, email: str, role: Role) -> str:
    async with session_factory() as session:
        user = await UserRepository.create(
            session,
            email=email,
            password_hash="hashed",
            first_name="Test",
            last_name="User",
            phone=None,
            role=role,
        )
        await session.commit()
        return create_access_token(subject=str(user.id), role=user.role.value)


@pytest.mark.asyncio
async def test_replace_from_sync_upserts_and_deletes_stale_rows(db_session):
    await seed_aerodrome(
        db_session,
        local_identifier="OLD",
        icao_code="OLDX",
        name="Old Aerodrome",
    )
    await db_session.commit()

    upserted, deleted = await AerodromeRepository.replace_from_sync(
        db_session,
        items=[
            {
                "local_identifier": "SVO",
                "icao_code": "SAAV",
                "name": "Santa Fe / Sauce Viejo",
                "latitude": -31.7108,
                "longitude": -60.8114,
                "is_controlled": True,
            },
            {
                "local_identifier": "ACB",
                "icao_code": None,
                "name": "Coronel Bogado",
                "latitude": -33.27226,
                "longitude": -60.57066,
                "is_controlled": False,
            },
        ],
    )
    await db_session.commit()

    assert upserted == 2
    assert deleted == 1

    controlled = await AerodromeRepository.get_by_local_identifier(db_session, local_identifier="SVO")
    non_controlled = await AerodromeRepository.get_by_local_identifier(db_session, local_identifier="ACB")
    assert controlled is not None
    assert controlled.icao_code == "SAAV"
    assert controlled.is_active is True
    assert non_controlled is not None
    assert non_controlled.is_active is True


@pytest.mark.asyncio
async def test_list_active_for_flight_plan_includes_active_controlled_and_non_controlled(db_session):
    await seed_aerodrome(
        db_session,
        local_identifier="SAEZ",
        icao_code="SAEZ",
        name="Ezeiza",
        is_active=False,
    )
    await seed_aerodrome(
        db_session,
        local_identifier="ACB",
        icao_code=None,
        name="Coronel Bogado",
        is_controlled=False,
    )
    await seed_aerodrome(
        db_session,
        local_identifier="SABE",
        icao_code="SABE",
        name="Aeroparque",
    )
    await db_session.commit()

    active = await AerodromeRepository.list_active_for_flight_plan(db_session)

    assert {(item.local_identifier, item.icao_code) for item in active} == {
        ("SABE", "SABE"),
        ("ACB", None),
    }


@pytest.mark.asyncio
async def test_dropdown_returns_active_aerodromes_with_location_code(client_with_session_factory):
    client, session_factory = client_with_session_factory
    token = await create_user_and_token(session_factory, email="pilot@example.com", role=Role.PILOT)
    async with session_factory() as session:
        await seed_aerodrome(session, local_identifier="SAEZ", icao_code="SAEZ", name="Ezeiza", is_active=False)
        await seed_aerodrome(session, local_identifier="SABE", icao_code="SABE", name="Aeroparque")
        await seed_aerodrome(
            session,
            local_identifier="ACB",
            icao_code=None,
            name="Coronel Bogado",
            is_controlled=False,
        )
        await session.commit()

    response = await client.get(
        "/flight-plans/aerodromes?limit=20",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 2
    by_code = {item["location_code"]: item for item in body}
    assert by_code["SABE"]["local_identifier"] == "SABE"
    assert by_code["SABE"]["is_controlled"] is True
    assert by_code["ACB"]["local_identifier"] == "ACB"
    assert by_code["ACB"]["icao_code"] is None
    assert by_code["ACB"]["is_controlled"] is False


@pytest.mark.asyncio
async def test_admin_can_sync_and_manage_aerodromes(client_with_session_factory, monkeypatch):
    client, session_factory = client_with_session_factory
    admin_token = await create_user_and_token(session_factory, email="admin@example.com", role=Role.ADMIN)
    pilot_token = await create_user_and_token(session_factory, email="pilot@example.com", role=Role.PILOT)

    class FakeIntelligenceClient:
        async def run(self, payload):
            assert payload == {"aerodrome_catalog_sync": {"force_refresh": True}}
            return {
                "intent": "aerodrome_catalog_sync",
                "aerodrome_catalog_sync": {
                    "source": "fresh_fetch",
                    "synced_at": "2026-06-24T12:00:00Z",
                    "total_listed": 2,
                    "total_aerodromes": 2,
                    "aerodromes": [
                        {
                            "local_identifier": "SVO",
                            "icao_code": "SAAV",
                            "name": "Santa Fe / Sauce Viejo",
                            "latitude": -31.7108,
                            "longitude": -60.8114,
                            "is_controlled": True,
                            "control_status": "CONTROLLED",
                        }
                    ],
                    "alerts": [],
                    "messages": ["Synced from ANAC list endpoint (single request)."],
                },
                "alerts": [],
            }

    monkeypatch.setattr(AerodromeCatalogSyncService, "_client", lambda self: FakeIntelligenceClient())

    denied = await client.post(
        "/flight-plans/admin/aerodromes/sync",
        json={"force_refresh": True},
        headers={"Authorization": f"Bearer {pilot_token}"},
    )
    assert denied.status_code == 403

    synced = await client.post(
        "/flight-plans/admin/aerodromes/sync",
        json={"force_refresh": True},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert synced.status_code == 200
    assert synced.json()["upserted"] == 1
    assert synced.json()["deleted"] == 0

    updated = await client.patch(
        "/flight-plans/admin/aerodromes/SVO",
        json={"name": "Santa Fe", "is_active": False},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert updated.status_code == 200
    assert updated.json()["name"] == "Santa Fe"
    assert updated.json()["is_active"] is False


@pytest.mark.asyncio
async def test_create_flight_plan_rejects_aerodrome_outside_catalog(client_with_session_factory):
    client, session_factory = client_with_session_factory
    token = await create_user_and_token(session_factory, email="pilot@example.com", role=Role.PILOT)
    async with session_factory() as session:
        await seed_flight_plan_aerodromes(session)
        await session.commit()

    response = await client.post(
        "/flight-plans",
        json={
            "departure_aerodrome_icao": "SABE",
            "departure_time_utc": "1430",
            "flight_date": "2026-05-18",
            "destination_aerodrome_icao": "SAEZ",
            "alternate1_aerodrome_icao": "SADP",
            "alternate2_aerodrome_icao": "SADF",
        },
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 201

    invalid = await client.post(
        "/flight-plans",
        json={
            "departure_aerodrome_icao": "SABE",
            "departure_time_utc": "1430",
            "flight_date": "2026-05-18",
            "destination_aerodrome_icao": "SAEZ",
            "alternate1_aerodrome_icao": "SADP",
            "alternate2_aerodrome_icao": "ZZZZ",
        },
        headers={"Authorization": f"Bearer {token}"},
    )

    assert invalid.status_code == 422
    assert "Aerodrome ZZZZ is not in the active catalog" in invalid.json()["detail"]


@pytest.mark.asyncio
async def test_create_flight_plan_stores_icao_or_local_identifier(client_with_session_factory):
    client, session_factory = client_with_session_factory
    token = await create_user_and_token(session_factory, email="pilot@example.com", role=Role.PILOT)
    async with session_factory() as session:
        await seed_flight_plan_aerodromes(session)
        await seed_aerodrome(
            session,
            local_identifier="ACB",
            icao_code=None,
            name="Coronel Bogado",
            is_controlled=False,
        )
        await seed_aerodrome(
            session,
            local_identifier="SVO",
            icao_code="SAAV",
            name="Santa Fe / Sauce Viejo",
        )
        await session.commit()

    response = await client.post(
        "/flight-plans",
        json={
            "departure_aerodrome_icao": "SABE",
            "departure_time_utc": "1430",
            "flight_date": "2026-05-18",
            "destination_aerodrome_icao": "SVO",
            "alternate1_aerodrome_icao": "ACB",
            "alternate2_aerodrome_icao": "SADF",
        },
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["departure_aerodrome_icao"] == "SABE"
    assert body["destination_aerodrome_icao"] == "SAAV"
    assert body["alternate1_aerodrome_icao"] == "ACB"
    assert body["alternate2_aerodrome_icao"] == "SADF"
