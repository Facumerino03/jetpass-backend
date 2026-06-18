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
        emergency_radio_uhf: bool = False,
        emergency_radio_vhf: bool = False,
        emergency_radio_elt: bool = False,
        survival_equipment_present: bool = False,
        survival_polar: bool = False,
        survival_desert: bool = False,
        survival_maritime: bool = False,
        survival_jungle: bool = False,
        life_jackets_present: bool = False,
        life_jackets_lights: bool = False,
        life_jackets_fluorescein: bool = False,
        life_jackets_uhf: bool = False,
        life_jackets_vhf: bool = False,
        dinghies_present: bool = False,
        dinghies_number: int | None = None,
        dinghies_capacity: int | None = None,
        dinghies_cover_present: bool = False,
        dinghies_color: str | None = None,
        color_and_markings: str = "",
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
            emergency_radio_uhf=emergency_radio_uhf,
            emergency_radio_vhf=emergency_radio_vhf,
            emergency_radio_elt=emergency_radio_elt,
            survival_equipment_present=survival_equipment_present,
            survival_polar=survival_polar,
            survival_desert=survival_desert,
            survival_maritime=survival_maritime,
            survival_jungle=survival_jungle,
            life_jackets_present=life_jackets_present,
            life_jackets_lights=life_jackets_lights,
            life_jackets_fluorescein=life_jackets_fluorescein,
            life_jackets_uhf=life_jackets_uhf,
            life_jackets_vhf=life_jackets_vhf,
            dinghies_present=dinghies_present,
            dinghies_number=dinghies_number,
            dinghies_capacity=dinghies_capacity,
            dinghies_cover_present=dinghies_cover_present,
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
