from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import CurrentActiveUserDep
from app.models.profiles import AuthorityType
from app.models.user import Role
from app.repositories.profile_repository import ProfileRepository
from pydantic import BaseModel, Field


class AuthorityProfileCreate(BaseModel):
    user_id: str = Field(min_length=1)
    organization_name: str = Field(min_length=1, max_length=160)
    authority_type: AuthorityType
    aerodrome_icao_code: str | None = Field(default=None, min_length=4, max_length=4)


class AuthorityProfilePublic(BaseModel):
    id: str
    user_id: str
    organization_name: str
    authority_type: AuthorityType
    aerodrome_icao_code: str | None


router = APIRouter(prefix="/admin/profiles", tags=["admin-profiles"])


@router.post("/authority", status_code=status.HTTP_201_CREATED)
async def create_authority_profile(
    payload: AuthorityProfileCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: CurrentActiveUserDep,
):
    if current_user.role != Role.ADMIN:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only admins can create profiles")

    from uuid import UUID

    profile = await ProfileRepository.create_authority_profile(
        db,
        user_id=UUID(payload.user_id),
        organization_name=payload.organization_name,
        authority_type=payload.authority_type,
        aerodrome_icao_code=payload.aerodrome_icao_code,
    )
    await db.commit()
    await db.refresh(profile)

    return {
        "id": str(profile.id),
        "user_id": str(profile.user_id),
        "organization_name": profile.organization_name,
        "authority_type": profile.authority_type.value,
        "aerodrome_icao_code": profile.aerodrome_icao_code,
    }
