import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.database import Base
from app.models import aircraft as _aircraft_model
from app.models import user as _user_model
from app.models.aircraft import WakeTurbulenceCat
from app.models.user import Role
from app.repositories.aircraft_repository import AircraftRepository
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


async def create_pilot(db_session, *, email: str = "pilot@example.com"):
    return await UserRepository.create(
        db_session,
        email=email,
        password_hash="hashed",
        first_name="Amelia",
        last_name="Earhart",
        phone=None,
        role=Role.PILOT,
    )


@pytest.mark.asyncio
async def test_aircraft_repository_creates_and_fetches_active_aircraft_by_owner(db_session):
    pilot = await create_pilot(db_session)
    aircraft = await AircraftRepository.create(
        db_session,
        owner_user_id=pilot.id,
        alias="Club trainer",
        identification="lv-abc",
        icao_type_designator="c172",
        wake_turbulence_category=WakeTurbulenceCat.L,
        equipment_com_nav="SDFGR",
        equipment_surveillance="B1",
        pbn_capabilities="B2C2D2",
        emergency_radio="UVE",
        survival_equipment="J",
        life_jackets="L",
        dinghies_number=1,
        dinghies_capacity=4,
        dinghies_cover=True,
        dinghies_color="Orange",
        color_and_markings="White with blue stripes",
    )
    await db_session.commit()

    fetched = await AircraftRepository.get_active_by_owner_and_id(
        db_session,
        owner_user_id=pilot.id,
        aircraft_id=aircraft.id,
    )
    active_aircraft = await AircraftRepository.list_active_by_owner(
        db_session,
        owner_user_id=pilot.id,
    )

    assert fetched is not None
    assert fetched.id == aircraft.id
    assert fetched.owner_user_id == pilot.id
    assert fetched.identification == "LV-ABC"
    assert fetched.icao_type_designator == "C172"
    assert fetched.wake_turbulence_category == WakeTurbulenceCat.L
    assert fetched.is_active is True
    assert fetched.image_url is None
    assert [item.id for item in active_aircraft] == [aircraft.id]


@pytest.mark.asyncio
async def test_aircraft_repository_persists_image_url(db_session):
    pilot = await create_pilot(db_session)
    aircraft = await AircraftRepository.create(
        db_session,
        owner_user_id=pilot.id,
        alias="Image Test",
        identification="LV-IMG",
        icao_type_designator="C172",
        wake_turbulence_category=WakeTurbulenceCat.L,
        equipment_com_nav="S",
        equipment_surveillance="C",
        pbn_capabilities=None,
        emergency_radio=None,
        survival_equipment=None,
        life_jackets=None,
        dinghies_number=None,
        dinghies_capacity=None,
        dinghies_cover=None,
        dinghies_color=None,
        color_and_markings="Red",
        image_url="https://bucket.example.com/aircraft/lv-img.jpg",
    )
    await db_session.commit()

    fetched = await AircraftRepository.get_active_by_owner_and_id(
        db_session,
        owner_user_id=pilot.id,
        aircraft_id=aircraft.id,
    )

    assert fetched is not None
    assert fetched.image_url == "https://bucket.example.com/aircraft/lv-img.jpg"


@pytest.mark.asyncio
async def test_aircraft_repository_excludes_soft_deleted_aircraft(db_session):
    pilot = await create_pilot(db_session)
    aircraft = await AircraftRepository.create(
        db_session,
        owner_user_id=pilot.id,
        alias=None,
        identification="LV-DEF",
        icao_type_designator="PA28",
        wake_turbulence_category=WakeTurbulenceCat.L,
        equipment_com_nav="S",
        equipment_surveillance="C",
        pbn_capabilities=None,
        emergency_radio=None,
        survival_equipment=None,
        life_jackets=None,
        dinghies_number=None,
        dinghies_capacity=None,
        dinghies_cover=None,
        dinghies_color=None,
        color_and_markings="White",
    )
    await AircraftRepository.soft_delete(aircraft)
    await db_session.commit()

    fetched = await AircraftRepository.get_active_by_owner_and_id(
        db_session,
        owner_user_id=pilot.id,
        aircraft_id=aircraft.id,
    )
    active_aircraft = await AircraftRepository.list_active_by_owner(
        db_session,
        owner_user_id=pilot.id,
    )

    assert fetched is None
    assert active_aircraft == []
