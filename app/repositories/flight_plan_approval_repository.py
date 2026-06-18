from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.flight_plan_approval import FlightPlanApproval, FlightPlanApprovalActor, FlightPlanApprovalStatus


class FlightPlanApprovalRepository:
    @staticmethod
    async def create(
        db: AsyncSession,
        *,
        flight_plan_id: UUID,
        actor: FlightPlanApprovalActor,
        criterion: str,
        status: FlightPlanApprovalStatus = FlightPlanApprovalStatus.PENDING,
        approved_by_user_id: UUID | None = None,
    ) -> FlightPlanApproval:
        approval = FlightPlanApproval(
            flight_plan_id=flight_plan_id,
            actor=actor,
            criterion=criterion,
            status=status,
            approved_by_user_id=approved_by_user_id,
            decided_at=datetime.now(timezone.utc) if status == FlightPlanApprovalStatus.APPROVED else None,
        )
        db.add(approval)
        await db.flush()
        return approval

    @staticmethod
    async def list_by_plan(db: AsyncSession, *, flight_plan_id: UUID) -> list[FlightPlanApproval]:
        result = await db.execute(
            select(FlightPlanApproval)
            .where(FlightPlanApproval.flight_plan_id == flight_plan_id)
            .order_by(FlightPlanApproval.created_at.asc())
        )
        return list(result.scalars().all())

    @staticmethod
    async def get_pending_by_actor(
        db: AsyncSession,
        *,
        flight_plan_id: UUID,
        actor: FlightPlanApprovalActor,
    ) -> FlightPlanApproval | None:
        result = await db.execute(
            select(FlightPlanApproval).where(
                FlightPlanApproval.flight_plan_id == flight_plan_id,
                FlightPlanApproval.actor == actor,
                FlightPlanApproval.status == FlightPlanApprovalStatus.PENDING,
            )
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def mark_approved(approval: FlightPlanApproval, *, approved_by_user_id: UUID) -> FlightPlanApproval:
        approval.status = FlightPlanApprovalStatus.APPROVED
        approval.approved_by_user_id = approved_by_user_id
        approval.rejected_by_user_id = None
        approval.reason = None
        approval.decided_at = datetime.now(timezone.utc)
        return approval

    @staticmethod
    async def mark_rejected(approval: FlightPlanApproval, *, rejected_by_user_id: UUID, reason: str) -> FlightPlanApproval:
        approval.status = FlightPlanApprovalStatus.REJECTED
        approval.rejected_by_user_id = rejected_by_user_id
        approval.approved_by_user_id = None
        approval.reason = reason
        approval.decided_at = datetime.now(timezone.utc)
        return approval
