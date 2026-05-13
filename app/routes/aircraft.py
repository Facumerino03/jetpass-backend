from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import CurrentActiveUserDep
from app.schemas.aircraft import AircraftCreate, AircraftDeleteResponse, AircraftPublic, AircraftUpdate
from app.services.aircraft_service import AircraftService

router = APIRouter(prefix="/pilot/aircraft", tags=["pilot-aircraft"])


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_aircraft(
    payload: AircraftCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: CurrentActiveUserDep,
) -> AircraftPublic:
    aircraft = await AircraftService.create_for_pilot(db, current_user, payload)
    return AircraftPublic.model_validate(aircraft)


@router.get("")
async def list_aircraft(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: CurrentActiveUserDep,
) -> list[AircraftPublic]:
    aircraft = await AircraftService.list_for_pilot(db, current_user)
    return [AircraftPublic.model_validate(item) for item in aircraft]


@router.get("/{aircraft_id}")
async def get_aircraft(
    aircraft_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: CurrentActiveUserDep,
) -> AircraftPublic:
    aircraft = await AircraftService.get_for_pilot(db, current_user, aircraft_id)
    if aircraft is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Aircraft not found")
    return AircraftPublic.model_validate(aircraft)


@router.patch("/{aircraft_id}")
async def update_aircraft(
    aircraft_id: UUID,
    payload: AircraftUpdate,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: CurrentActiveUserDep,
) -> AircraftPublic:
    aircraft = await AircraftService.update_for_pilot(db, current_user, aircraft_id, payload)
    return AircraftPublic.model_validate(aircraft)


@router.delete("/{aircraft_id}")
async def delete_aircraft(
    aircraft_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: CurrentActiveUserDep,
) -> AircraftDeleteResponse:
    deleted = await AircraftService.delete_for_pilot(db, current_user, aircraft_id)
    return AircraftDeleteResponse(deleted=deleted)
