import asyncio
from datetime import datetime, timezone
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.aircraft import Aircraft
from app.models.user import Role, User
from app.repositories.aircraft_repository import AircraftRepository
from app.schemas.aircraft import AircraftCreate, AircraftPublic, AircraftUpdate
from app.services.aircraft_image_service import AircraftImageService
from app.services.intelligence_client import IntelligenceClient


class AircraftService:
    def __init__(
        self,
        *,
        image_service: AircraftImageService | None = None,
        intelligence_client: IntelligenceClient | None = None,
    ) -> None:
        self._image_service = image_service or AircraftImageService()
        self._intelligence_client = intelligence_client

    def _get_intelligence_client(self) -> IntelligenceClient:
        if self._intelligence_client is None:
            from app.core.config import settings

            return IntelligenceClient(
                base_url=settings.INTELLIGENCE_BASE_URL,
                timeout_seconds=settings.INTELLIGENCE_TIMEOUT_SECONDS,
            )
        return self._intelligence_client

    @staticmethod
    def _ensure_pilot(current_user: User) -> None:
        if current_user.role != Role.PILOT:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only pilots can manage aircraft",
            )

    def to_public(self, aircraft: Aircraft) -> AircraftPublic:
        return AircraftPublic.from_model(aircraft, image_service=self._image_service)

    def _schedule_type_verification(self, *, aircraft_id: UUID, designator: str) -> None:
        asyncio.create_task(
            self._verify_and_persist(aircraft_id=aircraft_id, designator=designator),
        )

    async def _persist_verification(
        self,
        db: AsyncSession,
        *,
        aircraft_id: UUID,
        is_valid: bool | None,
        verified_at: datetime | None,
    ) -> Aircraft | None:
        aircraft = await AircraftRepository.get_by_id(db, aircraft_id=aircraft_id)
        if aircraft is None or not aircraft.is_active:
            return None
        if is_valid is None:
            return aircraft
        await AircraftRepository.update(
            aircraft,
            is_valid=is_valid,
            verified_at=verified_at,
        )
        await db.commit()
        await db.refresh(aircraft)
        return aircraft

    async def _verify_and_persist(
        self,
        *,
        aircraft_id: UUID,
        designator: str,
        db: AsyncSession | None = None,
    ) -> Aircraft | None:
        result = await self._get_intelligence_client().verify_aircraft_type(designator)
        is_valid = result.get("is_valid")
        verified_at = datetime.now(timezone.utc) if is_valid is not None else None

        if db is not None:
            return await self._persist_verification(
                db,
                aircraft_id=aircraft_id,
                is_valid=is_valid,
                verified_at=verified_at,
            )

        from app.core.database import AsyncSessionLocal

        if AsyncSessionLocal is None:
            return None

        async with AsyncSessionLocal() as session:
            return await self._persist_verification(
                session,
                aircraft_id=aircraft_id,
                is_valid=is_valid,
                verified_at=verified_at,
            )

    async def create_for_pilot(
        self,
        db: AsyncSession,
        current_user: User,
        payload: AircraftCreate,
    ) -> Aircraft:
        self._ensure_pilot(current_user)
        create_data = payload.model_dump(exclude={"image_key"})
        pending_image_key: str | None = None
        if payload.image_key is not None:
            pending_image_key = self._image_service.validate_image_key_for_create(
                current_user=current_user,
                image_key=payload.image_key,
            )

        aircraft = await AircraftRepository.create(
            db,
            owner_user_id=current_user.id,
            **create_data,
        )
        if pending_image_key is not None:
            final_image_key = self._image_service.finalize_pending_image(
                pending_key=pending_image_key,
                aircraft_id=aircraft.id,
            )
            await AircraftRepository.update(aircraft, image_url=final_image_key)

        await db.commit()
        await db.refresh(aircraft)
        self._schedule_type_verification(
            aircraft_id=aircraft.id,
            designator=aircraft.icao_type_designator,
        )
        return aircraft

    @staticmethod
    async def list_for_pilot(db: AsyncSession, current_user: User) -> list[Aircraft]:
        AircraftService._ensure_pilot(current_user)
        return await AircraftRepository.list_active_by_owner(db, owner_user_id=current_user.id)

    @staticmethod
    async def get_for_pilot(
        db: AsyncSession,
        current_user: User,
        aircraft_id: UUID,
    ) -> Aircraft | None:
        AircraftService._ensure_pilot(current_user)
        return await AircraftRepository.get_active_by_owner_and_id(
            db,
            owner_user_id=current_user.id,
            aircraft_id=aircraft_id,
        )

    async def update_for_pilot(
        self,
        db: AsyncSession,
        current_user: User,
        aircraft_id: UUID,
        payload: AircraftUpdate,
    ) -> Aircraft:
        self._ensure_pilot(current_user)
        aircraft = await AircraftRepository.get_active_by_owner_and_id(
            db,
            owner_user_id=current_user.id,
            aircraft_id=aircraft_id,
        )
        if aircraft is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Aircraft not found")

        previous_designator = aircraft.icao_type_designator
        update_data = payload.model_dump(exclude_unset=True, exclude={"image_key"})
        if payload.image_key is not None:
            validated_key = self._image_service.validate_image_key_for_update(
                aircraft=aircraft,
                image_key=payload.image_key,
            )
            self._image_service.delete_managed_image_if_present(stored_value=aircraft.image_url)
            update_data["image_url"] = validated_key

        new_designator = update_data.get("icao_type_designator")
        if new_designator is not None and new_designator.upper() != previous_designator:
            update_data["is_valid"] = None
            update_data["verified_at"] = None

        await AircraftRepository.update(aircraft, **update_data)
        await db.commit()
        await db.refresh(aircraft)

        if new_designator is not None and aircraft.icao_type_designator != previous_designator:
            self._schedule_type_verification(
                aircraft_id=aircraft.id,
                designator=aircraft.icao_type_designator,
            )
        return aircraft

    async def verify_type_for_pilot(
        self,
        db: AsyncSession,
        current_user: User,
        aircraft_id: UUID,
    ) -> Aircraft:
        self._ensure_pilot(current_user)
        aircraft = await AircraftRepository.get_active_by_owner_and_id(
            db,
            owner_user_id=current_user.id,
            aircraft_id=aircraft_id,
        )
        if aircraft is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Aircraft not found")

        updated = await self._verify_and_persist(
            db=db,
            aircraft_id=aircraft.id,
            designator=aircraft.icao_type_designator,
        )
        if updated is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Aircraft not found")
        return updated

    async def delete_for_pilot(
        self,
        db: AsyncSession,
        current_user: User,
        aircraft_id: UUID,
    ) -> bool:
        self._ensure_pilot(current_user)
        aircraft = await AircraftRepository.get_active_by_owner_and_id(
            db,
            owner_user_id=current_user.id,
            aircraft_id=aircraft_id,
        )
        if aircraft is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Aircraft not found")

        self._image_service.delete_managed_image_if_present(stored_value=aircraft.image_url)
        await AircraftRepository.soft_delete(aircraft)
        await db.commit()
        return True

    async def presign_image_for_create(self, *, current_user: User, content_type: str) -> dict[str, str | int]:
        self._ensure_pilot(current_user)
        return self._image_service.presign_for_create(current_user=current_user, content_type=content_type)

    async def presign_image_for_aircraft(
        self,
        db: AsyncSession,
        *,
        current_user: User,
        aircraft_id: UUID,
        content_type: str,
    ) -> dict[str, str | int]:
        self._ensure_pilot(current_user)
        aircraft = await AircraftRepository.get_active_by_owner_and_id(
            db,
            owner_user_id=current_user.id,
            aircraft_id=aircraft_id,
        )
        if aircraft is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Aircraft not found")
        return self._image_service.presign_for_aircraft(aircraft=aircraft, content_type=content_type)
