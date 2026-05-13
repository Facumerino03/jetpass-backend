from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.aircraft import Aircraft
from app.models.user import Role, User
from app.repositories.aircraft_repository import AircraftRepository
from app.schemas.aircraft import AircraftCreate, AircraftUpdate


class AircraftService:
    @staticmethod
    def _ensure_pilot(current_user: User) -> None:
        if current_user.role != Role.PILOT:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only pilots can manage aircraft",
            )

    @staticmethod
    async def create_for_pilot(
        db: AsyncSession,
        current_user: User,
        payload: AircraftCreate,
    ) -> Aircraft:
        AircraftService._ensure_pilot(current_user)
        aircraft = await AircraftRepository.create(
            db,
            owner_user_id=current_user.id,
            **payload.model_dump(),
        )
        await db.commit()
        await db.refresh(aircraft)
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

    @staticmethod
    async def update_for_pilot(
        db: AsyncSession,
        current_user: User,
        aircraft_id: UUID,
        payload: AircraftUpdate,
    ) -> Aircraft:
        AircraftService._ensure_pilot(current_user)
        aircraft = await AircraftRepository.get_active_by_owner_and_id(
            db,
            owner_user_id=current_user.id,
            aircraft_id=aircraft_id,
        )
        if aircraft is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Aircraft not found")

        await AircraftRepository.update(aircraft, **payload.model_dump(exclude_unset=True))
        await db.commit()
        await db.refresh(aircraft)
        return aircraft

    @staticmethod
    async def delete_for_pilot(
        db: AsyncSession,
        current_user: User,
        aircraft_id: UUID,
    ) -> bool:
        AircraftService._ensure_pilot(current_user)
        aircraft = await AircraftRepository.get_active_by_owner_and_id(
            db,
            owner_user_id=current_user.id,
            aircraft_id=aircraft_id,
        )
        if aircraft is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Aircraft not found")

        await AircraftRepository.soft_delete(aircraft)
        await db.commit()
        return True
