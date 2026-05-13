from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.security import (
    create_access_token,
    generate_refresh_token,
    get_password_hash,
    hash_refresh_token,
    verify_password,
)
from app.models.user import Role, User
from app.repositories.auth_session_repository import AuthSessionRepository
from app.repositories.user_repository import UserRepository


class AuthService:
    @staticmethod
    async def register_pilot(
        db: AsyncSession,
        *,
        email: str,
        password: str,
        first_name: str,
        last_name: str,
        phone: str | None,
        user_agent: str | None,
        ip_address: str | None,
        device_name: str | None,
    ) -> tuple[User, str, str, int]:
        existing_user = await UserRepository.get_by_email(db, email)
        if existing_user is not None:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already registered")

        user = await UserRepository.create(
            db,
            email=email,
            password_hash=get_password_hash(password),
            first_name=first_name,
            last_name=last_name,
            phone=phone,
            role=Role.PILOT,
        )
        access_token, refresh_token, expires_in = await AuthService._create_token_pair(
            db,
            user=user,
            user_agent=user_agent,
            ip_address=ip_address,
            device_name=device_name,
        )
        await db.commit()
        await db.refresh(user)
        return user, access_token, refresh_token, expires_in

    @staticmethod
    async def login(
        db: AsyncSession,
        *,
        email: str,
        password: str,
        user_agent: str | None,
        ip_address: str | None,
        device_name: str | None,
    ) -> tuple[User, str, str, int]:
        user = await UserRepository.get_by_email(db, email)
        if user is None or not verify_password(password, user.password_hash):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password")
        if not user.is_active:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Inactive user")

        access_token, refresh_token, expires_in = await AuthService._create_token_pair(
            db,
            user=user,
            user_agent=user_agent,
            ip_address=ip_address,
            device_name=device_name,
        )
        await db.commit()
        return user, access_token, refresh_token, expires_in

    @staticmethod
    async def _create_token_pair(
        db: AsyncSession,
        *,
        user: User,
        user_agent: str | None,
        ip_address: str | None,
        device_name: str | None,
    ) -> tuple[str, str, int]:
        expires_in = settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60
        access_token = create_access_token(subject=str(user.id), role=user.role.value)
        refresh_token = generate_refresh_token()
        refresh_expires_at = datetime.now(timezone.utc) + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
        await AuthSessionRepository.create(
            db,
            user_id=user.id,
            refresh_token_hash=hash_refresh_token(refresh_token),
            expires_at=refresh_expires_at,
            user_agent=user_agent,
            ip_address=ip_address,
            device_name=device_name,
        )
        return access_token, refresh_token, expires_in

    @staticmethod
    async def refresh(
        db: AsyncSession,
        *,
        refresh_token: str,
        user_agent: str | None,
        ip_address: str | None,
        device_name: str | None,
    ) -> tuple[User, str, str, int]:
        now = datetime.now(timezone.utc)
        auth_session = await AuthSessionRepository.get_active_by_refresh_token_hash(
            db,
            hash_refresh_token(refresh_token),
            now=now,
        )
        if auth_session is None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token")

        user = await UserRepository.get_by_id(db, auth_session.user_id)
        if user is None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token")
        if not user.is_active:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Inactive user")

        await AuthSessionRepository.revoke(db, auth_session, now=now)
        access_token, new_refresh_token, expires_in = await AuthService._create_token_pair(
            db,
            user=user,
            user_agent=user_agent,
            ip_address=ip_address,
            device_name=device_name,
        )
        await db.commit()
        return user, access_token, new_refresh_token, expires_in

    @staticmethod
    async def logout(db: AsyncSession, *, refresh_token: str) -> bool:
        now = datetime.now(timezone.utc)
        auth_session = await AuthSessionRepository.get_active_by_refresh_token_hash(
            db,
            hash_refresh_token(refresh_token),
            now=now,
        )
        if auth_session is None:
            return True

        await AuthSessionRepository.revoke(db, auth_session, now=now)
        await db.commit()
        return True
