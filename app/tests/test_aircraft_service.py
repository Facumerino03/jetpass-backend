import pytest
from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.database import Base
from app.models import aircraft as _aircraft_model
from app.models import auth_session as _auth_session_model
from app.models import user as _user_model
from app.models.aircraft import WakeTurbulenceCat
from app.models.user import Role
from app.repositories.user_repository import UserRepository
from app.schemas.aircraft import AircraftCreate, AircraftUpdate
from app.services.aircraft_service import AircraftService


@pytest.fixture
async def db_session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        yield session
    await engine.dispose()


async def create_user(db_session, *, email: str = "pilot@example.com", role: Role = Role.PILOT):
    return await UserRepository.create(
        db_session,
        email=email,
        password_hash="hashed",
        first_name="Amelia",
        last_name="Earhart",
        phone=None,
        role=role,
    )


def aircraft_create_payload() -> AircraftCreate:
    return AircraftCreate(
        alias="Club trainer",
        identification="lv-abc",
        icao_type_designator="c172",
        wake_turbulence_category=WakeTurbulenceCat.L,
        equipment_com_nav="SDFGR",
        equipment_surveillance="B1",
        color_and_markings="White with blue stripes",
    )


def test_aircraft_create_payload_defaults_optional_fields_to_none():
    payload = aircraft_create_payload()

    assert payload.alias == "Club trainer"
    assert payload.identification == "lv-abc"
    assert payload.icao_type_designator == "c172"
    assert payload.wake_turbulence_category == WakeTurbulenceCat.L
    assert payload.equipment_com_nav == "SDFGR"
    assert payload.equipment_surveillance == "B1"
    assert payload.pbn_capabilities is None
    assert payload.emergency_radio_uhf is False
    assert payload.emergency_radio_vhf is False
    assert payload.emergency_radio_elt is False
    assert payload.survival_equipment_present is False
    assert payload.survival_polar is False
    assert payload.survival_desert is False
    assert payload.survival_maritime is False
    assert payload.survival_jungle is False
    assert payload.life_jackets_present is False
    assert payload.life_jackets_lights is False
    assert payload.life_jackets_fluorescein is False
    assert payload.life_jackets_uhf is False
    assert payload.life_jackets_vhf is False
    assert payload.dinghies_present is False
    assert payload.dinghies_number is None
    assert payload.dinghies_capacity is None
    assert payload.dinghies_cover_present is False
    assert payload.dinghies_color is None
    assert payload.color_and_markings == "White with blue stripes"


def test_aircraft_create_rejects_blank_identification():
    with pytest.raises(ValidationError):
        AircraftCreate(
            identification="",
            icao_type_designator="c172",
            wake_turbulence_category=WakeTurbulenceCat.L,
            equipment_com_nav="SDFGR",
            equipment_surveillance="B1",
            color_and_markings="White with blue stripes",
        )


@pytest.mark.asyncio
async def test_aircraft_service_creates_updates_and_soft_deletes_for_pilot(db_session):
    pilot = await create_user(db_session)
    service = AircraftService()

    created = await service.create_for_pilot(db_session, pilot, aircraft_create_payload())
    updated = await service.update_for_pilot(
        db_session,
        pilot,
        created.id,
        AircraftUpdate(alias="Updated trainer", color_and_markings="White"),
    )
    deleted = await service.delete_for_pilot(db_session, pilot, created.id)
    fetched_after_delete = await service.get_for_pilot(db_session, pilot, created.id)

    assert created.owner_user_id == pilot.id
    assert created.identification == "LV-ABC"
    assert updated.alias == "Updated trainer"
    assert updated.color_and_markings == "White"
    assert deleted is True
    assert fetched_after_delete is None


@pytest.mark.asyncio
async def test_aircraft_service_rejects_non_pilot_users(db_session):
    user = await create_user(
        db_session,
        email="admin@example.com",
        role=Role.ADMIN,
    )

    with pytest.raises(HTTPException) as exc_info:
        await AircraftService().create_for_pilot(db_session, user, aircraft_create_payload())

    assert exc_info.value.status_code == 403
    assert exc_info.value.detail == "Only pilots can manage aircraft"
