from datetime import date

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.database import Base
from app.models import profiles as _profiles_model
from app.models import user as _user_model
from app.models.profiles import AuthorityType
from app.models.user import Role
from app.repositories.profile_repository import ProfileRepository
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


async def create_user(db_session, *, email: str, role: Role):
    return await UserRepository.create(
        db_session,
        email=email,
        password_hash="hashed",
        first_name="Test",
        last_name="User",
        phone=None,
        role=role,
    )


@pytest.mark.asyncio
async def test_profile_repository_creates_and_fetches_authority_profile(db_session):
    user = await create_user(db_session, email="authority@example.com", role=Role.ATC_AUTHORITY)

    profile = await ProfileRepository.create_authority_profile(
        db_session,
        user_id=user.id,
        organization_name="ANAC",
        authority_type=AuthorityType.ANAC,
        aerodrome_icao_code=None,
    )
    await db_session.commit()

    fetched = await ProfileRepository.get_authority_profile_by_user_id(db_session, user_id=user.id)

    assert fetched is not None
    assert fetched.id == profile.id
    assert fetched.user_id == user.id
    assert fetched.organization_name == "ANAC"
    assert fetched.authority_type == AuthorityType.ANAC
    assert fetched.aerodrome_icao_code is None


@pytest.mark.asyncio
async def test_profile_repository_normalizes_airport_operator_aerodrome(db_session):
    user = await create_user(db_session, email="operator@example.com", role=Role.AIRPORT_OPERATOR)

    profile = await ProfileRepository.create_airport_operator_profile(
        db_session,
        user_id=user.id,
        organization_name="Ezeiza Operator",
        aerodrome_icao_code="saez",
    )
    await db_session.commit()

    fetched = await ProfileRepository.get_airport_operator_profile_by_user_id(db_session, user_id=user.id)

    assert fetched is not None
    assert fetched.id == profile.id
    assert fetched.aerodrome_icao_code == "SAEZ"


@pytest.mark.asyncio
async def test_profile_repository_creates_pilot_profile(db_session):
    user = await create_user(db_session, email="pilot-profile@example.com", role=Role.PILOT)

    profile = await ProfileRepository.create_pilot_profile(
        db_session,
        user_id=user.id,
        license_number="PPA-123",
        license_type="PPA",
        license_country="AR",
        license_expiry=date(2030, 1, 1),
        signature="Amelia Earhart",
    )
    await db_session.commit()

    fetched = await ProfileRepository.get_pilot_profile_by_user_id(db_session, user_id=user.id)

    assert fetched is not None
    assert fetched.id == profile.id
    assert fetched.license_number == "PPA-123"
