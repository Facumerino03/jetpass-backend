from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.flight_plan import FlightPlanStatus
from app.models.flight_plan_status_history import FlightPlanStatusHistory


class FlightPlanStatusHistoryRepository:
    @staticmethod
    async def create(
        db: AsyncSession,
        *,
        flight_plan_id: UUID,
        from_status: FlightPlanStatus | None,
        to_status: FlightPlanStatus,
        updated_by_user_id: UUID | None,
        reason: str | None,
    ) -> FlightPlanStatusHistory:
        history = FlightPlanStatusHistory(
            flight_plan_id=flight_plan_id,
            from_status=from_status,
            to_status=to_status,
            updated_by_user_id=updated_by_user_id,
            reason=reason,
        )
        db.add(history)
        await db.flush()
        return history

    @staticmethod
    async def list_by_plan(db: AsyncSession, *, flight_plan_id: UUID) -> list[FlightPlanStatusHistory]:
        result = await db.execute(
            select(FlightPlanStatusHistory)
            .where(FlightPlanStatusHistory.flight_plan_id == flight_plan_id)
            .order_by(FlightPlanStatusHistory.created_at.asc())
        )
        return list(result.scalars().all())
