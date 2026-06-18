from datetime import date
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.profiles import AirportOperatorProfile, AuthorityProfile, AuthorityType, PilotProfile


class ProfileRepository:
    @staticmethod
    async def create_pilot_profile(
        db: AsyncSession,
        *,
        user_id: UUID,
        license_number: str,
        license_type: str,
        license_country: str,
        license_expiry: date,
        signature: str | None,
    ) -> PilotProfile:
        profile = PilotProfile(
            user_id=user_id,
            license_number=license_number,
            license_type=license_type,
            license_country=license_country.upper(),
            license_expiry=license_expiry,
            signature=signature,
        )
        db.add(profile)
        await db.flush()
        return profile

    @staticmethod
    async def get_pilot_profile_by_user_id(db: AsyncSession, *, user_id: UUID) -> PilotProfile | None:
        result = await db.execute(select(PilotProfile).where(PilotProfile.user_id == user_id))
        return result.scalar_one_or_none()

    @staticmethod
    async def create_authority_profile(
        db: AsyncSession,
        *,
        user_id: UUID,
        organization_name: str,
        authority_type: AuthorityType,
        aerodrome_icao_code: str | None,
    ) -> AuthorityProfile:
        profile = AuthorityProfile(
            user_id=user_id,
            organization_name=organization_name,
            authority_type=authority_type,
            aerodrome_icao_code=aerodrome_icao_code.upper() if aerodrome_icao_code else None,
        )
        db.add(profile)
        await db.flush()
        return profile

    @staticmethod
    async def get_authority_profile_by_user_id(db: AsyncSession, *, user_id: UUID) -> AuthorityProfile | None:
        result = await db.execute(select(AuthorityProfile).where(AuthorityProfile.user_id == user_id))
        return result.scalar_one_or_none()

    @staticmethod
    async def create_airport_operator_profile(
        db: AsyncSession,
        *,
        user_id: UUID,
        organization_name: str,
        aerodrome_icao_code: str,
    ) -> AirportOperatorProfile:
        profile = AirportOperatorProfile(
            user_id=user_id,
            organization_name=organization_name,
            aerodrome_icao_code=aerodrome_icao_code.upper(),
        )
        db.add(profile)
        await db.flush()
        return profile

    @staticmethod
    async def get_airport_operator_profile_by_user_id(db: AsyncSession, *, user_id: UUID) -> AirportOperatorProfile | None:
        result = await db.execute(select(AirportOperatorProfile).where(AirportOperatorProfile.user_id == user_id))
        return result.scalar_one_or_none()
