from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.aircraft import Aircraft, WakeTurbulenceCat


class AircraftRepository:
    @staticmethod
    async def create(
        db: AsyncSession,
        *,
        owner_user_id: UUID,
        alias: str | None,
        identification: str,
        icao_type_designator: str,
        wake_turbulence_category: WakeTurbulenceCat,
        equipment_com_nav: str,
        equipment_surveillance: str,
        pbn_capabilities: str | None,
        emergency_radio: str | None,
        survival_equipment: str | None,
        life_jackets: str | None,
        dinghies_number: int | None,
        dinghies_capacity: int | None,
        dinghies_cover: bool | None,
        dinghies_color: str | None,
        color_and_markings: str,
        image_url: str | None = None,
    ) -> Aircraft:
        aircraft = Aircraft(
            owner_user_id=owner_user_id,
            alias=alias,
            identification=identification.upper(),
            icao_type_designator=icao_type_designator.upper(),
            wake_turbulence_category=wake_turbulence_category,
            equipment_com_nav=equipment_com_nav,
            equipment_surveillance=equipment_surveillance,
            pbn_capabilities=pbn_capabilities,
            emergency_radio=emergency_radio,
            survival_equipment=survival_equipment,
            life_jackets=life_jackets,
            dinghies_number=dinghies_number,
            dinghies_capacity=dinghies_capacity,
            dinghies_cover=dinghies_cover,
            dinghies_color=dinghies_color,
            color_and_markings=color_and_markings,
            image_url=image_url,
            is_active=True,
        )
        db.add(aircraft)
        await db.flush()
        return aircraft

    @staticmethod
    async def list_active_by_owner(
        db: AsyncSession,
        *,
        owner_user_id: UUID,
    ) -> list[Aircraft]:
        result = await db.execute(
            select(Aircraft)
            .where(
                Aircraft.owner_user_id == owner_user_id,
                Aircraft.is_active.is_(True),
            )
            .order_by(Aircraft.created_at.desc())
        )
        return list(result.scalars().all())

    @staticmethod
    async def get_active_by_owner_and_id(
        db: AsyncSession,
        *,
        owner_user_id: UUID,
        aircraft_id: UUID,
    ) -> Aircraft | None:
        result = await db.execute(
            select(Aircraft).where(
                Aircraft.id == aircraft_id,
                Aircraft.owner_user_id == owner_user_id,
                Aircraft.is_active.is_(True),
            )
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def update(aircraft: Aircraft, **fields) -> Aircraft:
        for key, value in fields.items():
            if key in {"identification", "icao_type_designator"} and isinstance(value, str):
                value = value.upper()
            setattr(aircraft, key, value)
        return aircraft

    @staticmethod
    async def soft_delete(aircraft: Aircraft) -> Aircraft:
        aircraft.is_active = False
        return aircraft
