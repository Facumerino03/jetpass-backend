from datetime import datetime, timezone
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.aircraft import Aircraft
from app.models.flight_plan import FlightPlan, FlightPlanStatus, FlightRules
from app.models.flight_plan_approval import FlightPlanApprovalActor, FlightPlanApprovalStatus
from app.models.profiles import AuthorityType
from app.models.user import Role, User
from app.repositories.aircraft_repository import AircraftRepository
from app.repositories.aerodrome_repository import AerodromeRepository
from app.repositories.flight_plan_approval_repository import FlightPlanApprovalRepository
from app.repositories.flight_plan_repository import FlightPlanRepository
from app.repositories.flight_plan_status_history_repository import FlightPlanStatusHistoryRepository
from app.repositories.profile_repository import ProfileRepository
from app.schemas.flight_plan import FlightPlanCreate, FlightPlanUpdate
from app.services.flight_plan_official_pdf_service import FlightPlanOfficialPdfService
from app.services.flight_plan_signature_service import FlightPlanSignatureService
from app.services.flight_plan_validations import ensure_rule_change_point_valid, hhmm_to_minutes


class FlightPlanService:
    _signature_service: FlightPlanSignatureService | None = None
    _official_pdf_service: FlightPlanOfficialPdfService | None = None

    @classmethod
    def _get_signature_service(cls) -> FlightPlanSignatureService:
        if cls._signature_service is None:
            cls._signature_service = FlightPlanSignatureService()
        return cls._signature_service

    @classmethod
    def _get_official_pdf_service(cls) -> FlightPlanOfficialPdfService:
        if cls._official_pdf_service is None:
            cls._official_pdf_service = FlightPlanOfficialPdfService()
        return cls._official_pdf_service

    @staticmethod
    def _ensure_pilot(current_user: User) -> None:
        if current_user.role != Role.PILOT:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only pilots can manage flight plans")

    @staticmethod
    def _ensure_draft(plan: FlightPlan) -> None:
        if plan.status != FlightPlanStatus.DRAFT:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Flight plan can only be edited in draft status")

    @staticmethod
    def _pilot_in_command_name(user: User) -> str:
        return f"{user.first_name} {user.last_name}"

    @staticmethod
    async def create_draft(db: AsyncSession, current_user: User, payload: FlightPlanCreate) -> FlightPlan:
        FlightPlanService._ensure_pilot(current_user)

        (
            departure_aerodrome_icao,
            destination_aerodrome_icao,
            alternate1_aerodrome_icao,
            alternate2_aerodrome_icao,
        ) = await FlightPlanService._resolve_aerodrome_location_codes(
            db,
            payload.departure_aerodrome_icao,
            payload.destination_aerodrome_icao,
            payload.alternate1_aerodrome_icao,
            payload.alternate2_aerodrome_icao,
        )

        plan = await FlightPlanRepository.create_draft(
            db,
            pilot_user_id=current_user.id,
            pilot_in_command=FlightPlanService._pilot_in_command_name(current_user),
            departure_aerodrome_icao=departure_aerodrome_icao,
            departure_time_utc=payload.departure_time_utc,
            flight_date=payload.flight_date,
            destination_aerodrome_icao=destination_aerodrome_icao,
            alternate1_aerodrome_icao=alternate1_aerodrome_icao,
            alternate2_aerodrome_icao=alternate2_aerodrome_icao,
        )
        await db.commit()
        await db.refresh(plan)
        return plan

    @staticmethod
    def _snapshot_from_aircraft(aircraft: Aircraft) -> dict:
        return {
            "aircraft_identification_snapshot": aircraft.identification,
            "aircraft_type_designator_snapshot": aircraft.icao_type_designator,
            "wake_turbulence_category_snapshot": aircraft.wake_turbulence_category,
            "equipment_com_nav_snapshot": aircraft.equipment_com_nav,
            "equipment_surveillance_snapshot": aircraft.equipment_surveillance,
            "emergency_radio_uhf_snapshot": aircraft.emergency_radio_uhf,
            "emergency_radio_vhf_snapshot": aircraft.emergency_radio_vhf,
            "emergency_radio_elt_snapshot": aircraft.emergency_radio_elt,
            "survival_equipment_present_snapshot": aircraft.survival_equipment_present,
            "survival_polar_snapshot": aircraft.survival_polar,
            "survival_desert_snapshot": aircraft.survival_desert,
            "survival_maritime_snapshot": aircraft.survival_maritime,
            "survival_jungle_snapshot": aircraft.survival_jungle,
            "life_jackets_present_snapshot": aircraft.life_jackets_present,
            "life_jackets_lights_snapshot": aircraft.life_jackets_lights,
            "life_jackets_fluorescein_snapshot": aircraft.life_jackets_fluorescein,
            "life_jackets_uhf_snapshot": aircraft.life_jackets_uhf,
            "life_jackets_vhf_snapshot": aircraft.life_jackets_vhf,
            "dinghies_present_snapshot": aircraft.dinghies_present,
            "dinghies_number_snapshot": aircraft.dinghies_number,
            "dinghies_capacity_snapshot": aircraft.dinghies_capacity,
            "dinghies_cover_present_snapshot": aircraft.dinghies_cover_present,
            "dinghies_color_snapshot": aircraft.dinghies_color,
            "color_and_markings_snapshot": aircraft.color_and_markings,
            "aircraft_snapshot_confirmed_at": datetime.now(timezone.utc),
        }

    @staticmethod
    async def update_draft(
        db: AsyncSession,
        current_user: User,
        flight_plan_id: UUID,
        payload: FlightPlanUpdate,
    ) -> FlightPlan:
        FlightPlanService._ensure_pilot(current_user)
        plan = await FlightPlanRepository.get_by_owner_and_id(db, pilot_user_id=current_user.id, flight_plan_id=flight_plan_id)
        if plan is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Flight plan not found")
        FlightPlanService._ensure_draft(plan)

        fields = payload.model_dump(exclude_unset=True, exclude={"signature_key"})
        if "signature_key" in payload.model_fields_set and payload.signature_key is not None:
            signature_service = FlightPlanService._get_signature_service()
            validated_key = signature_service.validate_signature_key_for_plan(
                plan=plan,
                signature_key=payload.signature_key,
            )
            signature_service.delete_managed_signature_if_present(stored_value=plan.signature_url)
            fields["signature_url"] = validated_key

        aircraft_id = fields.pop("aircraft_id", None)
        if aircraft_id is not None:
            aircraft = await AircraftRepository.get_active_by_owner_and_id(db, owner_user_id=current_user.id, aircraft_id=aircraft_id)
            if aircraft is None:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Aircraft not found")
            fields["aircraft_id"] = aircraft.id
            fields.update(FlightPlanService._snapshot_from_aircraft(aircraft))

        await FlightPlanRepository.update(plan, **fields)
        await db.commit()
        await db.refresh(plan)
        return plan

    @staticmethod
    def _validate_complete_for_submit(plan: FlightPlan) -> None:
        missing = []
        required_fields = [
            "flight_rules",
            "flight_type",
            "aircraft_id",
            "aircraft_identification_snapshot",
            "aircraft_type_designator_snapshot",
            "wake_turbulence_category_snapshot",
            "equipment_com_nav_snapshot",
            "equipment_surveillance_snapshot",
            "color_and_markings_snapshot",
            "aircraft_snapshot_confirmed_at",
            "cruising_speed",
            "cruising_level",
            "route",
            "total_eet",
            "endurance",
            "persons_on_board",
            "signature_url",
        ]
        for field in required_fields:
            if getattr(plan, field) in {None, ""}:
                missing.append(field)
        if missing:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=f"Missing required fields: {', '.join(missing)}")

        if plan.persons_on_board is None or plan.persons_on_board < 1:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="persons_on_board must be at least 1")

        try:
            if hhmm_to_minutes(plan.endurance) <= hhmm_to_minutes(plan.total_eet):
                raise ValueError("endurance must be greater than total_eet")
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc

        if plan.flight_rules in {FlightRules.Y, FlightRules.Z} and not plan.route:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="route is required for Y/Z flight rules")

    @staticmethod
    async def _transition(
        db: AsyncSession,
        plan: FlightPlan,
        *,
        to_status: FlightPlanStatus,
        updated_by_user_id: UUID,
        reason: str,
    ) -> None:
        from_status = plan.status
        plan.status = to_status
        await FlightPlanStatusHistoryRepository.create(
            db,
            flight_plan_id=plan.id,
            from_status=from_status,
            to_status=to_status,
            updated_by_user_id=updated_by_user_id,
            reason=reason,
        )

    @staticmethod
    async def presign_signature(
        db: AsyncSession,
        current_user: User,
        flight_plan_id: UUID,
        content_type: str,
    ) -> dict[str, str | int]:
        FlightPlanService._ensure_pilot(current_user)
        plan = await FlightPlanRepository.get_by_owner_and_id(
            db,
            pilot_user_id=current_user.id,
            flight_plan_id=flight_plan_id,
        )
        if plan is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Flight plan not found")
        FlightPlanService._ensure_draft(plan)
        return FlightPlanService._get_signature_service().presign_for_plan(plan=plan, content_type=content_type)

    @staticmethod
    async def submit(db: AsyncSession, current_user: User, flight_plan_id: UUID) -> FlightPlan:
        FlightPlanService._ensure_pilot(current_user)
        plan = await FlightPlanRepository.get_by_owner_and_id(db, pilot_user_id=current_user.id, flight_plan_id=flight_plan_id)
        if plan is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Flight plan not found")
        FlightPlanService._ensure_draft(plan)
        FlightPlanService._validate_complete_for_submit(plan)

        official_pdf_key = FlightPlanService._get_official_pdf_service().generate_and_store(plan)
        await FlightPlanRepository.update(plan, official_pdf_key=official_pdf_key)

        await FlightPlanService._transition(db, plan, to_status=FlightPlanStatus.FILED, updated_by_user_id=current_user.id, reason="submitted")
        await FlightPlanApprovalRepository.create(
            db,
            flight_plan_id=plan.id,
            actor=FlightPlanApprovalActor.PILOT,
            criterion="pilot_submission",
            status=FlightPlanApprovalStatus.APPROVED,
            approved_by_user_id=current_user.id,
        )
        await FlightPlanApprovalRepository.create(
            db,
            flight_plan_id=plan.id,
            actor=FlightPlanApprovalActor.AUTHORITY,
            criterion="authority_acceptance",
        )
        await FlightPlanApprovalRepository.create(
            db,
            flight_plan_id=plan.id,
            actor=FlightPlanApprovalActor.DESTINATION_AERODROME_OPERATOR,
            criterion="destination_aerodrome_acceptance",
        )
        await FlightPlanService._transition(db, plan, to_status=FlightPlanStatus.PENDING_APPROVAL, updated_by_user_id=current_user.id, reason="awaiting manual approvals")
        await db.commit()
        await db.refresh(plan)
        return plan

    @staticmethod
    async def list_visible(db: AsyncSession, current_user: User) -> list[FlightPlan]:
        if current_user.role == Role.ADMIN:
            return await FlightPlanRepository.list_all(db)
        if current_user.role == Role.PILOT:
            return await FlightPlanRepository.list_by_pilot(db, pilot_user_id=current_user.id)
        if current_user.role == Role.AIRPORT_OPERATOR:
            profile = await ProfileRepository.get_airport_operator_profile_by_user_id(db, user_id=current_user.id)
            if profile is None:
                return []
            return await FlightPlanRepository.list_pending_for_destination(
                db,
                destination_aerodrome_icao=profile.aerodrome_icao_code,
            )
        if current_user.role == Role.ATC_AUTHORITY:
            profile = await ProfileRepository.get_authority_profile_by_user_id(db, user_id=current_user.id)
            if profile is None:
                return []
            if profile.authority_type in {AuthorityType.ANAC, AuthorityType.EANA}:
                return [plan for plan in await FlightPlanRepository.list_all(db) if plan.status == FlightPlanStatus.PENDING_APPROVAL]
            if profile.aerodrome_icao_code is None:
                return []
            return await FlightPlanRepository.list_pending_for_relevant_aerodrome(
                db,
                aerodrome_icao=profile.aerodrome_icao_code,
            )
        return []

    @staticmethod
    async def get_visible(db: AsyncSession, current_user: User, flight_plan_id: UUID) -> FlightPlan:
        if current_user.role == Role.ADMIN:
            plan = await FlightPlanRepository.get_by_id(db, flight_plan_id=flight_plan_id)
        elif current_user.role == Role.PILOT:
            plan = await FlightPlanRepository.get_by_owner_and_id(db, pilot_user_id=current_user.id, flight_plan_id=flight_plan_id)
        else:
            plan = await FlightPlanRepository.get_by_id(db, flight_plan_id=flight_plan_id)
        if plan is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Flight plan not found")
        return plan

    @staticmethod
    async def _approval_actor_for_user(db: AsyncSession, current_user: User, plan: FlightPlan) -> FlightPlanApprovalActor:
        if current_user.role == Role.ADMIN:
            authority = await FlightPlanApprovalRepository.get_pending_by_actor(db, flight_plan_id=plan.id, actor=FlightPlanApprovalActor.AUTHORITY)
            if authority is not None:
                return FlightPlanApprovalActor.AUTHORITY
            return FlightPlanApprovalActor.DESTINATION_AERODROME_OPERATOR

        if current_user.role == Role.ATC_AUTHORITY:
            profile = await ProfileRepository.get_authority_profile_by_user_id(db, user_id=current_user.id)
            if profile is None:
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Authority profile is required")
            if profile.authority_type in {AuthorityType.ANAC, AuthorityType.EANA}:
                return FlightPlanApprovalActor.AUTHORITY
            relevant = {
                plan.departure_aerodrome_icao,
                plan.destination_aerodrome_icao,
                plan.alternate1_aerodrome_icao,
                plan.alternate2_aerodrome_icao,
            }
            if profile.aerodrome_icao_code in relevant:
                return FlightPlanApprovalActor.AUTHORITY
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Authority profile does not apply to this flight plan")

        if current_user.role == Role.AIRPORT_OPERATOR:
            profile = await ProfileRepository.get_airport_operator_profile_by_user_id(db, user_id=current_user.id)
            if profile is None:
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Airport operator profile is required")
            if profile.aerodrome_icao_code != plan.destination_aerodrome_icao:
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Airport operator profile does not match destination aerodrome")
            return FlightPlanApprovalActor.DESTINATION_AERODROME_OPERATOR

        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User cannot approve flight plans")

    @staticmethod
    async def _get_pending_decision(db: AsyncSession, current_user: User, plan: FlightPlan):
        if plan.status != FlightPlanStatus.PENDING_APPROVAL:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Flight plan is not pending approval")
        actor = await FlightPlanService._approval_actor_for_user(db, current_user, plan)
        approval = await FlightPlanApprovalRepository.get_pending_by_actor(db, flight_plan_id=plan.id, actor=actor)
        if approval is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Pending approval not found")
        return approval

    @staticmethod
    async def approve(db: AsyncSession, current_user: User, flight_plan_id: UUID) -> FlightPlan:
        plan = await FlightPlanRepository.get_by_id(db, flight_plan_id=flight_plan_id)
        if plan is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Flight plan not found")
        approval = await FlightPlanService._get_pending_decision(db, current_user, plan)
        await FlightPlanApprovalRepository.mark_approved(approval, approved_by_user_id=current_user.id)
        approvals = await FlightPlanApprovalRepository.list_by_plan(db, flight_plan_id=plan.id)
        if all(item.status == FlightPlanApprovalStatus.APPROVED for item in approvals):
            await FlightPlanService._transition(db, plan, to_status=FlightPlanStatus.ACCEPTED, updated_by_user_id=current_user.id, reason="all approvals completed")
        await db.commit()
        await db.refresh(plan)
        return plan

    @staticmethod
    async def reject(db: AsyncSession, current_user: User, flight_plan_id: UUID, *, reason: str) -> FlightPlan:
        if not reason.strip():
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Rejection reason is required")
        plan = await FlightPlanRepository.get_by_id(db, flight_plan_id=flight_plan_id)
        if plan is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Flight plan not found")
        approval = await FlightPlanService._get_pending_decision(db, current_user, plan)
        await FlightPlanApprovalRepository.mark_rejected(approval, rejected_by_user_id=current_user.id, reason=reason.strip())
        await FlightPlanService._transition(db, plan, to_status=FlightPlanStatus.REJECTED, updated_by_user_id=current_user.id, reason=reason.strip())
        await db.commit()
        await db.refresh(plan)
        return plan

    @staticmethod
    async def _resolve_aerodrome_location_codes(db: AsyncSession, *references: str) -> tuple[str, ...]:
        resolved: list[str] = []
        for reference in references:
            aerodrome = await AerodromeRepository.get_by_location_code(db, code=reference)
            if aerodrome is None or not aerodrome.is_active:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail=f"Aerodrome {reference.upper()} is not in the active catalog",
                )
            resolved.append(AerodromeRepository.fpl_location_code(aerodrome))
        return tuple(resolved)

    @staticmethod
    async def _ensure_aerodromes_active(db: AsyncSession, *references: str) -> None:
        await FlightPlanService._resolve_aerodrome_location_codes(db, *references)
