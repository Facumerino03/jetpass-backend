from datetime import date

import pytest
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.database import Base
from app.models import aerodrome as _aerodrome_model
from app.models import aircraft as _aircraft_model
from app.models import flight_plan as _flight_plan_model
from app.models import user as _user_model
from app.models.aircraft import WakeTurbulenceCat
from app.models.user import Role
from app.repositories.aircraft_repository import AircraftRepository
from app.repositories.user_repository import UserRepository
from app.schemas.flight_plan import FlightPlanCreate, FlightPlanUpdate
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


class InvalidAircraftTypeIntelligenceClient:
    async def run(self, payload):
        fpl_fields = payload["fpl_field18"]["fpl_fields"]
        assert fpl_fields["aircraft_type"] == "C172"
        assert fpl_fields["aircraft_type_is_valid"] is False
        return {
            "intent": "fpl_field18",
            "fpl_field18": {
                "computed_field18": "TYP/C172",
                "suggestions": [
                    {
                        "indicator": "TYP/",
                        "full_field": "TYP/C172",
                        "reason": "Non-ICAO aircraft type requires TYP/ in field 18",
                    }
                ],
                "fpl_updates": [
                    {
                        "field": "aircraft_type",
                        "from_value": "C172",
                        "to_value": "ZZZZ",
                        "reason": "Non-ICAO aircraft type must use ZZZZ in item 9",
                    }
                ],
                "alerts": [],
                "messages": [],
            },
        }


async def create_aircraft_with_type_validation(
    db_session,
    pilot,
    *,
    designator: str = "C172",
    is_valid: bool | None = False,
):
    aircraft = await AircraftRepository.create(
        db_session,
        owner_user_id=pilot.id,
        alias="Trainer",
        identification="LV-ABC",
        icao_type_designator=designator,
        wake_turbulence_category=WakeTurbulenceCat.L,
        equipment_com_nav="SDFGR",
        equipment_surveillance="B1",
        pbn_capabilities=None,
        color_and_markings="White with blue stripes",
    )
    if is_valid is not None:
        await AircraftRepository.update(
            aircraft,
            is_valid=is_valid,
            verified_at=None if is_valid is None else aircraft.created_at,
        )
    await db_session.commit()
    return aircraft


async def create_plan_with_aircraft(db_session, pilot, aircraft):
    plan = await create_plan_with_departure(db_session, pilot, departure="sabe")
    return await FlightPlanService.update_draft(
        db_session,
        pilot,
        plan.id,
        FlightPlanUpdate(aircraft_id=aircraft.id),
    )


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


@pytest.mark.asyncio
async def test_build_fpl_field18_request_includes_aircraft_type_is_valid_when_known(db_session):
    pilot = await create_pilot(db_session)
    aircraft = await create_aircraft_with_type_validation(db_session, pilot, is_valid=False)
    plan = await create_plan_with_aircraft(db_session, pilot, aircraft)

    request = await build_fpl_field18_request(db_session, plan)

    assert request["fpl_field18"]["fpl_fields"]["aircraft_type"] == "C172"
    assert request["fpl_field18"]["fpl_fields"]["aircraft_type_is_valid"] is False


@pytest.mark.asyncio
async def test_build_fpl_field18_request_omits_aircraft_type_is_valid_when_pending(db_session):
    pilot = await create_pilot(db_session)
    aircraft = await create_aircraft_with_type_validation(db_session, pilot, is_valid=None)
    plan = await create_plan_with_aircraft(db_session, pilot, aircraft)

    request = await build_fpl_field18_request(db_session, plan)

    assert request["fpl_field18"]["fpl_fields"]["aircraft_type"] == "C172"
    assert "aircraft_type_is_valid" not in request["fpl_field18"]["fpl_fields"]


@pytest.mark.asyncio
async def test_apply_invalid_aircraft_type_persists_zzzz_and_typ_in_field18(db_session):
    pilot = await create_pilot(db_session)
    aircraft = await create_aircraft_with_type_validation(db_session, pilot, is_valid=False)
    plan = await create_plan_with_aircraft(db_session, pilot, aircraft)
    service = FlightPlanField18Service(intelligence_client=InvalidAircraftTypeIntelligenceClient())

    updated_plan, result = await service.apply(db_session, pilot, plan.id)

    assert result.computed_field18 == "TYP/C172"
    assert result.suggestions[0]["indicator"] == "TYP/"
    assert updated_plan.aircraft_type_designator_snapshot == "ZZZZ"
    assert updated_plan.other_information == "TYP/C172"
