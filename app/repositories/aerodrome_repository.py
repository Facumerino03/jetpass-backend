from collections.abc import Iterable
from uuid import UUID

from sqlalchemy import delete, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.aerodrome import Aerodrome


class AerodromeRepository:
    @staticmethod
    def _normalize_icao(value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip().upper()
        return normalized or None

    @staticmethod
    async def create(
        db: AsyncSession,
        *,
        local_identifier: str,
        name: str,
        latitude: float,
        longitude: float,
        is_controlled: bool,
        icao_code: str | None = None,
        is_active: bool = True,
    ) -> Aerodrome:
        aerodrome = Aerodrome(
            local_identifier=local_identifier.strip().upper(),
            icao_code=AerodromeRepository._normalize_icao(icao_code),
            name=name,
            latitude=latitude,
            longitude=longitude,
            is_controlled=is_controlled,
            is_active=is_active,
        )
        db.add(aerodrome)
        await db.flush()
        return aerodrome

    @staticmethod
    async def get_by_local_identifier(
        db: AsyncSession,
        *,
        local_identifier: str,
    ) -> Aerodrome | None:
        result = await db.execute(
            select(Aerodrome).where(Aerodrome.local_identifier == local_identifier.strip().upper())
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def get_by_location_code(db: AsyncSession, *, code: str) -> Aerodrome | None:
        normalized = code.strip().upper()
        aerodrome = await AerodromeRepository.get_by_icao(db, icao_code=normalized)
        if aerodrome is not None:
            return aerodrome
        return await AerodromeRepository.get_by_local_identifier(db, local_identifier=normalized)

    @staticmethod
    def fpl_location_code(aerodrome: Aerodrome) -> str:
        return aerodrome.icao_code or aerodrome.local_identifier

    @staticmethod
    async def get_by_icao(db: AsyncSession, *, icao_code: str) -> Aerodrome | None:
        result = await db.execute(select(Aerodrome).where(Aerodrome.icao_code == icao_code.upper()))
        return result.scalar_one_or_none()

    @staticmethod
    async def list_active_for_flight_plan(
        db: AsyncSession,
        *,
        query: str | None = None,
        limit: int | None = None,
    ) -> list[Aerodrome]:
        statement = (
            select(Aerodrome)
            .where(Aerodrome.is_active.is_(True))
            .order_by(Aerodrome.is_controlled.desc(), Aerodrome.icao_code.asc(), Aerodrome.local_identifier.asc())
        )
        if query:
            normalized = f"%{query.upper()}%"
            statement = statement.where(
                or_(
                    Aerodrome.icao_code.ilike(normalized),
                    Aerodrome.name.ilike(f"%{query}%"),
                    Aerodrome.local_identifier.ilike(normalized),
                )
            )
        if limit is not None:
            statement = statement.limit(limit)
        result = await db.execute(statement)
        return list(result.scalars().all())

    @staticmethod
    async def list_all(
        db: AsyncSession,
        *,
        is_controlled: bool | None = None,
    ) -> list[Aerodrome]:
        statement = select(Aerodrome).order_by(
            Aerodrome.is_controlled.desc(),
            Aerodrome.local_identifier.asc(),
        )
        if is_controlled is not None:
            statement = statement.where(Aerodrome.is_controlled.is_(is_controlled))
        result = await db.execute(statement)
        return list(result.scalars().all())

    @staticmethod
    async def update(aerodrome: Aerodrome, **fields) -> Aerodrome:
        for key, value in fields.items():
            if key == "icao_code":
                value = AerodromeRepository._normalize_icao(value)
            if key == "local_identifier" and isinstance(value, str):
                value = value.strip().upper()
            setattr(aerodrome, key, value)
        return aerodrome

    @staticmethod
    async def replace_from_sync(db: AsyncSession, *, items: Iterable[dict]) -> tuple[int, int]:
        synced_local_identifiers: set[str] = set()
        upserted = 0

        for raw_item in items:
            local_identifier = raw_item["local_identifier"].strip().upper()
            synced_local_identifiers.add(local_identifier)
            icao_code = AerodromeRepository._normalize_icao(raw_item.get("icao_code"))
            payload = {
                "name": raw_item["name"],
                "latitude": float(raw_item["latitude"]),
                "longitude": float(raw_item["longitude"]),
                "is_controlled": bool(raw_item["is_controlled"]),
                "icao_code": icao_code,
                "is_active": True,
            }

            existing = await AerodromeRepository.get_by_local_identifier(
                db,
                local_identifier=local_identifier,
            )
            if existing is None:
                await AerodromeRepository.create(
                    db,
                    local_identifier=local_identifier,
                    **payload,
                )
            else:
                await AerodromeRepository.update(existing, **payload)
            upserted += 1

        deleted = 0
        if synced_local_identifiers:
            result = await db.execute(select(Aerodrome.local_identifier))
            existing_identifiers = {row[0] for row in result.all()}
            stale_identifiers = existing_identifiers - synced_local_identifiers
            if stale_identifiers:
                await db.execute(
                    delete(Aerodrome).where(Aerodrome.local_identifier.in_(stale_identifiers))
                )
                deleted = len(stale_identifiers)

        return upserted, deleted

    @staticmethod
    async def delete_by_id(db: AsyncSession, *, aerodrome_id: UUID) -> bool:
        result = await db.execute(select(Aerodrome).where(Aerodrome.id == aerodrome_id))
        aerodrome = result.scalar_one_or_none()
        if aerodrome is None:
            return False
        await db.delete(aerodrome)
        return True
