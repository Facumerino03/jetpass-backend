from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import CurrentActiveUserDep
from app.schemas.aircraft import (
    AircraftCreate,
    AircraftDeleteResponse,
    AircraftImagePresignRequest,
    AircraftImagePresignResponse,
    AircraftPublic,
    AircraftUpdate,
)
from app.services.aircraft_service import AircraftService

router = APIRouter(prefix="/pilot/aircraft", tags=["pilot-aircraft"])


def get_aircraft_service() -> AircraftService:
    return AircraftService()


AircraftServiceDep = Annotated[AircraftService, Depends(get_aircraft_service)]


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_aircraft(
    payload: AircraftCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: CurrentActiveUserDep,
    aircraft_service: AircraftServiceDep,
) -> AircraftPublic:
    aircraft = await aircraft_service.create_for_pilot(db, current_user, payload)
    return aircraft_service.to_public(aircraft)


@router.get("")
async def list_aircraft(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: CurrentActiveUserDep,
    aircraft_service: AircraftServiceDep,
) -> list[AircraftPublic]:
    aircraft = await aircraft_service.list_for_pilot(db, current_user)
    return [aircraft_service.to_public(item) for item in aircraft]


@router.post("/image/presign")
async def presign_aircraft_image_for_create(
    payload: AircraftImagePresignRequest,
    current_user: CurrentActiveUserDep,
    aircraft_service: AircraftServiceDep,
) -> AircraftImagePresignResponse:
    result = await aircraft_service.presign_image_for_create(
        current_user=current_user,
        content_type=payload.content_type,
    )
    return AircraftImagePresignResponse.model_validate(result)


@router.get("/{aircraft_id}")
async def get_aircraft(
    aircraft_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: CurrentActiveUserDep,
    aircraft_service: AircraftServiceDep,
) -> AircraftPublic:
    aircraft = await aircraft_service.get_for_pilot(db, current_user, aircraft_id)
    if aircraft is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Aircraft not found")
    return aircraft_service.to_public(aircraft)


@router.post("/{aircraft_id}/image/presign")
async def presign_aircraft_image(
    aircraft_id: UUID,
    payload: AircraftImagePresignRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: CurrentActiveUserDep,
    aircraft_service: AircraftServiceDep,
) -> AircraftImagePresignResponse:
    result = await aircraft_service.presign_image_for_aircraft(
        db,
        current_user=current_user,
        aircraft_id=aircraft_id,
        content_type=payload.content_type,
    )
    return AircraftImagePresignResponse.model_validate(result)


@router.patch("/{aircraft_id}")
async def update_aircraft(
    aircraft_id: UUID,
    payload: AircraftUpdate,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: CurrentActiveUserDep,
    aircraft_service: AircraftServiceDep,
) -> AircraftPublic:
    aircraft = await aircraft_service.update_for_pilot(db, current_user, aircraft_id, payload)
    return aircraft_service.to_public(aircraft)


@router.delete("/{aircraft_id}")
async def delete_aircraft(
    aircraft_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: CurrentActiveUserDep,
    aircraft_service: AircraftServiceDep,
) -> AircraftDeleteResponse:
    deleted = await aircraft_service.delete_for_pilot(db, current_user, aircraft_id)
    return AircraftDeleteResponse(deleted=deleted)
