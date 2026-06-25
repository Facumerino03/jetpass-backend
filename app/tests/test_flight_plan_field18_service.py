from datetime import date

import pytest
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.database import Base
from app.models import aerodrome as _aerodrome_model
from app.models import flight_plan as _flight_plan_model
from app.models import user as _user_model
from app.models.user import Role
from app.repositories.user_repository import UserRepository
from app.schemas.flight_plan import FlightPlanCreate
from app.services.flight_plan_field18_service import FlightPlanField18Service
from app.services.flight_plan_service import FlightPlanService
from app.services.fpl_field18_mapper import build_fpl_field18_request
from app.services.intelligence_client import IntelligenceClient
from app.tests.aerodrome_fixtures import seed_aerodrome, seed_flight_plan_aerodromes


@pytest.fixture
async def db_session():
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
        yield session
    await engine.dispose()


async def create_pilot(db_session):
    return await UserRepository.create(
        db_session,
        email="pilot@example.com",
        password_hash="hashed",
        first_name="Amelia",
        last_name="Earhart",
        phone=None,
        role=Role.PILOT,
    )


async def create_plan_with_departure(db_session, pilot, *, departure: str):
    return await FlightPlanService.create_draft(
        db_session,
        pilot,
        FlightPlanCreate(
            departure_aerodrome_icao=departure,
            departure_time_utc="1430",
            flight_date=date(2026, 5, 18),
            destination_aerodrome_icao="saez",
            alternate1_aerodrome_icao="sadp",
            alternate2_aerodrome_icao="sadf",
        ),
    )


class ControlledIntelligenceClient:
    async def run(self, payload):
        assert "fpl_field18" in payload
        assert payload["fpl_field18"]["fpl_fields"]["departure_aerodrome"] == "SABE"
        assert "departure" in payload["fpl_field18"]["aerodromes"]
        return {
            "intent": "fpl_field18",
            "fpl_field18": {
                "computed_field18": "",
                "suggestions": [],
                "fpl_updates": [],
                "alerts": [],
                "messages": ["Controlled aerodrome requires no field 18 changes."],
            },
        }


class NonControlledIntelligenceClient:
    async def run(self, payload):
        assert payload["fpl_field18"]["fpl_fields"]["departure_aerodrome"] == "MZA"
        departure = payload["fpl_field18"]["aerodromes"]["departure"]
        assert departure["is_controlled"] is False
        assert departure["fpl_code"] == "MZA"
        return {
            "intent": "fpl_field18",
            "fpl_field18": {
                "computed_field18": "DEP/MZA3250S06848W",
                "suggestions": [{"code": "DEP", "value": "MZA3250S06848W"}],
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


class ErrorAlertIntelligenceClient:
    async def run(self, _payload):
        return {
            "intent": "fpl_field18",
            "fpl_field18": {
                "computed_field18": "",
                "suggestions": [],
                "fpl_updates": [],
                "alerts": [{"level": "error", "code": "MISSING_COORDS", "message": "Missing coordinates"}],
                "messages": [],
            },
        }


class StaleFromValueIntelligenceClient:
    async def run(self, _payload):
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


@pytest.mark.asyncio
async def test_build_fpl_field18_request_maps_slots_and_skips_zzzz(db_session):
    pilot = await create_pilot(db_session)
    plan = await create_plan_with_departure(db_session, pilot, departure="mza")
    plan.other_information = "DEP/MZA3250S06848W"
    plan.departure_aerodrome_icao = "ZZZZ"
    await db_session.commit()

    request = await build_fpl_field18_request(db_session, plan)

    assert request["fpl_field18"]["fpl_fields"]["departure_aerodrome"] == "ZZZZ"
    assert "departure" not in request["fpl_field18"]["aerodromes"]
    assert request["fpl_field18"]["current_field18"] == "DEP/MZA3250S06848W"


@pytest.mark.asyncio
async def test_preview_controlled_aerodrome_returns_no_updates(db_session):
    pilot = await create_pilot(db_session)
    plan = await create_plan_with_departure(db_session, pilot, departure="sabe")
    service = FlightPlanField18Service(intelligence_client=ControlledIntelligenceClient())

    intent, result = await service.preview(db_session, pilot, plan.id)

    assert intent == "fpl_field18"
    assert result.fpl_updates == []
    assert result.computed_field18 == ""


@pytest.mark.asyncio
async def test_preview_non_controlled_suggests_zzzz_and_dep_detail(db_session):
    pilot = await create_pilot(db_session)
    plan = await create_plan_with_departure(db_session, pilot, departure="mza")
    service = FlightPlanField18Service(intelligence_client=NonControlledIntelligenceClient())

    _, result = await service.preview(db_session, pilot, plan.id)

    assert result.computed_field18 == "DEP/MZA3250S06848W"
    assert len(result.fpl_updates) == 1
    assert result.fpl_updates[0].to_value == "ZZZZ"

    refreshed = await FlightPlanService.get_visible(db_session, pilot, plan.id)
    assert refreshed.departure_aerodrome_icao == "MZA"
    assert refreshed.other_information is None


@pytest.mark.asyncio
async def test_apply_non_controlled_persists_zzzz_and_field18(db_session):
    pilot = await create_pilot(db_session)
    plan = await create_plan_with_departure(db_session, pilot, departure="mza")
    service = FlightPlanField18Service(intelligence_client=NonControlledIntelligenceClient())

    updated_plan, result = await service.apply(db_session, pilot, plan.id)

    assert result.computed_field18 == "DEP/MZA3250S06848W"
    assert updated_plan.departure_aerodrome_icao == "ZZZZ"
    assert updated_plan.other_information == "DEP/MZA3250S06848W"


@pytest.mark.asyncio
async def test_apply_skips_stale_from_value_updates(db_session):
    pilot = await create_pilot(db_session)
    plan = await create_plan_with_departure(db_session, pilot, departure="mza")
    plan.departure_aerodrome_icao = "SABE"
    await db_session.commit()
    service = FlightPlanField18Service(intelligence_client=StaleFromValueIntelligenceClient())

    updated_plan, _ = await service.apply(db_session, pilot, plan.id)

    assert updated_plan.departure_aerodrome_icao == "SABE"
    assert updated_plan.other_information == "DEP/MZA3250S06848W"


@pytest.mark.asyncio
async def test_apply_with_error_alerts_returns_422_without_persisting_changes(db_session):
    pilot = await create_pilot(db_session)
    plan = await create_plan_with_departure(db_session, pilot, departure="mza")
    service = FlightPlanField18Service(intelligence_client=ErrorAlertIntelligenceClient())

    with pytest.raises(HTTPException) as exc:
        await service.apply(db_session, pilot, plan.id)

    assert exc.value.status_code == 422

    refreshed = await FlightPlanService.get_visible(db_session, pilot, plan.id)
    assert refreshed.departure_aerodrome_icao == "MZA"
    assert refreshed.other_information is None


@pytest.mark.asyncio
async def test_preview_raises_when_intelligence_unavailable(db_session):
    pilot = await create_pilot(db_session)
    plan = await create_plan_with_departure(db_session, pilot, departure="sabe")
    service = FlightPlanField18Service(
        intelligence_client=IntelligenceClient(base_url=None, timeout_seconds=1.0),
    )

    with pytest.raises(HTTPException) as exc:
        await service.preview(db_session, pilot, plan.id)

    assert exc.value.status_code == 503


@pytest.mark.asyncio
async def test_preview_rejects_non_owner(db_session):
    pilot = await create_pilot(db_session)
    other = await UserRepository.create(
        db_session,
        email="other@example.com",
        password_hash="hashed",
        first_name="Other",
        last_name="Pilot",
        phone=None,
        role=Role.PILOT,
    )
    plan = await create_plan_with_departure(db_session, pilot, departure="sabe")
    service = FlightPlanField18Service(intelligence_client=ControlledIntelligenceClient())

    with pytest.raises(HTTPException) as exc:
        await service.preview(db_session, other, plan.id)

    assert exc.value.status_code == 404
