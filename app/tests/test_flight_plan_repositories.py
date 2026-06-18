from datetime import date, datetime, timezone

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.database import Base
from app.models import aircraft as _aircraft_model
from app.models import flight_plan as _flight_plan_model
from app.models import flight_plan_approval as _approval_model
from app.models import flight_plan_status_history as _history_model
from app.models import profiles as _profiles_model
from app.models import user as _user_model
from app.models.flight_plan import FlightPlanStatus
from app.models.flight_plan_approval import FlightPlanApprovalActor, FlightPlanApprovalStatus
from app.models.user import Role
from app.repositories.flight_plan_approval_repository import FlightPlanApprovalRepository
from app.repositories.flight_plan_repository import FlightPlanRepository
from app.repositories.flight_plan_status_history_repository import FlightPlanStatusHistoryRepository
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
async def test_flight_plan_repository_creates_step_one_draft(db_session):
    pilot = await create_pilot(db_session)

    plan = await FlightPlanRepository.create_draft(
        db_session,
        pilot_user_id=pilot.id,
        pilot_in_command="Amelia Earhart",
        departure_aerodrome_icao="sabe",
        departure_time_utc="1430",
        flight_date=date(2026, 5, 18),
        destination_aerodrome_icao="saez",
        alternate1_aerodrome_icao="sadp",
        alternate2_aerodrome_icao="sadf",
    )
    await db_session.commit()

    fetched = await FlightPlanRepository.get_by_id(db_session, flight_plan_id=plan.id)

    assert fetched is not None
    assert fetched.id == plan.id
    assert fetched.status == FlightPlanStatus.DRAFT
    assert fetched.pilot_user_id == pilot.id
    assert fetched.departure_aerodrome_icao == "SABE"
    assert fetched.departure_time_utc == "1430"
    assert fetched.flight_date == date(2026, 5, 18)
    assert fetched.aircraft_number == 1
    assert fetched.pilot_in_command == "Amelia Earhart"


@pytest.mark.asyncio
async def test_approval_and_history_repositories_persist_records(db_session):
    pilot = await create_pilot(db_session)
    plan = await FlightPlanRepository.create_draft(
        db_session,
        pilot_user_id=pilot.id,
        pilot_in_command="Amelia Earhart",
        departure_aerodrome_icao="SABE",
        departure_time_utc="1430",
        flight_date=date(2026, 5, 18),
        destination_aerodrome_icao="SAEZ",
        alternate1_aerodrome_icao="SADP",
        alternate2_aerodrome_icao="SADF",
    )

    history = await FlightPlanStatusHistoryRepository.create(
        db_session,
        flight_plan_id=plan.id,
        from_status=FlightPlanStatus.DRAFT,
        to_status=FlightPlanStatus.FILED,
        updated_by_user_id=pilot.id,
        reason="submitted",
    )
    approval = await FlightPlanApprovalRepository.create(
        db_session,
        flight_plan_id=plan.id,
        actor=FlightPlanApprovalActor.PILOT,
        criterion="pilot_submission",
        status=FlightPlanApprovalStatus.APPROVED,
        approved_by_user_id=pilot.id,
    )
    await db_session.commit()

    histories = await FlightPlanStatusHistoryRepository.list_by_plan(db_session, flight_plan_id=plan.id)
    approvals = await FlightPlanApprovalRepository.list_by_plan(db_session, flight_plan_id=plan.id)

    assert [item.id for item in histories] == [history.id]
    assert [item.id for item in approvals] == [approval.id]
    assert approvals[0].criterion == "pilot_submission"
    assert approvals[0].status == FlightPlanApprovalStatus.APPROVED
