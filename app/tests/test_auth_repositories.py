from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.database import Base
from app.models import auth_session as _auth_session_model
from app.models import user as _user_model
from app.models.user import Role
from app.repositories.auth_session_repository import AuthSessionRepository
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


@pytest.mark.asyncio
async def test_user_repository_creates_and_fetches_by_email(db_session):
    user = await UserRepository.create(
        db_session,
        email="pilot@example.com",
        password_hash="hashed",
        first_name="Amelia",
        last_name="Earhart",
        phone=None,
        role=Role.PILOT,
    )
    await db_session.commit()

    fetched = await UserRepository.get_by_email(db_session, "pilot@example.com")

    assert fetched is not None
    assert fetched.id == user.id
    assert fetched.role == Role.PILOT
    assert fetched.is_active is True
    assert fetched.is_verified is False


@pytest.mark.asyncio
async def test_auth_session_repository_rotates_refresh_token(db_session):
    user = await UserRepository.create(
        db_session,
        email="pilot@example.com",
        password_hash="hashed",
        first_name="Amelia",
        last_name="Earhart",
        phone="+541111111111",
        role=Role.PILOT,
    )
    session = await AuthSessionRepository.create(
        db_session,
        user_id=user.id,
        refresh_token_hash="old-hash",
        expires_at=datetime.now(timezone.utc) + timedelta(days=30),
        user_agent="pytest",
        ip_address="127.0.0.1",
        device_name="test-device",
    )
    await db_session.commit()

    active = await AuthSessionRepository.get_active_by_refresh_token_hash(
        db_session,
        "old-hash",
        now=datetime.now(timezone.utc),
    )
    assert active is not None
    assert active.id == session.id

    await AuthSessionRepository.revoke(db_session, session, now=datetime.now(timezone.utc))
    await db_session.commit()

    reused = await AuthSessionRepository.get_active_by_refresh_token_hash(
        db_session,
        "old-hash",
        now=datetime.now(timezone.utc),
    )
    assert reused is None
