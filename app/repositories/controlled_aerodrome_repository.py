from collections.abc import Iterable

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.controlled_aerodrome import ControlledAerodrome


class ControlledAerodromeRepository:
    @staticmethod
    async def create(
        db: AsyncSession,
        *,
        icao_code: str,
        name: str,
        is_active: bool = True,
        traffic_type: str | None = None,
        flight_rules: str | None = None,
        category: str | None = None,
    ) -> ControlledAerodrome:
        aerodrome = ControlledAerodrome(
            icao_code=icao_code.upper(),
            name=name,
            is_active=is_active,
            traffic_type=traffic_type,
            flight_rules=flight_rules,
            category=category,
        )
        db.add(aerodrome)
        await db.flush()
        return aerodrome

    @staticmethod
    async def get_by_icao(db: AsyncSession, *, icao_code: str) -> ControlledAerodrome | None:
        result = await db.execute(
            select(ControlledAerodrome).where(ControlledAerodrome.icao_code == icao_code.upper())
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def list_active(
        db: AsyncSession,
        *,
        query: str | None = None,
        limit: int | None = None,
    ) -> list[ControlledAerodrome]:
        statement = select(ControlledAerodrome).where(ControlledAerodrome.is_active.is_(True))
        if query:
            normalized = f"%{query.upper()}%"
            statement = statement.where(
                or_(
                    ControlledAerodrome.icao_code.ilike(normalized),
                    ControlledAerodrome.name.ilike(f"%{query}%"),
                )
            )
        statement = statement.order_by(ControlledAerodrome.icao_code.asc())
        if limit is not None:
            statement = statement.limit(limit)
        result = await db.execute(statement)
        return list(result.scalars().all())

    @staticmethod
    async def list_all(db: AsyncSession) -> list[ControlledAerodrome]:
        result = await db.execute(select(ControlledAerodrome).order_by(ControlledAerodrome.icao_code.asc()))
        return list(result.scalars().all())

    @staticmethod
    async def update(aerodrome: ControlledAerodrome, **fields) -> ControlledAerodrome:
        for key, value in fields.items():
            if key == "icao_code" and isinstance(value, str):
                value = value.upper()
            setattr(aerodrome, key, value)
        return aerodrome

    @staticmethod
    async def upsert_many(db: AsyncSession, *, items: Iterable[dict]) -> int:
        count = 0
        for item in items:
            icao_code = item["icao_code"].upper()
            existing = await ControlledAerodromeRepository.get_by_icao(db, icao_code=icao_code)
            if existing is None:
                await ControlledAerodromeRepository.create(
                    db,
                    icao_code=icao_code,
                    name=item["name"],
                    is_active=item.get("is_active", True),
                    traffic_type=item.get("traffic_type"),
                    flight_rules=item.get("flight_rules"),
                    category=item.get("category"),
                )
            else:
                await ControlledAerodromeRepository.update(
                    existing,
                    name=item["name"],
                    is_active=item.get("is_active", existing.is_active),
                    traffic_type=item.get("traffic_type", existing.traffic_type),
                    flight_rules=item.get("flight_rules", existing.flight_rules),
                    category=item.get("category", existing.category),
                )
            count += 1
        return count
