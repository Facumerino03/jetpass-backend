from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.flight_plan import FlightPlan, FlightPlanStatus

_PLAN_OPTIONS = [selectinload(FlightPlan.approvals), selectinload(FlightPlan.status_history), selectinload(FlightPlan.pilot)]


class FlightPlanRepository:
    @staticmethod
    async def create_draft(
        db: AsyncSession,
        *,
        pilot_user_id: UUID,
        departure_aerodrome_icao: str,
        departure_eobt_utc: datetime,
        destination_aerodrome_icao: str,
        alternate1_aerodrome_icao: str,
        alternate2_aerodrome_icao: str,
    ) -> FlightPlan:
        plan = FlightPlan(
            pilot_user_id=pilot_user_id,
            status=FlightPlanStatus.DRAFT,
            departure_aerodrome_icao=departure_aerodrome_icao.upper(),
            departure_eobt_utc=departure_eobt_utc,
            destination_aerodrome_icao=destination_aerodrome_icao.upper(),
            alternate1_aerodrome_icao=alternate1_aerodrome_icao.upper(),
            alternate2_aerodrome_icao=alternate2_aerodrome_icao.upper(),
        )
        db.add(plan)
        await db.flush()
        return plan

    @staticmethod
    async def get_by_id(db: AsyncSession, *, flight_plan_id: UUID) -> FlightPlan | None:
        result = await db.execute(
            select(FlightPlan)
            .options(*_PLAN_OPTIONS)
            .where(FlightPlan.id == flight_plan_id)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def get_by_owner_and_id(db: AsyncSession, *, pilot_user_id: UUID, flight_plan_id: UUID) -> FlightPlan | None:
        result = await db.execute(
            select(FlightPlan)
            .options(*_PLAN_OPTIONS)
            .where(
                FlightPlan.id == flight_plan_id,
                FlightPlan.pilot_user_id == pilot_user_id,
            )
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def list_by_pilot(db: AsyncSession, *, pilot_user_id: UUID) -> list[FlightPlan]:
        result = await db.execute(
            select(FlightPlan)
            .options(*_PLAN_OPTIONS)
            .where(FlightPlan.pilot_user_id == pilot_user_id)
            .order_by(FlightPlan.created_at.desc())
        )
        return list(result.scalars().all())

    @staticmethod
    async def list_all(db: AsyncSession) -> list[FlightPlan]:
        result = await db.execute(
            select(FlightPlan)
            .options(*_PLAN_OPTIONS)
            .order_by(FlightPlan.created_at.desc())
        )
        return list(result.scalars().all())

    @staticmethod
    async def list_pending_for_destination(db: AsyncSession, *, destination_aerodrome_icao: str) -> list[FlightPlan]:
        result = await db.execute(
            select(FlightPlan)
            .options(*_PLAN_OPTIONS)
            .where(
                FlightPlan.destination_aerodrome_icao == destination_aerodrome_icao.upper(),
                FlightPlan.status == FlightPlanStatus.PENDING_APPROVAL,
            )
            .order_by(FlightPlan.created_at.desc())
        )
        return list(result.scalars().all())

    @staticmethod
    async def list_pending_for_relevant_aerodrome(db: AsyncSession, *, aerodrome_icao: str) -> list[FlightPlan]:
        code = aerodrome_icao.upper()
        result = await db.execute(
            select(FlightPlan)
            .options(*_PLAN_OPTIONS)
            .where(
                FlightPlan.status == FlightPlanStatus.PENDING_APPROVAL,
                (
                    (FlightPlan.departure_aerodrome_icao == code)
                    | (FlightPlan.destination_aerodrome_icao == code)
                    | (FlightPlan.alternate1_aerodrome_icao == code)
                    | (FlightPlan.alternate2_aerodrome_icao == code)
                ),
            )
            .order_by(FlightPlan.created_at.desc())
        )
        return list(result.scalars().all())

    @staticmethod
    async def update(plan: FlightPlan, **fields: Any) -> FlightPlan:
        uppercase_fields = {
            "departure_aerodrome_icao",
            "destination_aerodrome_icao",
            "alternate1_aerodrome_icao",
            "alternate2_aerodrome_icao",
            "cruising_speed",
            "cruising_level",
            "rule_change_point",
            "aircraft_identification_snapshot",
            "aircraft_type_designator_snapshot",
            "equipment_com_nav_snapshot",
            "equipment_surveillance_snapshot",
        }
        for key, value in fields.items():
            if key in uppercase_fields and isinstance(value, str):
                value = value.upper()
            setattr(plan, key, value)
        return plan
