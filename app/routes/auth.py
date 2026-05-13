from typing import Annotated

from fastapi import APIRouter, Depends, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import CurrentActiveUserDep
from app.schemas.auth import (
    AuthTokenResponse,
    LoginRequest,
    LogoutRequest,
    LogoutResponse,
    PilotRegisterRequest,
    RefreshRequest,
    UserPublic,
)
from app.services.auth_service import AuthService

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register/pilot", status_code=status.HTTP_201_CREATED)
async def register_pilot(
    payload: PilotRegisterRequest,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> AuthTokenResponse:
    user, access_token, refresh_token, expires_in = await AuthService.register_pilot(
        db,
        email=str(payload.email),
        password=payload.password,
        first_name=payload.first_name,
        last_name=payload.last_name,
        phone=payload.phone,
        user_agent=request.headers.get("user-agent"),
        ip_address=request.client.host if request.client else None,
        device_name=payload.device_name,
    )
    return AuthTokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=expires_in,
        user=user,
    )


@router.post("/login")
async def login(
    payload: LoginRequest,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> AuthTokenResponse:
    user, access_token, refresh_token, expires_in = await AuthService.login(
        db,
        email=str(payload.email),
        password=payload.password,
        user_agent=request.headers.get("user-agent"),
        ip_address=request.client.host if request.client else None,
        device_name=payload.device_name,
    )
    return AuthTokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=expires_in,
        user=user,
    )


@router.post("/refresh")
async def refresh(
    payload: RefreshRequest,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> AuthTokenResponse:
    user, access_token, refresh_token, expires_in = await AuthService.refresh(
        db,
        refresh_token=payload.refresh_token,
        user_agent=request.headers.get("user-agent"),
        ip_address=request.client.host if request.client else None,
        device_name=None,
    )
    return AuthTokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=expires_in,
        user=user,
    )


@router.post("/logout")
async def logout(
    payload: LogoutRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> LogoutResponse:
    revoked = await AuthService.logout(db, refresh_token=payload.refresh_token)
    return LogoutResponse(revoked=revoked)


@router.get("/me")
async def me(current_user: CurrentActiveUserDep) -> UserPublic:
    return UserPublic.model_validate(current_user)
