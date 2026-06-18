from datetime import date, datetime, timezone

import pytest
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.database import Base
from app.models import aircraft as _aircraft_model
from app.models import controlled_aerodrome as _controlled_aerodrome_model
from app.models import flight_plan as _flight_plan_model
from app.models import flight_plan_approval as _approval_model
from app.models import flight_plan_status_history as _history_model
from app.models import profiles as _profiles_model
from app.models import user as _user_model
from app.models.aircraft import WakeTurbulenceCat
from app.models.flight_plan import FlightPlanStatus
from app.models.flight_plan_approval import FlightPlanApprovalStatus
from app.models.profiles import AuthorityType
from app.models.user import Role
from app.repositories.aircraft_repository import AircraftRepository
from app.repositories.controlled_aerodrome_repository import ControlledAerodromeRepository
from app.repositories.flight_plan_approval_repository import FlightPlanApprovalRepository
from app.repositories.flight_plan_status_history_repository import FlightPlanStatusHistoryRepository
from app.repositories.profile_repository import ProfileRepository
from app.repositories.user_repository import UserRepository
from app.schemas.flight_plan import FlightPlanCreate, FlightPlanUpdate
from app.services.flight_plan_service import FlightPlanService


@pytest.fixture
async def db_session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        await ControlledAerodromeRepository.upsert_many(
            session,
            items=[
                {"icao_code": "SABE", "name": "Aeroparque", "is_active": True},
                {"icao_code": "SAEZ", "name": "Ezeiza", "is_active": True},
                {"icao_code": "SADP", "name": "El Palomar", "is_active": True},
                {"icao_code": "SADF", "name": "San Fernando", "is_active": True},
            ],
        )
        await session.commit()
        yield session
    await engine.dispose()


async def create_user(db_session, *, email: str, role: Role):
    return await UserRepository.create(
        db_session,
        email=email,
        password_hash="hashed",
        first_name="Amelia",
        last_name="Earhart",
        phone=None,
        role=role,
    )


async def create_aircraft(db_session, pilot):
    return await AircraftRepository.create(
        db_session,
        owner_user_id=pilot.id,
        alias="Trainer",
        identification="lv-abc",
        icao_type_designator="c172",
        wake_turbulence_category=WakeTurbulenceCat.L,
        equipment_com_nav="SDFGR",
        equipment_surveillance="B1",
        pbn_capabilities="B2C2D2",
        emergency_radio_uhf=True,
        emergency_radio_vhf=True,
        emergency_radio_elt=False,
        survival_equipment_present=True,
        survival_polar=False,
        survival_desert=False,
        survival_maritime=False,
        survival_jungle=True,
        life_jackets_present=True,
        life_jackets_lights=True,
        life_jackets_fluorescein=False,
        life_jackets_uhf=False,
        life_jackets_vhf=False,
        dinghies_present=True,
        dinghies_number=1,
        dinghies_capacity=4,
        dinghies_cover_present=True,
        dinghies_color="Orange",
        color_and_markings="White with blue stripes",
    )


def create_payload():
    return FlightPlanCreate(
        departure_aerodrome_icao="sabe",
        departure_time_utc="1430",
        flight_date=date(2026, 5, 18),
        destination_aerodrome_icao="saez",
        alternate1_aerodrome_icao="sadp",
        alternate2_aerodrome_icao="sadf",
    )


@pytest.mark.asyncio
async def test_service_creates_step_one_draft_for_pilot(db_session):
    pilot = await create_user(db_session, email="pilot@example.com", role=Role.PILOT)

    plan = await FlightPlanService.create_draft(db_session, pilot, create_payload())

    assert plan.status == FlightPlanStatus.DRAFT
    assert plan.pilot_user_id == pilot.id
    assert plan.departure_aerodrome_icao == "SABE"
    assert plan.departure_time_utc == "1430"
    assert plan.flight_date == date(2026, 5, 18)
    assert plan.aircraft_number == 1
    assert plan.pilot_in_command == "Amelia Earhart"


@pytest.mark.asyncio
async def test_service_selects_aircraft_and_generates_snapshot(db_session):
    pilot = await create_user(db_session, email="pilot@example.com", role=Role.PILOT)
    aircraft = await create_aircraft(db_session, pilot)
    plan = await FlightPlanService.create_draft(db_session, pilot, create_payload())

    updated = await FlightPlanService.update_draft(
        db_session,
        pilot,
        plan.id,
        FlightPlanUpdate(aircraft_id=aircraft.id),
    )

    assert updated.aircraft_id == aircraft.id
    assert updated.aircraft_identification_snapshot == "LV-ABC"
    assert updated.aircraft_type_designator_snapshot == "C172"
    assert updated.equipment_com_nav_snapshot == "SDFGR"
    assert updated.emergency_radio_uhf_snapshot is True
    assert updated.emergency_radio_vhf_snapshot is True
    assert updated.emergency_radio_elt_snapshot is False
    assert updated.survival_equipment_present_snapshot is True
    assert updated.survival_jungle_snapshot is True
    assert updated.life_jackets_present_snapshot is True
    assert updated.life_jackets_lights_snapshot is True
    assert updated.dinghies_present_snapshot is True
    assert updated.dinghies_number_snapshot == 1
    assert updated.dinghies_cover_present_snapshot is True
    assert updated.aircraft_snapshot_confirmed_at is not None


@pytest.mark.asyncio
async def test_service_rejects_aircraft_owned_by_another_pilot(db_session):
    owner = await create_user(db_session, email="owner@example.com", role=Role.PILOT)
    other = await create_user(db_session, email="other@example.com", role=Role.PILOT)
    aircraft = await create_aircraft(db_session, owner)
    plan = await FlightPlanService.create_draft(db_session, other, create_payload())

    with pytest.raises(HTTPException) as exc:
        await FlightPlanService.update_draft(
            db_session,
            other,
            plan.id,
            FlightPlanUpdate(aircraft_id=aircraft.id),
        )

    assert exc.value.status_code == 404


async def complete_plan(db_session, pilot):
    aircraft = await create_aircraft(db_session, pilot)
    plan = await FlightPlanService.create_draft(db_session, pilot, create_payload())
    return await FlightPlanService.update_draft(
        db_session,
        pilot,
        plan.id,
        FlightPlanUpdate(
            flight_rules="V",
            flight_type="G",
            aircraft_id=aircraft.id,
            cruising_speed="N0120",
            cruising_level="A045",
            route="DCT GUALE DCT",
            total_eet="0100",
            endurance="0230",
            persons_on_board=2,
            other_information="RMK/TRAINING",
        ),
    )


@pytest.mark.asyncio
async def test_submit_complete_plan_creates_history_and_approvals(db_session):
    pilot = await create_user(db_session, email="pilot@example.com", role=Role.PILOT)
    plan = await complete_plan(db_session, pilot)

    submitted = await FlightPlanService.submit(db_session, pilot, plan.id)

    assert submitted.status == FlightPlanStatus.PENDING_APPROVAL
    histories = await FlightPlanStatusHistoryRepository.list_by_plan(db_session, flight_plan_id=plan.id)
    approvals = await FlightPlanApprovalRepository.list_by_plan(db_session, flight_plan_id=plan.id)
    assert [(item.from_status, item.to_status) for item in histories] == [
        (FlightPlanStatus.DRAFT, FlightPlanStatus.FILED),
        (FlightPlanStatus.FILED, FlightPlanStatus.PENDING_APPROVAL),
    ]
    assert [item.criterion for item in approvals] == [
        "pilot_submission",
        "authority_acceptance",
        "destination_aerodrome_acceptance",
    ]
    assert approvals[0].status == FlightPlanApprovalStatus.APPROVED
    assert approvals[1].status == FlightPlanApprovalStatus.PENDING
    assert approvals[2].status == FlightPlanApprovalStatus.PENDING


@pytest.mark.asyncio
async def test_submit_requires_endurance_greater_than_total_eet(db_session):
    pilot = await create_user(db_session, email="pilot@example.com", role=Role.PILOT)
    aircraft = await create_aircraft(db_session, pilot)
    plan = await FlightPlanService.create_draft(db_session, pilot, create_payload())
    plan = await FlightPlanService.update_draft(
        db_session,
        pilot,
        plan.id,
        FlightPlanUpdate(
            flight_rules="V",
            flight_type="G",
            aircraft_id=aircraft.id,
            cruising_speed="N0120",
            cruising_level="A045",
            route="DCT GUALE DCT",
            total_eet="0200",
            endurance="0130",
            persons_on_board=2,
        ),
    )

    with pytest.raises(HTTPException) as exc:
        await FlightPlanService.submit(db_session, pilot, plan.id)

    assert exc.value.status_code == 422
    assert "endurance must be greater than total_eet" in exc.value.detail


@pytest.mark.asyncio
async def test_authority_and_airport_operator_approval_accepts_plan(db_session):
    pilot = await create_user(db_session, email="pilot@example.com", role=Role.PILOT)
    authority = await create_user(db_session, email="authority@example.com", role=Role.ATC_AUTHORITY)
    operator = await create_user(db_session, email="operator@example.com", role=Role.AIRPORT_OPERATOR)
    await ProfileRepository.create_authority_profile(
        db_session,
        user_id=authority.id,
        organization_name="ANAC",
        authority_type=AuthorityType.ANAC,
        aerodrome_icao_code=None,
    )
    await ProfileRepository.create_airport_operator_profile(
        db_session,
        user_id=operator.id,
        organization_name="Ezeiza Operator",
        aerodrome_icao_code="SAEZ",
    )
    plan = await complete_plan(db_session, pilot)
    plan = await FlightPlanService.submit(db_session, pilot, plan.id)

    plan = await FlightPlanService.approve(db_session, authority, plan.id)
    assert plan.status == FlightPlanStatus.PENDING_APPROVAL

    plan = await FlightPlanService.approve(db_session, operator, plan.id)
    assert plan.status == FlightPlanStatus.ACCEPTED


@pytest.mark.asyncio
async def test_reject_requires_reason_and_transitions_plan_to_rejected(db_session):
    pilot = await create_user(db_session, email="pilot@example.com", role=Role.PILOT)
    authority = await create_user(db_session, email="authority@example.com", role=Role.ATC_AUTHORITY)
    await ProfileRepository.create_authority_profile(
        db_session,
        user_id=authority.id,
        organization_name="ANAC",
        authority_type=AuthorityType.ANAC,
        aerodrome_icao_code=None,
    )
    plan = await complete_plan(db_session, pilot)
    plan = await FlightPlanService.submit(db_session, pilot, plan.id)

    with pytest.raises(HTTPException) as exc:
        await FlightPlanService.reject(db_session, authority, plan.id, reason="")
    assert exc.value.status_code == 422

    rejected = await FlightPlanService.reject(db_session, authority, plan.id, reason="Route requires correction")
    assert rejected.status == FlightPlanStatus.REJECTED
