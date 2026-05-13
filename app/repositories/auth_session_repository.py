from datetime import datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.auth_session import AuthSession


class AuthSessionRepository:
    @staticmethod
    async def create(
        db: AsyncSession,
        *,
        user_id: UUID,
        refresh_token_hash: str,
        expires_at: datetime,
        user_agent: str | None,
        ip_address: str | None,
        device_name: str | None,
    ) -> AuthSession:
        auth_session = AuthSession(
            user_id=user_id,
            refresh_token_hash=refresh_token_hash,
            expires_at=expires_at,
            user_agent=user_agent,
            ip_address=ip_address,
            device_name=device_name,
        )
        db.add(auth_session)
        await db.flush()
        return auth_session

    @staticmethod
    async def get_active_by_refresh_token_hash(
        db: AsyncSession,
        refresh_token_hash: str,
        *,
        now: datetime,
    ) -> AuthSession | None:
        result = await db.execute(
            select(AuthSession).where(
                AuthSession.refresh_token_hash == refresh_token_hash,
                AuthSession.revoked_at.is_(None),
                AuthSession.expires_at > now,
            )
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def revoke(db: AsyncSession, auth_session: AuthSession, *, now: datetime) -> None:
        auth_session.revoked_at = now
        await db.flush()
