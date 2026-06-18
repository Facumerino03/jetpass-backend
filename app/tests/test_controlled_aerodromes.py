import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.database import Base, get_db
from app.core.security import create_access_token
from app.main import app
from app.models import controlled_aerodrome as _controlled_aerodrome_model
from app.models import user as _user_model
from app.models.user import Role
from app.repositories.controlled_aerodrome_repository import ControlledAerodromeRepository
from app.repositories.user_repository import UserRepository


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
async def test_controlled_aerodrome_repository_upserts_and_searches_active(db_session):
    await ControlledAerodromeRepository.upsert_many(
        db_session,
        items=[
            {"icao_code": "saez", "name": "Ministro Pistarini", "is_active": True},
            {"icao_code": "sadp", "name": "El Palomar", "is_active": False},
        ],
    )
    await ControlledAerodromeRepository.upsert_many(
        db_session,
        items=[{"icao_code": "SAEZ", "name": "Ezeiza", "is_active": True}],
    )
    await db_session.commit()

    active = await ControlledAerodromeRepository.list_active(db_session, query="eze")
    inactive = await ControlledAerodromeRepository.get_by_icao(db_session, icao_code="SADP")

    assert [(item.icao_code, item.name) for item in active] == [("SAEZ", "Ezeiza")]
    assert inactive is not None
    assert inactive.is_active is False


@pytest.mark.asyncio
async def test_dropdown_returns_active_controlled_aerodromes(client_with_session_factory):
    client, session_factory = client_with_session_factory
    token = await create_user_and_token(session_factory, email="pilot@example.com", role=Role.PILOT)
    async with session_factory() as session:
        await ControlledAerodromeRepository.upsert_many(
            session,
            items=[
                {"icao_code": "SAEZ", "name": "Ezeiza", "is_active": True},
                {"icao_code": "SADP", "name": "El Palomar", "is_active": False},
            ],
        )
        await session.commit()

    response = await client.get(
        "/flight-plans/aerodromes?query=ez&limit=20",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    assert response.json() == [{"id": response.json()[0]["id"], "icao_code": "SAEZ", "name": "Ezeiza", "is_active": True, "traffic_type": None, "flight_rules": None, "category": None, "latitude": None, "longitude": None}]


@pytest.mark.asyncio
async def test_admin_and_authority_can_manage_and_import_controlled_aerodromes(client_with_session_factory):
    client, session_factory = client_with_session_factory
    admin_token = await create_user_and_token(session_factory, email="admin@example.com", role=Role.ADMIN)
    authority_token = await create_user_and_token(session_factory, email="authority@example.com", role=Role.ATC_AUTHORITY)
    pilot_token = await create_user_and_token(session_factory, email="pilot@example.com", role=Role.PILOT)

    denied = await client.post(
        "/flight-plans/admin/aerodromes",
        json={"icao_code": "SABE", "name": "Aeroparque", "is_active": True},
        headers={"Authorization": f"Bearer {pilot_token}"},
    )
    assert denied.status_code == 403

    created = await client.post(
        "/flight-plans/admin/aerodromes",
        json={"icao_code": "sabe", "name": "Aeroparque", "is_active": True},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert created.status_code == 201
    assert created.json()["icao_code"] == "SABE"

    updated = await client.patch(
        "/flight-plans/admin/aerodromes/SABE",
        json={"name": "Jorge Newbery", "is_active": False},
        headers={"Authorization": f"Bearer {authority_token}"},
    )
    assert updated.status_code == 200
    assert updated.json()["name"] == "Jorge Newbery"
    assert updated.json()["is_active"] is False

    json_import = await client.post(
        "/flight-plans/admin/aerodromes/import/json",
        json={"items": [{"icao_code": "SAEZ", "name": "Ezeiza", "is_active": True}]},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert json_import.status_code == 200
    assert json_import.json() == {"upserted": 1}

    csv_import = await client.post(
        "/flight-plans/admin/aerodromes/import/csv",
        json={"content": "icao_code,name,is_active\nSADP,El Palomar,true\n"},
        headers={"Authorization": f"Bearer {authority_token}"},
    )
    assert csv_import.status_code == 200
    assert csv_import.json() == {"upserted": 1}


@pytest.mark.asyncio
async def test_create_flight_plan_rejects_aerodrome_outside_controlled_catalog(client_with_session_factory):
    client, session_factory = client_with_session_factory
    token = await create_user_and_token(session_factory, email="pilot@example.com", role=Role.PILOT)
    async with session_factory() as session:
        await ControlledAerodromeRepository.upsert_many(
            session,
            items=[
                {"icao_code": "SABE", "name": "Aeroparque", "is_active": True},
                {"icao_code": "SAEZ", "name": "Ezeiza", "is_active": True},
                {"icao_code": "SADP", "name": "El Palomar", "is_active": True},
            ],
        )
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

    assert response.status_code == 422
    assert "Aerodrome SADF is not in the active controlled catalog" in response.json()["detail"]
