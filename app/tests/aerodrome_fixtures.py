from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.aerodrome_repository import AerodromeRepository


async def seed_aerodrome(
    db: AsyncSession,
    *,
    local_identifier: str,
    icao_code: str | None,
    name: str,
    latitude: float = -34.5,
    longitude: float = -58.4,
    is_controlled: bool = True,
    is_active: bool = True,
) -> None:
    await AerodromeRepository.create(
        db,
        local_identifier=local_identifier,
        icao_code=icao_code,
        name=name,
        latitude=latitude,
        longitude=longitude,
        is_controlled=is_controlled,
        is_active=is_active,
    )


async def seed_flight_plan_aerodromes(db: AsyncSession) -> None:
    await seed_aerodrome(db, local_identifier="SABE", icao_code="SABE", name="Aeroparque")
    await seed_aerodrome(db, local_identifier="SAEZ", icao_code="SAEZ", name="Ezeiza")
    await seed_aerodrome(db, local_identifier="SADP", icao_code="SADP", name="El Palomar")
    await seed_aerodrome(db, local_identifier="SADF", icao_code="SADF", name="San Fernando")
