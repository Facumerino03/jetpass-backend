import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.database import Base, get_db
from app.main import app
from app.models import auth_session as _auth_session_model
from app.models import user as _user_model


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


@pytest.mark.asyncio
async def test_register_pilot_returns_tokens_and_public_user(client):
    response = await client.post(
        "/auth/register/pilot",
        json={
            "email": "Pilot@Example.com",
            "password": "safe-password-123",
            "first_name": "Amelia",
            "last_name": "Earhart",
            "phone": "+541111111111",
        },
    )

    assert response.status_code == 201
    body = response.json()
    assert body["token_type"] == "bearer"
    assert body["access_token"]
    assert body["refresh_token"]
    assert body["expires_in"] == 900
    assert body["user"]["email"] == "pilot@example.com"
    assert body["user"]["role"] == "pilot"
    assert body["user"]["is_active"] is True
    assert body["user"]["is_verified"] is False
    assert "password_hash" not in body["user"]


@pytest.mark.asyncio
async def test_register_pilot_rejects_duplicate_email(client):
    payload = {
        "email": "pilot@example.com",
        "password": "safe-password-123",
        "first_name": "Amelia",
        "last_name": "Earhart",
        "phone": None,
    }
    first = await client.post("/auth/register/pilot", json=payload)
    second = await client.post("/auth/register/pilot", json=payload)

    assert first.status_code == 201
    assert second.status_code == 409


@pytest.mark.asyncio
async def test_login_returns_tokens(client):
    await client.post(
        "/auth/register/pilot",
        json={
            "email": "pilot@example.com",
            "password": "safe-password-123",
            "first_name": "Amelia",
            "last_name": "Earhart",
            "phone": None,
        },
    )

    response = await client.post(
        "/auth/login",
        json={"email": "pilot@example.com", "password": "safe-password-123"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["access_token"]
    assert body["refresh_token"]
    assert body["user"]["email"] == "pilot@example.com"


@pytest.mark.asyncio
async def test_login_rejects_invalid_password(client):
    await client.post(
        "/auth/register/pilot",
        json={
            "email": "pilot@example.com",
            "password": "safe-password-123",
            "first_name": "Amelia",
            "last_name": "Earhart",
            "phone": None,
        },
    )

    response = await client.post(
        "/auth/login",
        json={"email": "pilot@example.com", "password": "wrong-password"},
    )

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_me_returns_current_user_with_valid_access_token(client):
    register_response = await client.post(
        "/auth/register/pilot",
        json={
            "email": "pilot@example.com",
            "password": "safe-password-123",
            "first_name": "Amelia",
            "last_name": "Earhart",
            "phone": None,
        },
    )
    access_token = register_response.json()["access_token"]

    response = await client.get(
        "/auth/me",
        headers={"Authorization": f"Bearer {access_token}"},
    )

    assert response.status_code == 200
    assert response.json()["email"] == "pilot@example.com"


@pytest.mark.asyncio
async def test_me_without_token_returns_401(client):
    response = await client.get("/auth/me")

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_refresh_rotates_token_and_rejects_reuse(client):
    register_response = await client.post(
        "/auth/register/pilot",
        json={
            "email": "pilot@example.com",
            "password": "safe-password-123",
            "first_name": "Amelia",
            "last_name": "Earhart",
            "phone": None,
        },
    )
    old_refresh_token = register_response.json()["refresh_token"]

    refresh_response = await client.post(
        "/auth/refresh",
        json={"refresh_token": old_refresh_token},
    )

    assert refresh_response.status_code == 200
    new_body = refresh_response.json()
    assert new_body["access_token"]
    assert new_body["refresh_token"] != old_refresh_token

    reuse_response = await client.post(
        "/auth/refresh",
        json={"refresh_token": old_refresh_token},
    )
    assert reuse_response.status_code == 401


@pytest.mark.asyncio
async def test_logout_revokes_refresh_token(client):
    register_response = await client.post(
        "/auth/register/pilot",
        json={
            "email": "pilot@example.com",
            "password": "safe-password-123",
            "first_name": "Amelia",
            "last_name": "Earhart",
            "phone": None,
        },
    )
    refresh_token = register_response.json()["refresh_token"]

    logout_response = await client.post(
        "/auth/logout",
        json={"refresh_token": refresh_token},
    )
    refresh_response = await client.post(
        "/auth/refresh",
        json={"refresh_token": refresh_token},
    )

    assert logout_response.status_code == 200
    assert logout_response.json() == {"revoked": True}
    assert refresh_response.status_code == 401
