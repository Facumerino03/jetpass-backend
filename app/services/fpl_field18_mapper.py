from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.aerodrome import Aerodrome
from app.models.flight_plan import FlightPlan
from app.repositories.aerodrome_repository import AerodromeRepository
from app.repositories.aircraft_repository import AircraftRepository

FPL_FIELD_TO_COLUMN: dict[str, str] = {
    "departure_aerodrome": "departure_aerodrome_icao",
    "destination_aerodrome": "destination_aerodrome_icao",
    "alternate_aerodrome_1": "alternate1_aerodrome_icao",
    "alternate_aerodrome_2": "alternate2_aerodrome_icao",
    "aircraft_type": "aircraft_type_designator_snapshot",
}

COLUMN_TO_FPL_FIELD: dict[str, str] = {value: key for key, value in FPL_FIELD_TO_COLUMN.items()}

SLOT_COLUMNS: dict[str, str] = {
    "departure": "departure_aerodrome_icao",
    "destination": "destination_aerodrome_icao",
    "alternate_1": "alternate1_aerodrome_icao",
    "alternate_2": "alternate2_aerodrome_icao",
}


def to_fpl_aerodrome_context(aerodrome: Aerodrome, *, fpl_code: str) -> dict[str, Any]:
    return {
        "fpl_code": fpl_code,
        "local_identifier": aerodrome.local_identifier,
        "icao_code": aerodrome.icao_code,
        "is_controlled": aerodrome.is_controlled,
        "latitude": aerodrome.latitude,
        "longitude": aerodrome.longitude,
        "name": aerodrome.name,
    }


def build_fpl_fields(plan: FlightPlan, *, aircraft_type_is_valid: bool | None = None) -> dict[str, Any]:
    fields: dict[str, Any] = {
        "departure_aerodrome": plan.departure_aerodrome_icao,
        "destination_aerodrome": plan.destination_aerodrome_icao,
        "alternate_aerodrome_1": plan.alternate1_aerodrome_icao,
        "alternate_aerodrome_2": plan.alternate2_aerodrome_icao,
    }
    if plan.aircraft_type_designator_snapshot:
        fields["aircraft_type"] = plan.aircraft_type_designator_snapshot
        if aircraft_type_is_valid is not None:
            fields["aircraft_type_is_valid"] = aircraft_type_is_valid
    if plan.aircraft_identification_snapshot:
        fields["aircraft_identification"] = plan.aircraft_identification_snapshot
        fields["registration"] = plan.aircraft_identification_snapshot
    return fields


async def resolve_aircraft_type_is_valid(db: AsyncSession, plan: FlightPlan) -> bool | None:
    if plan.aircraft_id is None:
        return None
    aircraft = await AircraftRepository.get_by_id(db, aircraft_id=plan.aircraft_id)
    if aircraft is None:
        return None
    return aircraft.is_valid


async def build_aerodromes_by_slot(db: AsyncSession, plan: FlightPlan) -> dict[str, dict[str, Any]]:
    aerodromes_by_slot: dict[str, dict[str, Any]] = {}
    for slot, column in SLOT_COLUMNS.items():
        fpl_code = getattr(plan, column)
        if not fpl_code or fpl_code.upper() == "ZZZZ":
            continue
        aerodrome = await AerodromeRepository.get_by_location_code(db, code=fpl_code)
        if aerodrome is None:
            continue
        aerodromes_by_slot[slot] = to_fpl_aerodrome_context(aerodrome, fpl_code=fpl_code)
    return aerodromes_by_slot


async def build_fpl_field18_request(db: AsyncSession, plan: FlightPlan) -> dict[str, Any]:
    aerodromes_by_slot = await build_aerodromes_by_slot(db, plan)
    aircraft_type_is_valid = await resolve_aircraft_type_is_valid(db, plan)
    return {
        "fpl_field18": {
            "fpl_fields": build_fpl_fields(plan, aircraft_type_is_valid=aircraft_type_is_valid),
            "aerodromes": aerodromes_by_slot,
            "current_field18": plan.other_information or "",
        }
    }
