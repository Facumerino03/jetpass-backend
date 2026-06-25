from __future__ import annotations

from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.flight_plan import FlightPlan
from app.models.user import User
from app.repositories.flight_plan_repository import FlightPlanRepository
from app.schemas.fpl_field18 import FplField18Result, FplField18Update
from app.services.flight_plan_service import FlightPlanService
from app.services.fpl_field18_mapper import FPL_FIELD_TO_COLUMN, build_fpl_field18_request
from app.services.intelligence_client import IntelligenceClient


class FlightPlanField18Service:
    def __init__(self, *, intelligence_client: IntelligenceClient | None = None) -> None:
        self._intelligence_client = intelligence_client

    def _client(self) -> IntelligenceClient:
        if self._intelligence_client is None:
            from app.core.config import settings

            return IntelligenceClient(
                base_url=settings.INTELLIGENCE_BASE_URL,
                timeout_seconds=settings.INTELLIGENCE_TIMEOUT_SECONDS,
            )
        return self._intelligence_client

    @staticmethod
    async def _get_editable_plan(
        db: AsyncSession,
        current_user: User,
        flight_plan_id: UUID,
    ) -> FlightPlan:
        FlightPlanService._ensure_pilot(current_user)
        plan = await FlightPlanRepository.get_by_owner_and_id(
            db,
            pilot_user_id=current_user.id,
            flight_plan_id=flight_plan_id,
        )
        if plan is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Flight plan not found")
        FlightPlanService._ensure_draft(plan)
        return plan

    @staticmethod
    def _parse_field18_result(response: dict) -> tuple[str, FplField18Result]:
        if response.get("intent") == "unavailable":
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Field 18 intelligence is unavailable",
            )

        payload = response.get("fpl_field18")
        if not isinstance(payload, dict):
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Invalid field 18 response from intelligence",
            )

        raw_updates = payload.get("fpl_updates") or []
        fpl_updates = [FplField18Update.model_validate(item) for item in raw_updates]
        result = FplField18Result(
            computed_field18=payload.get("computed_field18") or "",
            suggestions=payload.get("suggestions") or [],
            fpl_updates=fpl_updates,
            alerts=payload.get("alerts") or [],
            messages=payload.get("messages") or [],
        )
        return response.get("intent") or "fpl_field18", result

    @staticmethod
    def _has_error_alerts(alerts: list[dict]) -> bool:
        return any(alert.get("level") == "error" for alert in alerts)

    @staticmethod
    def _apply_fpl_updates(plan: FlightPlan, fpl_updates: list[FplField18Update]) -> None:
        for update in fpl_updates:
            column = FPL_FIELD_TO_COLUMN.get(update.field)
            if column is None:
                continue
            current = getattr(plan, column)
            if update.from_value and current.upper() != update.from_value.upper():
                continue
            setattr(plan, column, update.to_value.upper())

    async def _run_intelligence(self, db: AsyncSession, plan: FlightPlan) -> tuple[str, FplField18Result]:
        request_payload = await build_fpl_field18_request(db, plan)
        response = await self._client().run(request_payload)
        return self._parse_field18_result(response)

    async def preview(
        self,
        db: AsyncSession,
        current_user: User,
        flight_plan_id: UUID,
    ) -> tuple[str, FplField18Result]:
        plan = await self._get_editable_plan(db, current_user, flight_plan_id)
        return await self._run_intelligence(db, plan)

    async def apply(
        self,
        db: AsyncSession,
        current_user: User,
        flight_plan_id: UUID,
    ) -> tuple[FlightPlan, FplField18Result]:
        plan = await self._get_editable_plan(db, current_user, flight_plan_id)
        _, result = await self._run_intelligence(db, plan)

        if self._has_error_alerts(result.alerts):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={"message": "Field 18 cannot be applied", "alerts": result.alerts},
            )

        self._apply_fpl_updates(plan, result.fpl_updates)
        plan.other_information = result.computed_field18
        await db.commit()
        await db.refresh(plan)
        return plan, result
